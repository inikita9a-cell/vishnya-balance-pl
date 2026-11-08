"""Retrieve applications for EXACTLY ONE row of the unified checks report.

ROW_ID resolves ambiguous check rows (same CHECK_ID/RESULT/ARGUMENT, different
SOURCE or APP_IDS). Historic checks.json files gain a deterministic ID on read.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user, get_run_readable
from engine.check_row_ids import assign_check_row_ids

router = APIRouter(prefix='/api/runs', tags=['checks'])


class CheckAppsIn(BaseModel):
    row_id: str | None = None       # ROW_ID obtained from GET .../checks
    result: str | None = None       # deprecated compatibility for unambiguous rows
    argument: str | None = None
    limit: int = Field(1000, ge=1, le=100000)
    offset: int = Field(0, ge=0)


def _load_checks(run_dir: Path) -> list[dict]:
    file = run_dir / 'checks.json'
    if not file.is_file():
        raise HTTPException(404, 'checks.json not found')
    try:
        rows = json.loads(file.read_text(encoding='utf-8'))
        return assign_check_row_ids(rows)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f'Invalid checks.json: {exc}') from exc


def _expand_row(row: dict, run_dir: Path) -> tuple[set[str], str]:
    """Expand one row or fail instead of showing an incorrect partial list."""
    declared_cnt = row.get('CNT')
    if isinstance(declared_cnt, bool) or not isinstance(declared_cnt, int) or declared_cnt < 0:
        raise ValueError('CNT must be a nonnegative integer')
    app_ids = row.get('APP_IDS')
    if not isinstance(app_ids, list) or not all(isinstance(x, str) for x in app_ids):
        raise ValueError('APP_IDS must be a list of strings')
    unique = set(app_ids)
    if len(unique) != len(app_ids):
        raise ValueError('APP_IDS contains duplicate IDs; cannot match distinct CNT')
    if len(unique) > declared_cnt:
        raise ValueError(f'APP_IDS contains {len(unique)} IDs, but CNT={declared_cnt}')
    if len(unique) == declared_cnt:
        return unique, 'APP_IDS'

    filters = row.get('FILTERS')
    if filters is None:
        raise ValueError(f'row truncated ({len(unique)} of {declared_cnt}) and has no FILTERS')
    if not isinstance(filters, dict):
        raise ValueError('FILTERS must be a dict')
    filters = dict(filters)
    if 'APP_ID' in filters and 'app_ids' not in filters:
        filters['app_ids'] = filters.pop('APP_ID')
    from engine.mart_api import MartAPI
    mart = MartAPI.from_run(run_dir)
    try:
        recovered = list(mart.app_ids(**filters))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'invalid FILTERS: {exc}') from exc
    recovered_unique = set(recovered)
    if len(recovered_unique) != declared_cnt:
        raise ValueError(f'FILTERS recovered {len(recovered_unique)} unique APP_IDs, '
                         f'but CNT={declared_cnt} (filters must describe this exact row)')
    if not unique.issubset(recovered_unique):
        raise ValueError('FILTERS result does not include the APP_IDS examples')
    return recovered_unique, 'FILTERS'


@router.post('/{rid}/checks/{check_id}/apps')
def check_apps(rid: str, check_id: str, body: CheckAppsIn,
               user: str = Depends(current_user)):
    get_run_readable(rid, user)
    run_dir = Path('runs') / rid
    rows = _load_checks(run_dir)
    matches = [row for row in rows if row.get('CHECK_ID') == check_id
               and (body.row_id is None or row.get('ROW_ID') == body.row_id)
               and (body.result is None or row.get('RESULT') == body.result)
               and (body.argument is None or str(row.get('ARGUMENT')) == body.argument)]
    if not matches:
        raise HTTPException(404, 'check result row not found; reload checks')
    if len(matches) != 1:
        raise HTTPException(409, 'ambiguous check rows; pass the ROW_ID from GET /checks')
    row = matches[0]
    try:
        unique, source = _expand_row(row, run_dir)
    except ValueError as exc:
        raise HTTPException(422, f"{check_id}/{row['ROW_ID']}: {exc}") from exc
    ordered = sorted(unique)
    page = ordered[body.offset:body.offset + body.limit]
    return {
        'check_id': check_id,
        'row_id': row['ROW_ID'],
        'total': len(ordered),
        'declared_cnt': row['CNT'],
        'truncated': len(page) < len(ordered),
        'has_more': body.offset + len(page) < len(ordered),
        'items': page,
        'limit': body.limit,
        'offset': body.offset,
        'source': source,
    }
