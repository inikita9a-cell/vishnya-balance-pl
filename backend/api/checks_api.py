import json, pathlib
from fastapi import APIRouter, Depends, HTTPException
from ..auth import current_user, get_run_readable

router = APIRouter(prefix="/api/runs", tags=["checks"])


@router.get("/{rid}/checks")
def get_checks(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    p = pathlib.Path("runs") / rid / "checks.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text(encoding="utf-8"))