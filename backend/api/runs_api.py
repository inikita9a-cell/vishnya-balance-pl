import json, threading, yaml, pathlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user, get_run_owned
from ..db import SessionLocal
from ..models import Run, StageLog
from ..runs import start_run, run_pipeline, rerun_checks

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunIn(BaseModel):
    config_id: int


@router.post("")
def create_run(body: RunIn, user: str = Depends(current_user)):
    try:
        rid = start_run(body.config_id, user)
    except ValueError as e:
        raise HTTPException(404, str(e))
    db = SessionLocal()
    try:
        run = db.get(Run, rid)
        cfg = yaml.safe_load(run.config_snapshot) or {}
    finally:
        db.close()
    threading.Thread(target=_bg, args=(rid, cfg), daemon=True).start()
    return {"run_id": rid}


def _bg(rid, cfg):
    try:
        run_pipeline(rid, cfg)
    except Exception:
        pass


@router.get("")
def list_runs(user: str = Depends(current_user)):
    """Only runs started by the current user. Admins see all via /admin (later)."""
    db = SessionLocal()
    try:
        return [{"id": r.id, "status": r.status, "started_by": r.started_by,
                 "created_at": r.created_at, "finished_at": r.finished_at,
                 "config_id": r.config_id}
                for r in db.query(Run).filter(Run.started_by == user)
                          .order_by(Run.created_at.desc()).all()]
    finally:
        db.close()


@router.get("/{rid}")
def get_run(rid: str, user: str = Depends(current_user)):
    get_run_owned(rid, user)  # 404 для чужого
    db = SessionLocal()
    try:
        r = db.get(Run, rid)
        logs = db.query(StageLog).filter(StageLog.run_id == rid).order_by(StageLog.id).all()
        return {"id": r.id, "status": r.status, "error": r.error,
                "started_by": r.started_by, "created_at": r.created_at,
                "finished_at": r.finished_at,
                "steps": [{"step": l.step, "status": l.status, "duration_ms": l.duration_ms,
                           "progress": l.progress, "rows_in": l.rows_in, "rows_out": l.rows_out,
                           "message": (l.message or "")[:500], "started_at": l.started_at}
                          for l in logs]}
    finally:
        db.close()


@router.get("/{rid}/steps/{step}")
def get_step(rid: str, step: str, user: str = Depends(current_user)):
    get_run_owned(rid, user)
    db = SessionLocal()
    try:
        l = db.query(StageLog).filter_by(run_id=rid, step=step).order_by(StageLog.id.desc()).first()
        if not l:
            raise HTTPException(404)
        return {"step": l.step, "status": l.status, "duration_ms": l.duration_ms,
                "rows_in": l.rows_in, "rows_out": l.rows_out,
                "params": l.params, "message": l.message,
                "code": l.code_snapshot, "started_by": l.started_by}
    finally:
        db.close()


@router.post("/{rid}/checks/rerun")
def rerun(rid: str, user: str = Depends(current_user)):
    get_run_owned(rid, user)
    threading.Thread(target=rerun_checks, args=(rid, user), daemon=True).start()
    return {"ok": True}


@router.get("/{rid}/report.html")
def report(rid: str, user: str = Depends(current_user)):
    get_run_owned(rid, user)
    p = pathlib.Path("runs") / rid / "report.html"
    if not p.exists():
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(p, media_type="text/html")