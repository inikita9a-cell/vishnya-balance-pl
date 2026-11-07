"""Compatibility bridge: platform run_checks(state) -> checks.json path.

Does not depend on or overwrite engine/mart.py, checks_runner.py, sandbox.py.
The five packaged checks run in one subprocess to keep code execution out
of the FastAPI worker. This is process separation, NOT an OS security sandbox.

Custom checks with CHECK metadata, and configured workspace/file overrides
are supported via an ephemeral check directory. These scripts still execute
with the permissions of the backend process; deploy a real sandbox for untrusted
users. A generic user script should export check(mart, params) or run(mart, params).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CHECKS = (
    'ar_drop_by_product', 'attribute_new_loss', 'external_score_drift',
    'stop_factor_disappeared', 'target_model_changed',
)


def _normalize_check_ids(config: dict) -> list[str]:
    selected = config.get('checks')
    if selected is None:
        return list(_DEFAULT_CHECKS)
    if not isinstance(selected, list):
        raise ValueError('cfg.checks must be a list of IDs or check definitions')
    ids = []
    for entry in selected:
        cid = entry if isinstance(entry, str) else entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', cid):
            raise ValueError(f'Invalid cfg.checks entry: {entry!r}')
        ids.append(cid)
    return ids


def _source_from_override(value):
    """Get Python source from a configured workspace snippet or .py file."""
    if value is None:
        return None
    if isinstance(value, dict):
        if isinstance(value.get('code'), str):
            return value['code']
        value = value.get('path') or value.get('file')
    if isinstance(value, str):
        if '\n' in value or value.lstrip().startswith(('def ', 'import ', 'from ', '#')):
            return value
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = _ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f'Configured Python check file not found: {path}')
        return path.read_text(encoding='utf-8')
    raise TypeError('Check override must be Python source or path to a .py file')


def _prepared_check_source(cid: str, code: str, label: str, entry: str = 'check') -> str:
    """Accept either the official CHECK contract or a plain check(mart,params)."""
    return (code + "\n\nif 'CHECK' not in globals():\n"
            + f'    _entry = globals().get({entry!r}) or globals().get("run")\n'
            + '    if not callable(_entry):\n'
            + '        raise ValueError("Custom check must define CHECK or check(mart, params)")\n'
            + f'    CHECK = {{"id": {cid!r}, "label": {label!r}, '
            + '"params": {}, "entrypoint": _entry}\n')


def freeze_checks(cfg: dict, checks_dir=None) -> dict:
    """Freeze selected standard, workspace, file and legacy override sources."""
    from .procedure_runtime import freeze_config, freeze_spec
    cfg = freeze_config(cfg)
    selected = _normalize_check_ids(cfg)
    entries = {c['id']: c for c in cfg.get('checks', []) if isinstance(c, dict)}
    base = Path(checks_dir or (_ROOT / 'procedures' / 'checks'))
    frozen = []
    params = dict(cfg.get('check_params') or {})
    overrides = cfg.get('overrides') or {}
    if not isinstance(overrides, dict):
        raise ValueError('cfg.overrides must be a dict')
    for cid in selected:
        spec = entries.get(cid, {})
        override = overrides.get(f'checks/{cid}')
        if override is not None:
            spec = {**spec, 'source': 'workspace', 'code': _source_from_override(override)}
            spec.pop('sha256', None)
            spec.pop('procedure_id', None)
        if not any(k in spec for k in ('code', 'path', 'file')):
            filename = base / f'check_{cid}.py'
            if not filename.is_file():
                frozen.append(spec or cid)  # Existing ERROR-row semantics for missing checks.
                continue
            spec = {**spec, 'source': 'file', 'path': str(filename)}
        spec = freeze_spec(spec, 'check')
        spec['id'] = cid
        frozen.append(spec)
        params[cid] = {**spec['params'], **params.get(cid, {})}
    cfg['checks'] = frozen
    cfg['check_params'] = params
    # The original override has been resolved into the check source above.
    cfg['overrides'] = {k: v for k, v in overrides.items() if not k.startswith('checks/')}
    return cfg


def checks_snapshot_event(cfg: dict) -> dict:
    sources, specs = [], []
    for spec in cfg.get('checks', []):
        if not isinstance(spec, dict) or 'code' not in spec:
            continue
        cid = spec['id']
        sources.append(f'# ---- check: {cid} ----\n' + _prepared_check_source(
            cid, spec['code'], spec.get('label', cid), spec.get('entry', 'check')))
        specs.append({k: v for k, v in spec.items() if k != 'code'})
    return {'code_snapshot': '\n\n'.join(sources),
            'procedure': {'kind': 'checks', 'selected': specs}}


def _stage_checks(cfg: dict, selected: list[str], base: Path, dest: Path) -> None:
    """Stage selected checks without changing the platform's working files."""
    overrides = cfg.get('overrides') or {}
    if not isinstance(overrides, dict):
        raise ValueError('cfg.overrides must be a dict')
    entry_by_id = {item['id']: item for item in (cfg.get('checks') or [])
                   if isinstance(item, dict) and isinstance(item.get('id'), str)}
    dest.mkdir(parents=True, exist_ok=True)
    for cid in selected:
        entry = entry_by_id.get(cid, {})
        override = overrides.get(f'checks/{cid}')
        if override is None and ('code' in entry or 'path' in entry or 'file' in entry):
            override = entry
        source = _source_from_override(override)
        target = dest / f'check_{cid}.py'
        if source is None:
            original = base / target.name
            if original.is_file():
                shutil.copyfile(original, target)
            # A missing check will produce an ERROR row in checks_service.
        else:
            target.write_text(_prepared_check_source(cid, source, entry.get('label', cid),
                                                     entry.get('entry', 'check')),
                              encoding='utf-8')


