"""Unicode login must round-trip without changing owners or breaking ASCII sessions."""
import pytest
from test_main_merge_repair import system


@pytest.mark.parametrize('name', ['Никита', 'Анжелика', 'Nga 🍒', 'Nikita%20literal'])
def test_login_roundtrip_and_logout(system, name):
    client = system['client']
    response = client.post('/api/login', json={'name': name})
    assert response.status_code == 200, response.text
    assert response.json()['name'] == name
    assert client.get('/api/me').json()['name'] == name
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_switch_between_unicode_and_legacy_ascii(system):
    client = system['client']
    assert client.post('/api/login', json={'name': 'Никита'}).status_code == 200
    assert client.get('/api/runs/alice_run').status_code == 404
    assert client.post('/api/login', json={'name': 'alice'}).status_code == 200
    assert client.get('/api/me').json()['name'] == 'alice'
    assert client.get('/api/runs/alice_run').status_code == 200
    client.cookies.set('spr_user', 'bob')
    assert client.get('/api/me').json()['name'] == 'bob'
