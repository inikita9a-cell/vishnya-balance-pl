"""Real Parquet flows: no cycles, conserved totals and exact drill-through filters."""
import json

import pandas as pd
import pytest

from backend.duck import get_sankey_data


@pytest.fixture
def segment_run(tmp_path):
    # Include unchanged decisions, opposite transitions, missing and literal values.
    rows = [
        ('a', 'APPROVE', 'APPROVE', None),
        ('b', 'APPROVE', 'REJECT', 'R1→R2'),
        ('c', 'REJECT', 'APPROVE', 'R2→∅'),
        ('d', 'REJECT', 'REJECT', 'R1→R2'),
        ('e', None, 'NULL', ''),
        ('f', '', None, 'NULL'),
        ('g', 'APPROVE', 'REJECT', 'R1→R2'),
        ('h', 'APPROVE', 'REJECT', 'R3→R4'),
    ]
    frame = pd.DataFrame(rows, columns=['APP_ID','DECISION_BEFORE','DECISION_AFTER','REASON_TRANSITION'])
    # Accidental identical rows must not inflate application counts.
    pd.concat([frame, frame.iloc[[0,1]]]).to_parquet(tmp_path/'segments.parquet',index=False)
    return tmp_path, frame


def test_sankey_levels_are_acyclic_and_totals_conserved(segment_run):
    root, frame = segment_run
    data = get_sankey_data(root)
    nodes = {node['name']:node for node in data['nodes']}
    assert len(nodes) == len(data['nodes'])
    assert sum(link['value'] for link in data['links'] if nodes[link['source']]['depth']==0)==len(frame)
    for link in data['links']:
        assert nodes[link['target']]['depth']==nodes[link['source']]['depth']+1
        assert link['source']!=link['target']
        selected = frame
        for field, value in link['filters'].items():
            selected = selected[selected[field].isna() if value is None else selected[field]==value]
        assert selected.APP_ID.nunique()==link['value']
    for node in data['nodes']:
        if node['depth']==1:
            assert sum(link['value'] for link in data['links'] if link['target']==node['name']) == sum(link['value'] for link in data['links'] if link['source']==node['name'])
    assert {json.loads(node['name'])[2] for node in data['nodes'] if node['depth']==0} >= {None,''}


def test_sankey_filters_are_parameterized_and_exact(segment_run):
    root, frame = segment_run
    for filters in [{'DECISION_AFTER':'REJECT'}, {'REASON_TRANSITION':None}, {'DECISION_BEFORE':['APPROVE','REJECT']}]:
        data = get_sankey_data(root,filters)
        selected = frame
        for key,value in filters.items():
            selected = selected[selected[key].isna() if value is None else selected[key].isin(value) if isinstance(value,list) else selected[key]==value]
        nodes={node['name']:node for node in data['nodes']}
        assert sum(link['value'] for link in data['links'] if nodes[link['source']]['depth']==0)==len(selected)
    assert get_sankey_data(root,{'DECISION_BEFORE':"x' OR 1=1 --"})=={'nodes':[],'links':[]}
    with pytest.raises(ValueError):
        get_sankey_data(root,{'BAD_COLUMN':'x'})


def test_sankey_missing_artifact_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_sankey_data(tmp_path)
