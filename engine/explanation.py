"""Read-only P0-11 explanation from the run's immutable prepared artifacts.

No dataset-specific paths, input reread, new calculations or causal claims.
DuckDB predicates/page limits apply before materializing changed rows.
"""
from pathlib import Path

CAUSE_LABELS = {'LOGIC': 'Логика / результаты стратегии', 'INPUT_DATA': 'Входные данные',
                'BOTH': 'Входные данные и результаты стратегии', 'NONE': 'Источник по настроенным группам не определён'}
DISCLAIMER = 'Источник изменений определён по настроенным путям. Это наблюдаемая связь, а не доказанная причина смены решения.'
HEADLINES = {'INCOMPLETE': 'Сравнение неполное', 'DECISION_UNKNOWN': 'Решение не определено',
             'DECISION_CHANGED': 'Решение изменилось',
             'ATTRIBUTES_CHANGED_DECISION_SAME': 'Данные изменились, решение сохранено',
             'UNCHANGED': 'Изменений не обнаружено'}
DETAILS = {
    'INCOMPLETE': 'Часть данных отсутствует, повреждена или неоднозначна. Наблюдаемые различия не подтверждают полноту сравнения.',
    'DECISION_UNKNOWN': 'Не удалось определить решение хотя бы одного среза. Делать вывод о сохранении или смене решения нельзя.',
    'DECISION_CHANGED': 'Решения BEFORE и AFTER различаются. Ниже перечислены наблюдаемые изменения атрибутов.',
    'ATTRIBUTES_CHANGED_DECISION_SAME': 'Найдены изменения атрибутов, но итоговые решения BEFORE и AFTER совпадают.',
    'UNCHANGED': 'В пределах выбранной конфигурации различий атрибутов и решений не обнаружено.',
}


def explain_application(run_dir, app_id, *, limit=200, offset=0, path=None, array_key=None):
    import duckdb
    root = Path(run_dir)
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
        raise ValueError('limit must be 1..1000 and offset nonnegative')
    for name in ('segments.parquet', 'comparison.parquet', 'quality.parquet'):
        if not (root / name).is_file():
            raise FileNotFoundError(f'Explanation needs {name}')
    with duckdb.connect(':memory:') as connection:
        def records(sql, args):
            result = connection.execute(sql, args)
            names = [description[0] for description in result.description]
            return [dict(zip(names, row)) for row in result.fetchall()]

        segments = records('SELECT * FROM read_parquet(?) WHERE APP_ID = ? LIMIT 2',
                           [str(root / 'segments.parquet'), app_id])
        if not segments:
            raise KeyError(app_id)
        if len(segments) != 1:
            raise ValueError('Ambiguous APP_ID in segments')
        segment = segments[0]
        params = [str(root / 'comparison.parquet'), app_id]
        where = 'APP_ID = ? AND DIFF_FLAG = 1'
        total = connection.execute('SELECT count(*) FROM read_parquet(?) WHERE '+where, params).fetchone()[0]
        if path is not None:
            where += ' AND PATH = ?'
            params.append(path)
        if array_key is not None:
            where += ' AND ARRAY_KEY = ?'
            params.append(array_key)
        filtered = connection.execute('SELECT count(*) FROM read_parquet(?) WHERE '+where, params).fetchone()[0]
        changed = records('SELECT PATH, ARRAY_KEY, CHANGE_TYPE, VALUE_BEFORE, VALUE_AFTER, '
                          'ADJUSTED_BEFORE, ADJUSTED_AFTER FROM read_parquet(?) WHERE '+where+
                          ' ORDER BY PATH, ARRAY_KEY LIMIT ? OFFSET ?', [*params, limit, offset])
        qparams = [str(root / 'quality.parquet'), app_id]
        issue_count = connection.execute('SELECT count(*) FROM read_parquet(?) WHERE APP_ID = ?', qparams).fetchone()[0]
        quality = records('SELECT SOURCE, ISSUE, PATH, DETAILS FROM read_parquet(?) WHERE APP_ID = ? '
                          'ORDER BY SOURCE, ISSUE, PATH, DETAILS LIMIT 100', qparams)

    complete = segment.get('COMPARISON_COMPLETE') == 1
    comparable = segment.get('DECISION_COMPARABLE') == 1
    decision_changed = bool(segment.get('DECISION_CHANGED')) if complete and comparable else None
    code = ('INCOMPLETE' if not complete else 'DECISION_UNKNOWN' if not comparable
            else 'DECISION_CHANGED' if decision_changed else
            'ATTRIBUTES_CHANGED_DECISION_SAME' if total else 'UNCHANGED')
    cause = segment.get('CAUSE') or 'NONE'
    for row in changed:
        row['BEFORE'] = {'present': row['CHANGE_TYPE'] != 'ATTRIBUTE_NEW', 'value': row.pop('VALUE_BEFORE')}
        row['AFTER'] = {'present': row['CHANGE_TYPE'] != 'ATTRIBUTE_LOST', 'value': row.pop('VALUE_AFTER')}
    return {
        'schema_version': 1, 'run_id': root.name, 'app_id': app_id,
        'decision': {'before': segment.get('DECISION_BEFORE'), 'after': segment.get('DECISION_AFTER'),
                     'comparable': comparable, 'changed': decision_changed},
        'reason': {'before': segment.get('REASON_BEFORE'), 'after': segment.get('REASON_AFTER'),
                   'changed': (segment.get('REASON_BEFORE') != segment.get('REASON_AFTER')) if complete else None},
        'comparison': {'complete': complete, 'observed_changes': int(total), 'has_quality_issues': issue_count > 0},
        'interpretation': {'code': code, 'headline': HEADLINES[code], 'detail': DETAILS[code],
                           'source': cause, 'source_label': CAUSE_LABELS.get(cause, str(cause)), 'disclaimer': DISCLAIMER},
        'changes': {'total': int(total), 'filtered_total': int(filtered), 'limit': limit, 'offset': offset,
                    'path': path, 'array_key': array_key, 'rows': changed},
        'quality': {'total': int(issue_count), 'truncated': issue_count > len(quality), 'items': quality},
    }
