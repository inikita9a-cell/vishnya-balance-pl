"""A group's drill filters must reproduce its count, including implicit scope."""
import pandas as pd
import pytest
from backend.duck import explorer_query, explorer_apps


@pytest.mark.parametrize('include_unchanged,expected', [(False, 1), (True, 2)])
def test_drill_replays_implicit_diff_scope(tmp_path, include_unchanged, expected):
    pd.DataFrame([
        {'APP_ID': 'changed', 'PATH': 'score', 'DIFF_FLAG': 1},
        {'APP_ID': 'same', 'PATH': 'score', 'DIFF_FLAG': 0},
    ]).to_parquet(tmp_path / 'comparison.parquet', index=False)
    pd.DataFrame([
        {'APP_ID': aid, 'DECISION_BEFORE': 'APPROVE', 'DECISION_AFTER': 'APPROVE',
         'N_DIFFS': int(aid == 'changed'), 'COMPARISON_COMPLETE': 1}
        for aid in ['changed', 'same']
    ]).to_parquet(tmp_path / 'segments.parquet', index=False)
    query = explorer_query(tmp_path, ['PATH'], {}, include_unchanged, 10, 0)
    row = query['rows'][0]
    apps = explorer_apps(tmp_path, row['drilldownFilters'], 10, 0)
    assert row['appsCount'] == apps['total'] == len(apps['items']) == expected
    if not include_unchanged:
        assert [app['APP_ID'] for app in apps['items']] == ['changed']
