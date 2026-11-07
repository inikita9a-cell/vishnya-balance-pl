"""Platform's SQLite-backed background executor for the data engine.

Public signatures used by backend/api/runs_api.py are preserved:
    start_run(config_id, user) -> run_id
    run_pipeline(run_id, cfg)
    rerun_checks(run_id)
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
from pathlib import Path
import time
import traceback
import uuid

import yaml

from .db import SessionLocal
from .models import Run, StageLog, Config
from engine.pipeline import run_pipeline as execute_pipeline
from engine.checks_runner import run_checks as execute_checks
from engine.summary import prepare_summary
from engine.report_html import write_report_html
from engine import steps as S, aggregates as A

RUNS_DIR = Path('runs')

# Code actually executed by each stage. The path-specific field rules stay in cfg.
STAGE_SOURCES = {
    's1_discover': (S.discover,),
    's2_s4_normalize': (S.load, S.flatten_pair, S.flatten, S.bucketize),
    's5_union': (S.union,),
    's6_check_keys': (S.check_keys,),
    's7_compare': (S.compare,),
    's8_quality': (S.quality,),
    's9_segments': (S.segments,),
    's10_blocks': (A.blocks,),
    's11_facts': (A.facts,),
    's12_checks': (execute_checks,),
    's13_summary': (prepare_summary,),
    's15_report': (write_report_html,),
}

STAGE_PARAMS = {
    's1_discover': ('dataset', 'pool'),
    's2_s4_normalize': ('flatten', 'xml', 'buckets', 'serialize'),
    's5_union': (), 's6_check_keys': (), 's7_compare': (),
    's8_quality': ('quality',), 's9_segments': ('segments',),
    's10_blocks': ('blocks',), 's11_facts': ('facts',),
    's12_checks': ('checks', 'check_params', 'overrides'),
    's13_summary': ('summary', 'segments'),
    's15_report': ('app_base_url',),
}


def _source_for(stage: str) -> str:
    chunks = []
    for fn in STAGE_SOURCES.get(stage, ()):
        try:
            chunks.append(inspect.getsource(fn))
        except (OSError, TypeError):
            chunks.append(f'# Source unavailable: {fn!r}')
    return '\n\n'.join(chunks)


def _parameters_for(stage: str, cfg: dict) -> str:
    keys = STAGE_PARAMS.get(stage, ())
    return json.dumps({k: cfg.get(k) for k in keys if k in cfg}, ensure_ascii=False, default=str)


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


def start_run(config_id: int, user: str) -> str:
    """Queue a run with a configuration snapshot owned by the requesting user."""
    db = SessionLocal()
    try:
        cfg = db.get(Config, config_id)
        if cfg is None or cfg.owner != user:
            raise ValueError('config not found for this user')
        run_id = uuid.uuid4().hex[:12]
        (RUNS_DIR / run_id).mkdir(parents=True, exist_ok=False)
        run = Run(id=run_id, config_id=config_id, config_snapshot=cfg.yaml,
                  started_by=user, status='queued')
        db.add(run)
        db.commit()
        return run_id
    finally:
        db.close()


class _StageJournal:
    """Sink for engine callbacks; reuses existing StageLog ORM and schema."""
    def __init__(self, db, run_id: str, author: str, cfg: dict):
        self.db = db
        self.run_id = run_id
        self.author = author
        self.cfg = cfg
        self.current: dict[str, StageLog] = {}
        self.start_times: dict[str, float] = {}
        self.active: str | None = None

    def __call__(self, event: dict):
        stage = event['step']
        status = event['status']
        if status == 'running':
            row = StageLog(run_id=self.run_id, step=stage, status='running',
                           started_by=self.author, code_snapshot=_source_for(stage),
                           params=_parameters_for(stage, self.cfg),
                           progress=int(event.get('progress') or 0),
                           rows_in=event.get('rows_in'))
            self.db.add(row)
            self.db.commit()
            self.current[stage] = row
            self.start_times[stage] = time.perf_counter()
            self.active = stage
            return
        row = self.current.get(stage)
        if row is None:
            raise RuntimeError(f'Stage {stage} emitted {status} without running event')
        if status == 'progress':
            row.progress = max(0, min(100, int(event.get('progress') or 0)))
            if 'rows_in' in event:
                row.rows_in = event['rows_in']
            if 'rows_out' in event:
                row.rows_out = event['rows_out']
            self.db.commit()
        elif status in ('done', 'failed'):
            row.status = 'done' if status == 'done' else 'failed'
            row.progress = 100 if status == 'done' else row.progress
            row.rows_in = event.get('rows_in', row.rows_in)
            row.rows_out = event.get('rows_out', row.rows_out)
            row.message = str(event.get('message') or '')[:4000]
            row.finished_at = _now()
            row.duration_ms = int((time.perf_counter() - self.start_times[stage]) * 1000)
            self.db.commit()
            if self.active == stage:
                self.active = None
        else:
            raise ValueError(f'Unknown stage status: {status}')

    def fail_active(self, exc: BaseException):
        if not self.active:
            return
        self({'step': self.active, 'status': 'failed',
              'message': ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]})


def run_pipeline(run_id: str, cfg: dict):
    """Run in a worker thread; mark done only after checks, summary and HTML."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            raise ValueError(f'Unknown run_id: {run_id}')
        run.status = 'running'
        run.error = None
        db.commit()
        journal = _StageJournal(db, run_id, run.started_by, cfg)
        try:
            result = execute_pipeline(cfg, RUNS_DIR / run_id, on_event=journal)
            run.status = 'done'
            return result
        except Exception as exc:
            journal.fail_active(exc)
            run.status = 'failed'
            run.error = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
            return None
        finally:
            run.finished_at = _now()
            db.commit()
    finally:
        db.close()


def rerun_checks(run_id: str):
    """Recompute checks, Verdict and HTML without touching comparison/aggregates."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None or run.status != 'done':
            raise ValueError('Only a completed run may rerun checks')
        cfg = yaml.safe_load(run.config_snapshot) or {}
        root = RUNS_DIR / run_id
        journal = _StageJournal(db, run_id, run.started_by, cfg)
        try:
            journal({'step': 's12_checks', 'status': 'running'})
            checks_path = Path(execute_checks({'cfg': cfg, 'run_dir': str(root)}))
            rows = json.loads(checks_path.read_text(encoding='utf-8'))
            journal({'step': 's12_checks', 'status': 'done', 'rows_out': len(rows)})
            journal({'step': 's13_summary', 'status': 'running'})
            summary = prepare_summary(root, cfg)
            journal({'step': 's13_summary', 'status': 'done', 'rows_out': summary.get('total_apps')})
            journal({'step': 's15_report', 'status': 'running'})
            output = write_report_html(root, cfg)
            journal({'step': 's15_report', 'status': 'done', 'message': str(output)})
            return str(checks_path)
        except Exception as exc:
            journal.fail_active(exc)
            # The previous run's Parquet remains intact; record rerun error in stage log.
            raise
    finally:
        db.close()
