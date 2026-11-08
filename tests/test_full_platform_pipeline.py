"""Stage 7 integration contracts: engine, SQLite journal, HTML and REST output.

These unit tests avoid big JSON datasets; one real Parquet integration test is
conditionally enabled if pyarrow + xmltodict are installed.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine import pipeline as engine_pipeline
from engine.report_html import write_report_html
from backend import runs as platform_runs
from backend.db import Base
from backend.models import Run, Config, StageLog


REQUIRED = ('union.parquet', 'comparison.parquet', 'segments.parquet',
            'blocks.parquet', 'facts.parquet', 'fact_apps.parquet')


def _fake_engine_parts(monkeypatch, output, *, report_error=False):
    def compare(cfg, run_dir, on_event=None):
        for phase in ('s1_discover', 's2_s4_normalize', 's5_union', 's6_check_keys',
                      's7_compare', 's8_quality', 's9_segments', 's10_blocks', 's11_facts'):
            on_event and on_event({'step': phase, 'status': 'running'})
            on_event and on_event({'step': phase, 'status': 'done', 'progress': 100})
        for name in REQUIRED:
            (Path(run_dir) / name).write_bytes(b'fixture')
        return {'apps_with_diff': 1}

    def checks(state):
        p = Path(state['run_dir']) / 'checks.json'
        p.write_text('[]', encoding='utf-8')
        return str(p)

    def summary(run_dir, cfg):
        doc = {'total_apps': 1, 'verdict': {'status': 'REVIEW_REQUIRED'}}
        (Path(run_dir) / 'summary.json').write_text(json.dumps(doc), encoding='utf-8')
        return doc

    def report(run_dir, cfg):
        if report_error:
            raise RuntimeError('report failed')
        p = Path(run_dir) / 'report.html'
        p.write_text('<html>ok</html>', encoding='utf-8')
        return p

    monkeypatch.setattr(engine_pipeline, 'prepare_comparison', compare)
    monkeypatch.setattr(engine_pipeline, 'run_checks', checks)
    monkeypatch.setattr(engine_pipeline, 'prepare_summary', summary)
    monkeypatch.setattr(engine_pipeline, 'write_report_html', report)


def test_engine_pipeline_writes_all_artifacts_and_calls_stages(monkeypatch, tmp_path):
    _fake_engine_parts(monkeypatch, tmp_path)
    events = []
    result = engine_pipeline.run_pipeline({}, tmp_path, on_event=events.append)
    assert result['status'] == 'done'
    assert all((tmp_path / name).is_file() for name in REQUIRED)
    assert all((tmp_path / name).is_file() for name in ('checks.json', 'summary.json', 'report.html'))
    assert [e['step'] for e in events if e['status'] == 'done'][-3:] == [
        's12_checks', 's13_summary', 's15_report']


def test_engine_pipeline_does_not_mark_report_done_on_failure(monkeypatch, tmp_path):
    _fake_engine_parts(monkeypatch, tmp_path, report_error=True)
    events = []
    with pytest.raises(RuntimeError, match='report failed'):
        engine_pipeline.run_pipeline({}, tmp_path, on_event=events.append)
    assert not any(e['step'] == 's15_report' and e['status'] == 'done' for e in events)


def _sqlite(monkeypatch, tmp_path):
    eng = create_engine(f'sqlite:///{tmp_path / "app.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    monkeypatch.setattr(platform_runs, 'SessionLocal', factory)
    from backend import auth as backend_auth
    monkeypatch.setattr(backend_auth, 'SessionLocal', factory)
    monkeypatch.setattr(platform_runs, 'RUNS_DIR', tmp_path / 'runs')
    (tmp_path / 'dataset/before').mkdir(parents=True)
    (tmp_path / 'dataset/after').mkdir(parents=True)
    cfg = {'dataset': {'path': str(tmp_path / 'dataset'), 'before_dir': 'before', 'after_dir': 'after'}, 'flatten': {}}
    with factory() as db:
        db.add(Config(owner='demo', name='test', yaml=json.dumps(cfg)))
        db.commit()
        config_id = db.query(Config).first().id
    return factory, config_id


def test_platform_logs_stages_as_done_and_saves_code(monkeypatch, tmp_path):
    factory, config_id = _sqlite(monkeypatch, tmp_path)
    rid = platform_runs.start_run(config_id, 'demo')

    def execute(cfg, run_dir, on_event):
        for name in ('s1_discover', 's2_s4_normalize', 's12_checks', 's13_summary', 's15_report'):
            on_event({'step': name, 'status': 'running'})
            if name == 's2_s4_normalize':
                on_event({'step': name, 'status': 'progress', 'progress': 35, 'rows_in': 1})
            on_event({'step': name, 'status': 'done', 'rows_out': 2})
        return {'ok': True}

    monkeypatch.setattr(platform_runs, 'execute_pipeline', execute)
    result = platform_runs.run_pipeline(rid, {'dataset': {'path': 'fixture'}})
    assert result == {'ok': True}
    with factory() as db:
        run = db.get(Run, rid)
        assert run.status == 'done' and run.finished_at is not None
        steps = db.query(StageLog).filter_by(run_id=rid).order_by(StageLog.id).all()
        assert [s.step for s in steps] == ['s1_discover', 's2_s4_normalize',
                                            's12_checks', 's13_summary', 's15_report']
        assert all(s.status == 'done' and s.progress == 100 for s in steps)
        assert steps[1].rows_in == 1 and steps[1].rows_out == 2
        assert 'def discover' in steps[0].code_snapshot
        assert steps[0].started_by == 'demo'


def test_platform_marks_failed_run_and_last_stage(monkeypatch, tmp_path):
    factory, cid = _sqlite(monkeypatch, tmp_path)
    rid = platform_runs.start_run(cid, 'demo')

    def fail(cfg, run_dir, on_event):
        on_event({'step': 's7_compare', 'status': 'running'})
        raise ValueError('broken compare')

    monkeypatch.setattr(platform_runs, 'execute_pipeline', fail)
    assert platform_runs.run_pipeline(rid, {}) is None
    with factory() as db:
        assert db.get(Run, rid).status == 'failed'
        assert 'broken compare' in db.get(Run, rid).error
        stage = db.query(StageLog).filter_by(run_id=rid).one()
        assert stage.status == 'failed' and 'broken compare' in stage.message


def test_platform_reruns_checks_summary_and_html_only(monkeypatch, tmp_path):
    factory, cid = _sqlite(monkeypatch, tmp_path)
    rid = platform_runs.start_run(cid, 'demo')
    with factory() as db:
        db.get(Run, rid).status = 'done'
        db.commit()
    root = tmp_path / 'runs' / rid
    for name in REQUIRED:
        (root / name).write_bytes(b'original')

    def checks(state):
        p = root / 'checks.json'
        p.write_text('[]')
        return str(p)

    def summary(path, cfg):
        (root / 'summary.json').write_text('{}')
        return {'total_apps': 2}

    def report(path, cfg):
        p = root / 'report.html'
        p.write_text('new report')
        return p

    monkeypatch.setattr(platform_runs, 'execute_checks', checks)
    monkeypatch.setattr(platform_runs, 'prepare_summary', summary)
    monkeypatch.setattr(platform_runs, 'write_report_html', report)
    assert platform_runs.rerun_checks(rid) == str(root / 'checks.json')
    assert all((root / name).read_bytes() == b'original' for name in REQUIRED)
    with factory() as db:
        steps = db.query(StageLog).filter_by(run_id=rid).order_by(StageLog.id).all()
        assert [s.step for s in steps] == ['s12_checks', 's13_summary', 's15_report']
        assert all(s.status == 'done' for s in steps)
        assert db.get(Run, rid).status == 'done'


def test_report_html_standalone_and_escapes_data(tmp_path):
    doc = {'total_apps': 3, 'apps_with_diff': 1, 'apps_decision_changed': 1,
           'approval_rates': {'before_rate': 0.5, 'after_rate': 0.4},
           'verdict': {'status': 'REVIEW_REQUIRED'},
           'checks': {'pass': 0, 'fail': 1, 'error': 0},
           'decision_transitions': [{'before': 'A', 'after': 'B', 'count': 1}],
           'top_changed_paths': [{'path': '<script>alert(1)</script>', 'apps_changed': 1, 'rows_changed': 1}]}
    (tmp_path / 'summary.json').write_text(json.dumps(doc))
    (tmp_path / 'checks.json').write_text(json.dumps([
        {'CHECK_ID': 'a', 'LABEL': '<img src=x onerror=alert(1)>', 'SOURCE': 'AFTER',
         'APP_IDS': ['APP A&1'], 'CNT': 1, 'TOTAL': 3, 'RESULT': 'FAIL'}]))
    path = write_report_html(tmp_path, {'app_base_url': 'https://example.org'})
    html = path.read_text(encoding='utf-8')
    assert 'https://example.org/?page=report' in html
    assert '/api/runs/' not in html
    assert 'APP%20A%261' in html
    assert '<script>alert(1)</script>' not in html
    assert '<img src=x onerror=' not in html
    assert '<style>' in html and '<link rel="stylesheet"' not in html
    assert 'REVIEW_REQUIRED' in html


def test_summary_route_returns_json_not_string(monkeypatch, tmp_path):
    import sys
    # backend.duck imports optional DuckDB, which is not needed for summary route.
    if 'backend.api.data_api' not in sys.modules:
        monkeypatch.setitem(sys.modules, 'backend.duck', SimpleNamespace())
    from backend.api import data_api
    (tmp_path / 'summary.json').write_text('{"total_apps": 2}', encoding='utf-8')
    monkeypatch.setattr(data_api, '_dir', lambda rid: tmp_path)
    monkeypatch.setattr(data_api, 'get_run_readable', lambda rid, user: None)  # This unit checks JSON serialization only.
    result = data_api.summary('unit-run', user='demo')
    assert result == {'total_apps': 2}


def test_stage_integration_small_real_data(tmp_path):
    """Smoke test of actual Parquet flow when optional data libs are available."""
    pytest.importorskip('pyarrow')
    pytest.importorskip('xmltodict')
    import yaml
    cfg = yaml.safe_load((Path(__file__).parents[1] / 'configs/default_spr.yaml').read_text())
    dataset = tmp_path / 'dataset'
    before = dataset / 'RESULTS/BEFORE_MASTER'
    after = dataset / 'RESULTS/AFTER_BETA'
    before.mkdir(parents=True)
    after.mkdir(parents=True)
    fixture = Path(__file__).parent / 'fixtures'
    (before / '1001.json').write_bytes((fixture / '01_response_BEFORE_MASTER_app1001.json').read_bytes())
    (after / '1001.json').write_bytes((fixture / '02_response_AFTER_BETA_app1001.json').read_bytes())
    cfg['dataset']['path'] = str(dataset)
    cfg['quality']['reason_rules'] = []
    cfg['checks'] = []  # tests plumbing; official checks are verified in test_mart_checks
    events = []
    result = engine_pipeline.run_pipeline(cfg, tmp_path / 'run', on_event=events.append)
    assert result['summary']['total_apps'] == 1
    assert (tmp_path / 'run' / 'report.html').exists()
    assert any(e['step'] == 's2_s4_normalize' and e['status'] == 'done' for e in events)


def test_actual_engine_logic_end_to_end_without_native_parquet(monkeypatch, tmp_path):
    """Exercise real normalize/compare/aggregates/summary/HTML on source JSON.

    A temporary pickle backend replaces Parquet only in this isolated test,
    since the five official checks (and real Parquet IO) are tested separately.
    """
    import shutil
    import pandas as pd
    import yaml

    fixture = Path(__file__).parent / 'fixtures'
    dataset = tmp_path / 'dataset'
    before = dataset / 'RESULTS' / 'BEFORE_MASTER'
    after = dataset / 'RESULTS' / 'AFTER_BETA'
    before.mkdir(parents=True)
    after.mkdir(parents=True)
    shutil.copyfile(fixture / '01_response_BEFORE_MASTER_app1001.json', before / '1001.json')
    shutil.copyfile(fixture / '02_response_AFTER_BETA_app1001.json', after / '1001.json')
    cfg = yaml.safe_load((Path(__file__).parents[1] / 'configs/default_spr.yaml').read_text())
    cfg['dataset']['path'] = str(dataset)
    cfg['checks'] = []
    cfg['quality']['reason_rules'] = []

    def fake_to_parquet(self, path, **kwargs):
        return self.to_pickle(path)

    def fake_read_parquet(path, columns=None, **kwargs):
        df = pd.read_pickle(path)
        return df[list(columns)] if columns is not None else df

    def fake_checks(state):
        p = Path(state['run_dir']) / 'checks.json'
        p.write_text('[]', encoding='utf-8')
        return str(p)

    monkeypatch.setattr(pd.DataFrame, 'to_parquet', fake_to_parquet)
    monkeypatch.setattr(pd, 'read_parquet', fake_read_parquet)
    monkeypatch.setattr(engine_pipeline, 'run_checks', fake_checks)
    events = []
    result = engine_pipeline.run_pipeline(cfg, tmp_path / 'run', events.append)
    assert result['summary']['total_apps'] == 1
    assert result['summary']['apps_with_diff'] == 1
    assert result['comparison_status']['comparison_rows'] > 0
    assert all((tmp_path / 'run' / name).exists() for name in REQUIRED)
    assert (tmp_path / 'run' / 'report.html').exists()
    assert len([e for e in events if e['status'] == 'done']) == 12


def test_real_fastapi_routes_with_sqlite_orchestrator(monkeypatch, tmp_path):
    """POST run -> GET status, summary, checks and report via real FastAPI routes."""
    import sys
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.auth import current_user
    if 'backend.api.data_api' not in sys.modules:
        monkeypatch.setitem(sys.modules, 'backend.duck', SimpleNamespace())
    from backend.api import runs_api, data_api, checks_api

    _fake_engine_parts(monkeypatch, tmp_path)
    factory, cid = _sqlite(monkeypatch, tmp_path)
    from backend import security_config
    monkeypatch.setattr(security_config, 'SessionLocal', factory)
    monkeypatch.setattr(runs_api, 'SessionLocal', factory)
    monkeypatch.setattr(runs_api, 'start_run', platform_runs.start_run)
    monkeypatch.setattr(runs_api, 'run_pipeline', platform_runs.run_pipeline)
    monkeypatch.setattr(data_api, '_dir', lambda rid: tmp_path / 'runs' / rid)
    monkeypatch.chdir(tmp_path)

    class InlineThread:
        def __init__(self, target, args=(), **kw):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(runs_api, 'threading', SimpleNamespace(Thread=InlineThread))
    app = FastAPI()
    app.include_router(runs_api.router)
    app.include_router(data_api.router)
    app.include_router(checks_api.router)
    app.dependency_overrides[current_user] = lambda: 'demo'

    client = TestClient(app)
    response = client.post('/api/runs', json={'config_id': cid})
    assert response.status_code == 200
    rid = response.json()['run_id']
    status = client.get(f'/api/runs/{rid}')
    assert status.status_code == 200
    assert status.json()['status'] == 'done'
    assert len(status.json()['steps']) == 12
    step = client.get(f'/api/runs/{rid}/steps/s1_discover').json()
    assert 'def discover' in step['code']
    assert client.get(f'/api/runs/{rid}/summary').json()['total_apps'] == 1
    assert client.get(f'/api/runs/{rid}/checks').json() == []
    html = client.get(f'/api/runs/{rid}/report.html')
    assert html.status_code == 200 and '<html>ok</html>' in html.text
