"""Campus discovery, confirmed appointments, group participation and moderation."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Activity, AdminRole, BuddyBlock, BuddyChat, BuddyRating, BuddyStatus,
                      CampusProfile, GroupMessage, Meetup, MeetupMember, MigrationStamp,
                      ModerationAction, ProfileAvatar, PublicIdentity, User, UserNotice, UserReport)
from ..schemas import BuddyStatusIn, BuddyMessageIn
from .media import identity_dict, cover_url

router = APIRouter()


def auth(request, db):
    from ..main import require_user
    return require_user(request, db)


def blocked(user_id):
    return select(BuddyBlock.blocked_id).where(BuddyBlock.user_id == user_id).union(
        select(BuddyBlock.user_id).where(BuddyBlock.blocked_id == user_id))


def chat_identities(db, user_ids, viewer):
    """Current names and photos for history, without exposing restricted profiles.

    Load each sender once for an entire message page and never fetch image bytes.
    Historical usernames remain available, matching existing chat behavior.
    """
    ids = set(user_ids)
    if not ids:
        return {}
    suspended = select(ModerationAction.user_id).where(
        ModerationAction.suspended_until > datetime.utcnow())
    hidden = set(db.scalars(select(User.id).where(
        User.id.in_(ids), User.id != viewer,
        or_(User.id.in_(blocked(viewer)), User.id.in_(suspended)))))
    rows = db.execute(select(User.id, User.username, PublicIdentity.nickname, ProfileAvatar.version)
                      .outerjoin(PublicIdentity, PublicIdentity.user_id == User.id)
                      .outerjoin(ProfileAvatar, ProfileAvatar.user_id == User.id)
                      .where(User.id.in_(ids))).all()
    return {uid: {"username": username,
                  "display_name": username if uid in hidden else nickname or username,
                  "avatar_url": f"/api/users/{uid}/avatar?v={version}" if version and uid not in hidden else None,
                  "identity_hidden": uid in hidden}
            for uid, username, nickname, version in rows}


def ensure_pair(db, a, b):
    if db.scalar(select(User.id).where(User.id == b, User.id.in_(blocked(a)))):
        raise HTTPException(403, "黑名单中的用户不能继续互动")


def writable(db, user):
    action = db.get(ModerationAction, user.id)
    if action and action.suspended_until and action.suspended_until > datetime.utcnow():
        raise HTTPException(403, "账号的社交功能暂受限制，请查看举报处理结果或联系管理员")


def lock_user(db, user_id):
    # An explicit write lock serializes slot/capacity decisions on both SQLite and PostgreSQL.
    db.execute(update(User).where(User.id == user_id).values(username=User.username))


def school(db, user_id):
    profile = db.get(CampusProfile, user_id)
    return profile.school if profile else "湘潭大学"


def completed_count(db, user_id):
    return db.scalar(select(func.count()).select_from(MeetupMember).join(Meetup).where(
        MeetupMember.user_id == user_id, MeetupMember.attended == 1, Meetup.state == "completed")) or 0


def sync_legacy_status(db, activity, remove=False):
    if activity.legacy_user_id is None:
        return
    old = db.get(BuddyStatus, activity.legacy_user_id)
    if old is None:
        return
    if remove:
        db.delete(old)
    else:
        for name in ("exercise_type", "starts_at", "location", "latitude", "longitude", "note"):
            setattr(old, name, getattr(activity, name))


def migrate_legacy(bind):
    with Session(bind) as db:
        for old in db.scalars(select(BuddyStatus)):
            if not db.scalar(select(Activity.id).where(Activity.legacy_user_id == old.user_id)):
                db.add(Activity(legacy_user_id=old.user_id, user_id=old.user_id,
                    exercise_type=old.exercise_type, starts_at=old.starts_at, location=old.location,
                    latitude=old.latitude, longitude=old.longitude, note=old.note))
        # Only grant the explicitly requested, already-existing account on first migration.
        # Recording the attempt prevents a later registration from acquiring this role.
        if not db.get(MigrationStamp, "v4-admin-test02"):
            existing = db.scalar(select(User).where(User.username == "test02"))
            if existing:
                db.add(AdminRole(user_id=existing.id))
            db.add(MigrationStamp(name="v4-admin-test02"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


class ProfileIn(BaseModel):
    school: str = Field(min_length=1, max_length=100)
    theme: Literal["forest", "ocean", "lilac", "night", "system"] = "forest"

    @field_validator("school")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请填写学校")
        return value.strip()


@router.get("/api/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    row = db.get(CampusProfile, user.id)
    return {"school": school(db, user.id), "theme": row.theme if row else "forest",
            "school_verified": False, "completed": completed_count(db, user.id),
            "is_admin": db.get(AdminRole, user.id) is not None,
            **identity_dict(db, user.id, user.username)}


@router.put("/api/profile")
def update_profile(payload: ProfileIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    lock_user(db, user.id)
    row = db.get(CampusProfile, user.id)
    if row is None:
        row = CampusProfile(user_id=user.id)
        db.add(row)
    row.school, row.theme = payload.school, payload.theme
    db.execute(update(Activity).where(Activity.user_id == user.id).values(school=payload.school))
    db.commit()
    return {"school": row.school, "theme": row.theme}


class ActivityIn(BuddyStatusIn):
    duration: int = Field(60, ge=15, le=360)
    capacity: int = Field(2, ge=2, le=20)
    level: Literal["不限", "新手", "有基础", "熟练"] = "不限"


def activity_dict(db, row, viewer):
    average, total = db.execute(select(func.avg(BuddyRating.score), func.count()).where(BuddyRating.target_id == row.user_id)).one()
    group = db.scalar(select(Meetup).where(Meetup.activity_id == row.id))
    members = db.scalar(select(func.count()).select_from(MeetupMember).where(
        MeetupMember.meetup_id == group.id, MeetupMember.status == "accepted")) if group else 1
    mine = db.get(MeetupMember, (group.id, viewer)) if group else None
    participant_ids = [row.user_id]
    if group:
        hidden_members = select(ModerationAction.user_id).where(
            ModerationAction.suspended_until > datetime.utcnow())
        participant_ids += list(db.scalars(select(MeetupMember.user_id).where(
            MeetupMember.meetup_id == group.id, MeetupMember.status == "accepted",
            MeetupMember.user_id != row.user_id,
            ~MeetupMember.user_id.in_(blocked(viewer)),
            ~MeetupMember.user_id.in_(hidden_members)).order_by(MeetupMember.user_id).limit(2)))
    participants = []
    for uid in participant_ids:
        identity = identity_dict(db, uid)
        participants.append({"user_id": uid, "display_name": identity["display_name"],
                             "avatar_url": identity["avatar_url"]})
    return {"id": row.id, "user_id": row.user_id, "username": db.get(User, row.user_id).username,
            **identity_dict(db, row.user_id), "cover_url": cover_url(db, row.id), "participants": participants,
            "exercise_type": row.exercise_type, "starts_at": row.starts_at.isoformat() + "Z",
            "duration": row.duration, "location": row.location, "school": row.school, "level": row.level,
            "capacity": row.capacity, "joined": members, "meetup_id": group.id if group else None,
            "is_member": bool(mine and mine.status == "accepted"), "latitude": row.latitude,
            "longitude": row.longitude, "note": row.note, "active": bool(row.active),
            "rating": round(float(average), 1) if average is not None else None,
            "rating_count": total, "completed": completed_count(db, row.user_id)}


@router.get("/api/activities")
def activities(request: Request, db: Session = Depends(get_db), keyword: str = Query("", max_length=50),
               place: str = Query("", max_length=100), level: Literal["", "新手", "有基础", "熟练"] = "",
               scope: Literal["school", "all"] = "school", on_date: date | None = None,
               period: Literal["", "morning", "afternoon", "evening"] = "",
               utc_offset: int = Query(480, ge=-840, le=840), sort: Literal["rating", "time"] = "rating",
               offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    user = auth(request, db)
    scores = select(BuddyRating.target_id, func.avg(BuddyRating.score).label("average"),
                    func.count().label("total")).group_by(BuddyRating.target_id).subquery()
    hidden_users = select(ModerationAction.user_id).where(ModerationAction.suspended_until > datetime.utcnow())
    query = select(Activity).outerjoin(scores, scores.c.target_id == Activity.user_id).where(
        Activity.active == 1, Activity.starts_at > datetime.utcnow(),
        ~Activity.user_id.in_(blocked(user.id)), ~Activity.user_id.in_(hidden_users))
    if scope == "school":
        query = query.where(Activity.school == school(db, user.id))
    if keyword.strip():
        query = query.where(Activity.exercise_type.icontains(keyword.strip(), autoescape=True))
    if place.strip():
        query = query.where(Activity.location.icontains(place.strip(), autoescape=True))
    if level:
        query = query.where(Activity.level.in_([level, "不限"]))
    if on_date is not None or period:
        today = (datetime.now(timezone.utc) + timedelta(minutes=utc_offset)).date()
        if on_date is not None and not today <= on_date <= today + timedelta(days=4):
            raise HTTPException(422, "请选择今天起五天内的日期")
        first, last = {"": (0, 24), "morning": (6, 12), "afternoon": (12, 18), "evening": (18, 24)}[period]
        dates = [on_date] if on_date else [today + timedelta(days=i) for i in range(5)]
        windows = []
        for day in dates:
            base = datetime.combine(day, datetime.min.time()) - timedelta(minutes=utc_offset)
            windows.append(and_(Activity.starts_at >= base + timedelta(hours=first), Activity.starts_at < base + timedelta(hours=last)))
        query = query.where(or_(*windows))
    if sort == "rating":
        query = query.order_by(func.coalesce(scores.c.average, 0).desc(), func.coalesce(scores.c.total, 0).desc())
    rows = db.scalars(query.order_by(Activity.starts_at, Activity.id).offset(offset).limit(limit)).all()
    return [activity_dict(db, row, user.id) for row in rows]


@router.get("/api/activities/mine")
def mine(request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    rows = db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.active == 1)
                      .order_by(Activity.starts_at.desc()).limit(30)).all()
    return [activity_dict(db, row, user.id) for row in rows]


@router.post("/api/activities")
def create_activity(payload: ActivityIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    lock_user(db, user.id)
    count = db.scalar(select(func.count()).select_from(Activity).where(
        Activity.user_id == user.id, Activity.active == 1, Activity.starts_at > datetime.utcnow()))
    if count >= 3:
        raise HTTPException(409, "最多保留三条未开始的运动状态，请先修改或撤下已有状态")
    row = Activity(user_id=user.id, school=school(db, user.id), **payload.model_dump())
    db.add(row)
    db.flush()
    if row.capacity > 2:
        meeting = Meetup(owner_id=user.id, activity_id=row.id, kind="group", state="confirmed",
                         exercise_type=row.exercise_type, starts_at=row.starts_at, duration=row.duration,
                         location=row.location, capacity=row.capacity)
        db.add(meeting)
        db.flush()
        db.add(MeetupMember(meetup_id=meeting.id, user_id=user.id, status="accepted"))
    db.commit()
    return activity_dict(db, row, user.id)


@router.put("/api/activities/{activity_id}")
def edit_activity(activity_id: int, payload: ActivityIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    lock_user(db, user.id)
    row = db.get(Activity, activity_id)
    if not row or row.user_id != user.id or not row.active:
        raise HTTPException(404, "状态不存在")
    if row.starts_at <= datetime.utcnow():
        raise HTTPException(409, "已开始的状态请保留记录，下一次运动请重新发布")
    if row.capacity != payload.capacity:
        raise HTTPException(409, "人数发布后不能直接修改，请撤下后重新发布")
    group = db.scalar(select(Meetup).where(Meetup.activity_id == row.id))
    if group:
        db.execute(update(Meetup).where(Meetup.id == group.id).values(id=Meetup.id))
        db.refresh(group)
        count = db.scalar(select(func.count()).select_from(MeetupMember).where(MeetupMember.meetup_id == group.id, MeetupMember.status == "accepted"))
        changed = any(getattr(row, k) != getattr(payload, k) for k in ("starts_at", "duration", "location", "exercise_type"))
        if count > 1 and changed:
            raise HTTPException(409, "已有成员加入，请进入组局提出改约，由成员确认")
        for k in ("starts_at", "duration", "location", "exercise_type"):
            setattr(group, k, getattr(payload, k))
        if changed:
            group.revision += 1
            group.proposal, group.proposal_by = "", None
            retire_reminders(db, group.id)
    for k, value in payload.model_dump().items():
        setattr(row, k, value)
    sync_legacy_status(db, row)
    db.commit()
    return activity_dict(db, row, user.id)


@router.delete("/api/activities/{activity_id}")
def withdraw_activity(activity_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    lock_user(db, user.id)
    row = db.get(Activity, activity_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "状态不存在")
    group = db.scalar(select(Meetup).where(Meetup.activity_id == row.id))
    if group and group.state == "confirmed":
        db.execute(update(Meetup).where(Meetup.id == group.id).values(id=Meetup.id))
        db.refresh(group)
        count = db.scalar(select(func.count()).select_from(MeetupMember).where(MeetupMember.meetup_id == group.id, MeetupMember.status == "accepted"))
        if count > 1:
            raise HTTPException(409, "组局已有成员，请进入约定填写原因后取消")
        group.state, group.cancelled_by, group.cancelled_at = "cancelled", user.id, datetime.utcnow()
        group.cancel_reason = "发起人撤下状态"
        retire_reminders(db, group.id)
    row.active = 0
    sync_legacy_status(db, row, remove=True)
    db.commit()
    return {"message": "状态已撤下，约定和聊天记录保留"}


def meeting_for(db, meeting_id, user_id, lock=False):
    if lock:
        db.execute(update(Meetup).where(Meetup.id == meeting_id).values(id=Meetup.id))
    meeting = db.get(Meetup, meeting_id)
    member = db.get(MeetupMember, (meeting_id, user_id))
    if not meeting or not member:
        raise HTTPException(404, "约定不存在或你不是参与者")
    return meeting, member


def members_for(db, meeting_id):
    return db.scalars(select(MeetupMember).where(MeetupMember.meetup_id == meeting_id)).all()


def active_members(db, meeting_id):
    return [m for m in members_for(db, meeting_id) if m.status == "accepted"]


def notify_members(db, meeting, title, body="", exclude=None):
    for m in members_for(db, meeting.id):
        if m.user_id != exclude and m.status in ("accepted", "pending"):
            db.add(UserNotice(user_id=m.user_id, meetup_id=meeting.id, title=title, body=body))


def retire_reminders(db, meeting_id, user_id=None):
    # Keep the history, but stop obsolete alarms from showing as unread or being retried.
    query = update(UserNotice).where(UserNotice.meetup_id == meeting_id, UserNotice.dedupe_key.is_not(None))
    if user_id is not None:
        query = query.where(UserNotice.user_id == user_id)
    db.execute(query.values(is_read=1, push_done=1))


def apply_change(db, meeting, start, duration, location):
    retire_reminders(db, meeting.id)
    meeting.starts_at, meeting.duration, meeting.location = start, duration, location
    meeting.proposal, meeting.proposal_by = "", None
    if meeting.activity_id:
        row = db.get(Activity, meeting.activity_id)
        row.starts_at, row.duration, row.location = start, duration, location
        row.latitude = row.longitude = None


def conflict_check(db, user_id, start, duration, except_id=None, allow=False):
    if allow:
        return
    others = db.scalars(select(Meetup).join(MeetupMember).where(MeetupMember.user_id == user_id,
        MeetupMember.status == "accepted", Meetup.state == "confirmed", Meetup.id != (except_id or 0),
        Meetup.starts_at < start + timedelta(minutes=duration), Meetup.starts_at > start - timedelta(hours=6))).all()
    conflicts = [m for m in others if m.starts_at + timedelta(minutes=m.duration) > start]
    if conflicts:
        raise HTTPException(409, {"message": "与已有约定时间重叠，仍要继续吗？", "conflicts": [m.id for m in conflicts]})


def meeting_dict(db, meeting, viewer):
    people = members_for(db, meeting.id)
    identities = chat_identities(db, (m.user_id for m in people), viewer)
    state = meeting.state
    if state == "pending" and meeting.starts_at <= datetime.utcnow():
        state = "expired"
    proposal = json.loads(meeting.proposal) if meeting.proposal else None
    return {"id": meeting.id, "owner_id": meeting.owner_id, "chat_id": meeting.chat_id, "kind": meeting.kind,
            "exercise_type": meeting.exercise_type, "starts_at": meeting.starts_at.isoformat() + "Z",
            "ends_at": (meeting.starts_at + timedelta(minutes=meeting.duration)).isoformat() + "Z",
            "duration": meeting.duration, "location": meeting.location, "capacity": meeting.capacity,
            "state": state, "revision": meeting.revision, "proposal": proposal, "proposal_by": meeting.proposal_by,
            "cancel_reason": meeting.cancel_reason, "cancelled_by": meeting.cancelled_by,
            "late_cancel": bool(meeting.cancelled_at and meeting.starts_at - meeting.cancelled_at < timedelta(hours=2)),
            "members": [{"user_id": m.user_id, **identities[m.user_id],
                         "status": m.status, "attended": bool(m.attended), "voted": m.vote == meeting.revision,
                         "cancel_reason": m.cancel_reason, "late_cancel": bool(m.cancelled_at and meeting.starts_at - m.cancelled_at < timedelta(hours=2))}
                        for m in people]}


class InviteIn(BaseModel):
    chat_id: int
    exercise_type: str = Field(min_length=1, max_length=50)
    starts_at: datetime
    duration: int = Field(60, ge=15, le=360)
    location: str = Field(min_length=1, max_length=200)
    allow_conflict: bool = False

    @field_validator("starts_at")
    @classmethod
    def future(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
        if value <= datetime.utcnow():
            raise ValueError("请选择未来时间")
        return value

    @field_validator("exercise_type", "location")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请填写项目和地点")
        return value.strip()


@router.post("/api/meetups")
def invite(payload: InviteIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    lock_user(db, user.id)
    chat = db.get(BuddyChat, payload.chat_id)
    if not chat or user.id not in (chat.user_a, chat.user_b):
        raise HTTPException(404, "聊天不存在")
    db.execute(update(BuddyChat).where(BuddyChat.id == chat.id).values(id=BuddyChat.id))
    other = chat.user_b if chat.user_a == user.id else chat.user_a
    ensure_pair(db, user.id, other)
    count = db.scalar(select(func.count()).select_from(Meetup).where(Meetup.chat_id == chat.id,
        Meetup.state == "pending", Meetup.starts_at > datetime.utcnow()))
    if count >= 3:
        raise HTTPException(409, "这个聊天已有三条待回应邀请，请先处理")
    conflict_check(db, user.id, payload.starts_at, payload.duration, allow=payload.allow_conflict)
    meeting = Meetup(owner_id=user.id, **payload.model_dump(exclude={"allow_conflict"}))
    db.add(meeting)
    db.flush()
    db.add_all([MeetupMember(meetup_id=meeting.id, user_id=user.id, status="accepted"),
                MeetupMember(meetup_id=meeting.id, user_id=other, status="pending")])
    db.add(UserNotice(user_id=other, meetup_id=meeting.id, title="收到运动邀请", body=f"{user.username} 邀你一起{meeting.exercise_type}"))
    db.commit()
    return meeting_dict(db, meeting, user.id)


@router.get("/api/meetups")
def list_meetups(request: Request, db: Session = Depends(get_db), chat_id: int | None = None,
                 offset: int = Query(0, ge=0)):
    user = auth(request, db)
    query = select(Meetup).join(MeetupMember).where(MeetupMember.user_id == user.id)
    if chat_id is not None:
        query = query.where(Meetup.chat_id == chat_id)
    rows = db.scalars(query.order_by(Meetup.starts_at.desc(), Meetup.id.desc()).offset(offset).limit(30)).all()
    return [meeting_dict(db, row, user.id) for row in rows]


@router.get("/api/meetups/{meeting_id}")
def get_meeting(meeting_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    meeting, _ = meeting_for(db, meeting_id, user.id)
    return meeting_dict(db, meeting, user.id)


class DecisionIn(BaseModel):
    action: Literal["accept", "decline", "cancel", "attend", "accept_change", "reject_change"]
    revision: int = Field(ge=1)
    reason: str = Field("", max_length=500)
    allow_conflict: bool = False


@router.post("/api/meetups/{meeting_id}/decision")
def decision(meeting_id: int, payload: DecisionIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    lock_user(db, user.id)
    meeting, member = meeting_for(db, meeting_id, user.id, lock=True)
    if payload.revision != meeting.revision:
        raise HTTPException(409, "约定已更新，请刷新后再操作")
    now = datetime.utcnow()
    action = payload.action
    if action in ("accept", "accept_change"):
        writable(db, user)
        for person in active_members(db, meeting.id):
            ensure_pair(db, user.id, person.user_id)
    if action in ("accept", "decline"):
        if meeting.state != "pending" or member.status != "pending" or meeting.starts_at <= now:
            raise HTTPException(409, "邀请已处理或已过期")
        if action == "accept":
            conflict_check(db, user.id, meeting.starts_at, meeting.duration, meeting.id, payload.allow_conflict)
            member.status, meeting.state = "accepted", "confirmed"
        else:
            member.status, meeting.state = "declined", "declined"
        notify_members(db, meeting, "运动邀请已接受" if action == "accept" else "运动邀请未接受", exclude=user.id)
    elif action == "cancel":
        if meeting.state not in ("pending", "confirmed") or member.status not in ("pending", "accepted"):
            raise HTTPException(409, "这条约定已结束")
        if not payload.reason.strip():
            raise HTTPException(422, "请说明取消原因，方便同伴调整安排")
        if now >= meeting.starts_at + timedelta(minutes=meeting.duration):
            raise HTTPException(409, "运动已结束，请确认参加情况")
        if meeting.kind == "pair" or meeting.owner_id == user.id:
            meeting.state, meeting.cancelled_by = "cancelled", user.id
            meeting.cancelled_at, meeting.cancel_reason = now, payload.reason.strip()
            if meeting.activity_id:
                db.get(Activity, meeting.activity_id).active = 0
        else:
            member.status, member.cancelled_at, member.cancel_reason = "cancelled", now, payload.reason.strip()
        meeting.proposal, meeting.proposal_by = "", None
        if meeting.state == "cancelled" or len(active_members(db, meeting.id)) < 2:
            retire_reminders(db, meeting.id)
        else:
            retire_reminders(db, meeting.id, user.id)
        notify_members(db, meeting, "运动约定有取消变更", "请查看取消说明并确认安排。", exclude=user.id)
    elif action == "attend":
        if member.status != "accepted" or meeting.state not in ("confirmed", "completed"):
            raise HTTPException(409, "当前不能确认参加")
        if now < meeting.starts_at + timedelta(minutes=meeting.duration):
            raise HTTPException(409, "运动结束后再确认参加")
        if not member.attended:
            member.attended = 1
            notify_members(db, meeting, "同伴已确认参加", "请根据实际参加情况完成确认。", exclude=user.id)
        people = active_members(db, meeting.id)
        if len(people) >= 2 and all(p.attended for p in people):
            meeting.state = "completed"
    else:
        if not meeting.proposal or meeting.state != "confirmed" or member.status != "accepted" or now >= meeting.starts_at:
            raise HTTPException(409, "当前没有可确认的改约")
        proposal = json.loads(meeting.proposal)
        if action == "reject_change":
            meeting.proposal, meeting.proposal_by = "", None
            notify_members(db, meeting, "改约未通过，保留原约定", exclude=user.id)
        else:
            start = datetime.fromisoformat(proposal["starts_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            if start <= now:
                raise HTTPException(409, "提议的新时间已过期，请重新改约")
            conflict_check(db, user.id, start, proposal["duration"], meeting.id, payload.allow_conflict)
            member.vote = meeting.revision
            if all(p.vote == meeting.revision for p in active_members(db, meeting.id)):
                apply_change(db, meeting, start, proposal["duration"], proposal["location"])
                notify_members(db, meeting, "改约已生效", "所有参与者已同意新的时间和地点。")
    # Keep a proposal's revision stable until all votes are collected.
    if action != "accept_change" or not meeting.proposal:
        meeting.revision += 1
    db.commit()
    return meeting_dict(db, meeting, user.id)


class ChangeIn(BaseModel):
    starts_at: datetime
    duration: int = Field(60, ge=15, le=360)
    location: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1)
    allow_conflict: bool = False
    validate_time = field_validator("starts_at")(InviteIn.future.__func__)
    validate_place = field_validator("location")(InviteIn.not_blank.__func__)


@router.post("/api/meetups/{meeting_id}/change")
def propose_change(meeting_id: int, payload: ChangeIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    lock_user(db, user.id)
    meeting, member = meeting_for(db, meeting_id, user.id, lock=True)
    if meeting.revision != payload.revision or meeting.state != "confirmed" or member.status != "accepted" or meeting.starts_at <= datetime.utcnow():
        raise HTTPException(409, "约定状态已变化，或已开始，无法改约")
    conflict_check(db, user.id, payload.starts_at, payload.duration, meeting.id, payload.allow_conflict)
    meeting.revision += 1
    meeting.proposal = json.dumps({"starts_at": payload.starts_at.isoformat() + "Z", "duration": payload.duration, "location": payload.location}, ensure_ascii=False)
    meeting.proposal_by, member.vote = user.id, meeting.revision
    if len(active_members(db, meeting.id)) == 1:
        # No other participant needs to approve an unjoined group's schedule.
        apply_change(db, meeting, payload.starts_at, payload.duration, payload.location)
    else:
        notify_members(db, meeting, "收到改约提议", "同意前仍按原时间和地点安排。", exclude=user.id)
    db.commit()
    return meeting_dict(db, meeting, user.id)


class JoinIn(BaseModel):
    allow_conflict: bool = False


@router.post("/api/activities/{activity_id}/join")
def join_group(activity_id: int, payload: JoinIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    lock_user(db, user.id)
    # Lock the meetup before checking capacity; never oversubscribe the last seat.
    found = db.scalar(select(Meetup.id).where(Meetup.activity_id == activity_id))
    if found is None:
        raise HTTPException(404, "这个状态不是多人组局")
    db.execute(update(Meetup).where(Meetup.id == found).values(id=Meetup.id))
    meeting = db.get(Meetup, found)
    activity = db.get(Activity, activity_id)
    if not activity.active or meeting.state != "confirmed" or meeting.starts_at <= datetime.utcnow():
        raise HTTPException(409, "组局已结束或已开始")
    if meeting.proposal:
        raise HTTPException(409, "组局正在确认改约，请稍后加入")
    people = active_members(db, meeting.id)
    for person in people:
        ensure_pair(db, user.id, person.user_id)
    member = db.get(MeetupMember, (meeting.id, user.id))
    if member and member.status == "accepted":
        return meeting_dict(db, meeting, user.id)
    if len(people) >= meeting.capacity:
        raise HTTPException(409, "人数已满，看看其他组局吧")
    conflict_check(db, user.id, meeting.starts_at, meeting.duration, meeting.id, payload.allow_conflict)
    if member is None:
        member = MeetupMember(meetup_id=meeting.id, user_id=user.id)
        db.add(member)
    member.status, member.attended, member.cancel_reason, member.cancelled_at = "accepted", 0, "", None
    meeting.revision += 1
    notify_members(db, meeting, "新同伴加入组局", f"{user.username} 已加入。", exclude=user.id)
    db.commit()
    return meeting_dict(db, meeting, user.id)


@router.get("/api/meetups/{meeting_id}/messages")
def group_messages(meeting_id: int, request: Request, db: Session = Depends(get_db),
                   after: int = Query(0, ge=0), before: int | None = Query(None, gt=0)):
    user = auth(request, db)
    meeting, member = meeting_for(db, meeting_id, user.id)
    if meeting.kind != "group" or member.status not in ("accepted", "cancelled"):
        raise HTTPException(403, "加入组局后才能查看群聊")
    query = select(GroupMessage, User.username).join(User, User.id == GroupMessage.sender_id).where(GroupMessage.meetup_id == meeting_id)
    # A member who left retains only messages sent before leaving.
    if member.cancelled_at:
        query = query.where(GroupMessage.created_at <= member.cancelled_at)
    if before:
        query = query.where(GroupMessage.id < before)
    if after:
        query = query.where(GroupMessage.id > after)
    rows = db.execute(query.order_by(GroupMessage.id if after else GroupMessage.id.desc()).limit(50)).all()
    if not after:
        rows.reverse()
    identities = chat_identities(db, (m.sender_id for m, _ in rows), user.id)
    return [{"id": m.id, "sender_id": m.sender_id, **identities[m.sender_id], "body": m.body,
             "created_at": m.created_at.isoformat() + "Z"} for m, name in rows]


@router.post("/api/meetups/{meeting_id}/messages")
def send_group_message(meeting_id: int, payload: BuddyMessageIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable(db, user)
    meeting, member = meeting_for(db, meeting_id, user.id, lock=True)
    if meeting.kind != "group" or member.status != "accepted" or meeting.state in ("cancelled", "declined"):
        raise HTTPException(403, "当前不能在这个组局发言")
    row = GroupMessage(meetup_id=meeting.id, sender_id=user.id, body=payload.body)
    db.add(row)
    db.flush()
    for person in active_members(db, meeting.id):
        if person.user_id != user.id and person.user_id not in set(db.scalars(blocked(user.id))):
            db.add(UserNotice(user_id=person.user_id, meetup_id=meeting.id, title="组局里有新消息", body="点击进入群聊查看。"))
    db.commit()
    return {"id": row.id}


@router.get("/api/notices")
def notices(request: Request, db: Session = Depends(get_db), after: int = Query(0, ge=0)):
    user = auth(request, db)
    rows = db.scalars(select(UserNotice).where(UserNotice.user_id == user.id, UserNotice.id > after, UserNotice.chat_id.is_(None))
                      .order_by(UserNotice.id.desc()).limit(50)).all()
    count = db.scalar(select(func.count()).select_from(UserNotice).where(UserNotice.user_id == user.id, UserNotice.is_read == 0, UserNotice.chat_id.is_(None)))
    return {"count": count, "items": [{"id": n.id, "meetup_id": n.meetup_id, "title": n.title,
            "body": n.body, "is_read": bool(n.is_read), "created_at": n.created_at.isoformat() + "Z"} for n in rows]}


@router.post("/api/notices/{notice_id}/read")
def read_notice(notice_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    db.execute(update(UserNotice).where(UserNotice.id == notice_id, UserNotice.user_id == user.id).values(is_read=1))
    db.commit()
    return {"ok": True}


@router.post("/api/meetups/{meeting_id}/read")
def read_meeting(meeting_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    meeting_for(db, meeting_id, user.id)
    db.execute(update(UserNotice).where(UserNotice.meetup_id == meeting_id, UserNotice.user_id == user.id).values(is_read=1))
    db.commit()
    return {"ok": True}


class ReportIn(BaseModel):
    target_id: int
    reason: str = Field(min_length=5, max_length=1000)
    chat_id: int | None = None
    activity_id: int | None = None
    meetup_id: int | None = None


@router.post("/api/reports")
def report(payload: ReportIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    lock_user(db, user.id)
    if payload.target_id == user.id or not db.get(User, payload.target_id):
        raise HTTPException(422, "请选择要举报的用户")
    if len(payload.reason.strip()) < 5:
        raise HTTPException(422, "请具体描述问题，至少五个字")
    if payload.chat_id:
        chat = db.get(BuddyChat, payload.chat_id)
        if not chat or {chat.user_a, chat.user_b} != {user.id, payload.target_id}:
            raise HTTPException(404, "聊天不存在")
    if payload.activity_id:
        activity = db.get(Activity, payload.activity_id)
        if not activity or activity.user_id != payload.target_id:
            raise HTTPException(404, "运动状态不存在")
    if payload.meetup_id:
        meeting_for(db, payload.meetup_id, user.id)
        if not db.get(MeetupMember, (payload.meetup_id, payload.target_id)):
            raise HTTPException(404, "组局成员不存在")
    if not any((payload.chat_id, payload.activity_id, payload.meetup_id)):
        raise HTTPException(422, "请从聊天、组局或状态页面发起举报")
    count = db.scalar(select(func.count()).select_from(UserReport).where(
        UserReport.reporter_id == user.id, UserReport.created_at > datetime.utcnow() - timedelta(days=1)))
    if count >= 5:
        raise HTTPException(429, "今天已提交五条举报，请等待处理")
    row = UserReport(reporter_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "message": "举报已提交，可在我的举报中查看进度"}


def report_dict(db, row, admin=False):
    data = {"id": row.id, "target": db.get(User, row.target_id).username,
            "reason": row.reason, "state": row.state, "resolution": row.resolution,
            "created_at": row.created_at.isoformat() + "Z"}
    if admin:
        data.update(reporter=db.get(User, row.reporter_id).username, target_id=row.target_id,
                    chat_id=row.chat_id, activity_id=row.activity_id, meetup_id=row.meetup_id)
    return data


@router.get("/api/reports/mine")
def my_reports(request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    rows = db.scalars(select(UserReport).where(UserReport.reporter_id == user.id).order_by(UserReport.id.desc()).limit(50))
    return [report_dict(db, row) for row in rows]


def admin_user(request, db):
    user = auth(request, db)
    if not db.get(AdminRole, user.id):
        raise HTTPException(403, "仅管理员可查看举报")
    return user


@router.get("/api/admin/reports")
def admin_reports(request: Request, db: Session = Depends(get_db), offset: int = Query(0, ge=0)):
    admin_user(request, db)
    rows = db.scalars(select(UserReport).order_by((UserReport.state == "pending").desc(), UserReport.id.desc()).offset(offset).limit(30))
    return [report_dict(db, row, True) for row in rows]


class ResolutionIn(BaseModel):
    resolution: str = Field(min_length=5, max_length=1000)
    action: Literal["resolve", "dismiss", "hide_activity", "suspend_7d", "restore"]


@router.post("/api/admin/reports/{report_id}")
def resolve_report(report_id: int, payload: ResolutionIn, request: Request, db: Session = Depends(get_db)):
    admin_user(request, db)
    row = db.get(UserReport, report_id)
    if not row:
        raise HTTPException(404, "举报不存在")
    if not payload.resolution.strip():
        raise HTTPException(422, "请填写处理说明")
    if payload.action == "hide_activity":
        activity = db.get(Activity, row.activity_id) if row.activity_id else None
        if not activity:
            raise HTTPException(422, "这条举报没有关联运动状态")
        activity.active = 0
        sync_legacy_status(db, activity, remove=True)
    if payload.action in ("suspend_7d", "restore"):
        if db.get(AdminRole, row.target_id):
            raise HTTPException(409, "管理员账号的权限需要由部署维护者处理")
        action = db.get(ModerationAction, row.target_id)
        if action is None:
            action = ModerationAction(user_id=row.target_id)
            db.add(action)
        action.suspended_until = datetime.utcnow() + timedelta(days=7) if payload.action == "suspend_7d" else None
        action.reason = payload.resolution[:500]
    row.state = "dismissed" if payload.action == "dismiss" else "resolved"
    row.resolution, row.handled_at = payload.resolution.strip(), datetime.utcnow()
    db.add(UserNotice(user_id=row.reporter_id, title="举报处理结果", body=f"举报 #{row.id} 已处理，请到“我的举报”查看。"))
    if payload.action in ("hide_activity", "suspend_7d", "restore"):
        db.add(UserNotice(user_id=row.target_id, title="账号或状态处理通知", body=payload.resolution[:300]))
    db.commit()
    return {"message": "处理结果已保存"}
