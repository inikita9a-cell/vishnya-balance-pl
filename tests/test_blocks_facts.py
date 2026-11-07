"""Этап 5: blocks, вертикальные facts, связь с заявками, пустые/неполные данные."""
import pandas as pd
import pytest
from engine.aggregates import blocks, facts, BLOCK_COLUMNS, FACT_BASE_DIMENSIONS


def sample():
    # Пути и имена искусственные: код не зависит от названий полей СПР.
    rows = [
        ('A', 'result.decision', '', 'NO', 'YES', 'VALUE_CHANGED'),
        ('A', 'catalog.rules.hit', 'r1', 'false', 'true', 'VALUE_CHANGED'),
        ('A', 'catalog.rules.hit', 'r2', 'false', 'true', 'VALUE_CHANGED'),
        ('B', 'result.decision', '', 'YES', 'YES', 'SAME'),
        ('B', 'result.newField', '', None, 'fresh', 'ATTRIBUTE_NEW'),
        ('B', 'catalog.oldField', '', 'legacy', None, 'ATTRIBUTE_LOST'),
        ('B', 'input.nullValue', '', 'NULL', 'NULL', 'SAME'),
    ]
    comparison = pd.DataFrame([
        dict(APP_ID=app, PREFIX=path.split('.')[0], CLASS=path.split('.')[1],
             SUFFIX='.'.join(path.split('.')[2:-1]), KEY=path.split('.')[-1],
             PATH=path, ARRAY_KEY=key, ADJUSTED_BEFORE=before, ADJUSTED_AFTER=after,
             DIFF_FLAG=int(change != 'SAME'), CHANGE_TYPE=change)
        for app, path, key, before, after, change in rows
    ])
    segments = pd.DataFrame([
        dict(APP_ID=app, DECISION_BEFORE=d1, DECISION_AFTER=d2,
             DECISION_CHANGED=int(d1 != d2), DECISION_TRANSITION=f'{d1}→{d2}',
             REASON_BEFORE=None, REASON_AFTER=None, REASON_TRANSITION='∅→∅',
             CAUSE='LOGIC' if app == 'A' else 'NONE', PARTNER_TYPE='bank',
             PRODUCTS='P', COMPARISON_COMPLETE=complete)
        for app, d1, d2, complete in [('A', 'NO', 'YES', 1), ('B', 'YES', 'YES', 0),
                                      ('C', 'YES', 'YES', 1)]
    ])
    return comparison, segments


def test_blocks_counts_distinct_apps_and_hierarchy():
    c, s = sample()
    b = blocks(c, s).set_index('BLOCK')
    assert set(b.columns).issuperset(set(BLOCK_COLUMNS) - {'BLOCK'})
    assert b.loc['result', 'LEVEL'] == 1
    assert b.loc['result', 'APPS_TOTAL'] == 2
    assert b.loc['result', 'APPS_CHANGED'] == 2
    assert b.loc['result', 'APPS_INCOMPLETE'] == 1
    assert b.loc['result', 'SHARE'] == 1.0
    assert b.loc['catalog.rules', 'APPS_TOTAL'] == 1
    assert b.loc['catalog.rules', 'APPS_CHANGED'] == 1  # 2 строки, 1 заявка
    assert b.loc['catalog.rules', 'ROWS_CHANGED'] == 2
    assert b.loc['catalog.rules', 'APPS_VALUE_CHANGED'] == 1
    assert b.loc['catalog.rules', 'ROWS_VALUE_CHANGED'] == 2
    assert b.loc['catalog', 'APPS_TOTAL'] == 2
    assert b.loc['catalog', 'APPS_CHANGED'] == 2
    assert b.loc['catalog', 'ROWS_CHANGED'] == 3
    assert b.loc['input', 'APPS_CHANGED'] == 0
    assert b.loc['input', 'SHARE'] == 0
    assert 'result.decision' not in b.index  # лист KEY по умолчанию не блок


def test_blocks_include_leaf_and_max_level():
    c, s = sample()
    b = blocks(c, s, {'blocks': {'include_leaf': True, 'max_level': 2}})
    assert 'result.decision' in set(b.BLOCK)
    assert 'catalog.rules' in set(b.BLOCK)
    assert 'catalog.rules.hit' not in set(b.BLOCK)
    with pytest.raises(ValueError):
        blocks(c, s, {'blocks': {'max_level': 0}})


