"""Real concurrent calculations, shared launch defaults, public static/API auth."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import queue
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

from backend import auth, db, runs, security_config
from backend.api import auth as login_api, configs, runs_api, data_api
from backend.models import Config, Run, StageLog
from backend.web_links import public_report_links
from backend.staging_access import password_hash
from tools.web_server import child_env, find_origin

ROOT = Path(__file__).resolve().parents[1]


def isolated_db(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "app.db"}',
                           connect_args={'check_same_thread':False, 'timeout':30})
    db.configure_sqlite_engine(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    db.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in (auth,db,runs,security_config,login_api,configs,runs_api,data_api):
        monkeypatch.setattr(module,'SessionLocal',factory)
    monkeypatch.setattr(db,'engine',engine)
    monkeypatch.setattr(runs,'RUNS_DIR',tmp_path/'runs')
    return engine,factory


def test_development_default_is_shared_staging_is_private(monkeypatch):
    monkeypatch.delenv('REPORT_ACCESS',raising=False)
    monkeypatch.setenv('APP_ENV','development')
    assert auth.reports_shared()
    monkeypatch.setenv('APP_ENV','staging')
    assert not auth.reports_shared()
    monkeypatch.setenv('REPORT_ACCESS','shared')
    assert auth.reports_shared()


def test_two_users_calculate_while_api_stays_available(tmp_path,monkeypatch):
    engine,factory = isolated_db(tmp_path,monkeypatch)
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.delenv('REPORT_ACCESS',raising=False)
    config = yaml.safe_load((ROOT/'configs/default_spr.yaml').read_text(encoding='utf-8'))
    config['dataset']['path'] = str(ROOT/'notebooks/demo_data')
    other = json.loads(json.dumps(config))
    other['pool'] = {'mode':'list','app_ids':['I32554354']}
    with factory() as session:
        for i,(owner,cfg) in enumerate([('alice',config),('bob',other)],1):
            session.add(Config(id=i,owner=owner,name=owner,yaml=yaml.safe_dump(cfg)))
        session.commit()
    monkeypatch.chdir(tmp_path)
    barrier = threading.Barrier(3)
    release = threading.Event()
    original = runs.execute_pipeline
    def held_pipeline(*args,**kwargs):
        barrier.wait(timeout=15)
        assert release.wait(timeout=15)
        return original(*args,**kwargs)
    monkeypatch.setattr(runs,'execute_pipeline',held_pipeline)
    import backend.main as main
    monkeypatch.setattr(main,'init_db',lambda:None)
    clients = [TestClient(main.app),TestClient(main.app)]
    try:
        for client,name in zip(clients,['alice','bob']):
            assert client.post('/api/login',json={'name':name}).status_code==200
        def start(pair):
            client,cid=pair
            response=client.post('/api/runs',json={'config_id':cid})
            assert response.status_code==200,response.text
            return response.json()['run_id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(start,zip(clients,[1,2])))
        barrier.wait(timeout=15)  # Both real worker threads reached execution.
        assert ids[0]!=ids[1]
        assert clients[0].get('/api/me').json()['name']=='alice'
        assert clients[1].get('/api/me').json()['name']=='bob'
        assert len(clients[0].get('/api/runs').json())==2
        assert clients[0].get('/api/configs/2').status_code==404
        assert clients[0].post(f'/api/runs/{ids[1]}/checks/rerun',json={}).status_code==404
        assert all(clients[0].get(f'/api/runs/{rid}').json()['status']=='running' for rid in ids)
        with TestClient(main.app) as viewer:
            assert viewer.post('/api/login',json={'name':'observer'}).status_code==200
            assert len(viewer.get('/api/runs').json())==2
            assert viewer.get(f'/api/runs/{ids[0]}').status_code==200
        release.set()
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            statuses=[clients[0].get(f'/api/runs/{rid}').json() for rid in ids]
            if all(r['status'] in ('done','failed') for r in statuses):break
            time.sleep(.1)
        assert [r['status'] for r in statuses]==['done','done'],statuses
        summaries=[clients[1].get(f'/api/runs/{rid}/summary').json() for rid in ids]
        assert [s['total_apps'] for s in summaries]==[4,1]
        pivot=clients[1].post(f'/api/runs/{ids[0]}/pivot',json={
            'rows':['PATH'],'cols':['CHANGE_TYPE'],'filters':{'DIFF_FLAG':1}})
        assert pivot.status_code==200,pivot.text
        cell=pivot.json()['rows'][0]
        page=clients[1].post(f'/api/runs/{ids[0]}/pivot/apps',json={
            'filters':{'PATH':cell['PATH'],'CHANGE_TYPE':cell['CHANGE_TYPE'],'DIFF_FLAG':1},
            'limit':50,'offset':0})
        assert page.status_code==200,page.text
        assert page.json()['total']==cell['CNT']
        for rid in ids:
            root=tmp_path/'runs'/rid
            assert all((root/name).is_file() for name in ['comparison.parquet','summary.json','checks.json','report.html'])
        with factory() as session:
            assert [session.get(Run,rid).started_by for rid in ids]==['alice','bob']
            for rid in ids:
                assert session.query(StageLog).filter_by(run_id=rid,status='done').count()==12
    finally:
        release.set()
        for client in clients:client.close()
        engine.dispose()


@pytest.mark.parametrize('windows_static_paths',[False,True],ids=['native-paths','windows-paths'])
def test_public_server_serves_static_and_api_with_shared_history(tmp_path,monkeypatch,windows_static_paths):
    if windows_static_paths:
        # StaticFiles.get_path uses os.path.normpath: Windows emits backslashes.
        from fastapi.staticfiles import StaticFiles
        get_path=StaticFiles.get_path
        monkeypatch.setattr(StaticFiles,'get_path',lambda self,scope:get_path(self,scope).replace('/',chr(92)))
    engine,factory=isolated_db(tmp_path,monkeypatch)
    static=tmp_path/'static';static.mkdir()
    (static/'index.html').write_text('<h1>StrategyLab built app</h1>',encoding='utf-8')
    (static/'app.js').write_text('window.appReady=true',encoding='utf-8')
    data=tmp_path/'outside_dataset';data.mkdir()
    monkeypatch.setenv('APP_ENV','staging')
    monkeypatch.setenv('REPORT_ACCESS','shared')
    monkeypatch.setenv('APP_BASE_URL','https://demo.trycloudflare.com')
    monkeypatch.setenv('STATIC_DIR',str(static))
    monkeypatch.setenv('DATA_DIR',str(data))
    salt='12'*16;secret='personal-demo-password-12345'
    users={name:salt+':'+password_hash(secret,salt) for name in ['alice','bob','Новый пользователь']}
    monkeypatch.setenv('STAGING_USERS_JSON',json.dumps(users))
    with factory() as session:
        session.add(Run(id='historic',started_by='alice',status='done',config_snapshot='{}'))
        session.commit()
    monkeypatch.chdir(tmp_path)
    root=tmp_path/'runs/historic';root.mkdir(parents=True)
    (root/'summary.json').write_text('{"total_apps":2002}',encoding='utf-8')
    spec=importlib.util.spec_from_file_location('backend.web_test_main',ROOT/'backend/main.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with TestClient(module.app,base_url='https://demo.trycloudflare.com') as client:
        assert client.get('/').status_code==401
        assert client.get('/healthz').status_code==200
        assert client.get('/',auth=('bob',secret)).text=='<h1>StrategyLab built app</h1>'
        assert client.get('/app.js',auth=('bob',secret)).status_code==200
        assert client.get('/api/me',auth=('bob',secret)).json()['name']=='bob'
        assert client.get('/api/me',auth=('Новый пользователь',secret)).json()['name']=='Новый пользователь'
        assert len(client.get('/api/runs',auth=('bob',secret)).json())==1
        assert client.get('/api/runs/historic/summary',auth=('bob',secret)).json()['total_apps']==2002
        assert client.post('/api/runs/historic/checks/rerun',auth=('bob',secret),
                           headers={'Origin':'https://demo.trycloudflare.com'},json={}).status_code==404
        assert client.post('/api/login',auth=('bob',secret),headers={'Origin':'https://evil.invalid'},json={'name':'alice'}).status_code==403
        assert client.get('/api/nonexistent',auth=('bob',secret)).status_code==404
        assert client.get('/api/nonexistent/nested',auth=('bob',secret)).status_code==404
        assert client.get('/api',auth=('bob',secret)).status_code==404
        assert client.get('/missing.js',auth=('bob',secret)).status_code==404
        assert client.get('/registry',auth=('bob',secret)).text=='<h1>StrategyLab built app</h1>'
    engine.dispose()


def test_configured_external_data_root_is_bounded(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','staging')
    root=tmp_path/'approved';root.mkdir()
    monkeypatch.setenv('DATA_DIR',str(root))
    assert auth.data_directory(root/'RUN')==root/'RUN'
    from fastapi import HTTPException
    with pytest.raises(HTTPException):auth.data_directory(tmp_path/'other')


def test_public_authenticated_user_runs_builtin_pipeline(tmp_path,monkeypatch):
    engine,factory=isolated_db(tmp_path,monkeypatch)
    config=yaml.safe_load((ROOT/'configs/default_spr.yaml').read_text(encoding='utf-8'))
    config['dataset']['path']=str(ROOT/'notebooks/demo_data')
    with factory() as session:
        session.add(Config(id=1,owner='alice',name='hosted',yaml=yaml.safe_dump(config)))
        session.commit()
    monkeypatch.setenv('APP_ENV','staging')
    monkeypatch.setenv('REPORT_ACCESS','shared')
    monkeypatch.setenv('DATA_DIR',str(ROOT/'notebooks'))
    monkeypatch.setenv('APP_BASE_URL','https://demo.trycloudflare.com')
    monkeypatch.setenv('FRONTEND_BASE_URL','https://demo.trycloudflare.com')
    salt='34'*16;secret='demo-personal-password-123456'
    monkeypatch.setenv('STAGING_USERS_JSON',json.dumps({'alice':salt+':'+password_hash(secret,salt)}))
    import backend.main as main
    monkeypatch.setattr(main,'init_db',lambda:None)
    monkeypatch.chdir(tmp_path)
    with TestClient(main.app,base_url='https://demo.trycloudflare.com') as client:
        client.auth=('alice',secret)
        client.headers['Origin']='https://demo.trycloudflare.com'
        response=client.post('/api/runs',json={'config_id':1})
        assert response.status_code==200,response.text
        rid=response.json()['run_id']
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            state=client.get(f'/api/runs/{rid}').json()
            if state['status'] in ('done','failed'):break
            time.sleep(.1)
        assert state['status']=='done',state
        assert client.get(f'/api/runs/{rid}/summary').json()['total_apps']==4
        raw=client.get(f'/api/runs/{rid}/apps/I32554354/raw')
        assert raw.status_code==200,raw.text
        html=client.get(f'/api/runs/{rid}/report.html')
        assert html.status_code==200
        assert 'https://demo.trycloudflare.com' in html.text
        checks=client.get(f'/api/runs/{rid}/checks')
        assert checks.status_code==200,checks.text
        assert checks.json() and all(row['RESULT']!='ERROR' for row in checks.json())
        refused=client.post(f'/api/runs/{rid}/checks/rerun',json={
            'checks':[{'id':'ar_drop_by_product','source':'file','path':'outside.py'}]})
        assert refused.status_code==400,refused.text
        job=client.post(f'/api/runs/{rid}/checks/rerun',json={})
        assert job.status_code==200,job.text
        job_id=job.json()['job_id'];deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            status=client.get(f'/api/runs/{rid}/checks/jobs/{job_id}').json()
            if status['status'] in ('done','failed'):break
            time.sleep(.1)
        assert status['status']=='done',status
    engine.dispose()


def test_historic_html_links_use_current_https_origin():
    source='<a href="http://127.0.0.1:5173/?page=registry&amp;run=old&amp;filters=%7B%7D">app</a>'
    result=public_report_links(source,'https://now.trycloudflare.com','old')
    assert '127.0.0.1' not in result
    assert 'https://now.trycloudflare.com/?page=registry&amp;run=old&amp;filters=%7B%7D' in result


def test_launcher_sets_shared_policy_and_same_database(tmp_path):
    env=child_env({'users':{'bob':'hash'},'data_root':str(tmp_path),'db_dir':'existing-db'},'https://x.trycloudflare.com')
    assert env['REPORT_ACCESS']=='shared'
    assert env['DB_DIR']=='existing-db'
    assert env['DATA_DIR']==str(tmp_path)
    assert env['FRONTEND_BASE_URL']==env['APP_BASE_URL']==env['PUBLIC_ORIGIN']


def test_tunnel_log_url_detection():
    lines=queue.Queue();lines.put('URL: https://safe-name.trycloudflare.com')
    class Process:
        def poll(self):return None
    assert find_origin(lines,Process(),timeout=1)=='https://safe-name.trycloudflare.com'


def test_public_rejects_injected_code_disguised_as_standard_check():
    from engine.platform_checks_adapter import validate_staging_checks
    cfg={'checks':[{'id':'ar_drop_by_product','source':'file','path':'elsewhere.py',
                    'code':'print("untrusted")','sha256':'bad'}]}
    with pytest.raises(ValueError):validate_staging_checks(cfg)
    with pytest.raises(ValueError):validate_staging_checks(cfg,allow_frozen=True)


def test_hosted_template_uses_approved_external_dataset(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','staging')
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    monkeypatch.setattr(configs,'DEFAULT',ROOT/'configs/default_spr.yaml')
    folder=tmp_path/'RUN-20260827-0001';folder.mkdir()
    cfg=yaml.safe_load(configs.get_template()['yaml'])
    assert cfg['dataset']['path']==folder.as_posix()
    assert len(cfg['checks'])==5
