"""P0-04 REST acceptance: create -> preview -> attach -> queue -> poll -> report."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

from backend import runs
from backend.auth import current_user
from backend.db import Base
from backend.models import Config, Procedure, Run, StageLog
from backend.api import runs_api, procedures, checks_api
from engine import check_jobs

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_CHECK = '''def check(mart, params):
    ids = mart.app_ids(diff_flag=1)
    total = mart.total_apps()
    return [{"LABEL": params.get("label", "CUSTOM P0-04"), "SOURCE": "AFTER", "ARGUMENT": "diff_flag=1",
             "CNT": len(ids), "TOTAL": total, "METRIC": len(ids) / total if total else 0,
             "APP_IDS": ids, "RESULT": "FAIL" if ids else "PASS", "CONFIDENCE": "HIGH"}]
'''


def digests(root, pattern='*.parquet'):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob(pattern)}


@pytest.fixture
def system(tmp_path, monkeypatch):
    dataset = tmp_path / 'dataset'
    for side in ['BEFORE_MASTER', 'AFTER_BETA']:
        folder = dataset / 'RESULTS' / side
        folder.mkdir(parents=True)
        shutil.copyfile(ROOT / 'notebooks/demo_data/RESULTS' / side / 'I32554354.json', folder / '1001.json')
    cfg = yaml.safe_load((ROOT / 'configs/default_spr.yaml').read_text(encoding='utf-8'))
    cfg['dataset']['path'] = str(dataset)
    cfg['quality']['reason_rules'] = []
    engine = create_engine(f'sqlite:///{tmp_path / "app.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runs, 'SessionLocal', factory)
    monkeypatch.setattr(runs, 'RUNS_DIR', tmp_path / 'runs')
    monkeypatch.setattr(runs_api, 'SessionLocal', factory)
    monkeypatch.setattr(procedures, 'SessionLocal', factory)
    monkeypatch.chdir(tmp_path)
    with factory() as db:
        row = Config(owner='alice', name='original', yaml=yaml.safe_dump(cfg))
        db.add(row)
        db.commit()
        cid = row.id
    rid = runs.start_run(cid, 'alice')
    with factory() as db:
        snapshot = db.get(Run, rid).config_snapshot
    result = runs.run_pipeline(rid, yaml.safe_load(snapshot))
    assert result is not None
    pending = []

    class DeferredThread:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args
        def start(self):
            pending.append(self)

    monkeypatch.setattr(runs_api, 'threading', type('Threads', (), {'Thread': DeferredThread}))
    app = FastAPI()
    for router in (runs_api.router, procedures.router, checks_api.router):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: 'alice'
    client = TestClient(app)
    return {'client': client, 'app': app, 'db': factory, 'rid': rid, 'cid': cid,
            'root': tmp_path / 'runs' / rid, 'pending': pending, 'snapshot': snapshot,
            'dataset': dataset, 'checks': cfg['checks']}


def queue(system, payload=None):
    response = system['client'].post(f'/api/runs/{system["rid"]}/checks/rerun', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def finish(system, job):
    thread = system['pending'].pop(0)
    thread.target(*thread.args)
    response = system['client'].get(f'/api/runs/{system["rid"]}/checks/jobs/{job["job_id"]}')
    assert response.status_code == 200
    return response.json()


def test_create_preview_attach_queue_poll_real_checks_and_regenerated_html(system, monkeypatch):
    s, client = system, system['client']
    proc = client.post('/api/procedures', json={'kind': 'check', 'source': 'workspace', 'code': CUSTOM_CHECK})
    assert proc.status_code == 200
    pid = proc.json()['id']
    draft = client.post(f'/api/procedures/{pid}/try', json={
        'config_id': s['cid'], 'app_ids': ['1001'], 'params': {'label': 'NEW CHECK'}}).json()
    assert draft['ok'] and draft['result']['rows'][0]['RESULT'] == 'FAIL'
    attached = client.post(f'/api/procedures/{pid}/attach', json={
        'config_id': s['cid'], 'check_id': 'user_check', 'params': {'label': 'NEW CHECK'}})
    assert attached.status_code == 200, attached.text
    with s['db']() as db:
        cfg = yaml.safe_load(db.get(Config, s['cid']).yaml)
        assert cfg['checks'][:5] == s['checks']
    before = digests(s['root'])
    old_report = (s['root'] / 'report.html').read_bytes()
    job = queue(s, {'config_id': s['cid']})
    assert job['status'] == 'queued' and job['ok'] and len(job['check_ids']) == 6
    assert 'config_snapshot' not in job
    assert client.get(f'/api/runs/{s["rid"]}/checks/jobs/{job["job_id"]}').json()['status'] == 'queued'
    assert (s['root'] / 'report.html').read_bytes() == old_report
    # Later edits and missing raw inputs cannot change this queued revision.
    with s['db']() as db:
        db.get(Procedure, pid).code = 'raise RuntimeError("edited after queue")'
        db.get(Config, s['cid']).yaml = 'checks: []'
        db.commit()
    shutil.rmtree(s['dataset'])
    monkeypatch.setattr(runs, 'execute_pipeline', lambda *a, **k: pytest.fail('Must not run normalization again'))
    completed = finish(s, job)
    assert completed['status'] == 'done' and completed['progress'] == 100
    assert completed['counts']['error'] == 0
    rows = client.get(f'/api/runs/{s["rid"]}/checks').json()
    assert set(s['checks']) | {'user_check'} == {row['CHECK_ID'] for row in rows}
    own = next(row for row in rows if row['CHECK_ID'] == 'user_check')
    assert own['CNT'] == own['TOTAL'] == 1 and own['APP_IDS'] == ['1001']
    assert own['RESULT'] == 'FAIL'
    assert 'NEW CHECK' in (s['root'] / 'report.html').read_text(encoding='utf-8')
    assert digests(s['root']) == before
    assert client.get(f'/api/runs/{s["rid"]}/checks/status').json()['job']['job_id'] == job['job_id']
    with s['db']() as db:
        assert db.get(Run, s['rid']).config_snapshot == s['snapshot']
        assert db.get(Run, s['rid']).status == 'done'
        latest = db.query(StageLog).filter_by(run_id=s['rid'], step='s12_checks').order_by(StageLog.id.desc()).first()
        assert CUSTOM_CHECK in latest.code_snapshot


@pytest.mark.parametrize('bad_code', [
    'def check(mart, params):\n    raise ValueError("broken check")',
    'def check(:\n    invalid syntax',
    'def check(mart, params):\n    return [{"RESULT": "PASS"}]',
])
def test_one_bad_check_is_error_row_others_continue(system, bad_code):
    s = system
    selected = s['checks'] + [{'id': 'broken', 'code': bad_code},
                               {'id': 'good', 'code': CUSTOM_CHECK}]
    job = queue(s, {'checks': selected})
    status = finish(s, job)
    assert status['status'] == 'done' and status['counts']['error'] == 1
    rows = json.loads((s['root'] / 'checks.json').read_text(encoding='utf-8'))
    assert next(r for r in rows if r['CHECK_ID'] == 'broken')['RESULT'] == 'ERROR'
    assert next(r for r in rows if r['CHECK_ID'] == 'good')['RESULT'] == 'FAIL'
    assert set(s['checks']) <= {r['CHECK_ID'] for r in rows}


def test_infrastructure_failure_keeps_previous_report_and_releases_lock(system, monkeypatch):
    s = system
    before = {p.name: p.read_bytes() for p in s['root'].iterdir() if p.is_file()}
    job = queue(s, {'checks': [{'id': 'good', 'code': CUSTOM_CHECK}]})
    def broken_report(*args, **kwargs):
        raise OSError('cannot write html')
    monkeypatch.setattr(runs, 'write_report_html', broken_report)
    status = finish(s, job)
    assert status['status'] == 'failed' and 'cannot write html' in status['error']
    assert all((s['root'] / name).read_bytes() == content for name, content in before.items())
    assert not (s['root'] / '.checks-rerun.lock').exists()
    assert queue(s)['status'] == 'queued'


def test_publish_failure_rolls_back_all_visible_files(system, monkeypatch):
    s = system
    before = {name: (s['root'] / name).read_bytes() if (s['root'] / name).exists() else None
              for name in check_jobs.PUBLISHED}
    job = queue(s, {'checks': [{'id': 'new', 'code': CUSTOM_CHECK}]})
    original_replace = check_jobs.os.replace
    def fail_report(source, dest):
        if Path(dest) == s['root'] / 'report.html':
            raise OSError('publish denied')
        return original_replace(source, dest)
    monkeypatch.setattr(check_jobs.os, 'replace', fail_report)
    status = finish(s, job)
    assert status['status'] == 'failed' and 'publish denied' in status['error']
    for name, content in before.items():
        if content is None:
            assert not (s['root'] / name).exists()
        else:
            assert (s['root'] / name).read_bytes() == content


def test_concurrent_job_for_same_run_is_rejected(system):
    job = queue(system)
    response = system['client'].post(f'/api/runs/{system["rid"]}/checks/rerun')
    assert response.status_code == 409 and len(system['pending']) == 1
    assert finish(system, job)['status'] == 'done'
    assert queue(system)['status'] == 'queued'


def test_no_body_reruns_latest_successful_selection(system):
    s = system
    job = queue(s, {'checks': [{'id': 'remembered', 'code': CUSTOM_CHECK,
                               'params': {'label': 'remember this revision'}}]})
    assert finish(s, job)['status'] == 'done'
    next_job = queue(s)
    assert next_job['check_ids'] == ['remembered']
    assert finish(s, next_job)['status'] == 'done'
    rows = json.loads((s['root'] / 'checks.json').read_text(encoding='utf-8'))
    assert rows[0]['LABEL'] == 'remember this revision'


def test_ownership_on_queue_poll_latest_and_attach(system):
    s = system
    job = queue(s)
    with s['db']() as db:
        proc = Procedure(owner='bob', kind='check', source='workspace', code=CUSTOM_CHECK)
        db.add(proc)
        db.commit()
        pid = proc.id
    assert s['client'].post(f'/api/procedures/{pid}/attach', json={
        'config_id': s['cid'], 'check_id': 'foreign'}).status_code == 400
    s['app'].dependency_overrides[current_user] = lambda: 'bob'
    for method, path in [
        ('post', f'/api/runs/{s["rid"]}/checks/rerun'),
        ('get', f'/api/runs/{s["rid"]}/checks/jobs/{job["job_id"]}'),
        ('get', f'/api/runs/{s["rid"]}/checks/status'),
    ]:
        assert getattr(s['client'], method)(path).status_code == 404
    assert s['client'].post(f'/api/procedures/{pid}/attach', json={
        'config_id': s['cid'], 'check_id': 'foreign'}).status_code == 404


def test_invalid_selection_is_not_queued_and_lock_is_released(system):
    s = system
    for payload in [{'checks': ['../bad']}, {'config_id': s['cid'], 'checks': []}, {'checks': [{'id': 'missing_id', 'procedure_id': 9999}]}]:
        response = s['client'].post(f'/api/runs/{s["rid"]}/checks/rerun', json=payload)
        assert response.status_code == 400, response.text
        assert not (s['root'] / '.checks-rerun.lock').exists()
    assert queue(s)['status'] == 'queued'


def test_only_completed_owned_config_and_existing_job_are_accepted(system):
    s = system
    with s['db']() as db:
        cfg = Config(owner='bob', name='foreign', yaml='checks: []')
        db.add(cfg)
        db.commit()
        cid = cfg.id
    assert s['client'].post(f'/api/runs/{s["rid"]}/checks/rerun', json={'config_id': cid}).status_code == 404
    assert s['client'].get(f'/api/runs/{s["rid"]}/checks/jobs/{"a" * 32}').status_code == 404
    assert s['client'].get(f'/api/runs/{s["rid"]}/checks/status').json()['job'] is None
    with s['db']() as db:
        db.get(Run, s['rid']).status = 'running'
        db.commit()
    assert s['client'].post(f'/api/runs/{s["rid"]}/checks/rerun').status_code == 409


def test_attach_updates_one_check_without_duplicates_and_rejects_wrong_kind(system):
    s = system
    with s['db']() as db:
        check = Procedure(owner='alice', kind='check', source='workspace', code=CUSTOM_CHECK)
        wrong = Procedure(owner='alice', kind='normalize', source='workspace', code='x = 1')
        db.add_all([check, wrong])
        db.commit()
        pid, bad_pid = check.id, wrong.id
    for label in ['v1', 'v2']:
        response = s['client'].post(f'/api/procedures/{pid}/attach', json={
            'config_id': s['cid'], 'check_id': 'same_id', 'params': {'label': label}})
        assert response.status_code == 200
    with s['db']() as db:
        selected = yaml.safe_load(db.get(Config, s['cid']).yaml)['checks']
        assert len(selected) == 6 and selected[-1]['params']['label'] == 'v2'
    assert s['client'].post(f'/api/procedures/{bad_pid}/attach', json={
        'config_id': s['cid'], 'check_id': 'bad_kind'}).status_code == 400


def test_file_check_source_frozen_before_worker_starts(system, tmp_path):
    source = tmp_path / 'my_check.py'
    source.write_text(CUSTOM_CHECK, encoding='utf-8')
    job = queue(system, {'checks': [{'id': 'file_check', 'source': 'file', 'path': str(source)}]})
    source.unlink()
    assert finish(system, job)['status'] == 'done'
    rows = json.loads((system['root'] / 'checks.json').read_text(encoding='utf-8'))
    assert rows[0]['CHECK_ID'] == 'file_check' and rows[0]['RESULT'] == 'FAIL'