def test_facts_vertical_source_missing_null_and_deduplication():
    c, s = sample()
    f, links = facts(c, s)
    assert (f.CNT > 0).all()
    assert f.FACT_ID.is_unique
    assert 'APP_ID' not in f.columns  # APP_ID живёт в links
    assert list(links.columns) == ['FACT_ID', 'APP_ID']
    assert not links.duplicated().any()
    assert f.set_index('FACT_ID').CNT.to_dict() == links.groupby('FACT_ID').size().to_dict()
    assert set(f.SOURCE) == {'BEFORE (MASTER)', 'AFTER (BETA)'}
    assert not f.loc[(f.PATH == 'result.newField') & (f.SOURCE == 'BEFORE (MASTER)')].shape[0]
    assert f.loc[(f.PATH == 'result.newField') & (f.SOURCE == 'AFTER (BETA)'), 'CNT'].sum() == 1
    assert f.loc[(f.PATH == 'catalog.oldField') & (f.SOURCE == 'BEFORE (MASTER)'), 'CNT'].sum() == 1
    assert not f.loc[(f.PATH == 'catalog.oldField') & (f.SOURCE == 'AFTER (BETA)')].shape[0]
    assert f.loc[f.PATH == 'input.nullValue', 'VALUE_ADJUSTED'].tolist() == ['NULL', 'NULL']
    # Два разных ключа массива у A, но в одной группе A учитываем один раз.
    matched = f.loc[(f.PATH == 'catalog.rules.hit') & (f.SOURCE == 'AFTER (BETA)')]
    assert len(matched) == 1 and int(matched.iloc[0].CNT) == 1
    member_ids = links.loc[links.FACT_ID.eq(matched.iloc[0].FACT_ID), 'APP_ID'].tolist()
    assert member_ids == ['A']
    assert set(links.APP_ID) == {'A', 'B'}  # C с нулём атрибутов остаётся в segments


def test_facts_optional_array_key_dimension_and_configurable_segments():
    c, s = sample()
    f, links = facts(c, s, {'facts': {'include_array_key': True,
                                     'segment_dimensions': ['CAUSE']}})
    assert 'ARRAY_KEY' in f.columns
    assert set(f.loc[(f.PATH == 'catalog.rules.hit') &
                     (f.SOURCE == 'AFTER (BETA)'), 'ARRAY_KEY']) == {'r1', 'r2'}
    assert 'CAUSE' in f.columns and 'PARTNER_TYPE' not in f.columns
    assert sum(f.loc[(f.PATH == 'catalog.rules.hit') &
                     (f.SOURCE == 'AFTER (BETA)'), 'CNT']) == 2
    assert len(links.loc[links.APP_ID.eq('A')]) > 2


def test_incomplete_orphan_and_empty_tables():
    c, s = sample()
    missing = s.loc[s.APP_ID.ne('A')]
    with pytest.raises(ValueError, match='missing from segments'):
        facts(c, missing)
    with pytest.raises(ValueError, match='missing from segments'):
        blocks(c, missing)
    assert blocks(c.iloc[0:0], s).empty
    f, members = facts(c.iloc[0:0], s)
    assert f.empty and members.empty
    assert list(members.columns) == ['FACT_ID', 'APP_ID']
    assert set(FACT_BASE_DIMENSIONS).issubset(f.columns)
    assert str(f.CNT.dtype) == 'int64'
    assert str(members.FACT_ID.dtype) == 'int64'


def test_shuffled_input_same_facts():
    c, s = sample()
    a, am = facts(c, s)
    b, bm = facts(c.sample(frac=1, random_state=123), s.sample(frac=1, random_state=456))
    pd.testing.assert_frame_equal(a.sort_values('FACT_ID').reset_index(drop=True),
                                  b.sort_values('FACT_ID').reset_index(drop=True))
    pd.testing.assert_frame_equal(am.sort_values(['FACT_ID','APP_ID']).reset_index(drop=True),
                                  bm.sort_values(['FACT_ID','APP_ID']).reset_index(drop=True))


def test_resume_aggregates_from_existing_run(monkeypatch, tmp_path):
    # В минимальной CI-среде нет pyarrow. Проверяем оркестрацию отдельно от
    # кодека parquet; в рабочем проекте pandas использует настоящий pyarrow.
    import json
    from engine.aggregates import prepare_aggregates
    c, s = sample()
    monkeypatch.setattr(pd.DataFrame, 'to_parquet', lambda self, path, index=False: self.to_pickle(path))
    monkeypatch.setattr(pd, 'read_parquet', lambda path: pd.read_pickle(path))
    c.to_pickle(tmp_path / 'comparison.parquet')
    s.to_pickle(tmp_path / 'segments.parquet')
    (tmp_path/'comparison_status.json').write_text(json.dumps({
        'stage': 'segments', 'total_apps': 3, 'duration_seconds': 12.0}), encoding='utf-8')
    status = prepare_aggregates(tmp_path)
    assert status['stage'] == 'facts'
    assert status['total_apps'] == 3
    assert status['block_rows'] > 0 and status['fact_rows'] > 0
    assert status['fact_membership_rows'] > 0
    assert status['duration_seconds'] >= 12.0
    assert (tmp_path/'blocks.parquet').exists()
    assert (tmp_path/'facts.parquet').exists()
    assert (tmp_path/'fact_apps.parquet').exists()
    assert set(pd.read_parquet(tmp_path/'facts.parquet').columns).issuperset({'FACT_ID','CNT','SOURCE'})
    assert set(pd.read_parquet(tmp_path/'fact_apps.parquet').columns) == {'FACT_ID','APP_ID'}
    with pytest.raises(FileExistsError):
        prepare_aggregates(tmp_path)
    assert json.loads((tmp_path/'comparison_status.json').read_text()) == status
