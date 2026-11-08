"""Full-application list for one check result row."""
from __future__ import annotations

import json
import pathlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user, get_run_owned


router = APIRouter(prefix="/api/runs", tags=["checks"])


class CheckAppsIn(BaseModel):
    result: str | None = None       # e.g. "FAIL"
    argument: str | None = None     # e.g. "PRODUCT_X"
    limit: int = Field(1000, ge=1, le=100000)
    offset: int = Field(0, ge=0)


def _load_checks(run_dir: pathlib.Path) -> list[dict]:
    p = run_dir / "checks.json"
    if not p.is_file():
        raise HTTPException(404, "checks.json not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _row_matches(row: dict, result: str | None, argument: str | None) -> bool:
    if result is not None and str(row.get("RESULT")) != result:
        return False
    if argument is not None and str(row.get("ARGUMENT")) != argument:
        return False
    return True


def _expand_row(mart, row: dict) -> set[str]:
    """Return full set of APP_IDs for a single check row.

    Raises ValueError when the row is truncated but cannot be expanded, or
    when the recovered count doesn't match CNT.
    """
    declared_cnt = int(row.get("CNT") or 0)
    app_ids = list(row.get("APP_IDS") or [])

    # Fast path: already complete.
    if len(app_ids) == declared_cnt:
        return set(app_ids)

    filters = row.get("FILTERS")
    if filters is None:
        raise ValueError(
            f"row truncated ({len(app_ids)} of {declared_cnt}) "
            f"and has no FILTERS"
        )
    if not isinstance(filters, dict):
        raise ValueError("FILTERS must be a dict")
    try:
        recovered = list(mart.app_ids(**filters))
    except TypeError as e:
        raise ValueError(f"invalid FILTERS: {e}")

    unique = set(recovered)
    if len(unique) != declared_cnt:
        raise ValueError(
            f"FILTERS recovered {len(unique)} unique APP_IDs, "
            f"but CNT={declared_cnt} (check must return matching filters)"
        )
    return unique


@router.post("/{rid}/checks/{check_id}/apps")
def check_apps(rid: str, check_id: str, body: CheckAppsIn,
               user: str = Depends(current_user)):
    get_run_owned(rid, user)
    run_dir = pathlib.Path("runs") / rid
    rows = _load_checks(run_dir)

    matching = [r for r in rows
                if r.get("CHECK_ID") == check_id
                and _row_matches(r, body.result, body.argument)]
    if not matching:
        raise HTTPException(404, "no rows match this check and filter")

    from engine.mart_api import MartAPI
    mart = MartAPI.from_run(run_dir)

    collected: set[str] = set()
    for row in matching:
        try:
            collected |= _expand_row(mart, row)
        except ValueError as e:
            raise HTTPException(422, f"{check_id}/{row.get('ARGUMENT')}: {e}")

    total = len(collected)
    ordered = sorted(collected)
    page = ordered[body.offset: body.offset + body.limit]
    return {
        "check_id": check_id,
        "total": total,
        "declared_cnt": sum(int(r.get("CNT") or 0) for r in matching),
        "truncated": len(page) < total,
        "items": page,
        "limit": body.limit,
        "offset": body.offset,
        "source": "MIXED",  # rows may be APP_IDS or FILTERS
    }