import json
import sqlite3
import pandas as pd
from tools.compare_run_results import compare, TABLES


def prepared(tmp_path):
    before, after = tmp_path/'old', tmp_path/'new'
    rows = [{'APP_ID':'a','VALUE':'x'}, {'APP_ID':'b','VALUE':'y'}]
    for root, data in [(before,rows), (after,list(reversed(rows)))]:
        root.mkdir()
        for table in TABLES:
            pd.DataFrame(data).to_parquet(root/(table+'.parquet'),index=False)
        for name,value in [('checks.json',[{'CHECK_ID':'c','RESULT':'PASS','DURATION_MS':1 if root==before else 9}]),
                           ('procedures_snapshot.json',{'checks':['c']}),
                           ('summary.json',{'total_apps':2,'run_id':root.name,'summary_seconds':1 if root==before else 9})]:
            (root/name).write_text(json.dumps(value),encoding='utf-8')
    dbpath=tmp_path/'app.db'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE runs (id TEXT, status TEXT, config_snapshot TEXT)')
        db.execute('CREATE TABLE stage_logs (id INTEGER, run_id TEXT, step TEXT, status TEXT, code_snapshot TEXT, params TEXT)')
        for i,rid in enumerate(['old','new']):
            db.execute('INSERT INTO runs VALUES (?, ?, ?)',(rid,'done','pool: {mode: all}'))
            db.execute('INSERT INTO stage_logs VALUES (?, ?, ?, ?, ?, ?)',(i,rid,'normalize','done','code','{}'))
    return before,after,dbpath


def test_order_and_runtime_do_not_change_business_result(tmp_path):
    a,b,db=prepared(tmp_path)
    assert compare(a,b,db)['status']=='PASS'


def test_dropped_attribute_detected_even_when_summary_unchanged(tmp_path):
    a,b,db=prepared(tmp_path)
    pd.DataFrame([{'APP_ID':'a','VALUE':'x'}]).to_parquet(b/'comparison.parquet',index=False)
    result=compare(a,b,db)
    assert result['status']=='FAIL'
    assert result['files']['comparison']['rows_removed']==1


def test_missing_proof_is_not_pass(tmp_path):
    a,b,db=prepared(tmp_path)
    assert compare(a,b,None)['status']=='INCOMPLETE'
    (b/'quality.parquet').unlink()
    assert compare(a,b,db)['status']=='FAIL'


def test_changed_config_is_not_equivalent_run(tmp_path):
    a,b,dbpath=prepared(tmp_path)
    with sqlite3.connect(dbpath) as db:
        db.execute("UPDATE runs SET config_snapshot='pool: {mode: list}' WHERE id='new'")
    result=compare(a,b,dbpath)
    assert result['status']=='FAIL'
    assert result['metadata']['config_equal'] is False
