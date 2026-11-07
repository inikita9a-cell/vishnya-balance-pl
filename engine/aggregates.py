"""s10–s11: отчётные блоки и вертикальные facts counts.

В этом модуле нет путей/полей исходного СПР: работаем только с контрактами
comparison и segments. Для drill-down сохраняется отдельная таблица fact_apps.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
import json
import os
import uuid

import pandas as pd


CHANGE_TYPES = ('VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST')
BLOCK_COLUMNS = [
    'BLOCK', 'LEVEL', 'APPS_TOTAL', 'APPS_CHANGED', 'SHARE',
    'ROWS_TOTAL', 'ROWS_CHANGED', 'APPS_INCOMPLETE',
    'APPS_VALUE_CHANGED', 'APPS_ATTRIBUTE_NEW', 'APPS_ATTRIBUTE_LOST',
    'ROWS_VALUE_CHANGED', 'ROWS_ATTRIBUTE_NEW', 'ROWS_ATTRIBUTE_LOST',
]

FACT_BASE_DIMENSIONS = [
    'PREFIX', 'CLASS', 'SUFFIX', 'KEY', 'PATH', 'VALUE_ADJUSTED',
    'DIFF_FLAG', 'CHANGE_TYPE', 'SOURCE',
]
FACT_DEFAULT_SEGMENT_DIMENSIONS = [
    'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED',
    'DECISION_TRANSITION', 'REASON_BEFORE', 'REASON_AFTER',
    'REASON_TRANSITION', 'CAUSE', 'PARTNER_TYPE', 'PRODUCTS',
]


def _need(frame: pd.DataFrame, columns, label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f'{label}: missing columns {missing}')


def _block_ancestors(path: str, include_leaf: bool, max_level):
    pieces = str(path).split('.')
    last = len(pieces) if include_leaf or len(pieces) == 1 else len(pieces) - 1
    if max_level is not None:
        last = min(last, max_level)
    return [('.'.join(pieces[:level]), level) for level in range(1, last + 1)]


def blocks(comparison: pd.DataFrame, segments: pd.DataFrame | None = None,
           cfg: dict | None = None) -> pd.DataFrame:
    """s10: иерархия блоков и доля затронутых заявок внутри каждого блока.

    APPS_TOTAL — distinct APP_ID с наблюдаемыми атрибутами в блоке,
    APPS_CHANGED — distinct APP_ID с DIFF_FLAG=1 в блоке,
    SHARE = APPS_CHANGED / APPS_TOTAL (0..1).
    ROWS_CHANGED — количество отличающихся строк, а НЕ число заявок.
    Типовые APPS_* не складываются: у одной заявки возможны разные типы.
    APPS_INCOMPLETE — число затронутых заявок, где полное сравнение недостоверно.
    Для обычных путей лист KEY исключается из названия блока; для корневых
    скаляров оставляется сам путь. Настройки не содержат имён полей датасета.
    """
    _need(comparison, ['APP_ID', 'PATH', 'DIFF_FLAG', 'CHANGE_TYPE'], 'comparison')
    cfg = (cfg or {}).get('blocks', {})
    max_level = cfg.get('max_level')
    if max_level is not None and (type(max_level) is not int or max_level < 1):
        raise ValueError('blocks.max_level must be positive integer or null')
    include_leaf = cfg.get('include_leaf', False)
    if type(include_leaf) is not bool:
        raise ValueError('blocks.include_leaf must be boolean')
    if comparison.empty:
        return _empty_blocks()

    paths = comparison['PATH'].dropna().astype(str).unique()
    mapping = [(path, block, level)
               for path in paths
               for block, level in _block_ancestors(path, include_leaf, max_level)]
    if not mapping:
        return _empty_blocks()
    path_table = pd.DataFrame(mapping, columns=['PATH', 'BLOCK', 'LEVEL'])
    expanded = comparison[['APP_ID', 'PATH', 'DIFF_FLAG', 'CHANGE_TYPE']].merge(
        path_table, on='PATH', how='inner', validate='many_to_many', sort=False)
    group = ['BLOCK', 'LEVEL']
    totals = expanded.groupby(group, observed=True, sort=True).agg(
        APPS_TOTAL=('APP_ID', 'nunique'), ROWS_TOTAL=('APP_ID', 'size'))
    changed = expanded.loc[expanded['DIFF_FLAG'].eq(1)]
    if not changed.empty:
        c = changed.groupby(group, observed=True).agg(
            APPS_CHANGED=('APP_ID', 'nunique'), ROWS_CHANGED=('APP_ID', 'size'))
        totals = totals.join(c)
    else:
        totals[['APPS_CHANGED', 'ROWS_CHANGED']] = 0

    for change in CHANGE_TYPES:
        suffix = change
        t = changed.loc[changed['CHANGE_TYPE'].eq(change)]
        if not t.empty:
            c = t.groupby(group, observed=True).agg(
                **{f'APPS_{suffix}': ('APP_ID', 'nunique'),
                   f'ROWS_{suffix}': ('APP_ID', 'size')})
            totals = totals.join(c)
        else:
            totals[f'APPS_{suffix}'] = 0
            totals[f'ROWS_{suffix}'] = 0

    if segments is not None:
        _need(segments, ['APP_ID', 'COMPARISON_COMPLETE'], 'segments')
        if segments['APP_ID'].duplicated().any():
            raise ValueError('segments: duplicate APP_ID')
        missing = expanded.loc[~expanded['APP_ID'].isin(segments['APP_ID']), 'APP_ID']
        if not missing.empty:
            raise ValueError(f'comparison contains APP_ID missing from segments: {missing.iloc[0]}')
        incomplete_ids = segments.loc[segments['COMPARISON_COMPLETE'].eq(0), 'APP_ID']
        if not incomplete_ids.empty:
            incomplete = expanded.loc[expanded['APP_ID'].isin(incomplete_ids)]
            stats = incomplete.groupby(group, observed=True)['APP_ID'].nunique().rename('APPS_INCOMPLETE')
            totals = totals.join(stats)
        else:
            totals['APPS_INCOMPLETE'] = 0
    else:
        totals['APPS_INCOMPLETE'] = 0

    for col in BLOCK_COLUMNS:
        if col not in ('BLOCK', 'LEVEL', 'SHARE'):
            totals[col] = totals[col].fillna(0).astype('int64')
    totals['SHARE'] = totals['APPS_CHANGED'] / totals['APPS_TOTAL']
    result = totals.reset_index()[BLOCK_COLUMNS]
    return result.sort_values(['LEVEL', 'BLOCK']).reset_index(drop=True)


def _empty_blocks():
    cols = {col: pd.Series(dtype='float64' if col == 'SHARE' else
                           'string' if col == 'BLOCK' else 'int64') for col in BLOCK_COLUMNS}
    return pd.DataFrame(cols)


def _fact_dimensions(cfg):
    fcfg = (cfg or {}).get('facts', {})
    dims = fcfg.get('segment_dimensions', FACT_DEFAULT_SEGMENT_DIMENSIONS)
    if not isinstance(dims, list) or any(not isinstance(col, str) for col in dims):
        raise ValueError('facts.segment_dimensions must be a list of column names')
    if len(dims) != len(set(dims)):
        raise ValueError('facts.segment_dimensions contains duplicates')
    include_array_key = fcfg.get('include_array_key', False)
    if type(include_array_key) is not bool:
        raise ValueError('facts.include_array_key must be boolean')
    if any(dim in FACT_BASE_DIMENSIONS or dim in ('FACT_ID', 'APP_ID', 'CNT', 'ARRAY_KEY') for dim in dims):
        raise ValueError('facts.segment_dimensions contains reserved columns')
    return FACT_BASE_DIMENSIONS + (['ARRAY_KEY'] if include_array_key else []) + dims, dims


def facts(comparison: pd.DataFrame, segments: pd.DataFrame,
          cfg: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """s11: агрегированные вертикальные facts и точные связи с APP_ID.

    На каждую наблюдаемую сторону сравнения приходится строка SOURCE:
    BEFORE (MASTER) / AFTER (BETA). Для ATTRIBUTE_NEW нет BEFORE-строки;
    для ATTRIBUTE_LOST нет AFTER-строки. Строковый VALUE='NULL' существует,
    в отличие от отсутствующего атрибута (NA в comparison).

    CNT = COUNT(DISTINCT APP_ID) при фиксированном полном наборе измерений.
    Из-за множественных атрибутов/значений нельзя суммировать CNT произвольно.
    fact_apps.parquet содержит (FACT_ID, APP_ID): через него возможен точный
    провал до заявок без неоднозначных обратных фильтров.
    """
    dimensions, seg_cols = _fact_dimensions(cfg)
    _need(comparison, [
        'APP_ID', 'PREFIX', 'CLASS', 'SUFFIX', 'KEY', 'PATH', 'ARRAY_KEY',
        'DIFF_FLAG', 'CHANGE_TYPE', 'ADJUSTED_BEFORE', 'ADJUSTED_AFTER',
    ], 'comparison')
    _need(segments, ['APP_ID'] + seg_cols, 'segments')
    if segments['APP_ID'].duplicated().any():
        raise ValueError('segments: duplicate APP_ID')
    if comparison.empty:
        return _empty_facts(dimensions)

    bad = comparison.loc[~comparison['APP_ID'].isin(segments['APP_ID']), 'APP_ID']
    if not bad.empty:
        raise ValueError(f'comparison contains APP_ID missing from segments: {bad.iloc[0]}')
    comparison = comparison.merge(segments[['APP_ID'] + seg_cols], on='APP_ID',
                                  how='left', validate='many_to_one', sort=False)
    fixed = ['APP_ID', 'PREFIX', 'CLASS', 'SUFFIX', 'KEY', 'PATH', 'DIFF_FLAG', 'CHANGE_TYPE']
    if 'ARRAY_KEY' in dimensions:
        fixed.append('ARRAY_KEY')
    fixed += seg_cols
    pieces = []
    for source, col, excluded in [
        ('BEFORE (MASTER)', 'ADJUSTED_BEFORE', 'ATTRIBUTE_NEW'),
        ('AFTER (BETA)', 'ADJUSTED_AFTER', 'ATTRIBUTE_LOST'),
    ]:
        # CHANGE_TYPE determines presence. Do not confuse the text "NULL"
        # with a missing attribute; a valid null is present in both slices.
        subset = comparison.loc[comparison['CHANGE_TYPE'].ne(excluded), fixed + [col]].copy()
        subset = subset.rename(columns={col: 'VALUE_ADJUSTED'})
        subset['SOURCE'] = source
        pieces.append(subset)
    vertical = pd.concat(pieces, ignore_index=True)
    if vertical.empty:
        return _empty_facts(dimensions)
    # Повторяющиеся ключи массивов/значения в одной заявке считаются один раз
    # в рамках фиксированного полного набора измерений.
    vertical = vertical.drop_duplicates(dimensions + ['APP_ID'])
    vertical['FACT_ID'] = vertical.groupby(dimensions, dropna=False, sort=True,
                                           observed=True).ngroup().astype('int64')
    # Каждый APP_ID встречается в FACT_ID не более одного раза после dedup.
    members = vertical[['FACT_ID', 'APP_ID']].sort_values(['FACT_ID', 'APP_ID']).reset_index(drop=True)
    members['FACT_ID'] = members['FACT_ID'].astype('int64')
    members['APP_ID'] = members['APP_ID'].astype('string')
    index = vertical.drop_duplicates('FACT_ID').set_index('FACT_ID')[dimensions]
    counts = members.groupby('FACT_ID', sort=True).size().rename('CNT')
    fact_table = index.join(counts).reset_index().sort_values('FACT_ID').reset_index(drop=True)
    fact_table['FACT_ID'] = fact_table['FACT_ID'].astype('int64')
    fact_table['CNT'] = fact_table['CNT'].astype('int64')
    return fact_table[['FACT_ID'] + dimensions + ['CNT']], members


def _empty_facts(dimensions):
    columns = {'FACT_ID': pd.Series(dtype='int64')}
    for dim in dimensions:
        columns[dim] = pd.Series(dtype='int64' if dim in ('DIFF_FLAG', 'DECISION_CHANGED',
                                                       'QUALITY_ISSUE', 'COMPARISON_COMPLETE')
                                 else 'string')
    columns['CNT'] = pd.Series(dtype='int64')
    return pd.DataFrame(columns), pd.DataFrame({
        'FACT_ID': pd.Series(dtype='int64'), 'APP_ID': pd.Series(dtype='string')})


def prepare_aggregates(run_dir, cfg: dict | None = None, on_event=None) -> dict:
    """Достроить s10–s11 по готовым comparison/segments Parquet без нового JSON-прогона.

    Существующие артефакты не перезаписываются. Успешный запуск расширяет
    comparison_status.json. Для новых прогонов вызывается после s9.
    """
    from .procedure_runtime import freeze_config, snapshot_event, execute, validate_facts
    cfg = freeze_config(cfg or {})
    out = Path(run_dir)
    files = ('blocks.parquet', 'facts.parquet', 'fact_apps.parquet')
    existing = [name for name in files if (out / name).exists()]
    if existing:
        raise FileExistsError('Агрегаты уже существуют: ' + ', '.join(existing) +
                              '. Выберите новый запуск, не перезаписывайте результаты.')
    for name in ('comparison.parquet', 'segments.parquet'):
        if not (out / name).is_file():
            raise FileNotFoundError(f'Для этапа 5 необходим файл {out / name}')
    started = perf_counter()
    comp = pd.read_parquet(out / 'comparison.parquet')
    seg = pd.read_parquet(out / 'segments.parquet')
    if on_event:
        on_event({'step': 's10_blocks', 'status': 'running', 'rows_in': len(comp)})
    b = blocks(comp, seg, cfg)
    if on_event:
        on_event({'step': 's10_blocks', 'status': 'done', 'rows_out': len(b), 'progress': 100})
        on_event({'step': 's11_facts', 'status': 'running', 'rows_in': len(comp),
                  **snapshot_event(cfg, 's11_facts')})
    if 'facts' in cfg.get('procedures', {}):
        f, members = validate_facts(execute('facts', cfg, comparison=comp, segments=seg), comp, cfg)
    else:
        f, members = facts(comp, seg, cfg)
    # Сначала все временные файлы, затем публикация. При ошибке очищаем
    # частично опубликованные артефакты этого вызова, не трогая старый прогон.
    tag = f'{os.getpid()}-{uuid.uuid4().hex}'
    written, published = [], []
    try:
        for name, df in [('blocks.parquet', b), ('facts.parquet', f), ('fact_apps.parquet', members)]:
            temporary = out / f'.{name}.{tag}.tmp'
            written.append(temporary)
            df.to_parquet(temporary, index=False)
        for name, temp in zip(files, written):
            destination = out / name
            if destination.exists():
                raise FileExistsError(f'Агрегат уже создан другим запуском: {destination}')
            os.replace(temp, destination)
            published.append(destination)
    except Exception:
        for path in written + published:
            path.unlink(missing_ok=True)
        raise
    elapsed = round(perf_counter() - started, 3)
    status_path = out / 'comparison_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    status.update(stage='facts', block_rows=len(b), fact_rows=len(f),
                  fact_membership_rows=len(members), aggregates_seconds=elapsed)
    if 'duration_seconds' in status:
        status['duration_seconds'] = round(float(status['duration_seconds']) + elapsed, 3)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    if on_event:
        on_event({'step': 's11_facts', 'status': 'done', 'rows_out': len(f),
                  'progress': 100, 'message': f'fact memberships: {len(members)}'})
    return status
