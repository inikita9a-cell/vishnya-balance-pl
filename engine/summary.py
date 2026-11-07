"""s13: аналитическая сводка для экрана Verdict из готовых артефактов.

Никаких путей в исходном JSON СПР здесь нет. Конкретное значение одобрения
передаётся конфигурацией segments.approve_value.

Публичный интерфейс:
    build_summary(segments, comparison, blocks, quality, checks, cfg, run_id)
    prepare_summary(run_dir, cfg) -> dict    # сохраняет summary.json и статус

Не изменяет Parquet, не запускает пользовательский код или исходную обработку.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pandas as pd


SCHEMA_VERSION = 1
SEGMENT_REQUIRED = (
    'APP_ID', 'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_COMPARABLE',
    'DECISION_CHANGED', 'COMPARISON_COMPLETE', 'HAS_DIFF', 'N_DIFFS',
    'QUALITY_ISSUE', 'CAUSE', 'CAUSE_DETAIL', 'REASON_BEFORE', 'REASON_AFTER',
)
COMPARISON_REQUIRED = ('APP_ID', 'PATH', 'DIFF_FLAG', 'CHANGE_TYPE')
BLOCK_REQUIRED = ('BLOCK', 'LEVEL', 'APPS_TOTAL', 'APPS_CHANGED', 'SHARE', 'ROWS_CHANGED')
CHANGE_TYPES = ('VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST')
CAUSES = ('NONE', 'LOGIC', 'INPUT_DATA', 'BOTH')


def _require(df: pd.DataFrame, columns, label: str):
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f'{label} must be a DataFrame')
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f'{label} missing columns: {missing}')


def _string(value, empty='∅') -> str:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return empty
    return str(value)


def _top_n(cfg: dict) -> int:
    n = (cfg.get('summary') or {}).get('top_n', 20)
    if type(n) is not int or not 1 <= n <= 100:
        raise ValueError('summary.top_n must be an integer from 1 through 100')
    return n


def _metric_ratio(part: int, total: int) -> float | None:
    return round(part / total, 6) if total else None


def _matrix(frame: pd.DataFrame, before_col: str, after_col: str,
            *, missing='∅') -> list[dict]:
    if frame.empty:
        return []
    pairs = pd.DataFrame({
        'BEFORE': frame[before_col].map(lambda x: _string(x, missing)),
        'AFTER': frame[after_col].map(lambda x: _string(x, missing)),
    })
    grouped = (pairs.groupby(['BEFORE', 'AFTER'], sort=True, dropna=False)
               .size().rename('CNT').reset_index())
    return [dict(before=str(r.BEFORE), after=str(r.AFTER),
                 count=int(r.CNT), changed=(r.BEFORE != r.AFTER))
            for r in grouped.itertuples(index=False)]


def _counts(series: pd.Series, priority: tuple[str, ...] = ()) -> dict[str, int]:
    values = series.map(lambda x: _string(x, 'UNKNOWN')).value_counts()
    output = {name: int(values.get(name, 0)) for name in priority}
    output.update({str(k): int(v) for k, v in sorted(values.items()) if k not in output})
    return output


def _changed_paths(comparison: pd.DataFrame, top_n: int) -> list[dict]:
    changed = comparison.loc[comparison['DIFF_FLAG'].eq(1)]
    if changed.empty:
        return []
    counts = (changed.groupby('PATH', sort=True, dropna=False)
              .agg(apps_changed=('APP_ID', 'nunique'), rows_changed=('APP_ID', 'size'))
              .reset_index())
    counts['PATH'] = counts['PATH'].map(lambda x: _string(x, 'UNKNOWN'))
    counts = counts.sort_values(['apps_changed', 'rows_changed', 'PATH'],
                                ascending=[False, False, True], kind='stable').head(top_n)
    return [dict(path=r.PATH, apps_changed=int(r.apps_changed),
                 rows_changed=int(r.rows_changed)) for r in counts.itertuples(index=False)]


def _changed_blocks(blocks: pd.DataFrame | None, top_n: int) -> list[dict]:
    if blocks is None or blocks.empty:
        return []
    _require(blocks, BLOCK_REQUIRED, 'blocks')
    ranks = blocks.loc[blocks['APPS_CHANGED'].gt(0)].sort_values(
        ['APPS_CHANGED', 'BLOCK'], ascending=[False, True], kind='stable').head(top_n)
    return [dict(block=_string(r.BLOCK), level=int(r.LEVEL),
                 apps_total=int(r.APPS_TOTAL), apps_changed=int(r.APPS_CHANGED),
                 share=round(float(r.SHARE), 6), rows_changed=int(r.ROWS_CHANGED))
            for r in ranks.itertuples(index=False)]


def _change_types(comparison: pd.DataFrame) -> list[dict]:
    changed = comparison.loc[comparison['DIFF_FLAG'].eq(1)]
    result = []
    for name in CHANGE_TYPES:
        subset = changed.loc[changed['CHANGE_TYPE'].eq(name)]
        result.append({'change_type': name, 'rows_changed': int(len(subset)),
                       'apps_changed': int(subset['APP_ID'].nunique())})
    others = sorted(set(changed['CHANGE_TYPE'].dropna().astype(str)) - set(CHANGE_TYPES))
    for name in others:
        subset = changed.loc[changed['CHANGE_TYPE'].eq(name)]
        result.append({'change_type': name, 'rows_changed': int(len(subset)),
                       'apps_changed': int(subset['APP_ID'].nunique())})
    return result


def _checks_summary(checks: list[dict] | None) -> dict:
    if checks is None:
        return {'status': 'NOT_RUN', 'rows': 0, 'pass': 0, 'fail': 0, 'error': 0,
                'checks_selected': 0, 'by_check': []}
    if not isinstance(checks, list) or any(not isinstance(item, dict) for item in checks):
        raise ValueError('checks.json must be a JSON array of objects')
    invalid = [row.get('RESULT') for row in checks if row.get('RESULT') not in ('PASS', 'FAIL', 'ERROR')]
    if invalid:
        raise ValueError(f'Unexpected checks.RESULT values: {invalid!r}')
    counts = {kind.lower(): sum(row.get('RESULT') == kind for row in checks)
              for kind in ('PASS', 'FAIL', 'ERROR')}
    groups = {}
    for row in checks:
        cid = _string(row.get('CHECK_ID') or row.get('LABEL'), 'UNKNOWN')
        g = groups.setdefault(cid, {'check_id': cid, 'label': _string(row.get('LABEL'), cid),
                                    'rows': 0, 'pass': 0, 'fail': 0, 'error': 0})
        g['rows'] += 1
        status = str(row.get('RESULT', '')).lower()
        if status in ('pass', 'fail', 'error'):
            g[status] += 1
    return {'status': 'COMPLETE', 'rows': len(checks), **counts,
            'checks_selected': len(groups), 'by_check': sorted(groups.values(), key=lambda x: x['check_id'])}


def _quality_summary(quality: pd.DataFrame | None, segments: pd.DataFrame) -> dict:
    issue_apps = int(segments['QUALITY_ISSUE'].eq(1).sum())
    if quality is None:
        return {'status': 'NOT_AVAILABLE', 'issues': None, 'apps_affected': issue_apps, 'by_issue': {}}
    _require(quality, ['APP_ID', 'ISSUE'], 'quality')
    return {'status': 'AVAILABLE', 'issues': int(len(quality)),
            'apps_affected': issue_apps,
            'by_issue': _counts(quality['ISSUE'])}


def _verdict(apps_with_diff: int, decision_changes: int, incomplete: int,
             quality_issues: int, checks_summary: dict, total_apps: int) -> dict:
    """Сигнал для просмотра аналитиком, НЕ разрешение на релиз стратегии."""
    codes = []
    if incomplete or not total_apps:
        codes.append('DATA_INCOMPLETE')
    if quality_issues:
        codes.append('QUALITY_ISSUES')
    if checks_summary['error']:
        codes.append('CHECK_EXECUTION_ERRORS')
    if checks_summary['status'] == 'NOT_RUN':
        codes.append('CHECKS_NOT_RUN')
    if checks_summary['fail']:
        codes.append('BUSINESS_CHECKS_FAILED')
    if decision_changes:
        codes.append('DECISIONS_CHANGED')
    if apps_with_diff:
        codes.append('ATTRIBUTES_CHANGED')
    if incomplete or not total_apps or checks_summary['error']:
        status = 'INCOMPLETE'
    elif apps_with_diff or checks_summary['fail'] or quality_issues:
        status = 'REVIEW_REQUIRED'
    elif checks_summary['status'] == 'NOT_RUN':
        status = 'CHECKS_PENDING'
    else:
        status = 'NO_CHANGES_OBSERVED'
    return {'status': status, 'reason_codes': codes,
            'disclaimer': 'Информационная сводка; не является решением о выкладке стратегии.'}


def build_summary(segments: pd.DataFrame, comparison: pd.DataFrame,
                  blocks: pd.DataFrame | None = None,
                  quality: pd.DataFrame | None = None,
                  checks: list[dict] | None = None,
                  cfg: dict | None = None, run_id: str | None = None) -> dict:
    """Строит JSON-ready dict из готовых DataFrame, не изменяя источники.

    Все показатели решений/approval rate считаются ТОЛЬКО по заявкам с двумя
    корректно прочитанными ответами (DECISION_COMPARABLE & COMPARISON_COMPLETE).
    Число наблюдаемых различий включает даже неполные заявки, но рядом выдаётся
    количество неполных сравнений, чтобы не трактовать их как достоверное SAME.
    """
    cfg = cfg or {}
    top_n = _top_n(cfg)
    _require(segments, SEGMENT_REQUIRED, 'segments')
    _require(comparison, COMPARISON_REQUIRED, 'comparison')
    if segments['APP_ID'].duplicated().any():
        raise ValueError('segments must have unique APP_ID')
    unknown_apps = comparison.loc[~comparison['APP_ID'].isin(segments['APP_ID']), 'APP_ID']
    if not unknown_apps.empty:
        raise ValueError(f'comparison APP_ID not in segments: {unknown_apps.iloc[0]}')

    valid_mask = segments['DECISION_COMPARABLE'].eq(1) & segments['COMPARISON_COMPLETE'].eq(1)
    valid = segments.loc[valid_mask]
    total = int(len(segments))
    valid_count = int(len(valid))
    incomplete = int(segments['COMPARISON_COMPLETE'].ne(1).sum())
    diff_apps = int(segments['HAS_DIFF'].eq(1).sum())
    decision_changed = int(valid['DECISION_CHANGED'].eq(1).sum())
    quality_apps = int(segments['QUALITY_ISSUE'].eq(1).sum())
    approve = (cfg.get('segments') or {}).get('approve_value')
    approvals = {'approve_value': approve, 'denominator': valid_count,
                 'before_count': None, 'after_count': None,
                 'before_rate': None, 'after_rate': None, 'delta_pp': None}
    if approve is not None:
        before_count = int(valid['DECISION_BEFORE'].eq(approve).sum())
        after_count = int(valid['DECISION_AFTER'].eq(approve).sum())
        before_rate = _metric_ratio(before_count, valid_count)
        after_rate = _metric_ratio(after_count, valid_count)
        approvals.update(before_count=before_count, after_count=after_count,
                         before_rate=before_rate, after_rate=after_rate,
                         delta_pp=(round((after_count - before_count) * 100 / valid_count, 4)
                                   if valid_count else None))

    checks_info = _checks_summary(checks)
    total_diff_rows = int(comparison['DIFF_FLAG'].eq(1).sum())
    summary = {
        'schema_version': SCHEMA_VERSION, 'run_id': run_id,
        'total_apps': total,
        'apps_with_diff': diff_apps,
        'apps_decision_changed': decision_changed,
        'apps_decision_comparable': valid_count,
        'apps_comparison_incomplete': incomplete,
        'apps_with_quality_issues': quality_apps,
        'comparison_rows': int(len(comparison)),
        'diff_rows': total_diff_rows,
        'apps_diff_but_decision_same': int((valid['HAS_DIFF'].eq(1) & valid['DECISION_CHANGED'].eq(0)).sum()),
        'approval_rates': approvals,
        'decision_transitions': _matrix(valid, 'DECISION_BEFORE', 'DECISION_AFTER'),
        'reason_transitions': _matrix(valid, 'REASON_BEFORE', 'REASON_AFTER'),
        'decision_distribution': {
            'before': _counts(valid['DECISION_BEFORE']),
            'after': _counts(valid['DECISION_AFTER']),
        },
        'cause_counts': _counts(segments['CAUSE'], CAUSES),
        'cause_detail_counts': _counts(segments['CAUSE_DETAIL']),
        'change_types': _change_types(comparison),
        'top_changed_paths': _changed_paths(comparison, top_n),
        'top_changed_blocks': _changed_blocks(blocks, top_n),
        'quality': _quality_summary(quality, segments),
        'checks': checks_info,
        'verdict': _verdict(diff_apps, decision_changed, incomplete, quality_apps, checks_info, total),
    }
    # Guard against invalid numbers in JSON (NaN, Infinity).
    json.dumps(summary, ensure_ascii=False, allow_nan=False)
    return summary


def _atomic_json(path: Path, data: dict):
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{uuid4().hex}.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def prepare_summary(run_dir: str | Path, cfg: dict | None = None) -> dict:
    """Построить/обновить summary.json поверх готовых Parquet и checks.json.

    Можно вызывать после каждого rerun checks. Исходные артефакты остаются нетронуты.
    Статус в comparison_status.json расширяется ключами summary_* без смены
    основного stage: stage остаётся фактическим последним этапом обработки.
    """
    root = Path(run_dir)
    required = ['segments.parquet', 'comparison.parquet', 'blocks.parquet', 'quality.parquet']
    for filename in required:
        if not (root / filename).is_file():
            raise FileNotFoundError(f'Summary requires {root / filename}')
    started = perf_counter()
    segments = pd.read_parquet(root / 'segments.parquet')
    comparison = pd.read_parquet(root / 'comparison.parquet',
                                  columns=list(COMPARISON_REQUIRED))
    blocks = pd.read_parquet(root / 'blocks.parquet')
    quality = pd.read_parquet(root / 'quality.parquet')
    checks_file = root / 'checks.json'
    checks = (json.loads(checks_file.read_text(encoding='utf-8'))
              if checks_file.is_file() else None)
    result = build_summary(segments, comparison, blocks, quality, checks,
                           cfg=cfg, run_id=root.name)
    elapsed = round(perf_counter() - started, 3)
    result['summary_seconds'] = elapsed
    _atomic_json(root / 'summary.json', result)
    status_file = root / 'comparison_status.json'
    status = (json.loads(status_file.read_text(encoding='utf-8'))
              if status_file.is_file() else {})
    previous = float(status.get('summary_seconds', 0) or 0)
    status['summary_seconds'] = elapsed
    status['summary_ready'] = True
    status['summary_checks_status'] = result['checks']['status']
    if 'duration_seconds' in status:
        status['duration_seconds'] = round(float(status['duration_seconds']) - previous + elapsed, 3)
    _atomic_json(status_file, status)
    return result
