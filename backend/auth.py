import os
import re
from pathlib import Path
from urllib.parse import unquote
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
UNICODE_COOKIE = "spr_user_utf8"

def staging():
    return os.getenv("APP_ENV", "development") != "development"

def reports_shared():
    """Explicit team report visibility; configuration ownership is unaffected."""
    return os.getenv('REPORT_ACCESS', 'private') == 'shared'

def report_read_request(request):
    if request.method in ('GET', 'HEAD'):
        return True
    # These POST operations query existing artifacts and do not change a run.
    return request.method == 'POST' and re.fullmatch(
        r'/api/runs/[A-Za-z0-9_-]+/(?:pivot|drilldown|sankey|explorer/(?:query|apps)|checks/[^/]+/apps)',
        request.url.path) is not None

def contained(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(400, "Path outside allowed storage")
    return path

def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise HTTPException(400, "Invalid identifier")
    return value

def run_directory(rid):
    identifier(rid)
    root = contained("runs", Path("runs") / rid)
    # Reject symlink escapes including artifacts accessed by analytics helpers.
    if root.exists():
        for item in root.rglob("*"):
            contained(root, item)
    return root

def owned_run(rid, user):
    identifier(rid)
    with SessionLocal() as db:
        row = db.get(Run, rid)
        if row is None or row.started_by != user:
            raise HTTPException(404, "Run not found")
    run_directory(rid)

def current_user(request: Request) -> str:
    if staging():
        name = getattr(request.state, "verified_user", None)
    else:
        # Retain existing ASCII sessions; Unicode names use an ASCII-safe cookie.
        name = request.cookies.get(COOKIE)
        if not name and request.cookies.get(UNICODE_COOKIE):
            try:
                name = unquote(request.cookies[UNICODE_COOKIE], encoding='utf-8', errors='strict')
            except UnicodeError:
                raise HTTPException(401, "login required")
    if not name:
        raise HTTPException(401, "login required")
    if "rid" in request.path_params:
        if reports_shared() and report_read_request(request):
            get_run_readable(request.path_params['rid'], name)
            run_directory(request.path_params['rid'])
        else:
            owned_run(request.path_params["rid"], name)
    return name


def get_run_readable(run_id: str, user: str) -> Run:
    """Authenticated report access under the selected team/private policy."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not user or not run or (run.started_by != user and not reports_shared()):
            raise HTTPException(404, 'run not found')
        return run
    finally:
        db.close()


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
