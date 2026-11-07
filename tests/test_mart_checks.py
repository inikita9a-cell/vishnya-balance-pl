"""Stage 6: check contracts from the organizer, indexes, isolation and resume."""
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.mart_api import MartAPI
from engine.checks_service import DEFAULT_CHECKS_DIR, load_check, prepare_checks, run_checks


CHECK_IDS = ['ar_drop_by_product', 'attribute_new_loss', 'external_score_drift',
             'stop_factor_disappeared', 'target_model_changed']


def sample():
    # Data format matches the published mart, with intentionally generic app IDs.
    items = [
        ('a', 'decision.state', '', 'APPROVE', 'REJECT', 'VALUE_CHANGED'),
        ('a', 'score.base', '', '760', '620', 'VALUE_CHANGED'),
        ('a', 'features.score', 'V1', '760', '620', 'VALUE_CHANGED'),
        ('a', 'strategy.rules.hit', 'P|ruleX', 'true', 'false', 'VALUE_CHANGED'),
        ('a', 'something.added', '', None, '1', 'ATTRIBUTE_NEW'),
        ('b', 'decision.state', '', 'APPROVE', 'APPROVE', 'SAME'),
        ('b', 'strategy.rules.hit', 'P|ruleX', 'true', None, 'ATTRIBUTE_LOST'),
        ('b', 'something.lost', '', '1', None, 'ATTRIBUTE_LOST'),
        ('b', 'features.score', 'V1', '510', '510', 'SAME'),
        ('c', 'decision.state', '', 'REJECT', 'REJECT', 'SAME'),
        ('c', 'score.base', '', '550', '550', 'SAME'),
    ]
    rows = [dict(APP_ID=app, PATH=path, ARRAY_KEY=key, KEY=path.split('.')[-1],
                 VALUE_BEFORE=before, VALUE_AFTER=after, DIFF_FLAG=int(change != 'SAME'),
                 CHANGE_TYPE=change)
            for app, path, key, before, after, change in items]
    comparison = pd.DataFrame(rows).convert_dtypes()
    segments = pd.DataFrame([
        dict(APP_ID='a', PRODUCTS='P', DECISION_BEFORE='APPROVE', DECISION_AFTER='REJECT',
             DECISION_CHANGED=1, PD_MODEL_BEFORE='v1', PD_MODEL_AFTER='v2',
             CUTOFF_BEFORE='low', CUTOFF_AFTER='high'),
        dict(APP_ID='b', PRODUCTS='P', DECISION_BEFORE='APPROVE', DECISION_AFTER='APPROVE',
             DECISION_CHANGED=0, PD_MODEL_BEFORE='v1', PD_MODEL_AFTER='v1',
             CUTOFF_BEFORE='low', CUTOFF_AFTER='low'),
        dict(APP_ID='c', PRODUCTS='Q', DECISION_BEFORE='REJECT', DECISION_AFTER='REJECT',
             DECISION_CHANGED=0, PD_MODEL_BEFORE='v1', PD_MODEL_AFTER='v1',
             CUTOFF_BEFORE='low', CUTOFF_AFTER='low'),
        dict(APP_ID='d', PRODUCTS='Q', DECISION_BEFORE=None, DECISION_AFTER=None,
             DECISION_CHANGED=0, PD_MODEL_BEFORE=None, PD_MODEL_AFTER=None,
             CUTOFF_BEFORE=None, CUTOFF_AFTER=None),
    ]).convert_dtypes()
    return comparison, segments


def test_mart_contract_all_filters_are_conjunctive():
    c, s = sample()
    mart = MartAPI(c, s)
    assert mart.total_apps() == 4   # includes no comparison rows
    assert mart.count() == len(c)
    assert mart.count(path='strategy.rules.hit') == 2
    assert mart.count(path=['decision.state', 'something.added']) == 4
    assert mart.app_ids(path='decision.state', diff_flag=1) == ['a']
    assert mart.app_ids(path_prefix='strategy.', change_type=['VALUE_CHANGED', 'ATTRIBUTE_LOST']) == ['a','b']
    assert mart.app_ids(key='hit', array_key='P|ruleX', app_ids=['b']) == ['b']
    assert mart.app_ids(value_before='true', value_after='false') == ['a']
    assert mart.count(change_type='SAME', diff_flag=0) == 4
    assert mart.count(app_ids=[]) == 0
    assert mart.count(path='missing.path') == 0
    assert next(mart.rows(path='something.added'))['VALUE_BEFORE'] is None
    assert mart.app_ids(value_before=None) == ['a']
    assert len(list(mart.segments())) == 4
    assert isinstance(next(mart.rows())['DIFF_FLAG'], int)


def test_mart_repeated_filters_and_non_mutation():
    c, s = sample()
    before = c.copy(deep=True)
    mart = MartAPI(c, s)
    for _ in range(5):
        assert mart.app_ids(path_prefix='decision.', diff_flag=1) == ['a']
        assert mart.count(path='strategy.rules.hit') == 2
    pd.testing.assert_frame_equal(c, before)
    with pytest.raises(TypeError, match='unknown filter'):
        mart.count(pathh='decision.state')
    with pytest.raises(TypeError, match='path_prefix must be'):
        mart.count(path_prefix=['decision'])


def test_unique_app_ids_not_number_of_rows():
    c, s = sample()
    c = pd.concat([c, c.iloc[[0]], c.iloc[[0]]], ignore_index=True)
    mart = MartAPI(c, s)
    assert mart.count(path='decision.state', diff_flag=1) == 3
    assert mart.app_ids(path='decision.state', diff_flag=1) == ['a']


