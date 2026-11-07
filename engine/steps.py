"""Чистые шаги модуля 3. Специфика данных задаётся конфигурацией."""
from copy import deepcopy
from fnmatch import fnmatchcase
from itertools import combinations
import json
import math
from bisect import bisect_left
from .paths import PathMatcher, ArrayRules


def serialize(value):
    """Единое представление листьев; отсутствие строки не равно строке NULL."""
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite number')
    return str(value)


def _get(obj, path):
    for part in path.split('.'):
        if not isinstance(obj, dict) or part not in obj:
            raise KeyError(path)
        obj = obj[part]
    return obj


def _fields(obj, prefix=''):
    for key, value in obj.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            yield from _fields(value, path)
        elif not isinstance(value, list):
            yield path


def resolve_array_rules(documents, cfg):
    """Выбирает общие ключи для обоих срезов; возвращает копию конфига.

    Кандидат должен быть заполнен и уникален в каждом непустом массиве
    данного пути. Проверяются одиночные, затем составные пары кандидатов.
    Без надёжного ключа используется индекс с предупреждением в flatten.
    """
    result = deepcopy(cfg)
    fcfg = result.setdefault('flatten', {})
    arrays = fcfg.setdefault('arrays', {})
    rules = ArrayRules(arrays)
    groups = {}
    def collect(value, path=''):
        if isinstance(value, dict):
            for key, child in value.items():
                collect(child, f'{path}.{key}' if path else key)
        elif isinstance(value, list):
            if value:
                groups.setdefault(path, []).append(value)
            for child in value:
                collect(child, path)
    for doc in documents:
        collect(doc)
    for path, batches in groups.items():
        if rules.lookup(path):
            continue
        items = [x for batch in batches for x in batch]
        if all(not isinstance(x, (dict, list)) for x in items):
            arrays[path] = {'mode': 'value'}
            continue
        candidates = []
        if fcfg.get('auto_key', True) and all(isinstance(x, dict) for x in items):
            fields = sorted(set.intersection(*(set(_fields(x)) for x in items)))
            for pattern in fcfg.get('auto_key_candidates', ['id', '*_id', 'name', 'code']):
                candidates.extend(k for k in fields if fnmatchcase(k, pattern) and k not in candidates)
        chosen = None
        for size in (1, 2):
            for keys in combinations(candidates, size):
                valid = True
                for batch in batches:
                    vals = [tuple(_get(x, k) for k in keys) for x in batch]
                    if any(any(v is None for v in row) for row in vals) or len(set(vals)) != len(vals):
                        valid = False
                        break
                if valid:
                    chosen = list(keys)
                    break
            if chosen:
                break
        arrays[path] = {'mode': 'field', 'key': chosen} if chosen else {'mode': 'index', '_fallback': True}
    return result


