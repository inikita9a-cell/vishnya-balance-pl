import csv
import json
from pathlib import Path
from copy import deepcopy
import pytest
import yaml
from engine.steps import flatten, flatten_pair, bucketize
from engine.paths import matches
from engine.adapters import read_any

HERE = Path(__file__).parent
FIX = HERE / 'fixtures'
ROOT = HERE.parent


def sample_config():
    return {'flatten': {'exclude_paths': ['company.decisionResult.calculatedAt'],
            'arrays': {'company.scoreCardResult': {'mode': 'field', 'key': ['name']},
                       'company.rejectReasons': {'mode': 'value'}}},
            'buckets': {'dash': '-', 'default_unit': [0, .3, .6, .8, 1],
                        'default_num': [0, 100000, 250000]}}


def test_teaching_pair_matches_csv_values_keys_and_counts():
    docs = [json.loads((FIX / n).read_text()) for n in
            ('01_response_BEFORE_MASTER_app1001.json', '02_response_AFTER_BETA_app1001.json')]
    pair = flatten_pair(*docs, sample_config(), app_id='1001')
    assert [len(x) for x in pair] == [12, 14]
    assert sum(map(len, pair)) == 26
    fields = ['APP_ID', 'SOURCE', 'PREFIX', 'CLASS', 'ARRAY_KEY', 'KEY', 'VALUE']
    for actual, name in zip(pair, ('03_normalized_BEFORE_app1001.csv','04_normalized_AFTER_app1001.csv')):
        with (FIX/name).open(encoding='utf-8-sig') as f:
            expected = list(csv.DictReader(f, delimiter=';'))
        project = lambda rows: sorted(tuple(r[k] for k in fields) for r in rows)
        assert project(actual) == project(expected)
    b, a = [bucketize(x, sample_config()) for x in pair]
    get = lambda rows: next(x for x in rows if x['ARRAY_KEY']=='TAKEUP_RATE_IP' and x['KEY']=='value')
    assert get(b)['VALUE'] != get(a)['VALUE']
    assert get(b)['ADJUSTED_VALUE'] == get(a)['ADJUSTED_VALUE'] == '(0.3 - 0.6]'


def test_unchanged_real_pair_and_reordering():
    cfg = yaml.safe_load((ROOT/'configs/default_spr.yaml').read_text())
    before, after = [json.loads((FIX/n).read_text()) for n in ('I32554355_bef.json', 'I32554355.json')]
    def reverse(value, path=''):
        if isinstance(value, dict):
            return {k: reverse(v, path+'.'+k if path else k) for k,v in value.items()}
        if isinstance(value, list):
            items = [reverse(v,path) for v in value]
            return items if path == 'decisionResult.scoring.value' else list(reversed(items))
        return value
    b,a = flatten_pair(before, reverse(after), cfg)
    project = lambda rows: sorted((r['PATH'],r['ARRAY_KEY'],r['VALUE']) for r in rows)
    assert project(b) == project(a)
    assert len(project(b)) == len(set((r['PATH'],r['ARRAY_KEY']) for r in b))


def test_common_auto_key_and_composite():
    before={'items':[{'id':1,'name':'a'},{'id':2,'name':'b'}]}
    after={'items':[{'id':1,'name':'b'},{'id':1,'name':'a'}]}
    b,a=flatten_pair(before,after,{'flatten':{'auto_key_candidates':['id','name']}})
    assert {r['ARRAY_KEY'] for r in b} == {r['ARRAY_KEY'] for r in a} == {'a','b'}
    doc={'items':[{'id':1,'type':'a'},{'id':1,'type':'b'},{'id':2,'type':'a'}]}
    rows=flatten(doc,{'flatten':{'auto_key_candidates':['id','type']}})
    assert {r['ARRAY_KEY'] for r in rows} == {'1+a','1+b','2+a'}


def test_null_bool_empty_and_depth():
    rows=flatten({'a':None,'b':False,'c':[], 'd':''},{})
    assert {r['PATH']:r['VALUE'] for r in rows} == {'a':'NULL','b':'false','d':''}
    issues=[]
    rows=flatten({'a':{'b':{'c':1}}},{'flatten':{'max_depth':2}},issues=issues)
    assert rows[0]['VALUE']=='{"c":1}'
    assert issues[0]['ISSUE']=='DEPTH_TRUNCATED'


def test_filters_wildcards_duplicates_and_fallback():
    assert matches('a.**.b','a.b') and matches('a.**.b','a.x.y.b')
    assert not matches('a.*.b','a.b')
    rows=flatten({'a':{'b':1,'c':2},'d':3},{'flatten':{'include_paths':['a'], 'exclude_paths':['a.c']}})
    assert [r['PATH'] for r in rows]==['a.b']
    issues=[]
    flatten({'a':[{'id':1},{'id':1}]},{'flatten':{'arrays':{'a':{'mode':'field','key':['id']}}}},issues=issues)
    assert any(i['ISSUE']=='DUPLICATE_KEY' for i in issues)
    issues=[]
    flatten({'a':[{'x':1}]},{'flatten':{'auto_key':False}},issues=issues)
    assert issues[0]['ISSUE']=='ARRAY_KEY_FALLBACK'


def test_buckets_boundaries_and_immutability():
    rows=flatten({'a':0,'b':1,'c':2,'d':-1,'e':False},{})
    old=deepcopy(rows)
    cfg={'buckets':{'default_unit':[0,1],'default_num':[0,1]}}
    out=bucketize(rows,cfg)
    assert rows==old
    assert [r['ADJUSTED_VALUE'] for r in out]==['[0 – 1]','[0 – 1]','(1 – +∞)','(-∞ – 0)','false']
    with pytest.raises(ValueError): bucketize(rows,{'buckets':{'default_unit':[1,0]}})


@pytest.mark.parametrize('xml',[
    '<root><a><id>1</id><value>0.5</value></a></root>',
    '<root><a><item><id>1</id><value>0.5</value></item></a></root>'])
def test_xml_singleton_and_wrapper(tmp_path,xml):
    cfg={'flatten':{'arrays':{'**.a':{'mode':'field','key':['id']}}}}
    path=tmp_path/'doc.xml'; path.write_text(xml)
    assert read_any(path,cfg)=={'a':[{'id':1,'value':.5}]}
