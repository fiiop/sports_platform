"""Persistent notices and an idempotent reminder sweep, run while the service is awake."""
import logging
from datetime import datetime, timedelta
from threading import Event, Thread

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Meetup, MeetupMember, UserNotice
from .push import deliver_notice_push

log = logging.getLogger(__name__)


def create_due_reminders(bind, now=None):
    now = now or datetime.utcnow()
    with Session(bind) as db:
        rows = db.scalars(select(Meetup).where(Meetup.state == "confirmed", Meetup.starts_at > now,
            Meetup.starts_at <= now + timedelta(hours=2)).order_by(Meetup.id)).all()
        for meeting in rows:
            # Serialize with cancellation/rescheduling so their notice invalidation
            # cannot be followed by inserting an alarm from this stale snapshot.
            locked = db.execute(update(Meetup).where(Meetup.id == meeting.id,
                Meetup.state == "confirmed").values(id=Meetup.id))
            if not locked.rowcount:
                continue
            db.refresh(meeting)
            if not now < meeting.starts_at <= now + timedelta(hours=2):
                continue
            members = db.scalars(select(MeetupMember).where(MeetupMember.meetup_id == meeting.id,
                                                           MeetupMember.status == "accepted")).all()
            if len(members) < 2:
                continue
            for minutes in (120, 30):
                due = meeting.starts_at - timedelta(minutes=minutes)
                # A 10-minute grace absorbs a restart without delivering stale alarms.
                if not due <= now < due + timedelta(minutes=10):
                    continue
                for member in members:
                    # Time/location identity avoids re-sending because another member joined.
                    key = f"{meeting.id}:{member.user_id}:{meeting.starts_at.isoformat()}:{minutes}"
                    if db.scalar(select(UserNotice.id).where(UserNotice.dedupe_key == key)):
                        continue
                    try:
                        with db.begin_nested():
                            db.add(UserNotice(user_id=member.user_id, meetup_id=meeting.id,
                                title=f"运动将在{'2 小时' if minutes == 120 else '30 分钟'}后开始",
                                body=f"{meeting.exercise_type} · {meeting.location}"[:300], dedupe_key=key))
                            db.flush()
                    except IntegrityError:
                        pass
        db.commit()


def deliver_pending(bind, now=None):
    now = now or datetime.utcnow()
    with Session(bind) as db:
        ids = list(db.scalars(select(UserNotice.id).where(UserNotice.push_done == 0,
            UserNotice.push_after <= now, UserNotice.push_attempts < 3).order_by(UserNotice.id).limit(30)))
    for notice_id in ids:
        with Session(bind) as db:
            claim = db.execute(update(UserNotice).where(UserNotice.id == notice_id, UserNotice.push_done == 0,
                UserNotice.push_after <= now, UserNotice.push_attempts < 3).values(push_after=now + timedelta(minutes=5),
                                                   push_attempts=UserNotice.push_attempts + 1))
            db.commit()
            if not claim.rowcount:
                continue
        try:
            delivered = deliver_notice_push(bind, notice_id)
        except Exception:
            delivered = False
        if delivered:
            with Session(bind) as db:
                db.execute(update(UserNotice).where(UserNotice.id == notice_id).values(push_done=1))
                db.commit()


def start_worker(bind):
    stop = Event()
    def work():
        while not stop.is_set():
            try:
                create_due_reminders(bind)
                deliver_pending(bind)
            except Exception:
                log.warning("Reminder sweep will retry on the next cycle")
            stop.wait(20)
    worker = Thread(target=work, name="campus-reminders", daemon=True)
    worker.start()
    return stop, worker