def flatten(doc, cfg, *, app_id=None, source=None, issues=None):
    """s3: рекурсивно преобразует dict в список строк с PATH и ARRAY_KEY.

    Для сравнения передайте обоим срезам конфиг resolve_array_rules([before,
    after], cfg), либо используйте flatten_pair. Глубина — число сегментов
    PATH; массив не добавляет сегмент. Проблемы добавляются в issues.
    Входные данные и конфиг не изменяются. Бакеты вычисляет bucketize.
    """
    if not isinstance(doc, dict):
        raise TypeError('Root must be a dict')
    issues = issues if issues is not None else []
    cfg = resolve_array_rules([doc], cfg)
    fc = cfg.get('flatten', {})
    rules = ArrayRules(fc.get('arrays', {}))
    include, exclude = PathMatcher(fc.get('include_paths')), PathMatcher(fc.get('exclude_paths'))
    max_depth = fc.get('max_depth', 10)
    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError('max_depth must be a positive integer')
    sep, composite = fc.get('sep_array_key', '|'), fc.get('sep_composite', '+')
    if not sep or not composite or sep == composite:
        raise ValueError('Array separators must be nonempty and distinct')
    rows = []
    def issue(kind, path, details):
        issues.append(dict(APP_ID=app_id, SOURCE=source, ISSUE=kind, PATH=path, DETAILS=details))
    def escape(value):
        text = serialize(value).replace('%', '%25')
        for char in set(sep + composite):
            text = text.replace(char, '%' + format(ord(char), '02X'))
        return text
    def emit(value, path, keys, scalar_array=False):
        if include and not include.match(path):
            return
        parts = path.split('.')
        row = dict(PREFIX=parts[0], CLASS=parts[1] if len(parts)>1 else parts[0],
                   SUFFIX='.'.join(parts[2:-1]), KEY='' if scalar_array else parts[-1],
                   PATH=path, DEPTH=len(parts), ARRAY_KEY=sep.join(keys),
                   VALUE=serialize(value), ADJUSTED_VALUE=serialize(value))
        if app_id is not None: row['APP_ID'] = str(app_id)
        if source is not None: row['SOURCE'] = source
        rows.append(row)
    def walk(value, path, keys):
        if path and exclude.match(path):
            return
        if path and len(path.split('.')) >= max_depth and isinstance(value, (dict, list)) and value:
            # Не сериализуем скрытые потомки в обход include/exclude.
            if exclude or include:
                issue('DEPTH_TRUNCATED', path, 'Subtree omitted at depth limit because path filters are active')
                return
            issue('DEPTH_TRUNCATED', path, 'Subtree serialized at depth limit')
            emit(value, path, keys)
        elif isinstance(value, dict):
            for key, child in value.items():
                walk(child, f'{path}.{key}' if path else key, keys)
        elif isinstance(value, list):
            if not value: return
            rule = rules.lookup(path) or {'mode': 'index', '_fallback': True}
            mode = rule.get('mode')
            if rule.get('_fallback'):
                issue('ARRAY_KEY_FALLBACK', path, 'No common unique key; positional comparison')
            if mode not in ('field', 'index', 'value'):
                raise ValueError(f'Unknown array mode: {mode}')
            fields = rule.get('key', [])
            if mode == 'field' and (not isinstance(fields, list) or not fields):
                raise ValueError(f'Empty key for {path}')
            for index, child in enumerate(value):
                if mode == 'field':
                    try:
                        values = [_get(child, k) for k in fields]
                        if any(v is None or isinstance(v, (dict, list)) for v in values): raise KeyError('Invalid key')
                        key = composite.join(escape(v) for v in values)
                    except KeyError:
                        issue('ARRAY_KEY_MISSING', path, f'Element {index} omitted: missing key')
                        continue
                elif mode == 'value':
                    if isinstance(child, (dict, list)):
                        raise ValueError(f'value mode requires scalars: {path}')
                    key = escape(child)
                else:
                    key = str(index)
                if mode == 'value': emit(child, path, keys + [key], True)
                else: walk(child, path, keys + [key])
                if mode == 'field' and fc.get('track_order', False):
                    emit(index, path + '.__position__', keys + [key])
        else:
            emit(value, path, keys)
    walk(doc, '', [])
    seen = set()
    for row in rows:
        key = (row['PATH'], row['ARRAY_KEY'])
        if key in seen: issue('DUPLICATE_KEY', row['PATH'], row['ARRAY_KEY'])
        seen.add(key)
    return rows


def flatten_pair(before, after, cfg, *, app_id=None, issues=None):
    """Нормализует пару с согласованными ключами, возвращает (before, after)."""
    resolved = resolve_array_rules([before, after], cfg)
    return tuple(flatten(doc, resolved, app_id=app_id, source=source, issues=issues)
                 for doc, source in ((before, 'BEFORE'), (after, 'AFTER')))


def bucketize(rows, cfg):
    """s4: копирует строки, группируя числовые VALUE в интервалы (a, b].

    Первая граница включена: [a, b]. Вне диапазона отдельные интервалы.
    Правило by_path приоритетнее default_unit/default_num. VALUE сохраняется.
    Булевы, NULL и строки, которые не являются числами, остаются как есть.
    """
    bc = cfg.get('buckets', {})
    rules = ArrayRules(bc.get('by_path', {}))
    dash = bc.get('dash', '–')
    def label(n):
        for divisor, suffix in ((1000000, 'M'), (1000, 'K')):
            if n and n % divisor == 0: return f'{n/divisor:g}{suffix}'
        return f'{n:g}'
    result = []
    for row in rows:
        out = dict(row)
        value = row['VALUE']
        out['ADJUSTED_VALUE'] = value
        try: number = float(value)
        except (ValueError, TypeError):
            result.append(out)
            continue
        edges = rules.lookup(row['PATH'])
        if edges is None:
            edges = bc.get('default_unit' if 0 <= number <= 1 else 'default_num')
        if edges is not None and math.isfinite(number):
            if len(edges)<2 or any(not math.isfinite(x) for x in edges) or any(a>=b for a,b in zip(edges, edges[1:])):
                raise ValueError('Bucket boundaries must be finite and strictly increasing')
            i = bisect_left(edges, number)
            if number < edges[0]: text = f'(-∞ {dash} {label(edges[0])})'
            elif number > edges[-1]: text = f'({label(edges[-1])} {dash} +∞)'
            else:
                i = max(1, i)
                text = f'{"[" if i == 1 else "("}{label(edges[i-1])} {dash} {label(edges[i])}]'
            out['ADJUSTED_VALUE'] = text
        result.append(out)
    return result
