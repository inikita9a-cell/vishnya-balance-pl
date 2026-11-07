import json
import pandas as pd
import pytest
from engine.steps import flatten_pair, union, compare, check_keys, discover, prepare_comparison


def test_four_changes_and_null_vs_absent():
    b,a=flatten_pair({'same':1,'changed':.42,'lost':None,'empty':''},
                     {'same':1,'changed':.58,'new':None,'empty':None},{},app_id='1')
    result=compare(union(b,a)).set_index('PATH')
    assert result.CHANGE_TYPE.to_dict()=={'same':'SAME','changed':'VALUE_CHANGED',
        'lost':'ATTRIBUTE_LOST','new':'ATTRIBUTE_NEW','empty':'VALUE_CHANGED'}
    assert result.loc['lost','VALUE_BEFORE']=='NULL'
    assert pd.isna(result.loc['lost','VALUE_AFTER'])
    assert result.DIFF_FLAG.sum()==4


def test_duplicate_keys_excluded_on_both_sides():
    b,a=flatten_pair({'x':1,'ok':2},{'x':2,'ok':2},{},app_id='1')
    u=union(b+[b[0]],a)
    assert len(check_keys(u))==2
    issues=[]
    result=compare(u,issues=issues)
    assert result.PATH.tolist()==['ok']
    assert issues[0]['ISSUE']=='DUPLICATE_KEY'


def test_empty_schema_and_parquet(tmp_path):
    u=union([],[]); c=compare(u)
    assert c.empty and 'DIFF_FLAG' in c
    c.to_parquet(tmp_path/'empty.parquet',index=False)
    assert list(pd.read_parquet(tmp_path/'empty.parquet').columns)==list(c.columns)


def dataset(tmp_path):
    for name in ['before','after']: (tmp_path/name).mkdir()
    return {'dataset':{'path':str(tmp_path),'before_dir':'before','after_dir':'after'}}


def test_discovery_errors_and_pool(tmp_path):
    cfg=dataset(tmp_path)
    (tmp_path/'before'/'1.json').write_text('{}')
    pairs=discover(cfg['dataset'],{'mode':'list','app_ids':['1','2']})
    assert len(pairs)==2 and pairs[0]['file_after'] is None and pairs[1]['file_before'] is None
    with pytest.raises(ValueError,match='requires segments'):
        discover(cfg['dataset'],{'mode':'filter'})
    (tmp_path/'before'/'1.xml').write_text('<root/>')
    with pytest.raises(ValueError,match='Ambiguous'):
        discover(cfg['dataset'])


def test_file_pipeline_manifest_missing_and_corrupt(tmp_path):
    cfg=dataset(tmp_path)
    for app in ['ok','missing','bad']:
        (tmp_path/'before'/f'{app}.json').write_text('{"x":1,"technical":1}')
    (tmp_path/'after'/'ok.json').write_text('{"x":1,"technical":2}')
    (tmp_path/'after'/'bad.json').write_text('broken')
    (tmp_path/'manifest.json').write_text('{"technical_fields_always_differ":["technical"]}')
    out=tmp_path/'run'
    status=prepare_comparison(cfg,out)
    c=pd.read_parquet(out/'comparison.parquet')
    q=pd.read_parquet(out/'quality.parquet')
    assert status['total_apps']==3 and status['skipped_parse_app_ids']==['bad']
    assert status['diff_rows']==1 and status['incomplete']
    assert set(c.APP_ID)=={'ok','missing'} and set(c.PATH)=={'x'}
    assert set(q.ISSUE)=={'PARSE_ERROR','APP_MISSING_AFTER'}
    assert cfg.get('flatten') is None
    with pytest.raises(FileExistsError): prepare_comparison(cfg,out)


def test_teaching_comparison_six_changes():
    from pathlib import Path
    from test_normalization import sample_config
    root=Path(__file__).parent/'fixtures'
    b,a=[json.loads((root/name).read_text()) for name in
         ('01_response_BEFORE_MASTER_app1001.json','02_response_AFTER_BETA_app1001.json')]
    result=compare(union(*flatten_pair(b,a,sample_config(),app_id='1001')))
    assert len(result)==14
    assert result.CHANGE_TYPE.value_counts().to_dict()=={'SAME':8,'VALUE_CHANGED':4,'ATTRIBUTE_NEW':2}
    assert result.DIFF_FLAG.sum()==6
