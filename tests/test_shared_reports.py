"""Shared reports are readable across users; edits and reruns stay owned."""
import pytest
from test_main_merge_repair import system
from backend.api import data_api


@pytest.fixture
def shared(system, monkeypatch):
    monkeypatch.setenv('REPORT_ACCESS', 'shared')
    return system['client']


def test_shared_history_and_existing_report(shared):
    assert {r['id'] for r in shared.get('/api/runs').json()} == {'alice_run', 'bob_run'}
    for path in ['/api/runs/bob_run', '/api/runs/bob_run/steps/s1_discover',
                 '/api/runs/bob_run/summary', '/api/runs/bob_run/checks',
                 '/api/runs/bob_run/report.html', '/api/runs/bob_run/apps/sample/raw',
                 '/api/runs/bob_run/checks/status']:
        response = shared.get(path)
        assert response.status_code == 200, (path, response.text)


@pytest.mark.parametrize('path,method', [('pivot','pivot'), ('drilldown','drilldown'),
                                        ('sankey','get_sankey_data'),
                                        ('explorer/query','explorer_query'),
                                        ('explorer/apps','explorer_apps')])
def test_shared_analytics_post(shared, monkeypatch, path, method):
    monkeypatch.setattr(data_api.duck, method, lambda *a, **kw: [])
    body = {'groupBy': ['PATH']} if path == 'explorer/query' else {}
    response = shared.post('/api/runs/bob_run/' + path, json=body)
    assert response.status_code == 200, response.text


def test_shared_does_not_grant_edits_or_anonymous_access(shared):
    assert shared.post('/api/runs/bob_run/checks/rerun', json={}).status_code == 404
    assert shared.put('/api/configs/2', json={'name':'changed'}).status_code == 404
    assert shared.get('/api/configs/2').status_code == 404
    assert shared.get('/api/runs/missing/summary').status_code == 404
    shared.post('/api/logout')
    assert shared.get('/api/runs').status_code == 401
    assert shared.get('/api/runs/bob_run/summary').status_code == 401


def test_new_user_sees_existing_reports(shared):
    assert shared.post('/api/login', json={'name': 'Новый пользователь'}).status_code == 200
    assert len(shared.get('/api/runs').json()) == 2
    assert shared.get('/api/runs/alice_run/summary').status_code == 200
    assert shared.post('/api/runs/alice_run/checks/rerun', json={}).status_code == 404
