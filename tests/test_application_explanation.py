"""P0-11: honest interpretation, exact changed rows, pagination and owned REST."""
from copy import deepcopy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import auth, runs
from backend.api import explanation_api
from backend.db import Base
from backend.models import Run
from engine.explanation import explain_application
from engine.pipeline import run_pipeline
from tools.p0_10_acceptance import build_synthetic, base_document, input_hashes


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp('p011')
    cfg = build_synthetic(output / 'dataset')
    before, after = Path(cfg['dataset']['path']) / 'before', Path(cfg['dataset']['path']) / 'after'
    source = base_document()
    changed = deepcopy(source)
    changed['audit_result'] = {'decision': 'DECLINE', 'reason': 'LIMIT'}
    changed['source']['score'] = 11
    rejected = deepcopy(source)
    rejected['audit_result'] = {'decision': 'DECLINE', 'reason': 'A'}
    reason_only = deepcopy(rejected)
    reason_only['audit_result']['reason'] = 'B'
    unknown = deepcopy(source)
    unknown['audit_result'].pop('decision')
    empty = deepcopy(source)
    empty['source']['empty'] = ''
    null = deepcopy(empty)
    null['source']['empty'] = None
    null['source']['new_null'] = None
    null['source'].pop('nullable')
    for app_id, pair in {'decision_changed': (source, changed), 'reason_only': (rejected, reason_only),
                         'unknown_decision': (unknown, source), 'null_vs_absent': (empty, null)}.items():
        for directory, doc in zip((before, after), pair):
            (directory / f'{app_id}.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    root = output / 'ready_run'
    run_pipeline(cfg, root)
    return root


@pytest.mark.parametrize('app_id,code,changed,complete', [
    ('same', 'UNCHANGED', False, True),
    ('attribute_changes', 'ATTRIBUTES_CHANGED_DECISION_SAME', False, True),
    ('decision_changed', 'DECISION_CHANGED', True, True),
    ('no_reason', 'ATTRIBUTES_CHANGED_DECISION_SAME', False, True),
    ('missing_after', 'INCOMPLETE', None, False),
    ('missing_before', 'INCOMPLETE', None, False),
    ('corrupt_json', 'INCOMPLETE', None, False),
    ('duplicate_keys', 'INCOMPLETE', None, False),
    ('array_fallback', 'INCOMPLETE', None, False),
    ('unknown_decision', 'DECISION_UNKNOWN', None, True),
])
def test_interpretation_distinguishes_decision_data_and_unknown(prepared, app_id, code, changed, complete):
    value = explain_application(prepared, app_id)
    assert value['interpretation']['code'] == code
    assert value['decision']['changed'] is changed
    assert value['comparison']['complete'] is complete
    assert 'не доказанная причина' in value['interpretation']['disclaimer']
    json.dumps(value, ensure_ascii=False, allow_nan=False)


def test_reason_before_after_and_missing_reason_are_not_fabricated(prepared):
    missing = explain_application(prepared, 'no_reason')
    assert missing['decision']['before'] == missing['decision']['after'] == 'DECLINE'
    assert missing['reason']['before'] == 'LIMIT' and missing['reason']['after'] is None
    assert any(q['ISSUE'] == 'DECISION_WITHOUT_REASON' and q['PATH'] == 'audit_result.reason'
               for q in missing['quality']['items'])
    only_reason = explain_application(prepared, 'reason_only')
    assert only_reason['reason'] == {'before': 'A', 'after': 'B', 'changed': True}
    assert only_reason['decision']['changed'] is False and only_reason['changes']['total'] == 1


def test_presence_null_empty_and_attribute_loss_are_distinct(prepared):
    value = explain_application(prepared, 'null_vs_absent')
    rows = {row['PATH']: row for row in value['changes']['rows']}
    assert rows['source.empty']['BEFORE'] == {'present': True, 'value': ''}
    assert rows['source.empty']['AFTER'] == {'present': True, 'value': 'NULL'}
    assert rows['source.nullable']['BEFORE'] == {'present': True, 'value': 'NULL'}
    assert rows['source.nullable']['AFTER'] == {'present': False, 'value': None}
    assert rows['source.new_null']['BEFORE'] == {'present': False, 'value': None}
    assert rows['source.new_null']['AFTER'] == {'present': True, 'value': 'NULL'}


def test_pagination_filters_and_array_keys_preserve_exact_counts(prepared):
    all_rows = explain_application(prepared, 'null_vs_absent')['changes']
    first = explain_application(prepared, 'null_vs_absent', limit=1, offset=0)['changes']
    second = explain_application(prepared, 'null_vs_absent', limit=1, offset=1)['changes']
    assert all_rows['total'] == 3 and first['filtered_total'] == second['filtered_total'] == 3
    assert first['rows'] != second['rows'] and first['rows'] == all_rows['rows'][:1]
    row = explain_application(prepared, 'named_model')['changes']['rows'][0]
    selected = explain_application(prepared, 'named_model', path=row['PATH'], array_key=row['ARRAY_KEY'])
    assert selected['changes']['filtered_total'] == 1 and selected['changes']['rows'] == [row]
    empty = explain_application(prepared, 'named_model', path="' OR 1=1 --")
    assert empty['changes']['filtered_total'] == 0 and empty['changes']['total'] == 1


def test_no_raw_input_needed_and_no_run_files_changed(prepared):
    before = input_hashes(prepared)
    # The endpoint receives only prepared artifacts, not dataset config or source path.
    explain_application(prepared, 'decision_changed')
    assert input_hashes(prepared) == before


@pytest.fixture
def api(prepared, tmp_path, monkeypatch):
    database = create_engine(f'sqlite:///{tmp_path / "app.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(database)
    factory = sessionmaker(bind=database)
    monkeypatch.setattr(auth, 'SessionLocal', factory)
    monkeypatch.setattr(runs, 'RUNS_DIR', prepared.parent)
    with factory() as db:
        db.add(Run(id=prepared.name, started_by='alice', status='done', config_snapshot='{}'))
        db.add(Run(id='pending', started_by='alice', status='running', config_snapshot='{}'))
        db.add(Run(id='missing_files', started_by='alice', status='done', config_snapshot='{}'))
        db.commit()
    app = FastAPI()
    app.include_router(explanation_api.router)
    client = TestClient(app)
    client.cookies.set('spr_user', 'alice')
    return client, prepared.name


def test_rest_owned_run_and_exact_application(api):
    client, rid = api
    response = client.get(f'/api/runs/{rid}/apps/decision_changed/explanation')
    assert response.status_code == 200 and response.json()['decision']['changed'] is True
    assert client.get(f'/api/runs/{rid}/apps/unknown/explanation').status_code == 404
    client.cookies.set('spr_user', 'bob')
    assert client.get(f'/api/runs/{rid}/apps/decision_changed/explanation').status_code == 404
    client.cookies.clear()
    assert client.get(f'/api/runs/{rid}/apps/decision_changed/explanation').status_code == 401


@pytest.mark.parametrize('query', ['limit=0', 'limit=1001', 'offset=-1'])
def test_rest_rejects_bad_page_bounds(api, query):
    client, rid = api
    assert client.get(f'/api/runs/{rid}/apps/same/explanation?{query}').status_code == 422


def test_rest_not_ready_missing_files_and_sql_literal_app_id(api):
    client, rid = api
    assert client.get('/api/runs/pending/apps/same/explanation').status_code == 409
    assert client.get('/api/runs/missing_files/apps/same/explanation').status_code == 409
    assert client.get(f'/api/runs/{rid}/apps/x%27%20OR%20%271%27=%271/explanation').status_code == 404
