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


NORMAL_COLUMNS = ['APP_ID', 'SOURCE', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY',
                  'KEY', 'PATH', 'DEPTH', 'VALUE', 'ADJUSTED_VALUE']
ROW_KEY = ['APP_ID', 'PATH', 'ARRAY_KEY']
QUALITY_COLUMNS = ['APP_ID', 'ISSUE', 'SOURCE', 'PATH', 'DETAILS']


def discover(dataset, pool=None):
    """s1: возвращает пары файлов, включая сироты, в порядке APP_ID.

    Идентификатор — имя файла без расширения. Два файла с одним ID в срезе
    неоднозначны: ошибка конфигурации. Пустой/неверный каталог — ошибка,
    а отсутствие отдельной заявки допустимо. pool.filter требует segments
    и на этом этапе явно отклоняется.
    """
    from pathlib import Path
    root = Path(dataset['path'])
    pool = pool or {'mode': 'all'}
    mode = pool.get('mode', 'all')
    if mode not in ('all', 'list'):
        raise ValueError('pool.filter requires segments; use all or list at this stage')
    formats = {'.' + x.lower().lstrip('.') for x in dataset.get('formats', ['json', 'xml'])}
    sides = []
    for field in ('before_dir', 'after_dir'):
        directory = root / dataset[field]
        if not directory.is_dir():
            raise ValueError(f'Dataset directory not found: {directory}')
        files = {}
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in formats:
                if path.stem in files:
                    raise ValueError(f'Ambiguous APP_ID {path.stem}: {files[path.stem]} and {path}')
                files[path.stem] = str(path)
        sides.append(files)
    ids = set(sides[0]) | set(sides[1])
    if mode == 'list':
        ids = set(map(str, pool.get('app_ids', [])))
    return [{'APP_ID': app_id, 'file_before': sides[0].get(app_id),
             'file_after': sides[1].get(app_id)} for app_id in sorted(ids)]


def load(file, cfg, *, app_id=None, source=None, issues=None):
    """s2: читает документ; ошибка файла возвращает None и PARSE_ERROR.

    None отличается от корректного пустого объекта {}. Отсутствующий путь
    регистрируется как APP_MISSING_BEFORE/AFTER. Ошибки одного файла не
    прерывают обработку остальных заявок.
    """
    from .adapters import read_any
    issues = issues if issues is not None else []
    if file is None:
        issues.append(dict(APP_ID=app_id, SOURCE=source, ISSUE=f'APP_MISSING_{source}',
                           PATH='', DETAILS='File absent from dataset'))
        return None
    try:
        return read_any(file, cfg)
    except Exception as exc:
        issues.append(dict(APP_ID=app_id, SOURCE=source, ISSUE='PARSE_ERROR', PATH='',
                           DETAILS=f'{file}: {type(exc).__name__}: {exc}'))
        return None


def union(rows_before, rows_after):
    """s5: вертикальный DataFrame с SOURCE, включая стабильную пустую схему."""
    import pandas as pd
    frames = []
    for rows, source in ((rows_before, 'BEFORE'), (rows_after, 'AFTER')):
        df = pd.DataFrame(rows).copy()
        if not df.empty:
            missing = set(NORMAL_COLUMNS) - {'SOURCE'} - set(df.columns)
            if missing:
                raise ValueError(f'Missing normalized columns: {sorted(missing)}')
        df['SOURCE'] = source
        frames.append(df.reindex(columns=NORMAL_COLUMNS))
    result = pd.concat(frames, ignore_index=True)
    for col in NORMAL_COLUMNS:
        result[col] = result[col].astype('int64' if col == 'DEPTH' else 'string')
    if result[ROW_KEY].isna().any().any():
        raise ValueError('Null row key')
    return result


def check_keys(union_df):
    """s6: все строки с дублирующимся (SOURCE, APP_ID, PATH, ARRAY_KEY)."""
    return union_df.loc[union_df.duplicated(['SOURCE'] + ROW_KEY, keep=False)].copy()


