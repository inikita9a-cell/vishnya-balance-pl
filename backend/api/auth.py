# backend/api/auth.py
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from pydantic import BaseModel
from urllib.parse import quote
from ..auth import current_user, COOKIE, UNICODE_COOKIE
from ..db import get_db, SessionLocal
from ..models import User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    name: str


@router.post("/login")
def login(body: LoginIn, response: Response, request: Request):
    from ..auth import staging
    if staging():
        return {"name": request.state.verified_user}
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
    if name.isascii():
        response.delete_cookie(UNICODE_COOKIE)
        response.set_cookie(COOKIE, name, httponly=True, samesite="lax")
    else:
        response.delete_cookie(COOKIE)
        response.set_cookie(UNICODE_COOKIE, quote(name, safe=''), httponly=True, samesite="lax")
    return {"name": name}


@router.get("/me")
def me(user: str = Depends(current_user)):
    from ..auth import staging
    return {"name": user, **({"auth_mode": "basic"} if staging() else {})}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    response.delete_cookie(UNICODE_COOKIE)
    return {"ok": True}
