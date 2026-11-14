"""Opt-in Web Push, bound to the browser's authenticated session."""
import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from pywebpush import WebPushException, webpush
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BuddyBlock, BuddyChat, BuddyMessage, BuddyReadCursor, LoginSession, Meetup, MeetupMember, PushKey, PushSubscription, User, UserNotice

router = APIRouter()
log = logging.getLogger(__name__)


def require_user(request, db):
    from ..main import require_user as authenticate
    return authenticate(request, db)


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(text):
    return base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)


def valid_endpoint(value):
    url = urlsplit(value)
    host = url.hostname or ""
    allowed = host in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"} or any(
        host.endswith("." + domain) for domain in ("push.services.mozilla.com", "push.apple.com", "notify.windows.com"))
    if (url.scheme != "https" or not allowed or url.port not in (None, 443)
            or url.username or url.password or url.fragment):
        raise ValueError("请选择支持标准推送服务的浏览器")
    return value


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=150)
    auth: str = Field(min_length=20, max_length=80)

    @field_validator("p256dh")
    @classmethod
    def public_point(cls, value):
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(value))
        return value

    @field_validator("auth")
    @classmethod
    def auth_secret(cls, value):
        if len(unb64(value)) != 16:
            raise ValueError("无效的推送认证信息")
        return value


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=4096)
    keys: SubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def endpoint_allowed(cls, value):
        return valid_endpoint(value)


