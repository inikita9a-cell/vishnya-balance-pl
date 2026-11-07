"""Step 7: pure Verdict math and reading existing run artifacts."""
import json
import pandas as pd
import pytest

from engine.summary import build_summary, prepare_summary


def sample():
    # d: comparison is incomplete; even if decisions are present, rates should
    # not count them as reliable. No dataset-specific JSON paths are required.
    segments = pd.DataFrame([
        ['a', 'REJECT', 'APPROVE', 1, 1, 1, 1, 2, 0, 'LOGIC', 'STOP_FACTOR', 'AGE', None],
        ['b', 'APPROVE', 'APPROVE', 1, 0, 1, 1, 1, 0, 'INPUT_DATA', 'SCORE_CHANGE', None, None],
        ['c', 'REJECT', 'REJECT', 1, 0, 1, 0, 0, 0, 'NONE', 'NONE', 'AGE', 'AGE'],
        ['d', 'REJECT', 'APPROVE', 1, 1, 0, 1, 1, 1, 'BOTH', 'OTHER', 'AGE', None],
        ['e', 'APPROVE', 'APPROVE', 1, 0, 1, 0, 0, 0, 'NONE', 'NONE', None, None],
    ], columns=['APP_ID', 'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_COMPARABLE',
                'DECISION_CHANGED', 'COMPARISON_COMPLETE', 'HAS_DIFF', 'N_DIFFS',
                'QUALITY_ISSUE', 'CAUSE', 'CAUSE_DETAIL', 'REASON_BEFORE', 'REASON_AFTER'])
    comparison = pd.DataFrame([
        ['a', 'strategy.decision', 1, 'VALUE_CHANGED'],
        ['a', 'strategy.score', 1, 'VALUE_CHANGED'],
        ['b', 'input.score', 1, 'VALUE_CHANGED'],
        ['c', 'strategy.decision', 0, 'SAME'],
        ['d', 'strategy.reason', 1, 'ATTRIBUTE_LOST'],
        ['e', 'strategy.decision', 0, 'SAME'],
    ], columns=['APP_ID', 'PATH', 'DIFF_FLAG', 'CHANGE_TYPE'])
    blocks = pd.DataFrame([
        ['strategy', 1, 5, 2, 0.4, 3],
        ['input', 1, 5, 1, 0.2, 1],
    ], columns=['BLOCK', 'LEVEL', 'APPS_TOTAL', 'APPS_CHANGED', 'SHARE', 'ROWS_CHANGED'])
    quality = pd.DataFrame([['d', 'APP_MISSING_AFTER']], columns=['APP_ID', 'ISSUE'])
    checks = [
        {'CHECK_ID': 'first', 'LABEL': 'One', 'RESULT': 'PASS'},
        {'CHECK_ID': 'first', 'LABEL': 'One', 'RESULT': 'FAIL'},
        {'CHECK_ID': 'second', 'LABEL': 'Two', 'RESULT': 'ERROR'},
    ]
    return segments, comparison, blocks, quality, checks


def config(n=20):
    return {'segments': {'approve_value': 'APPROVE'}, 'summary': {'top_n': n}}


def test_summary_main_metrics_and_approval_denominator():
    result = build_summary(*sample(), cfg=config(), run_id='run_demo')
    assert result['schema_version'] == 1
    assert result['run_id'] == 'run_demo'
    assert result['total_apps'] == 5
    assert result['apps_with_diff'] == 3
    assert result['apps_decision_changed'] == 1  # incomplete d excluded
    assert result['apps_decision_comparable'] == 4
    assert result['apps_comparison_incomplete'] == 1
    assert result['apps_diff_but_decision_same'] == 1
    assert result['diff_rows'] == 4
    assert result['approval_rates'] == {
        'approve_value': 'APPROVE', 'denominator': 4,
        'before_count': 2, 'after_count': 3,
        'before_rate': 0.5, 'after_rate': 0.75, 'delta_pp': 25.0,
    }
    assert sum(item['count'] for item in result['decision_transitions']) == 4
    assert not any(item['before'] == 'REJECT' and item['after'] == 'APPROVE'
                   and item['count'] > 1 for item in result['decision_transitions'])
    assert result['cause_counts'] == {'NONE': 2, 'LOGIC': 1, 'INPUT_DATA': 1, 'BOTH': 1}
    assert result['checks']['checks_selected'] == 2
    assert result['checks']['rows'] == 3
    assert result['checks']['pass'] == result['checks']['fail'] == result['checks']['error'] == 1
    assert result['verdict']['status'] == 'INCOMPLETE'
    json.dumps(result, allow_nan=False)


