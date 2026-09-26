from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import hashlib
import hmac
import os
import secrets
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import User, Plan, ExerciseRecord, LoginSession
from .schemas import UserIn, PlanIn, RecordIn
from .services.analytics import summary, chart_data, review
from .services.ai_advice import generate_ai_advice

Base.metadata.create_all(bind=engine)
app = FastAPI(title="大学生运动计划与训练记录平台", version="1.0.0")
APP_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, salt_hex, digest_hex = encoded.split("$", 2)
        if algo != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

# Only a hash of the random session token is stored in the database.
def current_user(request: Request, db: Session):
    token = request.cookies.get("session", "")
    if len(token) != 64:
        return None
    session = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at <= datetime.utcnow():
        return None
    return db.get(User, session.user_id)

def require_user(request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})

@app.post("/api/register")
def register(payload: UserIn, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(400, "用户名已存在")
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名已存在")
    db.refresh(user)
    return {"message": "注册成功", "user_id": user.id}

@app.post("/api/login")
def login(payload: UserIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    old_token = request.cookies.get("session", "")
    db.execute(delete(LoginSession).where(
        (LoginSession.expires_at <= datetime.utcnow()) |
        (LoginSession.token_hash == hashlib.sha256(old_token.encode()).hexdigest())
    ))
    token = secrets.token_hex(32)
    db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                        user_id=user.id, expires_at=datetime.utcnow() + timedelta(days=7)))
    db.commit()
    response.set_cookie("session", token, httponly=True, samesite="lax",
                        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
                        max_age=86400 * 7)
    response.delete_cookie("uid")
    return {"message": "登录成功", "username": user.username}

@app.post("/api/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("session", "")
    db.execute(delete(LoginSession).where(
        LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    db.commit()
    response.delete_cookie("session")
    response.delete_cookie("uid")
    return {"message": "已退出"}

@app.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "username": user.username, "id": user.id}

@app.get("/api/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return {"summary": summary(db, user.id), "chart": chart_data(db, user.id), "review": review(db, user.id)}

@app.get("/api/plans")
def get_plans(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    plans = db.scalars(select(Plan).where(Plan.user_id == user.id).order_by(Plan.start_date.desc())).all()
    return [{"id": p.id, "title": p.title, "target": p.target, "weekly_minutes": p.weekly_minutes,
             "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat()} for p in plans]

@app.post("/api/plans")
def create_plan(payload: PlanIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    plan = Plan(user_id=user.id, **payload.model_dump())
    db.add(plan); db.commit(); db.refresh(plan)
    return {"message": "计划创建成功", "id": plan.id}

@app.get("/api/records")
def get_records(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    rows = db.scalars(select(ExerciseRecord).where(ExerciseRecord.user_id == user.id).order_by(ExerciseRecord.exercise_date.desc(), ExerciseRecord.id.desc()).limit(100)).all()
    return [record_to_dict(r) for r in rows]

def record_to_dict(r):
    return {"id": r.id, "exercise_date": r.exercise_date.isoformat(), "exercise_type": r.exercise_type,
            "duration": r.duration, "distance": r.distance, "intensity": r.intensity,
            "calories": r.calories, "feeling": r.feeling, "note": r.note}

@app.post("/api/records")
def create_record(payload: RecordIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    exists = db.scalar(select(ExerciseRecord).where(
        ExerciseRecord.user_id == user.id,
        ExerciseRecord.exercise_date == payload.exercise_date,
        ExerciseRecord.exercise_type == payload.exercise_type,
    ))
    if exists:
        raise HTTPException(400, "同一天同类型运动已有记录，可修改为不同项目后再提交")
    row = ExerciseRecord(user_id=user.id, **payload.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同一天同类型运动已有记录")
    db.refresh(row)
    return record_to_dict(row)

@app.delete("/api/records/{record_id}")
def delete_record(record_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    row = db.get(ExerciseRecord, record_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(row); db.commit()
    return {"message": "删除成功"}

@app.get("/api/review")
def get_review(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return review(db, user.id)

@app.post("/api/ai-advice")
async def ai_advice(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    s = summary(db, user.id)
    r = review(db, user.id)
    advice = await generate_ai_advice(s, r)
    return {"advice": advice}
