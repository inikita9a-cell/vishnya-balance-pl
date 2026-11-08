"""P0-04: owned check-only revisions, durable job status and staged publication.

Reuses StageLog and the platform's existing executor; no migration/queue service.
Run.config_snapshot and all original Parquet files remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4

import yaml

from .platform_checks_adapter import freeze_checks, _normalize_check_ids
from .platform_procedures_adapter import resolve_run_config

PUBLISHED = ('checks.json', 'checks_log.json', 'summary.json', 'report.html',
             'comparison_status.json', 'checks_config_snapshot.json')
_IDENTIFIER = re.compile(r'^[A-Za-z0-9_-]+$')


class CheckJobError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _now():
    return datetime.now(timezone.utc).isoformat()


def _platform():
    # Lazy import avoids cycles with backend.runs / engine.pipeline.
    from backend import runs
    return runs


def _root(run_id):
    if not isinstance(run_id, str) or not _IDENTIFIER.fullmatch(run_id):
        raise CheckJobError('Run not found', 404)
    return Path(_platform().RUNS_DIR) / run_id


def _owned_run(db, run_id, user, *, read_only=False):
    from backend.models import Run
    _root(run_id)
    run = db.get(Run, run_id)
    from backend.auth import reports_shared
    if run is None or not user or (run.started_by != user and not (read_only and reports_shared())):
        raise CheckJobError('Run not found for current user', 404)
    return run


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _public(job):
    return {k: v for k, v in job.items() if k != 'config_snapshot'}


def _path(root, job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise CheckJobError('Check job not found', 404)
    return root / 'checks_jobs' / f'{job_id}.json'


def _release(root, job_id):
    lock = root / '.checks-rerun.lock'
    if lock.exists() and lock.read_text(encoding='ascii') == job_id:
        lock.unlink()


def queue_checks(run_id, user, *, config_id=None, checks=None, check_params=None):
    """Snapshot selected checks before returning; exclusive lock per run."""
    from backend.models import Config
    platform = _platform()
    root = _root(run_id)
    job_id = uuid4().hex
    locked = False
    with platform.SessionLocal() as db:
        run = _owned_run(db, run_id, user)
        if run.status != 'done':
            raise CheckJobError('Only a completed run may rerun checks', 409)
        if config_id is not None and checks is not None:
            raise CheckJobError('Choose config_id or checks, not both')
        if any(not (root / name).is_file() for name in (
                'comparison.parquet', 'segments.parquet', 'blocks.parquet', 'quality.parquet')):
            raise CheckJobError('Prepared run artifacts are missing', 409)
        root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(root / '.checks-rerun.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CheckJobError('A checks job is already queued/running for this run', 409) from exc
        try:
            locked = True
            with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
                stream.write(job_id)
            cfg = yaml.safe_load(run.config_snapshot) or {}
            if config_id is not None:
                source = db.get(Config, config_id)
                if source is None or source.owner != user:
                    raise CheckJobError('Config not found for current user', 404)
                selected = yaml.safe_load(source.yaml) or {}
            elif checks is not None:
                selected = {'checks': checks, 'check_params': check_params or {}}
            else:
                last = root / 'checks_config_snapshot.json'
                selected = json.loads(last.read_text(encoding='utf-8')) if last.is_file() else cfg
            # Copy only check settings from the selected config. Dataset, segments,
            # normalization and comparison always belong to the original run.
            settings = {k: deepcopy(selected[k]) for k in ('checks', 'check_params', 'overrides') if k in selected}
            if check_params is not None:
                settings['check_params'] = {**settings.get('check_params', {}), **check_params}
            if config_id is not None or checks is not None:
                settings = resolve_run_config(db, user, settings)
            settings = freeze_checks(settings)
            for key in ('checks', 'check_params', 'overrides'):
                cfg[key] = settings.get(key, {} if key != 'checks' else [])
            job = {'job_id': job_id, 'run_id': run_id, 'status': 'queued', 'progress': 0,
                   'stage': None, 'created_at': _now(), 'started_at': None, 'finished_at': None,
                   'error': None, 'counts': None, 'config_id': config_id,
                   'check_ids': _normalize_check_ids(cfg), 'config_snapshot': cfg}
            _write_json(_path(root, job_id), job)
            return _public(job)
        except Exception:
            if locked:
                _release(root, job_id)
            raise


def get_job(run_id, job_id, user):
    with _platform().SessionLocal() as db:
        _owned_run(db, run_id, user, read_only=True)
    path = _path(_root(run_id), job_id)
    if not path.is_file():
        raise CheckJobError('Check job not found', 404)
    return _public(json.loads(path.read_text(encoding='utf-8')))


def latest_job(run_id, user):
    with _platform().SessionLocal() as db:
        _owned_run(db, run_id, user, read_only=True)
    paths = list((_root(run_id) / 'checks_jobs').glob('*.json'))
    if not paths:
        return None
    jobs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    return _public(max(jobs, key=lambda job: job['created_at']))


def mark_failed(run_id, job_id, exc):
    root = _root(run_id)
    path = _path(root, job_id)
    job = json.loads(path.read_text(encoding='utf-8'))
    job.update(status='failed', error=f'{type(exc).__name__}: {exc}'[-4000:], finished_at=_now())
    try:
        _write_json(path, job)
    finally:
        _release(root, job_id)
    return _public(job)


def _publish(staged, root):
    """Rollback previous visible files if publication raises an IO exception."""
    old = {name: (root / name).read_bytes() if (root / name).is_file() else None for name in PUBLISHED}
    changed = []
    try:
        for name in PUBLISHED:
            if not (staged / name).is_file():
                raise FileNotFoundError(f'Checks job did not produce {name}')
        for name in PUBLISHED:
            os.replace(staged / name, root / name)
            changed.append(name)
    except Exception:
        for name in reversed(changed):
            path = root / name
            if old[name] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old[name])
        raise


def execute_job(run_id, job_id):
    """Worker entry. Infrastructure failures are persisted; check ERROR is data."""
    root = _root(run_id)
    path = _path(root, job_id)
    job = json.loads(path.read_text(encoding='utf-8'))
    if job['status'] != 'queued':
        raise CheckJobError('Check job has already started', 409)
    lock = root / '.checks-rerun.lock'
    if not lock.is_file() or lock.read_text(encoding='ascii') != job_id:
        raise CheckJobError('Checks job does not own the run lock', 409)
    try:
        job.update(status='running', started_at=_now(), stage='prepare', progress=5)
        _write_json(path, job)
        with tempfile.TemporaryDirectory(prefix='work_', dir=root / 'checks_jobs') as dirname:
            staged = Path(dirname) / run_id  # Preserve run ID in summary/HTML links.
            staged.mkdir()
            for original in root.glob('*.parquet'):
                shutil.copyfile(original, staged / original.name)
            status = root / 'comparison_status.json'
            if status.is_file():
                shutil.copyfile(status, staged / status.name)

            def progress(event):
                if event['status'] == 'running':
                    job['stage'] = event['step']
                    job['progress'] = {'s12_checks': 10, 's13_summary': 70, 's15_report': 85}.get(event['step'], 5)
                    _write_json(path, job)

            _platform().rerun_checks(run_id, cfg=job['config_snapshot'], run_dir=staged, on_event=progress)
            _write_json(staged / 'checks_config_snapshot.json', job['config_snapshot'])
            rows = json.loads((staged / 'checks.json').read_text(encoding='utf-8'))
            job.update(stage='publish', progress=95)
            _write_json(path, job)
            _publish(staged, root)
        job.update(status='done', progress=100, stage='done', finished_at=_now(),
                   counts={kind.lower(): sum(r['RESULT'] == kind for r in rows) for kind in ('PASS', 'FAIL', 'ERROR')})
        _write_json(path, job)
        _release(root, job_id)
        return _public(job)
    except Exception as exc:
        return mark_failed(run_id, job_id, exc)


def attach_check(db, user, procedure_id, config_id, *, check_id, params=None, label=None, entry='check'):
    """Attach/update one saved procedure; preserve the other selected checks."""
    from backend.models import Config
    config = db.get(Config, config_id)
    if config is None or config.owner != user:
        raise CheckJobError('Config not found for current user', 404)
    spec = {'id': check_id, 'procedure_id': procedure_id, 'entry': entry, 'params': params or {}}
    if label is not None:
        spec['label'] = label
    # Validate ID, owner, kind and file source without executing the script.
    freeze_checks(resolve_run_config(db, user, {'checks': [spec]}))
    cfg = yaml.safe_load(config.yaml) or {}
    selected = cfg.get('checks')
    if selected is None:
        selected = _normalize_check_ids({})
    if not isinstance(selected, list):
        raise CheckJobError('Config checks must be a list')
    output, replaced = [], False
    for item in selected:
        cid = item if isinstance(item, str) else item['id']
        if cid == check_id:
            if not replaced:
                output.append(spec)
                replaced = True
        else:
            output.append(item)
    if not replaced:
        output.append(spec)
    cfg['checks'] = output
    config.yaml = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    db.commit()
    return {'config_id': config_id, 'check_id': check_id, 'procedure_id': procedure_id}
