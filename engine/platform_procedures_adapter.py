"""Tiny DB boundary for Backend 2; ownership checked before source snapshotting."""
from __future__ import annotations

from .procedure_runtime import KINDS, ProcedureError, freeze_config


def resolve_run_config(db, user, cfg):
    from backend.models import Procedure

    def resolve(procedure_id, kind):
        row = db.get(Procedure, procedure_id)
        if row is None or row.owner != user:
            raise ProcedureError(f'Procedure {procedure_id} not found for current user')
        if row.kind not in KINDS[kind]:
            raise ProcedureError(f'Procedure {procedure_id}: kind {row.kind!r} cannot run as {kind}')
        return {'source': row.source, 'path': row.path, 'code': row.code}

    return freeze_config(cfg, resolver=resolve)


def preview_procedure(db, user, procedure_id, config_id, *, app_ids=None, code=None, entry=None,
                      params_override=None):
    """Run an unsaved editor draft on at most 3 pairs; never change saved data."""
    import json
    from pathlib import Path
    import tempfile
    import pandas as pd
    import yaml
    from backend.models import Config, Procedure
    from .pipeline import run_pipeline
    from .steps import discover

    row = db.get(Procedure, procedure_id)
    config = db.get(Config, config_id)
    if row is None or row.owner != user or config is None or config.owner != user:
        raise ProcedureError('Procedure/config not found for current user')
    kind = next((kind for kind, aliases in KINDS.items() if row.kind in aliases), None)
    if kind is None:
        raise ProcedureError(f'Unsupported procedure kind: {row.kind}')
    cfg = yaml.safe_load(config.yaml) or {}
    available = {pair['APP_ID'] for pair in discover(cfg['dataset'], cfg.get('pool'))}
    ids = sorted(available)[:3] if not app_ids else app_ids
    if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(not isinstance(x, str) for x in ids):
        raise ProcedureError('Preview requires 1-3 string APP_IDs')
    if len(set(ids)) != len(ids) or not set(ids) <= available:
        raise ProcedureError('Preview APP_IDs must be unique and present in the selected dataset/pool')
    cfg['pool'] = {'mode': 'list', 'app_ids': ids}
    params = {}
    if kind == 'check':
        for check in cfg.get('checks', []):
            if isinstance(check, dict) and check.get('procedure_id') == procedure_id:
                params = check.get('params', {})
                break
    else:
        original = cfg.get('procedures', {}).get(kind, {})
        if isinstance(original, dict):
            params = original.get('params', {})
    if params_override is not None:
        params = params_override
    spec = {'source': 'workspace' if code is not None else row.source,
            'code': code if code is not None else row.code, 'path': row.path,
            'params': params, 'entry': entry or kind}
    cfg['checks'] = []  # Comparison previews never execute unrelated business checks.
    if kind == 'check':
        cfg['checks'] = [{'id': f'preview_{procedure_id}', **spec}]
    else:
        cfg.setdefault('procedures', {})[kind] = spec
    cfg = resolve_run_config(db, user, cfg)
    events = []
    with tempfile.TemporaryDirectory(prefix='spr_preview_') as dirname:
        result = run_pipeline(cfg, dirname, events.append)
        if kind == 'check':
            rows = json.loads((Path(dirname) / 'checks.json').read_text(encoding='utf-8'))
            columns = list(rows[0]) if rows else []
        else:
            filename = {'normalize': 'union', 'compare': 'comparison', 'facts': 'facts'}[kind]
            frame = pd.read_parquet(Path(dirname) / f'{filename}.parquet')
            rows = json.loads(frame.head(20).to_json(orient='records', force_ascii=False))
            columns = list(frame.columns)
    return {'kind': kind, 'app_ids': ids, 'rows': rows[:20], 'columns': columns,
            'summary': result['summary'], 'events': events}
