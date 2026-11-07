"""Generate a self-contained HTML protocol (CSS and data inline, no CDN).

The downloaded HTML retains absolute links to the running frontend.
Set FRONTEND_BASE_URL / frontend_base_url when the UI uses a separate origin.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


def _esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def frontend_link(cfg: dict, run_id: str, app_id=None) -> str:
    """Use the existing React query routes, including an APP_ID registry filter."""
    base = str(cfg.get('frontend_base_url') or os.getenv('FRONTEND_BASE_URL')
               or cfg.get('app_base_url') or os.getenv('APP_BASE_URL')
               or 'http://127.0.0.1:5173')
    parsed = urlsplit(base)
    if (parsed.scheme not in ('http', 'https') or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError('frontend_base_url must be an absolute http(s) frontend URL without query/fragment/credentials')
    params = {'page': 'report' if app_id is None else 'registry', 'run': str(run_id)}
    if app_id is not None:
        params['filters'] = json.dumps({'APP_ID': str(app_id)}, ensure_ascii=False, separators=(',', ':'))
    path = parsed.path or '/'
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(params, quote_via=quote), ''))


def write_report_html(run_dir: str | Path, cfg: dict | None = None) -> Path:
    root = Path(run_dir)
    cfg = cfg or {}
    summary_file, checks_file = root / 'summary.json', root / 'checks.json'
    if not summary_file.is_file() or not checks_file.is_file():
        raise FileNotFoundError('report_html requires both summary.json and checks.json')
    summary = json.loads(summary_file.read_text(encoding='utf-8'))
    checks = json.loads(checks_file.read_text(encoding='utf-8'))
    if not isinstance(summary, dict) or not isinstance(checks, list):
        raise ValueError('Invalid report data structures')
    run_id = root.name
    summary_url = frontend_link(cfg, run_id)

    def row_cells(values):
        return '<tr>' + ''.join(f'<td>{_esc(v)}</td>' for v in values) + '</tr>'

    verdict = summary.get('verdict') or {}
    approval = summary.get('approval_rates') or {}
    checks_summary = summary.get('checks') or {}
    counts = [('Заявок', summary.get('total_apps')),
              ('С различиями', summary.get('apps_with_diff')),
              ('Сменили решение', summary.get('apps_decision_changed')),
              ('Проверок PASS', checks_summary.get('pass')),
              ('Проверок FAIL', checks_summary.get('fail')),
              ('Проверок ERROR', checks_summary.get('error'))]
    cards = ''.join(f'<div class="metric"><div class="num">{_esc(v)}</div>'
                    f'<div>{_esc(k)}</div></div>' for k, v in counts)
    table_rows = []
    for item in checks:
        ids = item.get('APP_IDS') or []
        links = ', '.join(f'<a href="{_esc(frontend_link(cfg, run_id, a))}">{_esc(a)}</a>'
                          for a in ids[:10])
        if len(ids) > 10:
            links += f' и ещё {len(ids) - 10}'
        cells = [item.get('CHECK_ID', ''), item.get('LABEL', ''), item.get('SOURCE', ''),
                 item.get('ARGUMENT', ''), item.get('CNT', ''), item.get('TOTAL', ''),
                 item.get('METRIC', ''), item.get('RESULT', ''), item.get('CONFIDENCE', '')]
        klass = 'fail' if item.get('RESULT') in ('FAIL', 'ERROR') else 'pass'
        # Links are generated only from encoded identifiers and our chosen base URL.
        table_rows.append('<tr class="' + klass + '">' +
                          ''.join(f'<td>{_esc(v)}</td>' for v in cells) +
                          f'<td>{links}</td></tr>')
    matrix_rows = ''.join(row_cells((x.get('before'), x.get('after'), x.get('count')))
                          for x in summary.get('decision_transitions', []))
    top_rows = ''.join(row_cells((x.get('path'), x.get('apps_changed'), x.get('rows_changed')))
                       for x in summary.get('top_changed_paths', []))
    doc = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Протокол проверки — {_esc(run_id)}</title>
<style>
:root{{--bg:#f6f8fb;--text:#203044;--border:#dce3ec}}
body{{font:15px/1.55 system-ui,Arial,sans-serif;background:var(--bg);color:var(--text);max-width:1250px;margin:32px auto;padding:0 20px}}
h1,h2{{margin:20px 0 10px}}.muted{{color:#637487}}.metrics{{display:flex;flex-wrap:wrap;gap:12px}}
.metric{{background:white;border:1px solid var(--border);border-radius:10px;padding:12px 22px;min-width:130px}}
.num{{font-size:29px;font-weight:750}}table{{width:100%;border-collapse:collapse;background:white;overflow-wrap:anywhere}}
th,td{{text-align:left;padding:8px 10px;border:1px solid var(--border);vertical-align:top}}th{{background:#eaf0f7}}
tr.fail td:nth-child(8){{color:#a13232;font-weight:700}}tr.pass td:nth-child(8){{color:#136d42;font-weight:700}}
a{{color:#205cb7}}.scroll{{overflow-x:auto}}.subtle{{font-size:13px}}
</style></head><body>
<h1>Протокол анализа изменений</h1>
<p class="muted">Прогон: <strong>{_esc(run_id)}</strong> · Вердикт: <strong>{_esc(verdict.get('status'))}</strong></p>
<div class="metrics">{cards}</div>
<p>Доля одобрений BEFORE: {_esc(approval.get('before_rate'))} · AFTER: {_esc(approval.get('after_rate'))} · Изменение, п.п.: {_esc(approval.get('delta_pp'))}</p>
<p><a href="{_esc(summary_url)}">Открыть онлайн-аналитику запуска</a> (нужен доступ к работающему приложению).</p>
<h2>Матрица решений</h2><div class="scroll"><table><thead><tr><th>BEFORE</th><th>AFTER</th><th>Заявок</th></tr></thead>
<tbody>{matrix_rows}</tbody></table></div>
<h2>Топ изменившихся атрибутов</h2><div class="scroll"><table><thead><tr><th>Атрибут</th><th>Заявок</th><th>Строк</th></tr></thead>
<tbody>{top_rows}</tbody></table></div>
<h2>Автоматические проверки</h2><div class="scroll"><table><thead><tr>
<th>ID</th><th>Проверка</th><th>Срез</th><th>Аргумент</th><th>Кол-во</th><th>Всего</th><th>Метрика</th><th>Результат</th><th>Уверенность</th><th>Заявки</th>
</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
<p class="muted subtle">Статический документ с данными и стилями внутри. Ссылки на заявки требуют запущенного сервера.</p>
</body></html>'''
    dest = root / 'report.html'
    temporary = root / f'.report.{os.getpid()}.tmp'
    try:
        temporary.write_text(doc, encoding='utf-8')
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)
    return dest
