from datetime import date
from pydantic import BaseModel, Field, ConfigDict, field_validator

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
