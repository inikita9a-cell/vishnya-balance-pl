"""s12: run unmodified CHECK scripts against the indexed MartAPI.

This module executes trusted local Python scripts in-process. The platform
backend must provide process isolation for untrusted code from the UI.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import time
import traceback
from uuid import uuid4

import pandas as pd

from .mart_api import MartAPI

DEFAULT_CHECKS_DIR = Path(__file__).resolve().parents[1] / 'procedures' / 'checks'
_CHECK_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')
_REQUIRED_RESULT = {'LABEL', 'SOURCE', 'ARGUMENT', 'CNT', 'TOTAL', 'METRIC',
                    'APP_IDS', 'RESULT', 'CONFIDENCE'}


def _json_scalar(value):
    import numpy as np
    if isinstance(value, np.generic):
        return value.item()
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def load_check(check_id: str, checks_dir: str | Path = DEFAULT_CHECKS_DIR):
    """Load CHECK by ID; prevent directory traversal from user-provided IDs."""
    if not isinstance(check_id, str) or not _CHECK_ID.fullmatch(check_id):
        raise ValueError(f'Invalid check ID: {check_id!r}')
    if os.getenv("APP_ENV", "development") != "development":
        from .platform_checks_adapter import _DEFAULT_CHECKS
        if Path(checks_dir).resolve() != DEFAULT_CHECKS_DIR.resolve() or check_id not in _DEFAULT_CHECKS:
            raise ValueError("Only packaged checks allowed")
    path = Path(checks_dir) / f'check_{check_id}.py'
    if not path.is_file():
        raise FileNotFoundError(f'Check not found: {path}')
    spec = importlib.util.spec_from_file_location(f'_user_check_{uuid4().hex}', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load check module: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check = getattr(module, 'CHECK', None)
    if not isinstance(check, dict) or check.get('id') != check_id:
        raise ValueError(f'{path}: CHECK.id must match file ID {check_id!r}')
    if not isinstance(check.get('label'), str) or not callable(check.get('entrypoint')):
        raise ValueError(f'{path}: CHECK must define label and callable entrypoint')
    if not isinstance(check.get('params', {}), dict):
        raise ValueError(f'{path}: CHECK.params must be a dict')
    return check


def _normalize_row(row: dict, check_id: str, label: str, elapsed: float) -> dict:
    if not isinstance(row, dict):
        raise ValueError('Check result must be a list of dict rows')
    missing = _REQUIRED_RESULT.difference(row)
    if missing:
        raise ValueError(f'Missing check result fields: {sorted(missing)}')
    values = {k: _json_scalar(v) for k, v in row.items()}
    if values['RESULT'] not in ('PASS', 'FAIL'):
        raise ValueError('CHECK.RESULT must be PASS or FAIL')
    if values['CONFIDENCE'] not in ('HIGH', 'LOW'):
        raise ValueError('CHECK.CONFIDENCE must be HIGH or LOW')
    if values['SOURCE'] not in ('BEFORE', 'AFTER'):
        raise ValueError('CHECK.SOURCE must be BEFORE or AFTER')
    for k in ('CNT', 'TOTAL'):
        if isinstance(values[k], bool) or not isinstance(values[k], int) or values[k] < 0:
            raise ValueError(f'CHECK.{k} must be a nonnegative integer')
    if values['CNT'] > values['TOTAL']:
        raise ValueError('CHECK.CNT cannot exceed TOTAL')
    if not isinstance(values['APP_IDS'], list) or not all(isinstance(x, str) for x in values['APP_IDS']):
        raise ValueError('CHECK.APP_IDS must be a list of strings')
    if not isinstance(values['LABEL'], str):
        raise ValueError('CHECK.LABEL must be a string')
    values['CHECK_ID'] = check_id
    values['DURATION_MS'] = round(elapsed * 1000, 3)

    # Optional: filters that reproduce this row's CNT from MartAPI.
    # Any check may return FILTERS: {column: value | [values]}.
    filters = values.get('FILTERS')
    if filters is not None and not isinstance(filters, dict):
        raise ValueError('CHECK.FILTERS must be a dict or omitted')
    values['FILTERS'] = filters  # None if omitted

    return values


def _error_row(check_id: str, label: str, exc: Exception, elapsed: float) -> dict:
    return dict(CHECK_ID=check_id, LABEL=label, SOURCE='AFTER', ARGUMENT='',
                CNT=0, TOTAL=0, METRIC=None, APP_IDS=[], FILTERS=None,
                RESULT='ERROR', CONFIDENCE='LOW',
                DURATION_MS=round(elapsed * 1000, 3),
                ERROR=f'{type(exc).__name__}: {exc}',
                TRACEBACK=traceback.format_exc(limit=12))


def run_checks(mart: MartAPI, check_ids: list[str], *, checks_dir=DEFAULT_CHECKS_DIR,
               params_by_id: dict | None = None, on_event=None) -> list[dict]:
    """Run chosen user checks in order. One broken check never stops the others.

    on_event receives {check_id,status,duration_ms,message}. The row list is
    directly usable as the unified check report in the frontend.
    """
    params_by_id = params_by_id or {}
    result = []
    for check_id in check_ids:
        started = time.perf_counter()
        label = check_id
        if on_event:
            on_event(dict(check_id=check_id, status='running'))
        try:
            check = load_check(check_id, checks_dir)
            label = check['label']
            params = {**check.get('params', {}), **params_by_id.get(check_id, {})}
            output = check['entrypoint'](mart, params)
            if not isinstance(output, list):
                raise ValueError('Check entrypoint must return list[dict]')
            elapsed = time.perf_counter() - started
            # Validate whole check atomically; avoid publishing half its rows.
            lines = [_normalize_row(x, check_id, label, elapsed) for x in output]
            result.extend(lines)
            if on_event:
                on_event(dict(check_id=check_id, status='done', rows=len(lines),
                              duration_ms=round(elapsed * 1000, 3)))
        except Exception as exc:
            elapsed = time.perf_counter() - started
            result.append(_error_row(str(check_id), label, exc, elapsed))
            if on_event:
                on_event(dict(check_id=check_id, status='error', message=str(exc),
                              duration_ms=round(elapsed * 1000, 3)))
    return result


def _atomic_json(path: Path, obj) -> None:
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{uuid4().hex}.tmp')
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def prepare_checks(run_dir, cfg: dict | None = None, *, checks_dir=DEFAULT_CHECKS_DIR,
                   check_ids: list[str] | None = None, on_event=None) -> dict:
    """Run s12 on prepared comparison and segments without rereading JSON files.

    Repeated calls replace only the check report and check-related status.
    Existing s1-s11 parquet files are untouched. Supports a newly added check.
    """
    out = Path(run_dir)
    for name in ('comparison.parquet', 'segments.parquet'):
        if not (out / name).is_file():
            raise FileNotFoundError(f'Checks need {out / name}')
    cfg = cfg or {}
    selected = list(check_ids if check_ids is not None else cfg.get('checks', []))
    params = cfg.get('check_params', {}) or {}
    started = time.perf_counter()
    mart = MartAPI.from_run(out)
    events = []

    def event(payload):
        events.append(payload)
        if on_event:
            on_event(payload)

    results = run_checks(mart, selected, checks_dir=checks_dir,
                         params_by_id=params, on_event=event)
    elapsed = round(time.perf_counter() - started, 3)
    totals = {k.lower(): sum(r['RESULT'] == k for r in results)
              for k in ('PASS', 'FAIL', 'ERROR')}
    report = out / 'checks.json'
    # JSON array = unified report, directly suitable for GET /runs/{id}/checks.
    _atomic_json(report, results)
    _atomic_json(out / 'checks_log.json', events)
    status_path = out / 'comparison_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.is_file() else {}
    # A rerun must not add the previous checks duration again.
    previous = float(status.get('checks_seconds', 0))
    if 'duration_seconds' in status:
        status['duration_seconds'] = round(float(status['duration_seconds']) - previous + elapsed, 3)
    status.update(stage='checks', checks_selected=len(selected), checks_rows=len(results),
                  checks_pass=totals['pass'], checks_fail=totals['fail'],
                  checks_error=totals['error'], checks_seconds=elapsed)
    _atomic_json(status_path, status)
    return status
