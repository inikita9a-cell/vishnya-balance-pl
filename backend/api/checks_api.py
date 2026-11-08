"""Unified, user-accessible checks report (including stable row IDs)."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user, get_run_readable
from engine.check_row_ids import assign_check_row_ids

router = APIRouter(prefix='/api/runs', tags=['checks'])


@router.get('/{rid}/checks')
def get_checks(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    p = Path('runs') / rid / 'checks.json'
    if not p.is_file():
        raise HTTPException(404, 'checks.json not found')
    try:
        return assign_check_row_ids(json.loads(p.read_text(encoding='utf-8')))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, f'Invalid checks.json: {exc}') from exc