def test_segments_duplicates_rejected():
    c, s = sample()
    with pytest.raises(ValueError, match='unique'):
        MartAPI(c, pd.concat([s,s.iloc[[0]]], ignore_index=True))


def test_all_five_organizer_check_scripts_are_run_as_is():
    mart = MartAPI(*sample())
    for cid in CHECK_IDS:
        check = load_check(cid)
        assert check['id'] == cid and callable(check['entrypoint'])
    rows = run_checks(mart, CHECK_IDS)
    assert rows
    assert {r['CHECK_ID'] for r in rows} == set(CHECK_IDS)
    assert all(r['RESULT'] in ('PASS','FAIL') for r in rows)
    assert all(r['SOURCE'] in ('BEFORE', 'AFTER') for r in rows)
    assert all(isinstance(r['APP_IDS'],list) for r in rows)
    assert any(r['RESULT']=='FAIL' for r in rows)


def test_errors_are_isolated_and_not_partial(tmp_path):
    (tmp_path / 'check_broken.py').write_text('''\ndef run(mart, params):\n    raise RuntimeError("boom")\nCHECK = {"id":"broken", "label":"Broken", "params":{}, "entrypoint": run}\n''',encoding='utf-8')
    (tmp_path / 'check_badrows.py').write_text('''\ndef run(mart, params):\n    return [{"RESULT":"PASS"}, {"RESULT":"FAIL"}]\nCHECK={"id":"badrows", "label":"Invalid rows", "params":{}, "entrypoint":run}\n''', encoding='utf-8')
    (tmp_path / 'check_okay.py').write_text('''\ndef run(mart, params):\n    return [{"LABEL":"Okay", "SOURCE":"AFTER", "ARGUMENT":"", "CNT":0, "TOTAL":1, "METRIC":0.0, "APP_IDS":[], "RESULT":"PASS", "CONFIDENCE":"HIGH"}]\nCHECK={"id":"okay", "label":"Okay", "params":{}, "entrypoint":run}\n''',encoding='utf-8')
    rows=run_checks(MartAPI(*sample()), ['broken','badrows','okay'], checks_dir=tmp_path)
    assert [r['RESULT'] for r in rows] == ['ERROR','ERROR','PASS']
    assert 'RuntimeError' in rows[0]['ERROR']
    assert 'Missing check result fields' in rows[1]['ERROR']
    assert rows[2]['CHECK_ID']=='okay'


def test_bad_id_fails_without_traversal():
    with pytest.raises(ValueError, match='Invalid check ID'):
        load_check('../passwd')
    rows = run_checks(MartAPI(*sample()), ['../passwd','attribute_new_loss'])
    assert rows[0]['RESULT']=='ERROR'
    assert any(r['CHECK_ID']=='attribute_new_loss' for r in rows[1:])


def test_override_user_params_does_not_mutate_check_metadata():
    mart=MartAPI(*sample())
    out1=run_checks(mart, ['ar_drop_by_product'])
    out2=run_checks(mart, ['ar_drop_by_product'], params_by_id={
        'ar_drop_by_product': {'max_drop_rel': 1.0}})
    assert any(r['RESULT']=='FAIL' for r in out1)
    assert all(r['RESULT']=='PASS' for r in out2)
    assert load_check('ar_drop_by_product')['params']['max_drop_rel'] == .10


def test_persist_report_from_existing_run_and_repeat_without_reprocessing(tmp_path, monkeypatch):
    comparison, segments=sample()
    (tmp_path/'comparison.parquet').touch()
    (tmp_path/'segments.parquet').touch()
    monkeypatch.setattr(MartAPI, 'from_run', classmethod(lambda cls, path: cls(comparison, segments)))
    (tmp_path/'comparison_status.json').write_text(json.dumps({
        'stage':'facts', 'total_apps':4, 'duration_seconds':10.0}), encoding='utf-8')
    cfg={'checks': CHECK_IDS, 'check_params': {'ar_drop_by_product': {'max_drop_rel': .2}}}
    status=prepare_checks(tmp_path, cfg)
    report=json.loads((tmp_path/'checks.json').read_text(encoding='utf-8'))
    assert report and all('CHECK_ID' in r for r in report)
    assert sum(status[f'checks_{x}'] for x in ('pass','fail','error')) == status['checks_rows']
    assert status['checks_error'] == 0
    assert status['stage']=='checks'
    assert (tmp_path/'checks_log.json').exists()
    duration=status['duration_seconds']
    status2=prepare_checks(tmp_path, cfg, check_ids=['target_model_changed'])
    assert status2['checks_selected']==1
    assert status2['duration_seconds'] < duration + 2.0
    assert len(json.loads((tmp_path/'checks.json').read_text(encoding='utf-8'))) == status2['checks_rows']


def test_no_checks_is_valid_and_file_errors_clear(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        prepare_checks(tmp_path, {})
    c,s=sample()
    (tmp_path/'comparison.parquet').touch()
    (tmp_path/'segments.parquet').touch()
    monkeypatch.setattr(MartAPI, 'from_run', classmethod(lambda cls, path: cls(c,s)))
    result=prepare_checks(tmp_path, {})
    assert result['checks_rows']==0
    assert json.loads((tmp_path/'checks.json').read_text(encoding='utf-8'))==[]
