import pathlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user, get_procedure_owned, get_run_owned
from ..db import SessionLocal
from ..models import Procedure
from engine.sandbox import execute_user_code
from engine.mart import Mart

router = APIRouter(prefix="/api/procedures", tags=["procedures"])


class ProcIn(BaseModel):
    kind: str
    source: str = "workspace"
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
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"id": p.id}
    finally:
        db.close()


@router.post("/{pid}/try")
def try_proc(pid: int, body: TryIn, user: str = Depends(current_user)):
    # Owner процедуры и (если передан) owner прогона проверяются отдельно.
    proc = get_procedure_owned(pid, user)
    if body.run_id:
        get_run_owned(body.run_id, user)  # 404 для чужого прогона

    code = body.code or (pathlib.Path(proc.path).read_text() if proc.path else proc.code)
    if not code:
        raise HTTPException(400, "no code")

    mart = Mart(str(pathlib.Path("runs") / body.run_id)) if body.run_id else None
    ok, out = execute_user_code(code, body.entry,
                                {"app_ids": body.app_ids, "mart": mart})
    return {"ok": ok, "result": out}