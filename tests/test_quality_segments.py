from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import pandas as pd
import pytest
import yaml
from engine.steps import flatten_pair, union, compare, quality, segments, prepare_comparison


def config():
    # Нарочно другой набор имён: ядро не должно знать поля СПР.
    return {'flatten': {'arrays': {'products': {'mode': 'field', 'key': ['id']},
                                  'offers': {'mode': 'field', 'key': ['id']}}},
            'segments': {'decision': 'result', 'reject_code': 'products.reason',
                'reject_reason': 'products.reason_type', 'products': 'products.name',
                'pd_model': 'products.model', 'cutoff': 'products.threshold',
                'top_offer': {'path': 'offers.name', 'where': {'rank': '1'}},
                'partner_type': 'products.partner', 'routing': 'products.route',
                'score_okb': 'input.score', 'input_paths': ['input'], 'logic_paths': ['products', 'result'],
                'cause_detail': {'MODEL_CHANGE': ['products.model'], 'CUTOFF_CHANGE': ['products.threshold']}},
            'quality': {'required_paths': ['id', 'result'], 'reason_rules': [
                {'scope_path': 'products', 'when_path': 'result', 'when_value': 'NO', 'require_path': 'reason'}]}}


def doc():
    return {'id': '1', 'result': 'YES', 'input': {'score': 710},
            'products': [{'id': 'p1', 'name': 'A', 'result': 'YES', 'reason': None,
                          'reason_type': None, 'model': 'v1', 'threshold': 'low',
                          'partner': 'partner', 'route': 'api'}],
            'offers': [{'id': 'b', 'name': 'B', 'rank': 2}, {'id': 'a', 'name': 'A', 'rank': 1}]}


def calculate(before, after, cfg=None, existing=()):
    cfg = cfg or config()
    pairs = [dict(APP_ID='1', BEFORE=before, AFTER=after)]
    issues = list(existing)
    b,a = flatten_pair(before or {}, after or {}, cfg, app_id='1', issues=issues)
    c = compare(union(b,a), issues=issues)
    q = quality(pairs,cfg,issues)
    return segments(pairs,c,cfg,q), q


@pytest.mark.parametrize('value', [None, '', '   '])
def test_required_null_empty_and_zero(value):
    before=doc(); after=doc(); after['result']=value; after['id']=0
    seg,q=calculate(before,after)
    assert q.ISSUE.tolist()==['REQUIRED_FIELD_MISSING']
    assert q.PATH.tolist()==['result']
    assert seg.iloc[0].DECISION_COMPARABLE==0
    assert seg.iloc[0].DECISION_CHANGED==0
    assert pd.isna(seg.iloc[0].DECISION_TRANSITION)
    assert seg.iloc[0].QUALITY_ISSUE==1


def test_missing_field_and_raw_quality_despite_exclusion():
    before=doc(); after=doc(); del after['result']
    cfg=config(); cfg['flatten']['exclude_paths']=['result']
    seg,q=calculate(before,after,cfg)
    assert seg.iloc[0].HAS_DIFF==0
    assert q.ISSUE.tolist()==['REQUIRED_FIELD_MISSING']


def test_each_rejected_product_needs_own_reason():
    before=doc(); after=doc()
    after['products']=[{'id':'a','result':'NO','reason':'OK'}, {'id':'b','result':'NO','reason':None},
                       {'id':'c','result':'YES','reason':None}]
    _,q=calculate(before,after)
    assert q.ISSUE.tolist()==['DECISION_WITHOUT_REASON']
    assert 'products[1]' in q.iloc[0].DETAILS
    assert q.iloc[0].SOURCE=='AFTER'


def test_required_inside_each_array_item():
    cfg=config(); cfg['quality']['required_paths']=['products.name']
    before=doc(); after=doc(); after['products'].append({'id':'b'})
    _,q=calculate(before,after,cfg)
    assert q.PATH.tolist()==['products.name']
    assert 'products[1]' in q.iloc[0].DETAILS


def test_brief_rule_format_and_reject_untrusted_expression():
    cfg=config()
    cfg['quality']['reason_rules']=[{'when': "decision == 'NO'", 'require':'reject_code'}]
    after=doc(); after['result']='NO'
    _,q=calculate(doc(),after,cfg)
    assert q.ISSUE.tolist()==['DECISION_WITHOUT_REASON']
    cfg['quality']['reason_rules'][0]['when']="__import__('os').system('echo invalid')"
    with pytest.raises(ValueError): calculate(doc(),after,cfg)


