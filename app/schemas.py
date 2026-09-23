from datetime import date
from pydantic import BaseModel, Field, ConfigDict

class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=100)

class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    target: str = ""
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
    feeling: str = "一般"
    note: str = ""

class RecordOut(RecordIn):
    id: int
    model_config = ConfigDict(from_attributes=True)
