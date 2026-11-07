"""P0-08: standalone HTML links roundtrip to the existing frontend query routes."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from engine.report_html import frontend_link, write_report_html


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.append(dict(attrs)['href'])


@pytest.fixture(autouse=True)
def clear_base_urls(monkeypatch):
    monkeypatch.delenv('FRONTEND_BASE_URL', raising=False)
    monkeypatch.delenv('APP_BASE_URL', raising=False)


def test_html_links_open_summary_and_exact_application_not_json_api(tmp_path):
    root = tmp_path / 'run_Юникод'
    root.mkdir()
    app_id = 'APP A&1/Юникод#?="<'
    (root / 'summary.json').write_text(json.dumps({'total_apps': 1, 'verdict': {'status': 'REVIEW_REQUIRED'}}), encoding='utf-8')
    (root / 'checks.json').write_text(json.dumps([{'CHECK_ID': 'mine', 'LABEL': '<script>alert(1)</script>',
        'APP_IDS': [app_id], 'RESULT': 'FAIL', 'CNT': 1, 'TOTAL': 1}], ensure_ascii=False), encoding='utf-8')
    report = write_report_html(root, {'frontend_base_url': 'https://example.org/strategy/'})
    text = report.read_text(encoding='utf-8')
    links = Links()
    links.feed(text)
    assert len(links.urls) == 2
    summary, application = [urlsplit(url) for url in links.urls]
    assert summary.scheme == 'https' and summary.netloc == 'example.org' and summary.path == '/strategy/'
    assert parse_qs(summary.query) == {'page': ['report'], 'run': [root.name]}
    params = parse_qs(application.query)
    assert params['page'] == ['registry'] and params['run'] == [root.name]
    assert json.loads(params['filters'][0]) == {'APP_ID': app_id}
    assert '/api/runs/' not in text and 'file://' not in text
    assert '<script>alert(1)</script>' not in text
    assert '&lt;script&gt;' in text and 'charset="utf-8"' in text


@pytest.mark.parametrize('cfg,environment,expected', [
    ({}, {}, 'http://127.0.0.1:5173'),
    ({'app_base_url': 'https://legacy.example'}, {}, 'https://legacy.example'),
    ({}, {'APP_BASE_URL': 'https://old-env.example'}, 'https://old-env.example'),
    ({'frontend_base_url': 'https://ui.example'}, {'FRONTEND_BASE_URL': 'https://env.example'}, 'https://ui.example'),
    ({'app_base_url': 'http://api.example'}, {'FRONTEND_BASE_URL': 'https://ui.example'}, 'https://ui.example'),
])
def test_frontend_base_url_selection(cfg, environment, expected, monkeypatch):
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    url = frontend_link(cfg, 'run')
    assert url.startswith(expected + '/?')


@pytest.mark.parametrize('base', ['javascript:alert(1)', '//example.org', '/relative',
                                  'https://user:password@example.org', 'https://example.org/?page=other',
                                  'https://example.org/#/old-route'])
def test_bad_frontend_base_is_rejected(base):
    with pytest.raises(ValueError, match='frontend_base_url'):
        frontend_link({'frontend_base_url': base}, 'run')


def test_run_id_and_app_id_do_not_become_query_parameters():
    run_id, app_id = 'run&other=1/?#', 'app&run=evil?'
    parsed = urlsplit(frontend_link({}, run_id, app_id))
    params = parse_qs(parsed.query)
    assert set(params) == {'page', 'run', 'filters'}
    assert params['run'] == [run_id] and json.loads(params['filters'][0]) == {'APP_ID': app_id}
