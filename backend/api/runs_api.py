# backend/api/runs_api.py
import json, threading, yaml, pathlib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from ..auth import current_user
from ..db import SessionLocal
from ..models import Run, StageLog, Config
from ..runs import start_run, run_pipeline, rerun_checks
from engine.check_jobs import queue_checks, execute_job, get_job, latest_job, mark_failed, CheckJobError

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunIn(BaseModel):
    config_id: int


@router.post("")
def create_run(body: RunIn, user: str = Depends(current_user)):
    rid = start_run(body.config_id, user)
    db = SessionLocal()
    try:
        run = db.get(Run, rid)
        cfg = yaml.safe_load(run.config_snapshot)
        cfg.setdefault("_meta", {})
        # сохраняем автора и время в state при необходимости
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
    db = SessionLocal()
    try:
        return [{"id": r.id, "status": r.status, "started_by": r.started_by,
                 "created_at": r.created_at, "finished_at": r.finished_at,
                 "config_id": r.config_id}
                for r in db.query(Run).order_by(Run.created_at.desc()).all()]
    finally:
        db.close()


@router.get("/{rid}")
def get_run(rid: str, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        r = db.get(Run, rid)
        if not r: raise HTTPException(404)
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
    db = SessionLocal()
    try:
        l = db.query(StageLog).filter_by(run_id=rid, step=step).order_by(StageLog.id.desc()).first()
        if not l: raise HTTPException(404)
        return {"step": l.step, "status": l.status, "duration_ms": l.duration_ms,
                "rows_in": l.rows_in, "rows_out": l.rows_out,
                "params": l.params, "message": l.message,
                "code": l.code_snapshot, "started_by": l.started_by}
    finally:
        db.close()


class ChecksRerunIn(BaseModel):
    config_id: int | None = None
    checks: list[str | dict] | None = None
    check_params: dict | None = None


@router.post("/{rid}/checks/rerun")
def rerun(rid: str, body: ChecksRerunIn | None = None, user: str = Depends(current_user)):
    try:
        job = queue_checks(rid, user, **(body.model_dump() if body else {}))
    except CheckJobError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        threading.Thread(target=execute_job, args=(rid, job['job_id']), daemon=True).start()
    except Exception as exc:
        mark_failed(rid, job['job_id'], exc)
        raise HTTPException(500, 'Could not start checks worker') from exc
    return {"ok": True, **job}


@router.get("/{rid}/checks/jobs/{job_id}")
def check_job_status(rid: str, job_id: str, user: str = Depends(current_user)):
    try:
        return get_job(rid, job_id, user)
    except CheckJobError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/{rid}/checks/status")
def latest_check_job(rid: str, user: str = Depends(current_user)):
    try:
        return {"job": latest_job(rid, user)}
    except CheckJobError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/{rid}/report.html")
def report(rid: str, user: str = Depends(current_user)):
    p = pathlib.Path("runs") / rid / "report.html"
    if not p.exists(): raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(p, media_type="text/html")
