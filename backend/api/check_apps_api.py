"""Full-application list for one check result row.

Frontend flow:
  1. GET /api/runs/{rid}/checks -> rows with APP_IDS (may be truncated) + CNT.
  2. If len(APP_IDS) < CNT, call this endpoint to fetch the full list.

Contract:
  * If the check returned FILTERS, we replay it via MartAPI on comparison.parquet.
  * If FILTERS is absent but len(APP_IDS) == CNT, we return APP_IDS as-is.
  * Otherwise 422 with a clear message (no silent truncation).
"""
from __future__ import annotations

import json
import pathlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user, get_run_owned


router = APIRouter(prefix="/api/runs", tags=["checks"])


class CheckAppsIn(BaseModel):
    # Optional: filter by RESULT ("FAIL"/"PASS") and/or ARGUMENT (product, etc.).
    result: str | None = None
    argument: str | None = None
    limit: int = Field(5000, ge=1, le=100000)


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


@router.post("/{rid}/checks/{check_id}/apps")
def check_apps(rid: str, check_id: str, body: CheckAppsIn,
               user: str = Depends(current_user)):
    get_run_owned(rid, user)
    run_dir = pathlib.Path("runs") / rid
    rows = _load_checks(run_dir)

    # Collect the matching result rows for this check_id.
    matching = [r for r in rows
                if r.get("CHECK_ID") == check_id and _row_matches(r, body.result, body.argument)]
    if not matching:
        raise HTTPException(404, "no rows match this check and filter")

    # Full CNT across matching rows (each row may correspond to a product/segment).
    total_cnt = sum(int(r.get("CNT") or 0) for r in matching)

    # Fast path: APP_IDS already complete for all matching rows.
    if all(len(r.get("APP_IDS") or []) == int(r.get("CNT") or 0) for r in matching):
        app_ids = sorted({aid for r in matching for aid in (r.get("APP_IDS") or [])})
        return {
            "check_id": check_id,
            "total": len(app_ids),
            "declared_cnt": total_cnt,
            "truncated": False,
            "items": app_ids[: body.limit],
            "source": "APP_IDS",
        }

    # Otherwise replay via MartAPI using FILTERS (per row) and union results.
    from engine.mart_api import MartAPI  # same class checks_service uses

    mart = MartAPI.from_run(run_dir)
    collected: set[str] = set()
    used_filters = False
    for r in matching:
        filters = r.get("FILTERS")
        if filters is None:
            continue
        used_filters = True
        try:
            ids = mart.app_ids(**filters)
        except TypeError as e:
            raise HTTPException(422, f"invalid FILTERS in checks.json: {e}")
        collected.update(ids)

    if not used_filters:
        raise HTTPException(
            422,
            f"check '{check_id}' truncated APP_IDS "
            f"({len(matching[0].get('APP_IDS') or [])} of {total_cnt}) "
            f"but did not expose FILTERS; cannot expand",
        )

    items = sorted(collected)
    return {
        "check_id": check_id,
        "total": len(items),
        "declared_cnt": total_cnt,
        "truncated": False,
        "items": items[: body.limit],
        "source": "FILTERS",
    }