"""Selected Python procedures, immutable sources and validated stage contracts.

No database dependency. The platform resolves owned Procedure IDs before queueing.
Custom calculations run in a timed subprocess (trusted code, NOT a security sandbox).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGES = {'normalize': 's2_s4_normalize', 'compare': 's7_compare', 'facts': 's11_facts'}
KINDS = {'normalize': {'normalize', 'flatten', 'normalization'},
         'compare': {'compare', 'comparison'}, 'facts': {'facts', 'aggregate', 'aggregation'},
         'check': {'check', 'checks'}}


class ProcedureError(ValueError):
    """A selected procedure failed to execute or broke its output contract."""


def _object(value, name):
    if not isinstance(value, dict):
        raise ProcedureError(f'{name} must be a mapping')
    return value


def freeze_spec(spec, kind, resolver=None):
    """Read a file/DB source once, without executing any user code."""
    if type(spec) is int:
        spec = {'procedure_id': spec}
    spec = deepcopy(_object(spec, f'procedures.{kind}'))
    pid = spec.get('procedure_id')
    # Never trust client-supplied code for a database ID at the platform boundary.
    if pid is not None and resolver is not None:
        if type(pid) is not int or pid < 1:
            raise ProcedureError('procedure_id must be a positive integer')
        record = resolver(pid, kind)
        spec = {**spec, **record, 'procedure_id': pid}
        spec.pop('sha256', None)
    elif pid is not None and not spec.get('sha256'):
        raise ProcedureError(f'Procedure {pid} must be resolved by the platform before execution')
    source = spec.get('source', 'workspace')
    if source not in ('workspace', 'file'):
        raise ProcedureError(f'{kind}.source must be workspace or file')
    code = spec.get('code')
    if source == 'file' and not spec.get('sha256'):
        path = spec.get('path') or spec.get('file')
        if not isinstance(path, str) or not path:
            raise ProcedureError(f'{kind}: file source needs path')
        filename = Path(path).expanduser()
        filename = filename if filename.is_absolute() else ROOT / filename
        if filename.suffix.lower() != '.py':
            raise ProcedureError(f'{kind}: expected a .py file')
        code = filename.read_text(encoding='utf-8-sig')
    if not isinstance(code, str) or not code.strip():
        raise ProcedureError(f'{kind}: nonempty Python code is required')
    digest = hashlib.sha256(code.encode('utf-8')).hexdigest()
    if spec.get('sha256') and spec['sha256'] != digest:
        raise ProcedureError(f'{kind}: source snapshot hash mismatch')
    entry = spec.get('entry', kind if kind != 'check' else 'check')
    if not isinstance(entry, str) or not entry.isidentifier():
        raise ProcedureError(f'{kind}.entry must be a Python identifier')
    params = _object(spec.get('params', {}), f'{kind}.params')
    timeout = spec.get('timeout_seconds', 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ProcedureError(f'{kind}.timeout_seconds must be positive and finite')
    return {**spec, 'source': source, 'code': code, 'sha256': digest,
            'entry': entry, 'params': params, 'timeout_seconds': timeout}


def freeze_config(cfg, resolver=None):
    """Copy config and freeze selected sources; legacy configs remain valid."""
    cfg = deepcopy(_object(cfg, 'cfg'))
    procedures = _object(cfg.get('procedures', {}), 'cfg.procedures')
    unknown = set(procedures) - set(STAGES)
    if unknown:
        raise ProcedureError(f'Unknown procedure kinds: {sorted(unknown)}; checks go in cfg.checks')
    if procedures:
        cfg['procedures'] = {kind: freeze_spec(spec, kind, resolver)
                             for kind, spec in procedures.items()}
    if 'checks' in cfg:
        if not isinstance(cfg['checks'], list):
            raise ProcedureError('cfg.checks must be a list')
        selected, ids = [], set()
        for check in cfg['checks']:
            cid = check if isinstance(check, str) else _object(check, 'check').get('id')
            if not isinstance(cid, str) or not cid:
                raise ProcedureError('check.id must be a nonempty string')
            if cid in ids:
                raise ProcedureError(f'Duplicate check ID: {cid}')
            ids.add(cid)
            if isinstance(check, dict) and any(k in check for k in ('procedure_id', 'code', 'path', 'file')):
                check = freeze_spec(check, 'check', resolver)
            selected.append(check)
        cfg['checks'] = selected
    return cfg


def snapshot_event(cfg, stage):
    """Metadata attached to running events; journal can persist it verbatim."""
    for kind, step in STAGES.items():
        if step == stage and kind in cfg.get('procedures', {}):
            spec = cfg['procedures'][kind]
            metadata = {k: v for k, v in spec.items() if k != 'code'}
            return {'code_snapshot': spec['code'], 'procedure': {'kind': kind, **metadata}}
    return {}


def _need(frame, columns, label):
    import pandas as pd
    if not isinstance(frame, pd.DataFrame):
        raise ProcedureError(f'{label}: expected pandas.DataFrame')
    if not frame.columns.is_unique:
        raise ProcedureError(f'{label}: duplicate column names')
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ProcedureError(f'{label}: missing columns {missing}')


def validate_normalized(rows, app_id, source):
    """No fabricated IDs/slices, null keys, duplicate keys or object leaves."""
    import pandas as pd
    from .steps import NORMAL_COLUMNS, ROW_KEY
    if isinstance(rows, pd.DataFrame):
        rows = rows.to_dict('records')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProcedureError('normalize: expected two lists of row dictionaries or DataFrames')
    seen = set()
    for row in rows:
        missing = set(NORMAL_COLUMNS) - set(row)
        if missing:
            raise ProcedureError(f'normalize: missing columns {sorted(missing)}')
        if row['APP_ID'] != str(app_id) or row['SOURCE'] != source:
            raise ProcedureError('normalize: APP_ID/SOURCE must match the input pair')
        if any(not isinstance(row[k], str) for k in NORMAL_COLUMNS if k != 'DEPTH'):
            raise ProcedureError('normalize: all columns except DEPTH must contain strings (null value = "NULL")')
        if not row['PATH'] or type(row['DEPTH']) is not int or row['DEPTH'] < 1:
            raise ProcedureError('normalize: nonempty PATH and positive integer DEPTH required')
        key = tuple(row[k] for k in ROW_KEY)
        if key in seen:
            raise ProcedureError(f'normalize: duplicate row key {key}')
        seen.add(key)
    return rows


def validate_comparison(frame, united):
    import pandas as pd
    from .steps import ROW_KEY
    cols = ['APP_ID', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY', 'KEY', 'PATH', 'DEPTH',
            'VALUE_BEFORE', 'VALUE_AFTER', 'ADJUSTED_BEFORE', 'ADJUSTED_AFTER', 'DIFF_FLAG', 'CHANGE_TYPE']
    _need(frame, cols, 'compare')
    for col in ('DEPTH', 'DIFF_FLAG'):
        if not pd.api.types.is_integer_dtype(frame[col].dtype):
            raise ProcedureError(f'compare: {col} must have integer dtype')
    if frame[ROW_KEY].isna().any().any() or frame.duplicated(ROW_KEY).any():
        raise ProcedureError('compare: null/duplicate row key')
    if not frame['APP_ID'].isin(united['APP_ID']).all():
        raise ProcedureError('compare: APP_ID not present in input')
    keys = set(map(tuple, united[ROW_KEY].itertuples(index=False, name=None)))
    if any(key not in keys for key in frame[ROW_KEY].itertuples(index=False, name=None)):
        raise ProcedureError('compare: row key not present in input')
    if not frame['CHANGE_TYPE'].isin(['SAME', 'VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']).all():
        raise ProcedureError('compare: invalid CHANGE_TYPE')
    if not frame['DIFF_FLAG'].isin([0, 1]).all() or not frame['DIFF_FLAG'].eq(frame['CHANGE_TYPE'].ne('SAME').astype(int)).all():
        raise ProcedureError('compare: DIFF_FLAG must agree with CHANGE_TYPE')
    return frame


def validate_facts(output, comparison, cfg):
    import pandas as pd
    from .aggregates import _fact_dimensions
    if not isinstance(output, (tuple, list)) or len(output) != 2:
        raise ProcedureError('facts: expected (facts_df, fact_apps_df)')
    facts, members = output
    _need(facts, ['FACT_ID', *_fact_dimensions(cfg)[0], 'CNT'], 'facts')
    _need(members, ['FACT_ID', 'APP_ID'], 'fact_apps')
    for frame, columns in ((facts, ['FACT_ID', 'CNT', 'DIFF_FLAG']), (members, ['FACT_ID'])):
        for col in columns:
            if not pd.api.types.is_integer_dtype(frame[col].dtype) or frame[col].isna().any():
                raise ProcedureError(f'facts: {col} must have non-null integer dtype')
    if facts['FACT_ID'].isna().any() or facts['FACT_ID'].duplicated().any():
        raise ProcedureError('facts: null/duplicate FACT_ID')
    if members[['FACT_ID', 'APP_ID']].isna().any().any() or members.duplicated(['FACT_ID', 'APP_ID']).any():
        raise ProcedureError('facts: null/duplicate membership')
    if not members['APP_ID'].isin(comparison['APP_ID']).all():
        raise ProcedureError('facts: membership contains unknown APP_ID')
    if set(members['FACT_ID']) != set(facts['FACT_ID']):
        raise ProcedureError('facts: every FACT_ID needs memberships and vice versa')
    counts = members.groupby('FACT_ID')['APP_ID'].nunique()
    expected = facts['FACT_ID'].map(counts)
    if not facts['CNT'].eq(expected).all():
        raise ProcedureError('facts: CNT must equal distinct membership APP_ID count')
    if not facts['SOURCE'].isin(['BEFORE (MASTER)', 'AFTER (BETA)']).all():
        raise ProcedureError('facts: invalid SOURCE')
    if not facts['CHANGE_TYPE'].isin(['SAME', 'VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']).all():
        raise ProcedureError('facts: invalid CHANGE_TYPE')
    if not facts['DIFF_FLAG'].eq(facts['CHANGE_TYPE'].ne('SAME').astype(int)).all():
        raise ProcedureError('facts: DIFF_FLAG must agree with CHANGE_TYPE')
    return facts, members


def execute(kind, cfg, **payload):
    """One subprocess per selected stage, including the whole normalization batch."""
    if os.getenv('APP_ENV', 'development') != 'development':
        raise ProcedureError('Custom Python is disabled on staging')
    spec = cfg['procedures'][kind]
    with tempfile.TemporaryDirectory(prefix='spr_procedure_') as dirname:
        request, response = Path(dirname) / 'request.pkl', Path(dirname) / 'response.pkl'
        request.write_bytes(pickle.dumps({'kind': kind, 'spec': spec, 'cfg': cfg, 'payload': payload}))
        environment = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
                       'PYTHONPATH': os.pathsep.join(filter(None, [str(ROOT), os.getenv('PYTHONPATH')]))}
        try:
            result = subprocess.run([sys.executable, '-m', 'engine.procedure_worker', str(request), str(response)],
                                    cwd=ROOT, env=environment, capture_output=True,
                                    timeout=spec['timeout_seconds'])
        except subprocess.TimeoutExpired as exc:
            raise ProcedureError(f'{kind}: timeout after {spec["timeout_seconds"]}s') from exc
        if result.returncode or not response.is_file():
            error = result.stderr.decode('utf-8', errors='replace')[-4000:]
            raise ProcedureError(f'{kind}: Python execution failed: {error or result.returncode}')
        return pickle.loads(response.read_bytes())


def write_snapshot(cfg, out):
    """The run's frozen source/parameters, useful also for CLI runs."""
    cfg = freeze_config(cfg)
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    data = {'procedures': cfg.get('procedures', {}), 'checks': cfg.get('checks', []),
            'check_params': cfg.get('check_params', {}), 'overrides': cfg.get('overrides', {})}
    path = root / 'procedures_snapshot.json'
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if path.exists() and json.loads(path.read_text(encoding='utf-8')) != data:
        raise ProcedureError('Existing procedure snapshot differs; use a new run directory')
    path.write_text(content, encoding='utf-8')
    return cfg
