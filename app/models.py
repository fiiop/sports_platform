from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    plans = relationship("Plan", back_populates="user", cascade="all, delete-orphan")
    records = relationship("ExerciseRecord", back_populates="user", cascade="all, delete-orphan")

class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(Text, default="")
    weekly_minutes: Mapped[int] = mapped_column(Integer, default=150)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    user = relationship("User", back_populates="plans")

class ExerciseRecord(Base):
    __tablename__ = "exercise_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_date: Mapped[date] = mapped_column(Date, index=True)
    exercise_type: Mapped[str] = mapped_column(String(50))
    duration: Mapped[int] = mapped_column(Integer)
    distance: Mapped[float] = mapped_column(Float, default=0.0)
    intensity: Mapped[int] = mapped_column(Integer, default=3)
    calories: Mapped[int] = mapped_column(Integer, default=0)
    feeling: Mapped[str] = mapped_column(String(20), default="一般")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="records")
    __table_args__ = (UniqueConstraint("user_id", "exercise_date", "exercise_type", name="uq_record_type_day"),)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class WeeklyReflection(Base):
    __tablename__ = "weekly_reflections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    reflection: Mapped[str] = mapped_column(Text, default="")
    next_action: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_reflection_week"),)


class BuddyStatus(Base):
    __tablename__ = "buddy_statuses"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    exercise_type: Mapped[str] = mapped_column(String(50))
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class BuddyChat(Base):
    __tablename__ = "buddy_chats"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_a: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user_b: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(300))
    __table_args__ = (UniqueConstraint("user_a", "user_b", name="uq_buddy_pair"),)


class BuddyMessage(Base):
    __tablename__ = "buddy_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("buddy_chats.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BuddyRating(Base):
    __tablename__ = "buddy_ratings"
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    score: Mapped[int] = mapped_column(Integer)


class BuddyBlock(Base):
    __tablename__ = "buddy_blocks"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class BuddyReadCursor(Base):
    __tablename__ = "buddy_read_cursors"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("buddy_chats.id"), primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, default=0)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    endpoint_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_hash: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(150))
    auth: Mapped[str] = mapped_column(String(80))


class PushKey(Base):
    __tablename__ = "push_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    private_key: Mapped[str] = mapped_column(Text)


class CampusProfile(Base):
    __tablename__ = "campus_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    school: Mapped[str] = mapped_column(String(100), default="湘潭大学")
    theme: Mapped[str] = mapped_column(String(20), default="forest")


class Activity(Base):
    __tablename__ = "sports_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    legacy_user_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    exercise_type: Mapped[str] = mapped_column(String(50))
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str] = mapped_column(String(200))
    school: Mapped[str] = mapped_column(String(100), default="湘潭大学")
    level: Mapped[str] = mapped_column(String(20), default="不限")
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[int] = mapped_column(Integer, default=1)


class Meetup(Base):
    __tablename__ = "meetups"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("sports_activities.id"), unique=True, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("buddy_chats.id"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="pair")
    exercise_type: Mapped[str] = mapped_column(String(50))
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str] = mapped_column(String(200))
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    proposal: Mapped[str] = mapped_column(Text, default="")
    proposal_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(500), default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MeetupMember(Base):
    __tablename__ = "meetup_members"
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attended: Mapped[int] = mapped_column(Integer, default=0)
    vote: Mapped[int] = mapped_column(Integer, default=0)
    cancel_reason: Mapped[str] = mapped_column(String(500), default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_id: Mapped[int] = mapped_column(Integer, default=0)


class GroupMessage(Base):
    __tablename__ = "group_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetups.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserNotice(Base):
    __tablename__ = "user_notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    meetup_id: Mapped[int | None] = mapped_column(ForeignKey("meetups.id"), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("buddy_chats.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("buddy_messages.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(300), default="")
    is_read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    push_attempts: Mapped[int] = mapped_column(Integer, default=0)
    push_after: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    push_done: Mapped[int] = mapped_column(Integer, default=0)
    dedupe_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)


class UserReport(Base):
    __tablename__ = "user_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("buddy_chats.id"), nullable=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("sports_activities.id"), nullable=True)
    meetup_id: Mapped[int | None] = mapped_column(ForeignKey("meetups.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(1000))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    resolution: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")


class AdminRole(Base):
    __tablename__ = "admin_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class MigrationStamp(Base):
    __tablename__ = "migration_stamps"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
