"""P0-03: real user code changes Parquet, immutable IDs/sources and SQL journal."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.pipeline import run_pipeline
from engine.procedure_runtime import (ProcedureError, freeze_config, freeze_spec,
                                      execute, validate_normalized, validate_comparison,
                                      validate_facts)
from backend import runs
from backend.db import Base
from backend.models import Config, Procedure, Run, StageLog


NORMALIZE = '''from engine.steps import flatten_pair
def normalize(before, after, cfg, params, app_id, issues):
    before = {**before, "custom_marker": params["marker"]}
    after = {**after, "custom_marker": params["marker"]}
    return flatten_pair(before, after, cfg, app_id=app_id, issues=issues)
'''
COMPARE = '''from engine.steps import compare as builtin
def compare(union_df, cfg, params, issues):
    result = builtin(union_df, issues=issues)
    mask = result.PATH.eq(params["ignore_path"])
    result.loc[mask, "CHANGE_TYPE"] = "SAME"
    result.loc[mask, "DIFF_FLAG"] = 0
    return result
'''
FACTS = '''from engine.aggregates import facts as builtin
def facts(comparison, segments, cfg, params):
    table, members = builtin(comparison, segments, cfg)
    table["CUSTOM_DIMENSION"] = params["dimension"]
    return table, members
'''
CHECK = '''def check(mart, params):
    return [{"LABEL": params["label"], "SOURCE": "AFTER", "ARGUMENT": "",
             "CNT": 0, "TOTAL": mart.total_apps(), "METRIC": 0.0,
             "APP_IDS": [], "RESULT": "PASS", "CONFIDENCE": "HIGH"}]
'''


@pytest.fixture
def config(tmp_path):
    root = tmp_path / 'dataset'
    for side, value in [('BEFORE_MASTER', 1), ('AFTER_BETA', 2)]:
        folder = root / 'RESULTS' / side
        folder.mkdir(parents=True)
        (folder / 'a.json').write_text(json.dumps({'risk': {'score': value}, 'decision': 'YES'}))
    return {'dataset': {'path': str(root), 'before_dir': 'RESULTS/BEFORE_MASTER',
                        'after_dir': 'RESULTS/AFTER_BETA', 'formats': ['json']},
            'buckets': {}, 'segments': {'decision': 'decision', 'approve_value': 'YES'},
            'quality': {}, 'checks': []}


def custom(cfg):
    cfg = deepcopy(cfg)
    cfg['procedures'] = {
        'normalize': {'source': 'workspace', 'code': NORMALIZE, 'params': {'marker': 'P003'}},
        'compare': {'source': 'workspace', 'code': COMPARE, 'params': {'ignore_path': 'risk.score'}},
        'facts': {'source': 'workspace', 'code': FACTS, 'params': {'dimension': 'chosen'}},
    }
    cfg['checks'] = [{'id': 'user_check', 'source': 'workspace', 'code': CHECK,
                      'params': {'label': 'USER CODE EXECUTED'}}]
    return cfg


def test_actual_selected_code_changes_outputs_and_events(config, tmp_path):
    base = run_pipeline(config, tmp_path / 'base')
    events = []
    result = run_pipeline(custom(config), tmp_path / 'custom', events.append)
    assert base['summary']['apps_with_diff'] == 1
    assert result['summary']['apps_with_diff'] == 0  # custom compare, not builtin
    united = pd.read_parquet(tmp_path / 'custom/union.parquet')
    assert united.loc[united.PATH.eq('custom_marker'), 'VALUE'].tolist() == ['P003', 'P003']
    table = pd.read_parquet(tmp_path / 'custom/facts.parquet')
    assert table.CUSTOM_DIMENSION.eq('chosen').all()
    assert json.loads((tmp_path / 'custom/checks.json').read_text())[0]['LABEL'] == 'USER CODE EXECUTED'
    for kind, stage, source in [('normalize', 's2_s4_normalize', NORMALIZE),
                                 ('compare', 's7_compare', COMPARE), ('facts', 's11_facts', FACTS)]:
        event = next(e for e in events if e['step'] == stage and e['status'] == 'running')
        assert event['code_snapshot'] == source
        assert event['procedure']['sha256'] == hashlib.sha256(source.encode()).hexdigest()
    check_event = next(e for e in events if e['step'] == 's12_checks' and e['status'] == 'running')
    assert CHECK in check_event['code_snapshot']
    assert (tmp_path / 'custom/procedures_snapshot.json').is_file()


def test_file_source_is_frozen_not_reread(config, tmp_path):
    filename = tmp_path / 'normalizer.py'
    filename.write_text(NORMALIZE, encoding='utf-8')
    cfg = custom(config)
    cfg['procedures']['normalize'] = {'source': 'file', 'path': str(filename),
                                     'params': {'marker': 'P003'}}
    frozen = freeze_config(cfg)
    filename.write_text('raise RuntimeError("changed after queue")')
    run_pipeline(frozen, tmp_path / 'run')
    assert frozen['procedures']['normalize']['code'] == NORMALIZE
    assert cfg['procedures']['normalize'].get('code') is None


@pytest.fixture
def database(monkeypatch, tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "app.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runs, 'SessionLocal', factory)
    from backend import auth as backend_auth
    monkeypatch.setattr(backend_auth, 'SessionLocal', factory)
    monkeypatch.setattr(runs, 'RUNS_DIR', tmp_path / 'runs')
    return factory


def test_platform_resolves_ids_snapshots_before_queue_and_logs_real_code(database, config, tmp_path):
    cfg = custom(config)
    with database() as db:
        for kind in ['normalize', 'compare', 'facts', 'check']:
            target = cfg['checks'][0] if kind == 'check' else cfg['procedures'][kind]
            proc = Procedure(owner='alice', kind=kind, source='workspace', code=target.pop('code'))
            db.add(proc)
            db.flush()
            target['procedure_id'] = proc.id
        row = Config(owner='alice', name='selected', yaml=yaml.safe_dump(cfg))
        db.add(row)
        db.commit()
        cid = row.id
    rid = runs.start_run(cid, 'alice')
    with database() as db:
        snap = yaml.safe_load(db.get(Run, rid).config_snapshot)
        for proc in db.query(Procedure):
            proc.code = 'raise RuntimeError("edited later")'
        db.get(Config, cid).yaml = 'checks: []'
        db.commit()
    result = runs.run_pipeline(rid, snap)
    assert result is not None and result['summary']['apps_with_diff'] == 0
    with database() as db:
        assert db.get(Run, rid).status == 'done'
        stages = {row.step: row for row in db.query(StageLog).filter_by(run_id=rid)}
        for kind, stage, source in [('normalize', 's2_s4_normalize', NORMALIZE),
                                     ('compare', 's7_compare', COMPARE), ('facts', 's11_facts', FACTS)]:
            assert stages[stage].code_snapshot == source
            assert json.loads(stages[stage].params)['procedure']['params'] == cfg['procedures'][kind]['params']
        assert CHECK in stages['s12_checks'].code_snapshot
    # Old run/check sources stay executable after Procedure/Config edits.
    runs.rerun_checks(rid)
    assert json.loads((tmp_path / 'runs' / rid / 'checks.json').read_text())[0]['RESULT'] == 'PASS'


@pytest.mark.parametrize('owner,kind', [('bob', 'normalize'), ('alice', 'facts')])
def test_platform_refuses_foreign_or_wrong_kind(database, config, owner, kind):
    with database() as db:
        proc = Procedure(owner=owner, kind=kind, source='workspace', code=NORMALIZE)
        db.add(proc)
        db.flush()
        config['procedures'] = {'normalize': {'procedure_id': proc.id}}
        cfg = Config(owner='alice', name='bad', yaml=yaml.safe_dump(config))
        db.add(cfg)
        db.commit()
        cid = cfg.id
    with pytest.raises(ProcedureError):
        runs.start_run(cid, 'alice')
    with database() as db:
        assert db.query(Run).count() == 0


@pytest.mark.parametrize('kind,code,stage', [
    ('normalize', 'def normalize(**kw):\n    return [], [{}]', 's2_s4_normalize'),
    ('compare', 'def compare(**kw):\n    return None', 's7_compare'),
    ('facts', 'def facts(**kw):\n    return None', 's11_facts'),
    ('compare', 'def compare(**kw):\n    raise RuntimeError("custom boom")', 's7_compare'),
])
def test_contract_failures_mark_correct_sql_stage_failed(database, config, kind, code, stage):
    config['procedures'] = {kind: {'source': 'workspace', 'code': code}}
    with database() as db:
        cfg = Config(owner='alice', name='bad output', yaml=yaml.safe_dump(config))
        db.add(cfg)
        db.commit()
        cid = cfg.id
    rid = runs.start_run(cid, 'alice')
    with database() as db:
        snap = yaml.safe_load(db.get(Run, rid).config_snapshot)
    assert runs.run_pipeline(rid, snap) is None
    with database() as db:
        run = db.get(Run, rid)
        assert run.status == 'failed'
        row = db.query(StageLog).filter_by(run_id=rid, step=stage).one()
        assert row.status == 'failed' and kind in row.message
        assert row.code_snapshot == code
        assert not db.query(StageLog).filter_by(run_id=rid, step='s15_report').count()


def test_custom_timeout():
    cfg = freeze_config({'procedures': {'compare': {
        'code': 'def compare(**kw):\n    while True: pass', 'timeout_seconds': 0.2}}})
    with pytest.raises(ProcedureError, match='timeout'):
        execute('compare', cfg, union_df=pd.DataFrame())


def test_custom_check_error_is_a_row_and_other_checks_continue(config, tmp_path):
    cfg = custom(config)
    cfg['checks'].insert(0, {'id': 'broken', 'code': 'def check(mart, params):\n    raise ValueError("bad check")'})
    run_pipeline(cfg, tmp_path / 'run')
    rows = json.loads((tmp_path / 'run/checks.json').read_text())
    assert [r['RESULT'] for r in rows] == ['ERROR', 'PASS']


def test_explicit_check_entry_and_params_precedence(config, tmp_path):
    config['checks'] = [{'id': 'named', 'entry': 'mine', 'code': CHECK.replace('def check(', 'def mine('),
                         'params': {'label': 'entry default'}}]
    config['check_params'] = {'named': {'label': 'config override'}}
    run_pipeline(config, tmp_path / 'run')
    assert json.loads((tmp_path / 'run/checks.json').read_text())[0]['LABEL'] == 'config override'


@pytest.mark.parametrize('spec', [
    {'procedure_id': 123}, {'source': 'oops', 'code': NORMALIZE},
    {'code': NORMALIZE, 'params': []}, {'code': NORMALIZE, 'timeout_seconds': -1},
    {'code': NORMALIZE, 'entry': 'not.valid'}, {'code': NORMALIZE, 'sha256': 'wrong'},
])
def test_invalid_specs_fail_clearly(spec):
    with pytest.raises(ProcedureError):
        freeze_spec(spec, 'normalize')


def test_bad_fact_counts_rejected(config, tmp_path):
    cfg = custom(config)
    cfg['procedures']['facts']['code'] = FACTS.replace('return table, members', 'table["CNT"] = 999\n    return table, members')
    with pytest.raises(ProcedureError, match='CNT'):
        run_pipeline(cfg, tmp_path / 'run')


def test_missing_entry_reports_selected_stage(config, tmp_path):
    config['procedures'] = {'compare': {'code': 'x = 1'}}
    with pytest.raises(ProcedureError, match='callable'):
        run_pipeline(config, tmp_path / 'run')


@pytest.mark.parametrize('kind,source,params', [
    ('normalize', NORMALIZE, {'marker': 'PREVIEW'}),
    ('compare', COMPARE, {'ignore_path': 'risk.score'}),
    ('facts', FACTS, {'dimension': 'PREVIEW'}),
    ('check', CHECK, {'label': 'PREVIEW'}),
])
def test_real_preview_api_uses_stage_contract_and_never_saves_draft(database, config, monkeypatch, kind, source, params):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.auth import current_user
    from backend.api import procedures
    monkeypatch.setattr(procedures, 'SessionLocal', database)
    with database() as db:
        proc = Procedure(owner='alice', kind=kind, source='workspace', code='old saved code')
        cfg = Config(owner='alice', name='preview dataset', yaml=yaml.safe_dump(config))
        db.add_all([proc, cfg])
        db.commit()
        pid, cid = proc.id, cfg.id
    app = FastAPI()
    app.include_router(procedures.router)
    app.dependency_overrides[current_user] = lambda: 'alice'
    client = TestClient(app)
    response = client.post(f'/api/procedures/{pid}/try', json={
        'config_id': cid, 'app_ids': ['a'], 'code': source, 'params': params})
    assert response.status_code == 200
    data = response.json()
    assert data['ok'], data
    assert data['result']['kind'] == kind and data['result']['summary']['total_apps'] == 1
    if kind == 'normalize':
        assert any(r['PATH'] == 'custom_marker' and r['VALUE'] == 'PREVIEW' for r in data['result']['rows'])
    if kind == 'compare':
        assert data['result']['summary']['apps_with_diff'] == 0
    if kind == 'facts':
        assert all(r['CUSTOM_DIMENSION'] == 'PREVIEW' for r in data['result']['rows'])
    if kind == 'check':
        assert data['result']['rows'][0]['LABEL'] == 'PREVIEW'
    with database() as db:
        assert db.get(Procedure, pid).code == 'old saved code'
        assert db.query(Run).count() == 0
    too_many = client.post(f'/api/procedures/{pid}/try', json={
        'config_id': cid, 'app_ids': ['a', 'b', 'c', 'd'], 'code': source, 'params': params}).json()
    assert not too_many['ok'] and '1-3' in too_many['result']['error']
    app.dependency_overrides[current_user] = lambda: 'bob'
    assert client.post(f'/api/procedures/{pid}/try', json={'config_id': cid}).status_code == 404
