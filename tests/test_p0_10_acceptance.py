"""P0-10 acceptance over a deliberately different JSON/XML schema."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.pipeline import run_pipeline
from engine.steps import flatten_pair, compare, union
from tools.p0_10_acceptance import (run_synthetic, build_synthetic, synthetic_config,
                                    nested_document, verify_public, as_xml, inspect_artifacts)


@pytest.fixture(scope='module')
def synthetic(tmp_path_factory):
    return run_synthetic(tmp_path_factory.mktemp('p0_10'))


@pytest.mark.parametrize('name', [
    'all_applications_retained', 'four_change_types', 'changes_without_decision_change',
    'decision_without_reason', 'missing_application_not_complete_pair', 'lost_attribute_is_complete_pair',
    'damaged_input_diagnosed', 'json_xml_equivalent', 'four_array_levels_reordered',
    'extended_depth_composite_keys', 'vector_compared_by_index', 'model_compared_by_name',
    'duplicate_keys_diagnosed', 'missing_array_key_diagnosed', 'fallback_is_not_silent',
    'summary_has_diagnostics', 'source_files_unchanged',
])
def test_synthetic_acceptance(synthetic, name):
    result = next(check for check in synthetic['checks'] if check['name'] == name)
    assert result['passed'], result


def test_depth_limit_is_diagnosed_and_does_not_bypass_path_filters():
    cfg = synthetic_config('unused')
    cfg['flatten']['max_depth'] = 3
    cfg['flatten']['exclude_paths'] = ['catalog.products.offers.rules']
    issues = []
    b, a = flatten_pair(nested_document(), nested_document(), cfg, app_id='deep', issues=issues)
    assert any(item['ISSUE'] == 'DEPTH_TRUNCATED' for item in issues)
    assert all('models' not in row['VALUE'] for row in b + a)
    assert not any(row['PATH'].startswith('catalog.products.offers.rules') for row in b + a)


def test_repeated_run_is_deterministic(synthetic, tmp_path):
    cfg = deepcopy(synthetic['config'])
    repeated = tmp_path / 'second'
    run_pipeline(cfg, repeated)
    for name in ['union', 'comparison', 'quality', 'segments', 'blocks', 'facts', 'fact_apps']:
        original = pd.read_parquet(Path(synthetic['run_dir']) / f'{name}.parquet')
        actual = pd.read_parquet(repeated / f'{name}.parquet')
        pd.testing.assert_frame_equal(actual, original)


def test_exact_fact_counts_and_summary_are_consistent(synthetic):
    results = inspect_artifacts(synthetic['run_dir'])
    assert results['passed'], results


def test_json_xml_equivalence_preserves_unicode_null_bool_and_leading_zero(tmp_path):
    from engine.adapters import read_any
    document = nested_document()
    path = tmp_path / 'response.xml'
    path.write_text(as_xml(document), encoding='utf-8')
    actual = read_any(path, synthetic_config('unused'))
    assert actual == document
    assert actual['source']['code'] == '007'
    assert actual['source']['nullable'] is None
    assert actual['source']['enabled'] is False


def test_public_oracle_checks_actual_numbers_does_not_overwrite_them():
    values = {'total_apps': 7, 'apps_with_diff': 3, 'apps_decision_changed': 1}
    original = deepcopy(values)
    assert not verify_public(values, {})['passed']
    assert values == original
    exact = {'total_apps': 2002, 'apps_with_diff': 502, 'apps_decision_changed': 385}
    assert verify_public(exact, {})['passed']
    assert not verify_public(exact, {'skipped_parse_app_ids': ['bad']})['passed']