def compare(union_df, *, issues=None):
    """s7: outer merge с четырьмя CHANGE_TYPE, DIFF_FLAG строго по VALUE.

    Неоднозначный ключ исключается ИЗ ОБОИХ срезов с DUPLICATE_KEY, чтобы
    не создавать ложные NEW/LOST и декартово произведение. Результат такого
    запуска неполон; диагностику нужно показывать вместе с витриной.
    NULL, пустая строка и отсутствие атрибута различаются через merge indicator.
    """
    import pandas as pd
    issues = issues if issues is not None else []
    df = union_df.copy()
    if not df['SOURCE'].isin(['BEFORE', 'AFTER']).all():
        raise ValueError('SOURCE must be BEFORE or AFTER')
    duplicates = check_keys(df)
    for row in duplicates.drop_duplicates(['SOURCE'] + ROW_KEY).to_dict('records'):
        issues.append(dict(APP_ID=row['APP_ID'], SOURCE=row['SOURCE'], ISSUE='DUPLICATE_KEY',
                           PATH=row['PATH'], DETAILS=f"Excluded ambiguous key: {row['ARRAY_KEY']}"))
    if not duplicates.empty:
        bad = pd.MultiIndex.from_frame(duplicates[ROW_KEY].drop_duplicates())
        df = df.loc[~pd.MultiIndex.from_frame(df[ROW_KEY]).isin(bad)]
    before = df.loc[df.SOURCE == 'BEFORE'].drop(columns='SOURCE')
    after = df.loc[df.SOURCE == 'AFTER'].drop(columns='SOURCE')
    merged = before.merge(after, on=ROW_KEY, how='outer', suffixes=('_BEFORE', '_AFTER'),
                          indicator=True, validate='one_to_one')
    for col in ['PREFIX', 'CLASS', 'SUFFIX', 'KEY', 'DEPTH']:
        merged[col] = merged[col+'_BEFORE'].where(merged[col+'_BEFORE'].notna(), merged[col+'_AFTER'])
    merged = merged.rename(columns={'ADJUSTED_VALUE_BEFORE':'ADJUSTED_BEFORE',
                                     'ADJUSTED_VALUE_AFTER':'ADJUSTED_AFTER'})
    merged['CHANGE_TYPE'] = 'SAME'
    merged.loc[merged['_merge'] == 'left_only', 'CHANGE_TYPE'] = 'ATTRIBUTE_LOST'
    merged.loc[merged['_merge'] == 'right_only', 'CHANGE_TYPE'] = 'ATTRIBUTE_NEW'
    changed = merged.VALUE_BEFORE.ne(merged.VALUE_AFTER).fillna(False)
    merged.loc[(merged['_merge'] == 'both') & changed, 'CHANGE_TYPE'] = 'VALUE_CHANGED'
    merged['DIFF_FLAG'] = merged.CHANGE_TYPE.ne('SAME').astype('int64')
    columns = ['APP_ID', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY', 'KEY', 'PATH', 'DEPTH',
               'VALUE_BEFORE', 'VALUE_AFTER', 'ADJUSTED_BEFORE', 'ADJUSTED_AFTER', 'DIFF_FLAG', 'CHANGE_TYPE']
    return merged[columns].sort_values(ROW_KEY).reset_index(drop=True)


def prepare_comparison(cfg, run_dir):
    """Исполняет доступную часть s1–s7, сохраняет parquet и диагностику.

    Отдельный последовательный прогон для разработки. Не заменяет будущий
    фоновый оркестратор. Повреждённая пара целиком исключается из сравнения:
    сбой парсинга не означает исчезновение всех её атрибутов.
    """
    from pathlib import Path
    import pandas as pd
    cfg = deepcopy(cfg)
    root = Path(cfg['dataset']['path'])
    manifest_path = root / 'manifest.json'
    if cfg['dataset'].get('use_manifest_excludes', True) and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        exclude = cfg.setdefault('flatten', {}).setdefault('exclude_paths', [])
        exclude.extend(p for p in manifest.get('technical_fields_always_differ', []) if p not in exclude)
    pairs = discover(cfg['dataset'], cfg.get('pool'))
    before_rows, after_rows, issues = [], [], []
    skipped = []
    for pair in pairs:
        app_id = pair['APP_ID']
        start = len(issues)
        before = load(pair['file_before'], cfg, app_id=app_id, source='BEFORE', issues=issues)
        after = load(pair['file_after'], cfg, app_id=app_id, source='AFTER', issues=issues)
        if any(i['ISSUE'] == 'PARSE_ERROR' for i in issues[start:]):
            skipped.append(app_id)
            continue
        b, a = flatten_pair(before or {}, after or {}, cfg, app_id=app_id, issues=issues)
        before_rows.extend(bucketize(b, cfg))
        after_rows.extend(bucketize(a, cfg))
    united = union(before_rows, after_rows)
    compared = compare(united, issues=issues)
    quality = pd.DataFrame(issues, columns=QUALITY_COLUMNS).astype('string').drop_duplicates()
    out = Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Не затираем артефакты другого/предыдущего запуска.
    filenames = ['union.parquet', 'comparison.parquet', 'quality.parquet', 'comparison_status.json']
    if any((out / name).exists() for name in filenames):
        raise FileExistsError('Choose a fresh run directory')
    united.to_parquet(out/'union.parquet', index=False)
    compared.to_parquet(out/'comparison.parquet', index=False)
    quality.to_parquet(out/'quality.parquet', index=False)
    status = dict(stage='comparison', total_apps=len(pairs), union_rows=len(united),
                  comparison_rows=len(compared), diff_rows=int(compared.DIFF_FLAG.sum()),
                  quality_issues=len(quality), skipped_parse_app_ids=skipped,
                  incomplete=bool(len(quality)))
    (out/'comparison_status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    return status
