"""Fresh, access-checked activity details for discovery cards."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Activity
from .campus import activity_dict, auth
from .media import visible_owner

router = APIRouter()


@router.get('/api/activities/{activity_id}')
def activity_detail(activity_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth(request, db)
    row = db.get(Activity, activity_id)
    if row is None or not row.active or row.starts_at <= datetime.utcnow():
        raise HTTPException(404, '这场运动已开始或已撤下，请看看其他邀请')
    visible_owner(db, user, row.user_id)
    return activity_dict(db, row, user.id)
