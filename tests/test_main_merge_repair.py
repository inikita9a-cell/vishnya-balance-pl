"""648e9fa regression: startup, P0-02, P0-09 and retained P0-03/P0-04 APIs."""
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

from backend import auth as guards, runs
from backend.api import auth, configs, data_api, checks_api, procedures, pools, runs_api
from backend.db import Base
import backend.main as main
from backend.models import Config, Procedure, Run, StageLog
from backend.validation import validate_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def system(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "isolated.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in (guards, runs, auth, configs, data_api, procedures, pools, runs_api):
        monkeypatch.setattr(module, 'SessionLocal', factory)
    monkeypatch.setattr(runs, 'RUNS_DIR', tmp_path / 'runs')
    monkeypatch.setattr(configs, 'DEFAULT', ROOT / 'configs/default_spr.yaml')
    monkeypatch.setattr(main, 'init_db', lambda: Base.metadata.create_all(engine))
    monkeypatch.chdir(tmp_path)
    cfg = yaml.safe_load((ROOT / 'configs/default_spr.yaml').read_text(encoding='utf-8'))
    cfg['dataset']['path'] = str(tmp_path / 'dataset')
    for side in ('BEFORE_MASTER', 'AFTER_BETA'):
        folder = tmp_path / 'dataset/RESULTS' / side
        folder.mkdir(parents=True)
        fixture = ROOT / 'notebooks/demo_data/RESULTS' / side / 'I32554354.json'
        (folder / 'sample.json').write_bytes(fixture.read_bytes())
    with factory() as db:
        for i, name in enumerate(('alice', 'bob'), 1):
            db.add(Config(id=i, owner=name, name=name, yaml=yaml.safe_dump(cfg)))
            db.add(Procedure(id=i, owner=name, kind='check', source='workspace', code='def check(mart, params):\n    return []'))
            db.add(Run(id=name+'_run', config_id=i, config_snapshot=yaml.safe_dump(cfg), started_by=name, status='done'))
            db.add(StageLog(run_id=name+'_run', step='s1_discover', status='done', started_by=name, code_snapshot=name+' private code'))
            folder = tmp_path / 'runs' / (name+'_run')
            folder.mkdir(parents=True)
            (folder / 'report.html').write_text(name+' private HTML', encoding='utf-8')
            (folder / 'checks.json').write_text('[]', encoding='utf-8')
            (folder / 'summary.json').write_text('{"total_apps":1}', encoding='utf-8')
        db.commit()
    pending = []
    class Deferred:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args
        def start(self):
            pending.append(self)
    monkeypatch.setattr(runs_api, 'threading', type('Threads', (), {'Thread': Deferred}))
    with TestClient(main.app) as client:
        assert client.post('/api/login', json={'name': 'alice'}).status_code == 200
        yield {'client': client, 'db': factory, 'cfg': cfg, 'pending': pending, 'root': tmp_path}


def test_restored_login_routes_and_logout(system):
    client = system['client']
    assert client.get('/api/me').json() == {'name': 'alice'}
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_existing_template_and_new_empty_config_can_be_saved(system):
    client = system['client']
    template = client.get('/api/configs/template').json()['yaml']
    assert client.post('/api/configs/validate', json={'yaml': template, 'check_dataset': False}).json()['valid']
    assert client.post('/api/configs', json={'name': 'from template', 'yaml': template, 'check_dataset': False}).status_code == 200
    response = client.post('/api/configs', json={'name': 'empty'})
    assert response.status_code == 200, response.text
    cid = response.json()['id']
    stored = client.get(f'/api/configs/{cid}').json()['yaml']
    assert validate_config(yaml.safe_load(stored), check_dataset=False)['valid']
    # A draft can be saved; a missing dataset cannot be started.
    before = len(client.get('/api/runs').json())
    assert client.post('/api/runs', json={'config_id': cid}).status_code == 422
    assert len(client.get('/api/runs').json()) == before
    assert not system['pending']


def test_config_rename_preserves_yaml_and_upload_accepts_utf8_bom(system):
    client = system['client']
    before = client.get('/api/configs/1').json()['yaml']
    assert client.put('/api/configs/1', json={'name': 'renamed', 'check_dataset': False}).status_code == 200
    assert client.get('/api/configs/1').json()['yaml'] == before
    response = client.post('/api/configs/upload', files={'file': ('sample.yaml', ('\ufeff'+before).encode('utf-8'), 'application/yaml')})
    assert response.status_code == 200 and response.json()['yaml'] == before
    assert client.post('/api/configs/upload', files={'file': ('bad.yaml', 'имя: тест'.encode('cp1251'))}).status_code == 400


@pytest.mark.parametrize('change', [
    {'dataset': {'formats': [{}]}}, {'pool': {'mode': {}}}, {'pool': {'mode': 'filter', 'filter': 'N_DIFFS > 0'}},
    {'flatten': None}, {'flatten': {'max_depth': True}}, {'buckets': None},
    {'buckets': {'default_num': [0, float('inf')]}}, {'buckets': {'by_path': {'a': ['0', '1']}}},
    {'segments': {'top_offer': {'path': 1}}},
    {'quality': {'reason_rules': [{'when_path': 'decision', 'when_value': 'NO'}]}},
])
def test_invalid_config_returns_diagnostics_instead_of_500(system, change):
    cfg = deepcopy(system['cfg'])
    for key, value in change.items():
        cfg[key] = {**cfg.get(key, {}), **value} if isinstance(value, dict) else value
    response = system['client'].post('/api/configs/validate', json={'yaml': yaml.safe_dump(cfg), 'check_dataset': False})
    assert response.status_code == 200, response.text
    assert not response.json()['valid'] and response.json()['errors']


@pytest.mark.parametrize('method,path,body', [
    ('get', '/api/runs/bob_run', None),
    ('get', '/api/runs/bob_run/steps/s1_discover', None),
    ('get', '/api/runs/bob_run/report.html', None),
    ('get', '/api/runs/bob_run/checks', None),
    ('get', '/api/runs/bob_run/summary', None),
    ('get', '/api/runs/bob_run/blocks', None),
    ('get', '/api/runs/bob_run/quality', None),
    ('get', '/api/runs/bob_run/apps/sample', None),
    ('get', '/api/runs/bob_run/apps/sample/raw', None),
    ('get', '/api/runs/bob_run/explorer/fields', None),
    ('get', '/api/runs/bob_run/checks/status', None),
    ('post', '/api/runs/bob_run/checks/rerun', {}),
    ('post', '/api/runs/bob_run/pivot', {}),
    ('post', '/api/runs/bob_run/drilldown', {}),
    ('post', '/api/runs/bob_run/sankey', {}),
    ('post', '/api/runs/bob_run/explorer/query', {}),
    ('post', '/api/runs/bob_run/explorer/apps', {}),
    ('post', '/api/procedures/2/try', {}),
    ('post', '/api/procedures/1/try', {'run_id': 'bob_run'}),
    ('post', '/api/procedures/1/try', {'config_id': 2}),
    ('post', '/api/procedures/2/attach', {'config_id': 1, 'check_id': 'foreign'}),
    ('post', '/api/runs', {'config_id': 2}),
    ('get', '/api/configs/2', None),
    ('put', '/api/configs/2', {'name': 'hijack'}),
    ('post', '/api/configs/2/duplicate', None),
    ('delete', '/api/configs/2', None),
])
def test_foreign_ids_are_404_without_execution(system, method, path, body):
    response = system['client'].request(method, path, **({'json': body} if body is not None else {}))
    assert response.status_code == 404, response.text
    assert not system['pending']


def test_lists_only_contain_current_user_and_own_run_still_opens(system):
    client = system['client']
    assert [r['id'] for r in client.get('/api/runs').json()] == ['alice_run']
    assert [r['id'] for r in client.get('/api/configs').json()] == [1]
    assert [r['id'] for r in client.get('/api/procedures').json()] == [1]
    assert client.get('/api/runs/alice_run').status_code == 200
    assert client.get('/api/runs/alice_run/steps/s1_discover').json()['code'] == 'alice private code'
    assert client.get('/api/runs/alice_run/report.html').text == 'alice private HTML'
    assert client.get('/api/runs/alice_run/summary').json() == {'total_apps': 1}


def test_cached_raw_utf8_and_path_validation_before_read(system, monkeypatch):
    folder = system['root'] / 'runs/alice_run/raw/BEFORE_MASTER'
    folder.mkdir(parents=True)
    source = '{"причина":"Отказ"}'
    (folder / 'sample.json').write_text('\ufeff'+source, encoding='utf-8')
    response = system['client'].get('/api/runs/alice_run/apps/sample/raw')
    assert response.status_code == 200 and response.json()['BEFORE_MASTER'] == source
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid app id must be rejected before reading a file')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    assert system['client'].get('/api/runs/alice_run/apps/..%5C..%5Csecret/raw').status_code == 400


def test_real_new_run_preview_attach_rerun_keeps_p003_p004(system):
    client = system['client']
    response = client.post('/api/runs', json={'config_id': 1})
    assert response.status_code == 200, response.text
    rid = response.json()['run_id']
    worker = system['pending'].pop(0)
    worker.target(*worker.args)
    assert client.get(f'/api/runs/{rid}').json()['status'] == 'done'
    code = '''def check(mart, params):
    return [{"LABEL":"merge repair", "SOURCE":"AFTER", "ARGUMENT":"", "CNT":0,
             "TOTAL":mart.total_apps(), "METRIC":0.0, "APP_IDS":[], "RESULT":"PASS", "CONFIDENCE":"HIGH"}]
'''
    pid = client.post('/api/procedures', json={'kind': 'check', 'code': code}).json()['id']
    result = client.post(f'/api/procedures/{pid}/try', json={'config_id': 1, 'app_ids': ['sample']}).json()
    assert result['ok'] and result['result']['kind'] == 'check'
    assert client.post(f'/api/procedures/{pid}/attach', json={'config_id': 1, 'check_id': 'repaired'}).status_code == 200
    job = client.post(f'/api/runs/{rid}/checks/rerun', json={'config_id': 1}).json()
    assert job['status'] == 'queued'
    worker = system['pending'].pop(0)
    worker.target(*worker.args)
    assert client.get(f'/api/runs/{rid}/checks/jobs/{job["job_id"]}').json()['status'] == 'done'
    assert any(row['CHECK_ID'] == 'repaired' for row in client.get(f'/api/runs/{rid}/checks').json())
    client.cookies.set('spr_user', 'bob')
    assert client.get(f'/api/runs/{rid}/checks/jobs/{job["job_id"]}').status_code == 404


@pytest.mark.parametrize('path,function', [
    ('/api/runs/alice_run/sankey', 'get_sankey_data'),
    ('/api/runs/alice_run/explorer/query', 'explorer_query'),
    ('/api/runs/alice_run/explorer/apps', 'explorer_apps'),
])
def test_existing_sankey_and_explorer_routes_still_delegate(system, monkeypatch, path, function):
    monkeypatch.setattr(data_api.duck, function, lambda *args, **kwargs: {'retained': function})
    response = system['client'].post(path, json={})
    assert response.status_code == 200 and response.json() == {'retained': function}
