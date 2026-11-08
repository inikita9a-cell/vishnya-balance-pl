"""P0-07 compatibility tests migrated from CHECK_ID/ARGUMENT union to ROW_ID.

The old aggregation of several matching check rows was ambiguous: a click on
CNT=1 could return 2 APP_IDs. A legacy request is now accepted only when it
identifies a single row; otherwise HTTP 409 tells the client to pass ROW_ID.
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from engine.mart_api import MartAPI


def _row(argument, apps, cnt, filters=None):
    return {'CHECK_ID': 'c1', 'LABEL': 'demo', 'SOURCE': 'AFTER',
            'RESULT': 'FAIL', 'ARGUMENT': argument, 'APP_IDS': apps,
            'CNT': cnt, 'TOTAL': 100, 'METRIC': None, 'CONFIDENCE': 'LOW',
            'FILTERS': filters}


@pytest.fixture
def local_api(tmp_path, monkeypatch):
    from backend import auth
    monkeypatch.setattr(auth, 'get_run_readable', lambda rid, user: None, raising=False)
    from backend.api import check_apps_api, checks_api

    def readable(rid, user):
        if rid != 'run_test' or user != 'alice':
            raise HTTPException(404, 'run not found')

    monkeypatch.setattr(check_apps_api, 'get_run_readable', readable)
    monkeypatch.setattr(checks_api, 'get_run_readable', readable)
    run_dir = tmp_path / 'runs' / 'run_test'
    run_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(checks_api.router)
    app.include_router(check_apps_api.router)
    app.dependency_overrides[check_apps_api.current_user] = lambda: 'alice'
    client = TestClient(app)

    def save(rows, apps):
        (run_dir / 'checks.json').write_text(json.dumps(rows), encoding='utf-8')
        comparison = pd.DataFrame({
            'APP_ID': apps, 'PATH': ['p'] * len(apps), 'ARRAY_KEY': [''] * len(apps),
            'KEY': ['p'] * len(apps), 'DIFF_FLAG': [0] * len(apps),
            'CHANGE_TYPE': ['SAME'] * len(apps),
            'VALUE_BEFORE': ['v'] * len(apps), 'VALUE_AFTER': ['v'] * len(apps),
        })
        segments = pd.DataFrame({'APP_ID': list(dict.fromkeys(apps))})
        mart = MartAPI(comparison, segments)
        monkeypatch.setattr(MartAPI, 'from_run', classmethod(lambda cls, path: mart))
        return client.get('/api/runs/run_test/checks').json()

    def request(**kwargs):
        return client.post('/api/runs/run_test/checks/c1/apps', json=kwargs)

    return save, request, client, check_apps_api, checks_api


def test_expand_full_rows_only(local_api):
    save, request, *_ = local_api
    check, = save([_row('A', ['x', 'y'], 2)], ['x', 'y'])
    response = request(row_id=check['ROW_ID'])
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 2
    assert response.json()['truncated'] is False


def test_expand_truncated_rows_with_filters(local_api):
    save, request, *_ = local_api
    check, = save([_row('A', ['x', 'y'], 3, {'app_ids': ['x', 'y', 'z']})], ['x', 'y', 'z'])
    response = request(row_id=check['ROW_ID'])
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 3
    assert set(response.json()['items']) == {'x', 'y', 'z'}


def test_mixed_full_and_truncated_rows_are_independent(local_api):
    save, request, *_ = local_api
    checks = save([_row('A', ['x', 'y'], 2),
                   _row('B', ['z'], 2, {'app_ids': ['z', 'w']})], ['x', 'y', 'z', 'w'])
    assert request().status_code == 409
    first = request(row_id=checks[0]['ROW_ID'])
    second = request(row_id=checks[1]['ROW_ID'])
    assert first.status_code == second.status_code == 200
    assert set(first.json()['items']) == {'x', 'y'}
    assert set(second.json()['items']) == {'z', 'w'}


def test_truncated_without_filters_returns_422(local_api):
    save, request, *_ = local_api
    checks = save([_row('A', ['x', 'y'], 2), _row('B', ['z'], 2)], ['x', 'y', 'z'])
    response = request(row_id=checks[1]['ROW_ID'])
    assert response.status_code == 422
    assert 'no FILTERS' in response.json()['detail']


def test_filters_count_mismatch_returns_422(local_api):
    save, request, *_ = local_api
    check, = save([_row('A', ['x'], 5, {'app_ids': ['x', 'y']})], ['x', 'y'])
    response = request(row_id=check['ROW_ID'])
    assert response.status_code == 422
    assert 'recovered 2' in response.json()['detail']


def test_pagination_truncated_flag(local_api):
    save, request, *_ = local_api
    apps = [f'a{i:03d}' for i in range(25)]
    check, = save([_row('A', apps[:5], 25, {'app_ids': apps})], apps)
    page = request(row_id=check['ROW_ID'], limit=10, offset=0)
    assert page.status_code == 200, page.text
    assert page.json()['total'] == 25
    assert page.json()['truncated'] is True
    assert len(page.json()['items']) == 10
    page2 = request(row_id=check['ROW_ID'], limit=100, offset=20)
    assert page2.status_code == 200
    assert set(page2.json()['items']) == set(apps[20:])


def test_foreign_run_returns_404(local_api, monkeypatch):
    save, request, client, check_apps_api, checks_api = local_api
    save([_row('A', ['x'], 1)], ['x'])
    def deny(rid, user):
        raise HTTPException(404, 'run not found')
    monkeypatch.setattr(check_apps_api, 'get_run_readable', deny)
    monkeypatch.setattr(checks_api, 'get_run_readable', deny)
    assert request().status_code == 404
    assert client.get('/api/runs/run_test/checks').status_code == 404