def get_key(db):
    row = db.get(PushKey, 1)
    if row is None:
        private = ec.generate_private_key(ec.SECP256R1())
        row = PushKey(id=1, private_key=b64(private.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())))
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.get(PushKey, 1)
    private = serialization.load_der_private_key(unb64(row.private_key), password=None)
    public = b64(private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return row.private_key, public


@router.get("/api/push/public-key")
def public_key(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    return {"public_key": get_key(db)[1]}


@router.put("/api/push/subscriptions")
def subscribe(payload: SubscriptionIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    session_hash = hashlib.sha256(request.cookies["session"].encode()).hexdigest()
    key = hashlib.sha256(payload.endpoint.encode()).hexdigest()
    row = db.get(PushSubscription, key)
    # Knowing an endpoint alone cannot take over another browser's subscription.
    if row and (row.p256dh != payload.keys.p256dh or row.auth != payload.keys.auth):
        raise HTTPException(409, "通知订阅已变化，请先关闭再重新开启")
    live_sessions = select(LoginSession.token_hash).where(LoginSession.expires_at > datetime.utcnow())
    db.execute(delete(PushSubscription).where(~PushSubscription.session_hash.in_(live_sessions)))
    if row is not None and row not in db:
        row = None
    if row is None:
        count = db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
        if count >= 10:
            raise HTTPException(409, "已开启通知的设备过多，请先在旧设备关闭通知")
        row = PushSubscription(endpoint_hash=key)
        db.add(row)
    row.user_id, row.session_hash = user.id, session_hash
    row.endpoint, row.p256dh, row.auth = payload.endpoint, payload.keys.p256dh, payload.keys.auth
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "通知设置正在更新，请重试")
    return {"enabled": True}


@router.delete("/api/push/subscriptions")
def unsubscribe(payload: SubscriptionIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    key = hashlib.sha256(payload.endpoint.encode()).hexdigest()
    db.execute(delete(PushSubscription).where(PushSubscription.endpoint_hash == key,
        PushSubscription.user_id == user.id, PushSubscription.auth == payload.keys.auth,
        PushSubscription.p256dh == payload.keys.p256dh))
    db.commit()
    return {"enabled": False}


def incoming_query(user_id):
    blocked = select(BuddyBlock.blocked_id).where(BuddyBlock.user_id == user_id).union(
        select(BuddyBlock.user_id).where(BuddyBlock.blocked_id == user_id))
    return (select(BuddyMessage).join(BuddyChat, BuddyChat.id == BuddyMessage.chat_id)
            .where(or_(BuddyChat.user_a == user_id, BuddyChat.user_b == user_id),
                   BuddyMessage.sender_id != user_id, ~BuddyMessage.sender_id.in_(blocked)))


@router.get("/api/buddy-notifications")
def notifications(request: Request, db: Session = Depends(get_db), after: int | None = Query(None, ge=0)):
    user = require_user(request, db)
    base = incoming_query(user.id)
    newest = db.scalar(base.with_only_columns(func.max(BuddyMessage.id))) or 0
    if after is None:
        return {"cursor": newest, "items": []}
    query = (base.join(User, User.id == BuddyMessage.sender_id)
             .outerjoin(BuddyReadCursor, and_(BuddyReadCursor.user_id == user.id, BuddyReadCursor.chat_id == BuddyChat.id))
             .where(BuddyMessage.id > after, BuddyMessage.id > func.coalesce(BuddyReadCursor.message_id, 0))
             .add_columns(User.username).order_by(BuddyMessage.id).limit(50))
    rows = db.execute(query).all()
    return {"cursor": rows[-1][0].id if len(rows) == 50 else max(newest, after),
            "items": [{"id": row.id, "chat_id": row.chat_id, "username": name} for row, name in rows]}


@router.get("/api/push/check")
def check_push(request: Request, user_id: int, chat_id: int = 0, message_id: int = 0,
               notice_id: int = 0, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.id != user_id:
        return {"show": False}
    if notice_id:
        notice = db.get(UserNotice, notice_id)
        show = bool(notice and notice.user_id == user.id and not notice.is_read
                    and reminder_is_current(db, notice))
        if show and notice.chat_id:
            return {"show": should_deliver(db, user.id, notice.chat_id, notice.message_id),
                    "url": f"/#messages/{notice.chat_id}"}
        return {"show": show, "title": "循动 · 约定与消息提醒",
                "url": f"/#buddies/group/{notice.meetup_id}" if show and notice.meetup_id else "/#messages"}
    return {"show": should_deliver(db, user.id, chat_id, message_id), "url": f"/#messages/{chat_id}"}


def should_deliver(db, user_id, chat_id, message_id):
    row = db.scalar(incoming_query(user_id).where(BuddyMessage.id == message_id, BuddyMessage.chat_id == chat_id))
    cursor = db.get(BuddyReadCursor, (user_id, chat_id))
    return bool(row and (not cursor or cursor.message_id < message_id))


def reminder_is_current(db, notice, now=None):
    """Recheck delayed pushes, including ones already queued by the push provider."""
    if not notice.dedupe_key:
        return True
    now = now or datetime.utcnow()
    meeting = db.get(Meetup, notice.meetup_id) if notice.meetup_id else None
    member = db.get(MeetupMember, (notice.meetup_id, notice.user_id)) if meeting else None
    if notice.dedupe_key.startswith("repeat:"):
        # Repeat invitations use a request key for idempotence, not a reminder schedule.
        if not (meeting and member and member.status == "pending"
                and meeting.state in ("pending", "confirmed") and meeting.starts_at > now):
            return False
        from .campus import blocked
        return meeting.owner_id not in set(db.scalars(blocked(notice.user_id)))
    if not meeting or meeting.state != "confirmed" or not member or member.status != "accepted":
        return False
    for minutes in (120, 30):
        key = f"{meeting.id}:{notice.user_id}:{meeting.starts_at.isoformat()}:{minutes}"
        due = meeting.starts_at - timedelta(minutes=minutes)
        if notice.dedupe_key == key and due <= now < due + timedelta(minutes=10):
            count = db.scalar(select(func.count()).select_from(MeetupMember).where(
                MeetupMember.meetup_id == meeting.id, MeetupMember.status == "accepted"))
            return count >= 2
    return False


class PushSession(requests.Session):
    def request(self, method, url, **kwargs):
        valid_endpoint(url)
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def deliver_message_push(bind, user_id, chat_id, message_id):
    # Separate session: message persistence does not depend on push availability.
    try:
        with Session(bind) as db:
            if not should_deliver(db, user_id, chat_id, message_id):
                return
            subscriptions = db.scalars(select(PushSubscription).join(LoginSession,
                LoginSession.token_hash == PushSubscription.session_hash).where(
                PushSubscription.user_id == user_id, LoginSession.user_id == user_id,
                LoginSession.expires_at > datetime.utcnow())).all()
            if not subscriptions:
                return
            private, _ = get_key(db)
            data = json.dumps({"user_id": user_id, "chat_id": chat_id, "id": message_id})
            with PushSession() as transport:
                for sub in subscriptions:
                    try:
                        webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                                data, vapid_private_key=private,
                                vapid_claims={"sub": os.getenv("VAPID_SUBJECT", "https://sports-platform-6809.onrender.com")},
                                ttl=3600, timeout=8, requests_session=transport)
                    except WebPushException as error:
                        status = getattr(error, "status_code", None)
                        if status is None and error.response is not None:
                            status = error.response.status_code
                        if status in (404, 410):
                            db.delete(sub)
                        else:
                            log.warning("Push delivery failed (status=%s)", status)
                    except Exception:
                        log.warning("Push delivery unavailable")
            db.commit()
    except Exception:
        # Never log subscription endpoints, keys, or private message text.
        log.warning("Push task could not complete")


def deliver_notice_push(bind, notice_id):
    """Return False on transient delivery errors so the durable queue can retry."""
    with Session(bind) as db:
        notice = db.get(UserNotice, notice_id)
        if not notice or notice.is_read or not reminder_is_current(db, notice):
            return True
        if notice.chat_id and not should_deliver(db, notice.user_id, notice.chat_id, notice.message_id):
            return True
        subscriptions = db.scalars(select(PushSubscription).join(LoginSession,
            LoginSession.token_hash == PushSubscription.session_hash).where(
            PushSubscription.user_id == notice.user_id, LoginSession.user_id == notice.user_id,
            LoginSession.expires_at > datetime.utcnow())).all()
        if not subscriptions:
            return True
        private, _ = get_key(db)
        ok = True
        with PushSession() as transport:
            for sub in subscriptions:
                try:
                    webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                            json.dumps({"user_id": notice.user_id, "notice_id": notice.id}),
                            vapid_private_key=private,
                            vapid_claims={"sub": os.getenv("VAPID_SUBJECT", "https://sports-platform-6809.onrender.com")},
                            ttl=3600, timeout=8, requests_session=transport)
                except WebPushException as error:
                    status = getattr(error, "status_code", None)
                    if status is None and error.response is not None:
                        status = error.response.status_code
                    if status in (404, 410):
                        db.delete(sub)
                    else:
                        ok = False
                except Exception:
                    ok = False
        db.commit()
        return ok
