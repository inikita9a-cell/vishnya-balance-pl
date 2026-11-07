"""Cookie-based session for the hackathon MVP.

WARNING: The cookie is set from a user-supplied name and is NOT a secure
authentication mechanism. Anyone who knows a name can impersonate it by
setting the same cookie. This is acceptable only inside a trusted network
behind the demo. For a public deployment, replace `current_user` with real
auth (password, OAuth, or signed JWT) and keep the rest of the code intact.
"""
from fastapi import Request, HTTPException
from .db import SessionLocal
from .models import Run, Config, Procedure

COOKIE = "spr_user"


def current_user(request: Request) -> str:
    name = request.cookies.get(COOKIE)
    if not name:
        raise HTTPException(401, "login required")
    return name


def get_run_owned(run_id: str, user: str) -> Run:
    """Fetch Run and enforce ownership. 404 (not 403) to avoid leaking existence."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run or run.started_by != user:
            raise HTTPException(404, "run not found")
        return run
    finally:
        db.close()


def get_config_owned(cid: int, user: str) -> Config:
    db = SessionLocal()
    try:
        cfg = db.get(Config, cid)
        if not cfg or cfg.owner != user:
            raise HTTPException(404, "config not found")
        return cfg
    finally:
        db.close()


def get_procedure_owned(pid: int, user: str) -> Procedure:
    db = SessionLocal()
    try:
        proc = db.get(Procedure, pid)
        if not proc or proc.owner != user:
            raise HTTPException(404, "procedure not found")
        return proc
    finally:
        db.close()