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
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
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
