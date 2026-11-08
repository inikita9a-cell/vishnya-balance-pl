"""API regressions: check row -> exact application -> strict-JSON details."""
import json

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def details_api(tmp_path, monkeypatch):
    from backend.api import data_api, checks_api, check_apps_api
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'runs'/'r'
    root.mkdir(parents=True)
    comparison = pd.DataFrame([
        {'APP_ID':'I32554678','PATH':'decisionResult.product_trials.rules.name','ARRAY_KEY':'loan|AGELOW@21',
         'VALUE_BEFORE':'AGELOW@21','VALUE_AFTER':None,'DEPTH':None,'DIFF_FLAG':1,'CHANGE_TYPE':'ATTRIBUTE_LOST'},
        {'APP_ID':'other','PATH':'p','ARRAY_KEY':'','VALUE_BEFORE':'','VALUE_AFTER':'NULL',
         'DEPTH':3,'DIFF_FLAG':0,'CHANGE_TYPE':'SAME'},
    ])
    comparison.to_parquet(root/'comparison.parquet',index=False)
    # Nullable numeric and boolean metadata are common in historical artifacts.
    pd.DataFrame([{'APP_ID':'I32554678','DECISION_BEFORE':'REJECT','DECISION_AFTER':'APPROVE'},
                  {'APP_ID':'other','DECISION_BEFORE':'APPROVE','DECISION_AFTER':'APPROVE'}]).to_parquet(root/'segments.parquet',index=False)
    (root/'checks.json').write_text(json.dumps([{
        'CHECK_ID':'attribute_new_loss','LABEL':'Изменился состав атрибутов','SOURCE':'BEFORE',
        'ARGUMENT':'decisionResult.product_trials.rules.name','RESULT':'FAIL','CONFIDENCE':'HIGH',
        'CNT':1,'TOTAL':2,'METRIC':0.5,'APP_IDS':['I32554678'],'FILTERS':{'app_ids':['I32554678']},
    }]),encoding='utf-8')
    app = FastAPI()
    for module in (data_api,checks_api,check_apps_api):
        monkeypatch.setattr(module,'get_run_readable',lambda rid,user:None)
        app.include_router(module.router)
        app.dependency_overrides[module.current_user]=lambda:'reader'
    return TestClient(app), root


def test_check_application_details_are_json_safe(details_api):
    client,root=details_api
    rows=client.get('/api/runs/r/checks').json()
    response=client.post('/api/runs/r/checks/attribute_new_loss/apps',json={'row_id':rows[0]['ROW_ID'],'limit':100,'offset':0})
    assert response.status_code==200,response.text
    assert response.json()['items']==['I32554678']
    result=client.get('/api/runs/r/apps/I32554678?diff_only=1')
    assert result.status_code==200,result.text
    details=result.json()
    assert len(details)==1
    assert details[0]['VALUE_BEFORE']=='AGELOW@21'
    assert details[0]['VALUE_AFTER'] is None
    assert details[0]['DEPTH'] is None
    assert details[0]['ARRAY_KEY']=='loan|AGELOW@21'
    json.dumps(details,allow_nan=False)


def test_missing_application_artifact_is_not_an_empty_success(details_api):
    client,root=details_api
    (root/'comparison.parquet').unlink()
    response=client.get('/api/runs/r/apps/I32554678?diff_only=1')
    assert response.status_code==409
    assert 'comparison.parquet' in response.json()['detail']


def test_same_application_is_distinct_from_request_failure(details_api):
    client,_=details_api
    assert client.get('/api/runs/r/apps/other?diff_only=1').json()==[]
    response=client.get('/api/runs/r/apps/other?diff_only=0')
    assert response.status_code==200
    assert response.json()[0]['VALUE_BEFORE']==''
    assert response.json()[0]['VALUE_AFTER']=='NULL'
