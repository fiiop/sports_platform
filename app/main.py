from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import hashlib
import hmac
import os
import secrets
from sqlalchemy import select, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import User, Plan, ExerciseRecord, LoginSession, WeeklyReflection, BuddyStatus, BuddyChat, BuddyMessage
from .schemas import UserIn, PlanIn, RecordIn, ReflectionIn, BuddyStatusIn, BuddyMessageIn
from .services.analytics import summary, chart_data, review
from .services.ai_advice import generate_ai_advice

Base.metadata.create_all(bind=engine)
app = FastAPI(title="大学生运动计划与训练记录平台", version="2.0.0")
APP_DIR = Path(__file__).resolve().parent
ASSET_VERSION = hashlib.sha256(b"".join(
    (APP_DIR / "static" / name).read_bytes()
    for name in ("app.js", "buddies.js", "style.css")
)).hexdigest()[:16]
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
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"user": user, "asset_version": ASSET_VERSION},
                                      headers={"Cache-Control": "no-store"})

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
def get_records(request: Request, db: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    user = require_user(request, db)
    rows = db.scalars(select(ExerciseRecord).where(ExerciseRecord.user_id == user.id).order_by(ExerciseRecord.exercise_date.desc(), ExerciseRecord.id.desc()).offset(offset).limit(limit)).all()
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
    return advice


@app.get("/sw.js")
def service_worker():
    script = (APP_DIR / "static" / "sw.js").read_text(encoding="utf-8").replace("__ASSET_VERSION__", ASSET_VERSION)
    return Response(script, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.put("/api/records/{record_id}")
def update_record(record_id: int, payload: RecordIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    row = db.get(ExerciseRecord, record_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同一天同类型运动已有记录，请编辑原记录")
    db.refresh(row)
    return record_to_dict(row)


@app.put("/api/plans/{plan_id}")
def update_plan(plan_id: int, payload: PlanIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    plan = db.get(Plan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(404, "计划不存在")
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    db.commit()
    return {"message": "计划已更新", "id": plan.id}


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    plan = db.get(Plan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(404, "计划不存在")
    db.delete(plan)
    db.commit()
    return {"message": "计划已删除，训练记录会保留"}


@app.get("/api/reflection")
def get_reflection(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    today = date.today()
    week = today - timedelta(days=today.weekday())
    row = db.scalar(select(WeeklyReflection).where(
        WeeklyReflection.user_id == user.id, WeeklyReflection.week_start == week))
    return {"week_start": week.isoformat(), "reflection": row.reflection if row else "",
            "next_action": row.next_action if row else ""}


@app.put("/api/reflection")
def save_reflection(payload: ReflectionIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    today = date.today()
    week = today - timedelta(days=today.weekday())
    row = db.scalar(select(WeeklyReflection).where(
        WeeklyReflection.user_id == user.id, WeeklyReflection.week_start == week))
    if not row:
        row = WeeklyReflection(user_id=user.id, week_start=week)
        db.add(row)
    row.reflection = payload.reflection
    row.next_action = payload.next_action
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "复盘已在其他页面更新，请刷新后重试")
    return {"message": "本周复盘已保存"}


def buddy_status_dict(row, username):
    return {"user_id": row.user_id, "username": username, "exercise_type": row.exercise_type,
            "starts_at": row.starts_at.isoformat() + "Z", "location": row.location,
            "latitude": row.latitude, "longitude": row.longitude, "note": row.note}


@app.get("/api/buddies")
def list_buddies(request: Request, db: Session = Depends(get_db),
                 exercise_type: str = Query("", max_length=50), offset: int = Query(0, ge=0),
                 limit: int = Query(100, ge=1, le=100)):
    require_user(request, db)
    query = select(BuddyStatus, User.username).join(User, User.id == BuddyStatus.user_id).where(
        BuddyStatus.starts_at > datetime.utcnow())
    if exercise_type.strip():
        query = query.where(BuddyStatus.exercise_type == exercise_type.strip())
    rows = db.execute(query.order_by(BuddyStatus.starts_at, BuddyStatus.user_id).offset(offset).limit(limit)).all()
    return [buddy_status_dict(row, name) for row, name in rows]


@app.get("/api/buddies/me")
def my_buddy_status(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    row = db.get(BuddyStatus, user.id)
    return buddy_status_dict(row, user.username) if row else None


@app.put("/api/buddies/me")
def save_buddy_status(payload: BuddyStatusIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    row = db.get(BuddyStatus, user.id)
    if row is None:
        row = BuddyStatus(user_id=user.id, **payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "状态已在其他页面更新，请刷新重试")
    return buddy_status_dict(row, user.username)


@app.delete("/api/buddies/me")
def remove_buddy_status(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    db.execute(delete(BuddyStatus).where(BuddyStatus.user_id == user.id))
    db.commit()
    return {"message": "状态已撤下，已有聊天保留"}


@app.post("/api/buddies/{user_id}/chat")
def start_buddy_chat(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.id == user_id:
        raise HTTPException(400, "不能和自己发起聊天")
    a, b = sorted([user.id, user_id])
    chat = db.scalar(select(BuddyChat).where(BuddyChat.user_a == a, BuddyChat.user_b == b))
    if chat:
        return {"id": chat.id}
    status = db.get(BuddyStatus, user_id)
    if not status or status.starts_at <= datetime.utcnow():
        raise HTTPException(404, "对方状态已撤下或已过期，请刷新地图")
    chat = BuddyChat(user_a=a, user_b=b, topic=f"{status.exercise_type} · {status.location}")
    db.add(chat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        chat = db.scalar(select(BuddyChat).where(BuddyChat.user_a == a, BuddyChat.user_b == b))
        if chat is None:
            raise HTTPException(409, "暂时无法创建聊天，请重试")
    return {"id": chat.id}


@app.get("/api/buddy-chats")
def list_buddy_chats(request: Request, db: Session = Depends(get_db), offset: int = Query(0, ge=0)):
    user = require_user(request, db)
    chats = db.scalars(select(BuddyChat).where(or_(BuddyChat.user_a == user.id, BuddyChat.user_b == user.id))
                       .order_by(BuddyChat.id.desc()).offset(offset).limit(100)).all()
    results = []
    for chat in chats:
        other = db.get(User, chat.user_b if chat.user_a == user.id else chat.user_a)
        last = db.scalar(select(BuddyMessage).where(BuddyMessage.chat_id == chat.id).order_by(BuddyMessage.id.desc()).limit(1))
        results.append({"id": chat.id, "username": other.username, "topic": chat.topic,
                        "last_message": last.body if last else "还没有消息，打个招呼吧",
                        "last_id": last.id if last else 0})
    return results


def require_buddy_chat(chat_id, user, db):
    chat = db.get(BuddyChat, chat_id)
    if not chat or user.id not in (chat.user_a, chat.user_b):
        raise HTTPException(404, "聊天不存在")
    return chat


@app.get("/api/buddy-chats/{chat_id}/messages")
def buddy_messages(chat_id: int, request: Request, db: Session = Depends(get_db), after: int = Query(0, ge=0)):
    user = require_user(request, db)
    require_buddy_chat(chat_id, user, db)
    rows = db.scalars(select(BuddyMessage).where(BuddyMessage.chat_id == chat_id, BuddyMessage.id > after)
                      .order_by(BuddyMessage.id).limit(100)).all()
    return [{"id": row.id, "sender_id": row.sender_id, "body": row.body,
             "created_at": row.created_at.isoformat() + "Z"} for row in rows]


@app.post("/api/buddy-chats/{chat_id}/messages")
def send_buddy_message(chat_id: int, payload: BuddyMessageIn, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    require_buddy_chat(chat_id, user, db)
    row = BuddyMessage(chat_id=chat_id, sender_id=user.id, body=payload.body)
    db.add(row)
    db.commit()
    return {"id": row.id}
