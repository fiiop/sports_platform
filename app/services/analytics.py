from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..models import ExerciseRecord

def summary(db: Session, user_id: int):
    today = date.today()
    start = today - timedelta(days=29)
    base = select(ExerciseRecord).where(
        ExerciseRecord.user_id == user_id,
        ExerciseRecord.exercise_date >= start,
        ExerciseRecord.exercise_date <= today,
    )
    rows = list(db.scalars(base))
    total_minutes = sum(r.duration for r in rows)
    total_distance = round(sum(r.distance for r in rows), 2)
    total_calories = sum(r.calories for r in rows)
    active_days = len({r.exercise_date for r in rows})
    avg_intensity = round(sum(r.intensity for r in rows) / len(rows), 1) if rows else 0
    last7 = today - timedelta(days=6)
    last7_minutes = sum(r.duration for r in rows if r.exercise_date >= last7)
    return {
        "total_minutes": total_minutes,
        "total_distance": total_distance,
        "total_calories": total_calories,
        "active_days": active_days,
        "avg_intensity": avg_intensity,
        "last7_minutes": last7_minutes,
    }

def chart_data(db: Session, user_id: int):
    today = date.today()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    rows = db.scalars(select(ExerciseRecord).where(
        ExerciseRecord.user_id == user_id,
        ExerciseRecord.exercise_date >= days[0],
        ExerciseRecord.exercise_date <= days[-1],
    )).all()
    by_day = {d: 0 for d in days}
    for r in rows:
        by_day[r.exercise_date] = by_day.get(r.exercise_date, 0) + r.duration
    return {"labels": [d.isoformat() for d in days], "minutes": [by_day[d] for d in days]}

def review(db: Session, user_id: int):
    s = summary(db, user_id)
    target = 150
    completion = round(s["last7_minutes"] / target * 100)
    completion = min(completion, 200)
    if s["last7_minutes"] == 0:
        status = "尚未开始"
        advice = "本周还没有记录，先完成 20–30 分钟的轻到中等强度运动，建立连续记录习惯。"
    elif s["last7_minutes"] < 90:
        status = "需要提高频率"
        advice = "本周运动量偏少，可以从每周 3 次、每次 30 分钟开始，逐步增加。"
    elif s["last7_minutes"] < 150:
        status = "接近目标"
        advice = "已经形成一定习惯，可以保持当前频率，并逐步补齐每周活动量。"
    else:
        status = "目标达成"
        advice = "本周运动量达到设定目标，继续保持，同时关注恢复、睡眠和训练强度。"
    return {"weekly_minutes": s["last7_minutes"], "target": target, "completion": completion, "status": status, "advice": advice}
