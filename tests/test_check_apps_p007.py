"""P0-07: unique check rows, complete APP_IDS and exact-row drilldown.

No parquet fixture is needed: filters are exercised against a real in-memory
MartAPI, while HTTP requests exercise the real FastAPI routers.
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from engine.check_row_ids import assign_check_row_ids
from engine.checks_service import _normalize_row, run_checks
from engine.mart_api import MartAPI


def row(*, source='AFTER', argument='same', app_ids=None, cnt=None,
        filters=None, check_id='attr', result='FAIL'):
    app_ids = list(app_ids or [])
    return {
        'CHECK_ID': check_id, 'LABEL': 'Изменился состав атрибутов',
        'SOURCE': source, 'ARGUMENT': argument, 'RESULT': result,
        'APP_IDS': app_ids, 'CNT': len(app_ids) if cnt is None else cnt,
        'TOTAL': 12, 'METRIC': None, 'CONFIDENCE': 'LOW', 'FILTERS': filters,
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    from backend import auth
    # The attached project ZIP precedes the newer get_run_readable helper.
    # This bootstrap only affects the test runtime and is not a shipped patch.
    monkeypatch.setattr(auth, 'get_run_readable', lambda rid, user: True, raising=False)
    from backend.api import checks_api, check_apps_api

    def readable(rid, user):
        if user != 'alice' or rid != 'demo':
            raise HTTPException(404, 'run not found')

    monkeypatch.setattr(checks_api, 'get_run_readable', readable)
    monkeypatch.setattr(check_apps_api, 'get_run_readable', readable)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'runs' / 'demo'
    out.mkdir(parents=True)

    # Both WHERE checks and COUNT(DISTINCT APP_ID) use the real MartAPI.
    comparison = pd.DataFrame({
        'APP_ID': ['new', 'lost', 'x', 'y', 'z', 'q', 'new'],
        'PATH': ['attr', 'attr', 'rule', 'rule', 'rule', 'rule', 'other'],
        'ARRAY_KEY': ['', '', '', '', '', '', ''],
        'KEY': ['attr', 'attr', 'rule', 'rule', 'rule', 'rule', 'other'],
        'DIFF_FLAG': [1] * 7,
        'CHANGE_TYPE': ['ATTRIBUTE_NEW', 'ATTRIBUTE_LOST', 'VALUE_CHANGED',
                        'VALUE_CHANGED', 'VALUE_CHANGED', 'VALUE_CHANGED', 'VALUE_CHANGED'],
        'VALUE_BEFORE': [''] * 7, 'VALUE_AFTER': ['x'] * 7,
    })
    segments = pd.DataFrame({'APP_ID': ['new', 'lost', 'x', 'y', 'z', 'q']})
    mart = MartAPI(comparison, segments)
    monkeypatch.setattr(MartAPI, 'from_run', classmethod(lambda cls, path: mart))
    web_app = FastAPI()
    web_app.include_router(checks_api.router)
    web_app.include_router(check_apps_api.router)
    web_app.dependency_overrides[checks_api.current_user] = lambda: 'alice'
    client = TestClient(web_app)

    def save(rows):
        (out / 'checks.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        return client.get('/api/runs/demo/checks').json()

    def apps(check_id='attr', **payload):
        return client.post(f'/api/runs/demo/checks/{check_id}/apps', json=payload)

    return save, apps, client


def test_same_check_result_argument_selects_exact_source_row(api):
    save, apps, _ = api
    result = save([
        row(source='AFTER', app_ids=['new']),
        row(source='BEFORE', app_ids=['lost']),
    ])
    assert len({r['ROW_ID'] for r in result}) == 2
    for expected, item in zip(('new', 'lost'), result):
        response = apps(row_id=item['ROW_ID'])
        assert response.status_code == 200, response.text
        assert response.json()['items'] == [expected]
        assert response.json()['total'] == response.json()['declared_cnt'] == 1
        assert response.json()['row_id'] == item['ROW_ID']
    ambiguous = apps(result='FAIL', argument='same')
    assert ambiguous.status_code == 409
    assert 'ROW_ID' in ambiguous.json()['detail']


def test_stop_factor_rows_with_identical_properties_remain_separate(api):
    save, apps, _ = api
    rows = save([
        row(argument='AGELOW@21', app_ids=['x'], check_id='stop'),
        row(argument='AGELOW@21', app_ids=['y'], check_id='stop'),
    ])
    assert rows[0]['ROW_ID'] != rows[1]['ROW_ID']
    assert apps('stop', row_id=rows[0]['ROW_ID']).json()['items'] == ['x']
    assert apps('stop', row_id=rows[1]['ROW_ID']).json()['items'] == ['y']


def test_duplicate_app_ids_with_matching_raw_length_is_rejected(api):
    save, apps, _ = api
    check, = save([row(app_ids=['x', 'x'], cnt=2)])
    response = apps(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'duplicate' in response.json()['detail']


def test_duplicate_app_ids_even_with_filters_is_rejected(api):
    save, apps, _ = api
    check, = save([row(app_ids=['x', 'x'], cnt=3, filters={'app_ids': ['x', 'y', 'z']})])
    response = apps(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'duplicate' in response.json()['detail']


def test_truncated_filter_expansion_and_page_navigation(api):
    save, apps, _ = api
    check, = save([row(app_ids=['x'], cnt=3, filters={'app_ids': ['x', 'y', 'z']})])
    page_1 = apps(row_id=check['ROW_ID'], limit=2, offset=0)
    assert page_1.status_code == 200, page_1.text
    assert page_1.json()['items'] == ['x', 'y']
    assert page_1.json()['total'] == 3
    assert page_1.json()['has_more'] is True
    page_2 = apps(row_id=check['ROW_ID'], limit=2, offset=2)
    assert page_2.status_code == 200, page_2.text
    assert page_2.json()['items'] == ['z']
    assert page_2.json()['has_more'] is False
    assert page_2.json()['source'] == 'FILTERS'


def test_truncated_missing_filters_fails_closed(api):
    save, apps, _ = api
    check, = save([row(app_ids=['x'], cnt=2)])
    response = apps(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'no FILTERS' in response.json()['detail']


def test_filters_cannot_return_wrong_count(api):
    save, apps, _ = api
    check, = save([row(app_ids=['x'], cnt=3, filters={'app_ids': ['x', 'y']})])
    response = apps(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'recovered 2' in response.json()['detail']


def test_filters_must_include_previously_returned_sample(api):
    save, apps, _ = api
    check, = save([row(app_ids=['q'], cnt=3, filters={'app_ids': ['x', 'y', 'z']})])
    response = apps(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'does not include' in response.json()['detail']


def test_single_row_old_request_still_works(api):
    save, apps, _ = api
    save([row(app_ids=['x'])])
    response = apps(result='FAIL', argument='same')
    assert response.status_code == 200
    assert response.json()['items'] == ['x']


def test_legacy_checks_json_get_ids_are_stable(api):
    save, apps, _ = api
    before = save([row(app_ids=['x']), row(source='BEFORE', app_ids=['lost'])])
    after = save([row(app_ids=['x']), row(source='BEFORE', app_ids=['lost'])])
    assert [r['ROW_ID'] for r in before] == [r['ROW_ID'] for r in after]
    assert apps(row_id=before[0]['ROW_ID']).json()['items'] == ['x']


def test_exact_duplicate_result_rows_get_distinct_identifiers(api):
    save, apps, _ = api
    r = row(app_ids=['x'])
    rows = save([r, dict(r)])
    assert rows[0]['ROW_ID'] != rows[1]['ROW_ID']
    assert apps(row_id=rows[0]['ROW_ID']).json()['items'] == ['x']


def test_unknown_row_id_does_not_expand_another_one(api):
    save, apps, _ = api
    save([row(app_ids=['x'])])
    assert apps(row_id='nonexistent').status_code == 404


def test_denied_read_never_reveals_row_ids(api, monkeypatch):
    save, apps, client = api
    save([row(app_ids=['x'])])
    from backend.api import checks_api, check_apps_api
    def reject(rid, user):
        raise HTTPException(404, 'run not found')
    monkeypatch.setattr(checks_api, 'get_run_readable', reject)
    monkeypatch.setattr(check_apps_api, 'get_run_readable', reject)
    assert client.get('/api/runs/demo/checks').status_code == 404
    assert apps().status_code == 404


def test_service_rejects_duplicates_during_result_normalization():
    data = row(app_ids=['x', 'x'], cnt=2)
    with pytest.raises(ValueError, match='duplicate'):
        _normalize_row(data, 'attr', 'Label', 0.01)


def test_service_assigns_stable_distinct_row_ids(monkeypatch):
    from engine import checks_service as service
    check_output = [row(app_ids=['x']), row(source='BEFORE', app_ids=['lost'])]
    for r in check_output:
        r.pop('CHECK_ID')
    monkeypatch.setattr(service, 'load_check', lambda *a, **kw: {
        'label': 'demo', 'params': {}, 'entrypoint': lambda mart, params: check_output})
    result = run_checks(None, ['attr'])
    assert len(result) == 2
    assert len({r['ROW_ID'] for r in result}) == 2
    assert [x['ROW_ID'] for x in result] == [x['ROW_ID'] for x in run_checks(None, ['attr'])]


def test_service_broken_check_outputs_single_error_row(monkeypatch):
    from engine import checks_service as service
    bad_output = [row(app_ids=['x']), row(app_ids=['x', 'x'], cnt=2)]
    monkeypatch.setattr(service, 'load_check', lambda *a, **kw: {
        'label': 'demo', 'params': {}, 'entrypoint': lambda mart, params: bad_output})
    result = run_checks(None, ['attr'])
    assert len(result) == 1
    assert result[0]['RESULT'] == 'ERROR'
    assert 'duplicate' in result[0]['ERROR']
    assert result[0]['ROW_ID'].startswith('cr_')