def test_changed_path_and_block_sorting_top_n():
    result = build_summary(*sample(), cfg=config(1))
    assert len(result['top_changed_paths']) == 1
    assert result['top_changed_paths'][0]['path'] == 'input.score'  # same counts, lexicographic
    assert result['top_changed_blocks'][0]['block'] == 'strategy'
    assert result['top_changed_blocks'][0]['apps_changed'] == 2
    assert result['change_types'] == [
        {'change_type': 'VALUE_CHANGED', 'rows_changed': 3, 'apps_changed': 2},
        {'change_type': 'ATTRIBUTE_NEW', 'rows_changed': 0, 'apps_changed': 0},
        {'change_type': 'ATTRIBUTE_LOST', 'rows_changed': 1, 'apps_changed': 1},
    ]


def test_reasons_matrix_handles_nulls_and_missing_values():
    result = build_summary(*sample(), cfg=config())
    reasons = {(x['before'], x['after']): x['count'] for x in result['reason_transitions']}
    assert reasons[('AGE', '∅')] == 1
    assert reasons[('∅', '∅')] == 2
    assert sum(reasons.values()) == 4


def test_no_checks_is_pending_and_does_not_invent_passes():
    s, c, b, q, _ = sample()
    r = build_summary(s, c, b, q, None, config())
    assert r['checks']['status'] == 'NOT_RUN'
    assert r['checks']['rows'] == 0
    assert 'CHECKS_NOT_RUN' in r['verdict']['reason_codes']


def test_empty_app_set_has_null_approval_rates():
    s, c, b, q, _ = sample()
    s = s.iloc[:0].copy()
    c = c.iloc[:0].copy()
    b = b.iloc[:0].copy()
    q = q.iloc[:0].copy()
    r = build_summary(s, c, b, q, [], config())
    assert r['total_apps'] == 0
    assert r['approval_rates']['before_rate'] is None
    assert r['approval_rates']['delta_pp'] is None
    assert r['decision_transitions'] == []
    assert r['verdict']['status'] == 'INCOMPLETE'


def test_checks_status_when_only_pass_and_no_changes():
    s, c, b, q, _ = sample()
    s = s[s.APP_ID.isin(['c', 'e'])].copy()
    c = c[c.APP_ID.isin(['c', 'e'])].copy()
    b = b.iloc[:0].copy()
    q = q.iloc[:0].copy()
    r = build_summary(s, c, b, q,
                      [{'CHECK_ID': 'ok', 'LABEL': 'ok', 'RESULT': 'PASS'}], config())
    assert r['verdict']['status'] == 'NO_CHANGES_OBSERVED'
    assert r['apps_with_diff'] == 0


def test_missing_approve_value_does_not_assume_label():
    s, c, b, q, checks = sample()
    r = build_summary(s, c, b, q, checks, cfg={'summary': {'top_n': 2}})
    assert r['approval_rates']['approve_value'] is None
    assert r['approval_rates']['before_count'] is None
    assert r['decision_distribution']['before']['APPROVE'] == 2


@pytest.mark.parametrize('n', [0, -1, 101, 1.4, '20'])
def test_reject_invalid_top_n(n):
    with pytest.raises(ValueError, match='summary.top_n'):
        build_summary(*sample(), cfg=config(n))


