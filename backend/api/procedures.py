# backend/api/procedures.py
import pathlib, yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user
from ..db import SessionLocal
from ..models import Procedure
from engine.sandbox import execute_user_code
from engine.mart import Mart

router = APIRouter(prefix="/api/procedures", tags=["procedures"])


class ProcIn(BaseModel):
    kind: str
    source: str = "workspace"  # file|workspace
    path: str | None = None
    code: str | None = None


class TryIn(BaseModel):
    run_id: str | None = None
    app_ids: list[str] = []
    code: str | None = None
    entry: str = "entry"


@router.get("")
def list_procs(user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        return [{"id": p.id, "kind": p.kind, "source": p.source, "path": p.path, "code": p.code}
                for p in db.query(Procedure).filter(Procedure.owner == user)]
    finally:
        db.close()


@router.post("")
def create_proc(body: ProcIn, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        p = Procedure(owner=user, kind=body.kind, source=body.source,
                      path=body.path, code=body.code)
        db.add(p);
        db.commit();
        db.refresh(p)
        return {"id": p.id}
    finally:
        db.close()


@router.post("/{pid}/try")
def try_proc(pid: int, body: TryIn, user: str = Depends(current_user)):
    """Выполнить процедуру на 1–3 заявках в песочнице. Для редактора."""
    db = SessionLocal()
    try:
        p = db.get(Procedure, pid)
        if not p: raise HTTPException(404)
        code = body.code or (pathlib.Path(p.path).read_text() if p.path else p.code)
        if not code: raise HTTPException(400, "no code")
        mart = Mart(str(pathlib.Path("runs") / body.run_id)) if body.run_id else None
        ok, out = execute_user_code(code, body.entry,
                                    {"app_ids": body.app_ids, "mart": mart})
        return {"ok": ok, "result": out}
    finally:
        db.close()
