from datetime import date, datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=100)

class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    target: str = Field(default="", max_length=2000)
    weekly_minutes: int = Field(ge=30, le=1000)
    start_date: date
    end_date: date

class RecordIn(BaseModel):
    exercise_date: date
    exercise_type: str = Field(min_length=1, max_length=50)
    duration: int = Field(gt=0, le=600)
    distance: float = Field(default=0, ge=0, le=500)
    intensity: int = Field(default=3, ge=1, le=5)
    calories: int = Field(default=0, ge=0, le=10000)
    feeling: str = Field(default="一般", max_length=20)
    note: str = Field(default="", max_length=2000)

    @field_validator("exercise_type")
    @classmethod
    def clean_type(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("运动项目不能为空")
        return value

class RecordOut(RecordIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ReflectionIn(BaseModel):
    reflection: str = Field(default="", max_length=2000)
    next_action: str = Field(default="", max_length=1000)


class BuddyStatusIn(BaseModel):
    exercise_type: str = Field(min_length=1, max_length=50)
    location: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    latitude: float | None = Field(default=None, ge=-85, le=85, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("经纬度需要同时填写，或只填写场地名称")
        return self

    @field_validator("exercise_type", "location")
    @classmethod
    def clean_text(cls, value):
        if not value.strip():
            raise ValueError("内容不能为空")
        return value.strip()

    @field_validator("starts_at")
    @classmethod
    def future_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
        if value <= datetime.utcnow():
            raise ValueError("请选择未来的运动时间")
        return value


class BuddyMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value.strip()


class BuddyReadIn(BaseModel):
    message_id: int = Field(ge=0)
