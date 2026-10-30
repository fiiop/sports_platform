"""Opt-in public identity and bounded image uploads, persisted in the database."""
from datetime import datetime
from io import BytesIO
import secrets
import warnings

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Activity, ActivityCover, Meetup, MeetupMember, ModerationAction,
                      ProfileAvatar, PublicIdentity, User)

router = APIRouter()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


def auth(request, db):
    from ..main import require_user
    return require_user(request, db)


def identity_dict(db, user_id, username=None):
    identity = db.get(PublicIdentity, user_id)
    nickname = identity.nickname if identity else ""
    if username is None:
        username = db.scalar(select(User.username).where(User.id == user_id)) or "运动伙伴"
    version = db.scalar(select(ProfileAvatar.version).where(ProfileAvatar.user_id == user_id))
    return {"nickname": nickname, "display_name": nickname or username,
            "bio": identity.bio if identity else "",
            "avatar_url": f"/api/users/{user_id}/avatar?v={version}" if version else None}


def cover_url(db, activity_id):
    version = db.scalar(select(ActivityCover.version).where(ActivityCover.activity_id == activity_id))
    return f"/api/activities/{activity_id}/cover?v={version}" if version else None


def visible_owner(db, viewer, owner_id):
    if viewer.id == owner_id:
        return
    from .campus import blocked
    if db.scalar(select(User.id).where(User.id == owner_id, User.id.in_(blocked(viewer.id)))):
        raise HTTPException(404, "图片不存在或当前不可查看")
    moderation = db.get(ModerationAction, owner_id)
    if moderation and moderation.suspended_until and moderation.suspended_until > datetime.utcnow():
        raise HTTPException(404, "图片不存在或当前不可查看")


def writable_owner(db, user):
    from .campus import lock_user, writable
    writable(db, user)
    lock_user(db, user.id)


def normalized_image(file, size):
    """Decode a bounded still image, orient it, and encode fresh pixels without metadata."""
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "图片不能超过 5 MB，请压缩后重试")
    if not raw:
        raise HTTPException(422, "请选择一张图片")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as original:
                if original.width * original.height > MAX_PIXELS:
                    raise HTTPException(413, "图片像素过大，请缩小到 2000 万像素以内")
                if getattr(original, "is_animated", False):
                    raise HTTPException(422, "请上传静态照片，暂不支持动图")
                original.load()
                corrected = ImageOps.exif_transpose(original)
                corrected.thumbnail((size, size), Image.Resampling.LANCZOS)
                clean = Image.new("RGB", corrected.size, "white")
                if corrected.mode in ("RGBA", "LA") or "transparency" in corrected.info:
                    rgba = corrected.convert("RGBA")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean.paste(corrected.convert("RGB"))
                output = BytesIO()
                clean.save(output, format="JPEG", quality=82, optimize=True)
                return output.getvalue()
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "图片像素过大，请缩小后重试")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "图片无法读取，请使用有效的 JPEG、PNG 或 WebP 照片")


def image_response(content):
    return Response(content, media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


class IdentityIn(BaseModel):
    nickname: str = Field("", max_length=30)
    bio: str = Field("", max_length=160)

    @field_validator("nickname", "bio")
    @classmethod
    def trim(cls, value):
        return value.strip()


@router.put("/api/profile/identity")
def update_identity(payload: IdentityIn, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    writable_owner(db, user)
    row = db.get(PublicIdentity, user.id)
    if row is None:
        row = PublicIdentity(user_id=user.id)
        db.add(row)
    row.nickname, row.bio = payload.nickname, payload.bio
    db.commit()
    return identity_dict(db, user.id, user.username)


@router.post("/api/profile/avatar")
def upload_avatar(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = auth(request, db)
    writable_owner(db, user)
    content = normalized_image(file, 512)
    row = db.get(ProfileAvatar, user.id)
    if row is None:
        row = ProfileAvatar(user_id=user.id)
        db.add(row)
    row.content, row.version = content, secrets.token_hex(16)
    db.commit()
    return identity_dict(db, user.id, user.username)


@router.delete("/api/profile/avatar")
def remove_avatar(request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    from .campus import lock_user
    lock_user(db, user.id)
    row = db.get(ProfileAvatar, user.id)
    if row:
        db.delete(row)
    db.commit()
    return identity_dict(db, user.id, user.username)


@router.get("/api/users/{user_id}/avatar")
def avatar(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    visible_owner(db, user, user_id)
    row = db.get(ProfileAvatar, user_id)
    if row is None:
        raise HTTPException(404, "头像不存在")
    return image_response(row.content)


def own_activity(db, user, activity_id):
    row = db.get(Activity, activity_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "运动状态不存在")
    return row


@router.post("/api/activities/{activity_id}/cover")
def upload_cover(activity_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = auth(request, db)
    writable_owner(db, user)
    activity = own_activity(db, user, activity_id)
    if not activity.active:
        raise HTTPException(409, "状态已撤下，不能更换封面")
    content = normalized_image(file, 1280)
    row = db.get(ActivityCover, activity_id)
    if row is None:
        row = ActivityCover(activity_id=activity_id)
        db.add(row)
    row.content, row.version = content, secrets.token_hex(16)
    db.commit()
    return {"cover_url": cover_url(db, activity_id)}


@router.delete("/api/activities/{activity_id}/cover")
def remove_cover(activity_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    from .campus import lock_user
    lock_user(db, user.id)
    own_activity(db, user, activity_id)
    row = db.get(ActivityCover, activity_id)
    if row:
        db.delete(row)
    db.commit()
    return {"cover_url": None}


@router.get("/api/activities/{activity_id}/cover")
def cover(activity_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "活动封面不存在")
    visible_owner(db, user, activity.user_id)
    if not activity.active and activity.user_id != user.id:
        member = db.scalar(select(MeetupMember.user_id).join(Meetup).where(
            Meetup.activity_id == activity_id, MeetupMember.user_id == user.id,
            MeetupMember.status.in_(["accepted", "cancelled"])))
        if member is None:
            raise HTTPException(404, "图片不存在或当前不可查看")
    row = db.get(ActivityCover, activity_id)
    if row is None:
        raise HTTPException(404, "活动封面不存在")
    return image_response(row.content)
