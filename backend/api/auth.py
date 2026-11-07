# backend/api/auth.py
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user, COOKIE
from ..db import get_db, SessionLocal
from ..models import User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    name: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    name = body.name.strip()
    if not 1 <= len(name) <= 64:
        raise HTTPException(400, "bad name")
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(name=name).first():
            db.add(User(name=name));
            db.commit()
    finally:
        db.close()
    response.set_cookie(COOKIE, name, httponly=True, samesite="lax")
    return {"name": name}


@router.get("/me")
def me(user: str = Depends(current_user)):
    return {"name": user}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}