@pytest.mark.parametrize('change,expected', [('none','NONE'), ('input','INPUT_DATA'), ('logic','LOGIC'), ('both','BOTH')])
def test_cause_classifies_observed_paths(change,expected):
    before=doc(); after=doc()
    if change in ('input','both'): after['input']['score']=650
    if change in ('logic','both'): after['products'][0]['model']='v2'
    seg,q=calculate(before,after)
    row=seg.iloc[0]
    assert q.empty and row.CAUSE==expected
    assert row.CAUSE_DETAIL==('MODEL_CHANGE' if change in ('logic','both') else 'OTHER' if change=='input' else 'NONE')
    assert row.TOP_OFFER_BEFORE=='A'
    assert row.COMPARISON_COMPLETE==1
    assert row.DECISION_CHANGED==0


def test_model_order_invariance_full_sets_and_reason_transition():
    before=doc(); before['products'].append({**before['products'][0], 'id':'p2', 'model':'v2'})
    after=deepcopy(before); after['products'].reverse()
    seg,q=calculate(before,after)
    assert seg.iloc[0].PD_MODEL_BEFORE==seg.iloc[0].PD_MODEL_AFTER=='v1'
    assert seg.iloc[0].PD_MODELS_AFTER=='v1;v2'
    assert seg.iloc[0].N_DIFFS==0
    after['result']='NO'; after['products'][0].update(result='NO',reason='CODE',reason_type='LIMIT')
    seg,_=calculate(before,after)
    assert seg.iloc[0].DECISION_CHANGED==1
    assert seg.iloc[0].DECISION_TRANSITION=='YES→NO'
    assert seg.iloc[0].REASON_TRANSITION=='∅→CODE'
    assert seg.iloc[0].REJECT_REASON_AFTER=='LIMIT'


def test_empty_frames_have_stable_schemas():
    q=quality([],config())
    s=segments([],compare(union([],[])),config(),q)
    assert q.empty and s.empty
    assert 'DECISION_TRANSITION' in s and str(s.N_DIFFS.dtype)=='int64'


def test_corrupt_missing_and_empty_documents_remain_in_segments(tmp_path):
    cfg=config(); cfg['dataset']={'path':str(tmp_path),'before_dir':'b','after_dir':'a'}
    (tmp_path/'a').mkdir(); (tmp_path/'b').mkdir()
    for app in ('ok','bad','missing','empty'):
        (tmp_path/'b'/f'{app}.json').write_text(json.dumps(doc()))
    (tmp_path/'a'/'ok.json').write_text(json.dumps(doc()))
    (tmp_path/'a'/'bad.json').write_text('broken')
    (tmp_path/'a'/'empty.json').write_text('{}')
    status=prepare_comparison(cfg,tmp_path/'out')
    s=pd.read_parquet(tmp_path/'out'/'segments.parquet').set_index('APP_ID')
    assert len(s)==4 and status['segment_rows']==4
    assert s.loc['bad','QUALITY_ISSUE']==1 and s.loc['bad','COMPARISON_COMPLETE']==0
    assert s.loc['bad','N_DIFFS']==0 and s.loc['bad','DECISION_COMPARABLE']==0
    assert s.loc['missing','COMPARISON_COMPLETE']==0
    assert s.loc['empty','COMPARISON_COMPLETE']==1  # пустой объект прочитан, поля отмечены quality
    assert s.loc['empty','QUALITY_ISSUE']==1
    assert status['apps_decision_changed']==0
    assert status['apps_decision_comparable']==1
    # Проверка занятой папки должна сработать раньше даже неверного пути датасета.
    cfg['dataset']['path']='does-not-exist'
    with pytest.raises(FileExistsError): prepare_comparison(cfg,tmp_path/'out')
    path=tmp_path/'config.yaml'; path.write_text(yaml.safe_dump(cfg))
    # В Windows дочерний Python может выводить stderr в кодировке системы,
    # поэтому не декодируем поток внутри subprocess.run (его reader thread).
    # Принудительно выбираем UTF-8 у дочернего процесса и проверяем байты после завершения.
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    run = subprocess.run(
        [sys.executable, '-m', 'engine.run_comparison', '--config', str(path), '--out', str(tmp_path/'out')],
        capture_output=True,
        env=env,
    )
    stderr = run.stderr.decode('utf-8', errors='replace')
    assert run.returncode == 2, stderr
    assert 'Результаты уже существуют' in stderr, stderr
    assert 'Traceback' not in stderr, stderr


def test_public_real_pair_segments():
    root=Path(__file__).parent
    cfg=yaml.safe_load((root.parent/'configs/default_spr.yaml').read_text())
    before,after=[json.loads((root/'fixtures'/f).read_text()) for f in ('I32554355_bef.json','I32554355.json')]
    s,q=calculate(before,after,cfg)
    assert q.empty
    row=s.iloc[0]
    assert row.DECISION_BEFORE==row.DECISION_AFTER=='REJECT'
    assert row.DECISION_TRANSITION=='REJECT→REJECT'
    assert row.CAUSE=='NONE' and row.N_DIFFS==0
    assert row.SCORE_OKB_BEFORE=='664'