def run_checks(state: dict) -> str:
    """Return a checks.json path, preserving the platform function contract.

    state = {"cfg": saved_run_config, "run_dir": "runs/<run_id>"}.
    Raises on infrastructure failures; per-check Python failures become ERROR
    rows inside checks.json via checks_service.
    """
    cfg = state['cfg']
    if not isinstance(cfg, dict):
        raise TypeError('state.cfg must be a dict')
    run_dir = Path(state['run_dir']).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f'Run directory not found: {run_dir}')
    checks_dir = Path(state.get('checks_dir') or (_ROOT / 'procedures' / 'checks')).resolve()
    cfg = freeze_checks(cfg, checks_dir)
    selected = _normalize_check_ids(cfg)
    snapshot = {**cfg, 'checks': selected}
    timeout = float(state.get('checks_timeout', 120))
    if timeout <= 0:
        raise ValueError('checks_timeout must be positive')
    with tempfile.TemporaryDirectory(prefix='spr_checks_') as td:
        conf_path = Path(td) / 'checks_config.json'
        staged_dir = Path(td) / 'checks'
        _stage_checks(cfg, selected, checks_dir, staged_dir)
        conf_path.write_text(json.dumps(snapshot, ensure_ascii=False, default=str), encoding='utf-8')
        command = [sys.executable, '-m', 'engine.run_checks', '--run', str(run_dir),
                   '--config', str(conf_path), '--checks-dir', str(staged_dir)]
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(
            filter(None, [str(_ROOT), environment.get('PYTHONPATH')]))
        try:
            completed = subprocess.run(
                command, cwd=_ROOT, env=environment, capture_output=True,
                text=True, encoding='utf-8', errors='replace', timeout=timeout,
                check=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f'Checks subprocess exceeded {timeout}s') from exc
        if completed.returncode:
            raise RuntimeError('Checks subprocess failed: ' + completed.stderr[-4000:])
    report = run_dir / 'checks.json'
    if not report.is_file():
        raise RuntimeError(f'Checks subprocess completed but did not write {report}')
    return str(report)
