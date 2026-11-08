"""P0-11 owns a separate router; P0-07 data/check endpoints stay untouched."""
from fastapi import APIRouter, Depends, HTTPException, Query
from ..auth import current_user, get_run_readable
from .. import runs
from engine.explanation import explain_application
from duckdb import Error as DuckDBError

router = APIRouter(prefix='/api/runs', tags=['explanation'])


@router.get('/{rid}/apps/{app_id}/explanation')
def app_explanation(rid: str, app_id: str, limit: int = Query(200, ge=1, le=1000),
                    offset: int = Query(0, ge=0), path: str | None = None,
                    array_key: str | None = None, user: str = Depends(current_user)):
    run = get_run_readable(rid, user)
    if run.status != 'done':
        raise HTTPException(409, 'Run is not complete')
    try:
        return explain_application(runs.RUNS_DIR / rid, app_id, limit=limit, offset=offset,
                                   path=path, array_key=array_key)
    except KeyError as exc:
        raise HTTPException(404, 'Application not found in this run') from exc
    except (FileNotFoundError, ValueError, DuckDBError) as exc:
        raise HTTPException(409, str(exc)) from exc