def test_duplicate_segment_app_rejected():
    s, c, b, q, checks = sample()
    s = pd.concat([s, s.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match='unique APP_ID'):
        build_summary(s, c, b, q, checks, config())


def test_unknown_comparison_app_rejected():
    s, c, b, q, checks = sample()
    c.loc[0, 'APP_ID'] = 'unknown'
    with pytest.raises(ValueError, match='not in segments'):
        build_summary(s, c, b, q, checks, config())


def test_pure_function_does_not_mutate_sources():
    data = sample()
    copies = [item.copy(deep=True) if isinstance(item, pd.DataFrame) else
              [dict(row) for row in item] for item in data]
    build_summary(*data, cfg=config())
    for a, b in zip(data, copies):
        if isinstance(a, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b)
        else:
            assert a == b


def test_prepare_summary_reads_only_preprocessed_files_and_updates_atomically(tmp_path, monkeypatch):
    import engine.summary as module
    s, c, b, q, checks = sample()
    frames = {'segments.parquet': s, 'comparison.parquet': c, 'blocks.parquet': b,
              'quality.parquet': q}
    for filename in frames:
        (tmp_path / filename).touch()
    (tmp_path / 'checks.json').write_text(json.dumps(checks), encoding='utf-8')
    (tmp_path / 'comparison_status.json').write_text(json.dumps({
        'stage': 'checks', 'duration_seconds': 20.0, 'summary_seconds': 0.0,
        'total_apps': 5}), encoding='utf-8')
    def reader(path, columns=None):
        df = frames[path.name].copy(deep=True)
        return df[list(columns)] if columns is not None else df
    monkeypatch.setattr(module.pd, 'read_parquet', reader)
    first = prepare_summary(tmp_path, config())
    assert first['run_id'] == tmp_path.name
    assert first['checks']['rows'] == 3
    out = json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))
    assert out == first
    status = json.loads((tmp_path / 'comparison_status.json').read_text(encoding='utf-8'))
    assert status['stage'] == 'checks' and status['summary_ready'] is True
    assert status['total_apps'] == 5
    assert status['duration_seconds'] >= 20
    (tmp_path / 'checks.json').write_text(json.dumps([
        {'CHECK_ID': 'ok', 'LABEL': 'OK', 'RESULT': 'PASS'}]), encoding='utf-8')
    second = prepare_summary(tmp_path, config())
    assert second['checks']['rows'] == 1
    status2 = json.loads((tmp_path / 'comparison_status.json').read_text(encoding='utf-8'))
    # A second summary call replaces previous time instead of counting it twice.
    assert abs(status2['duration_seconds'] - (20 + second['summary_seconds'])) < 0.01


def test_prepare_summary_requires_artifacts(tmp_path):
    with pytest.raises(FileNotFoundError, match='segments.parquet'):
        prepare_summary(tmp_path, config())


def test_malformed_checks_report_is_error_not_fake_pass():
    s, c, b, q, _ = sample()
    with pytest.raises(ValueError, match='JSON array'):
        build_summary(s, c, b, q, {'RESULT': 'PASS'}, config())


def test_quality_issue_without_diff_still_requires_review():
    s, c, b, q, _ = sample()
    s = s[s.APP_ID.isin(['c'])].copy()
    s.loc[:, 'QUALITY_ISSUE'] = 1
    c = c[c.APP_ID.isin(['c'])].copy()
    b = b.iloc[:0].copy()
    q = pd.DataFrame([['c', 'WARNING']], columns=['APP_ID', 'ISSUE'])
    r = build_summary(s, c, b, q,
                      [{'CHECK_ID': 'ok', 'LABEL': 'OK', 'RESULT': 'PASS'}], config())
    assert r['verdict']['status'] == 'REVIEW_REQUIRED'


def test_invalid_check_result_is_not_ignored():
    s, c, b, q, _ = sample()
    with pytest.raises(ValueError, match='Unexpected checks.RESULT'):
        build_summary(s, c, b, q,
                      [{'CHECK_ID': 'ok', 'LABEL': 'Bad', 'RESULT': 'SKIPPED'}], config())
