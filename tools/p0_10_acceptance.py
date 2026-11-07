"""P0-10: reproducible synthetic acceptance plus an optional original-dataset run.

Never changes source JSON/XML, configs, API files or existing run directories.
All text IO is explicitly UTF-8, including the resulting verification protocol.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def synthetic_config(dataset):
    return {
        'dataset': {'path': str(dataset), 'before_dir': 'before', 'after_dir': 'after',
                    'formats': ['json', 'xml'], 'use_manifest_excludes': False},
        'flatten': {'max_depth': 24, 'auto_key': True, 'arrays': {
            'catalog.products': {'mode': 'field', 'key': ['key_id', 'kind']},
            'catalog.products.offers': {'mode': 'field', 'key': ['key_id', 'band']},
            'catalog.products.offers.rules': {'mode': 'field', 'key': ['key_id', 'revision']},
            'catalog.products.offers.rules.models': {'mode': 'field', 'key': ['modelName']},
            'catalog.products.offers.rules.models.vector': {'mode': 'index'},
            '**.deep_array': {'mode': 'field', 'key': ['key_id', 'tag']},
        }},
        'buckets': {},
        'xml': {'strip_root': True, 'coerce_types': True, 'item_tags': ['item']},
        'segments': {'decision': 'audit_result.decision', 'reject_code': 'audit_result.reason',
                     'approve_value': 'ACCEPT', 'products': 'catalog.products.title',
                     'pd_model': 'catalog.products.offers.rules.models.modelName',
                     'input_paths': ['source'], 'logic_paths': ['audit_result', 'catalog']},
        'quality': {'required_paths': ['request_key', 'audit_result.decision'],
                    'reason_rules': [{'when_path': 'audit_result.decision', 'when_value': 'DECLINE',
                                      'require_path': 'audit_result.reason'}]},
        'checks': [],
    }


def base_document():
    return {'request_key': 'sample', 'audit_result': {'decision': 'ACCEPT'},
            'source': {'score': 10, 'nullable': None, 'enabled': False, 'code': '007'},
            'catalog': {'products': [{'key_id': 'p|1', 'kind': 'основной', 'title': 'Кредит'}]}}


def nested_document():
    doc = base_document()
    model_a = {'modelName': 'M|1', 'value': .1, 'vector': [.2, .7],
               'extra': {'l1': {'l2': {'l3': {'l4': {'l5': {
                   'deep_array': [{'key_id': 'a+b', 'tag': '%|', 'value': 'Глубокий'},
                                  {'key_id': 'a', 'tag': 'b+%|', 'value': 'Другой'}]}}}}}}}
    model_b = {'modelName': 'M2', 'value': .3, 'vector': [.1, .9]}
    rule = {'key_id': 'rule', 'revision': 'v1', 'models': [model_a, model_b]}
    offer = {'key_id': 'offer', 'band': 'A', 'rules': [rule, {**deepcopy(rule), 'revision': 'v2'}]}
    product = doc['catalog']['products'][0]
    product['offers'] = [offer, {**deepcopy(offer), 'band': 'B'}]
    doc['catalog']['products'].append({**deepcopy(product), 'kind': 'дополнительный'})
    return doc


def reorder(value, path=''):
    if isinstance(value, dict):
        return {k: reorder(v, f'{path}.{k}' if path else k) for k, v in reversed(list(value.items()))}
    if isinstance(value, list):
        items = [reorder(v, path) for v in value]
        return items if path.endswith('.vector') else list(reversed(items))
    return value


def as_xml(document):
    def node(name, value):
        if value is None:
            return f'<{name} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>'
        if isinstance(value, dict):
            content = ''.join(node(k, v) for k, v in value.items())
        elif isinstance(value, list):
            content = ''.join(node('item', v) for v in value)
        else:
            content = escape(str(value).lower() if isinstance(value, bool) else str(value))
        return f'<{name}>{content}</{name}>'
    return '<?xml version="1.0" encoding="UTF-8"?>' + node('response', document)


def build_synthetic(dataset):
    """15 APP_IDs: new field names, deep keys, mixed formats and damaged inputs."""
    dataset = Path(dataset)
    before, after = dataset / 'before', dataset / 'after'
    before.mkdir(parents=True, exist_ok=False)
    after.mkdir(parents=True, exist_ok=False)
    plain, deep = base_document(), nested_document()
    changed = deepcopy(plain)
    changed['source'].update(score=11, new_field='новый')
    changed['source'].pop('nullable')
    rejected = deepcopy(plain)
    rejected['audit_result'] = {'decision': 'DECLINE', 'reason': 'LIMIT'}
    no_reason = deepcopy(rejected)
    no_reason['audit_result'].pop('reason')
    vector = deepcopy(deep)
    vector['catalog']['products'][0]['offers'][0]['rules'][0]['models'][0]['vector'].reverse()
    model = reorder(deep)
    models = model['catalog']['products'][0]['offers'][0]['rules'][0]['models']
    next(item for item in models if item['modelName'] == 'M|1')['value'] = .8
    duplicate = deepcopy(plain)
    duplicate['catalog']['products'].append(deepcopy(duplicate['catalog']['products'][0]))
    no_key = deepcopy(plain)
    no_key['catalog']['products'][0].pop('key_id')
    fallback = deepcopy(plain)
    fallback['unknown_array'] = [{'payload': 'x'}, {'payload': 'y'}]
    cases = {
        'same': (plain, deepcopy(plain)),
        'attribute_changes': (plain, changed),
        'no_reason': (rejected, no_reason),
        'missing_after': (plain, None),
        'missing_before': (None, plain),
        'corrupt_json': (plain, '{broken json'),
        'invalid_root': (plain, '[]'),
        'xml_equivalent': (deep, as_xml(deep)),
        'nested_reorder': (deep, reorder(deep)),
        'index_vector': (deep, vector),
        'named_model': (deep, model),
        'corrupt_xml': (plain, '<response><broken>'),
        'duplicate_keys': (duplicate, deepcopy(duplicate)),
        'missing_array_key': (plain, no_key),
        'array_fallback': (fallback, deepcopy(fallback)),
    }
    for app_id, pair in cases.items():
        for folder, doc in zip((before, after), pair):
            if doc is None:
                continue
            xml = isinstance(doc, str) and doc.startswith('<')
            path = folder / f'{app_id}.{ "xml" if xml else "json"}'
            text = doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False, allow_nan=False)
            path.write_text(text, encoding='utf-8')
    return synthetic_config(dataset)


def input_hashes(dataset):
    root = Path(dataset)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*')) if path.is_file()}


def inspect_synthetic(run_dir):
    import pandas as pd
    root = Path(run_dir)
    comparison = pd.read_parquet(root / 'comparison.parquet')
    seg = pd.read_parquet(root / 'segments.parquet').set_index('APP_ID')
    quality = pd.read_parquet(root / 'quality.parquet')
    summary = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
    checks = []

    def verify(name, passed, details=''):
        checks.append({'name': name, 'passed': bool(passed), 'details': details})

    def rows(app_id):
        return comparison.loc[comparison.APP_ID.eq(app_id)]

    def issues(app_id):
        return set(quality.loc[quality.APP_ID.eq(app_id), 'ISSUE'])

    verify('all_applications_retained', len(seg) == 15 and summary['total_apps'] == 15)
    changes = rows('attribute_changes').set_index('PATH')
    verify('four_change_types',
           changes.loc['source.score', 'CHANGE_TYPE'] == 'VALUE_CHANGED'
           and changes.loc['source.nullable', 'CHANGE_TYPE'] == 'ATTRIBUTE_LOST'
           and changes.loc['source.new_field', 'CHANGE_TYPE'] == 'ATTRIBUTE_NEW'
           and changes.loc['request_key', 'CHANGE_TYPE'] == 'SAME')
    verify('changes_without_decision_change', seg.loc['attribute_changes', 'HAS_DIFF'] == 1
           and seg.loc['attribute_changes', 'DECISION_CHANGED'] == 0)
    reason = quality.loc[quality.APP_ID.eq('no_reason')]
    verify('decision_without_reason', seg.loc['no_reason', 'DECISION_AFTER'] == 'DECLINE'
           and pd.isna(seg.loc['no_reason', 'REASON_AFTER'])
           and 'DECISION_WITHOUT_REASON' in set(reason.ISSUE)
           and 'audit_result.reason' in set(reason.PATH))
    verify('missing_application_not_complete_pair',
           all(seg.loc[app, 'COMPARISON_COMPLETE'] == 0 and seg.loc[app, 'DECISION_CHANGED'] == 0
               for app in ('missing_after', 'missing_before'))
           and 'APP_MISSING_AFTER' in issues('missing_after')
           and 'APP_MISSING_BEFORE' in issues('missing_before'))
    verify('lost_attribute_is_complete_pair', seg.loc['attribute_changes', 'COMPARISON_COMPLETE'] == 1)
    verify('damaged_input_diagnosed',
           all('PARSE_ERROR' in issues(app) and seg.loc[app, 'COMPARISON_COMPLETE'] == 0
               and rows(app).empty for app in ('corrupt_json', 'invalid_root', 'corrupt_xml')))
    verify('json_xml_equivalent', seg.loc['xml_equivalent', 'N_DIFFS'] == 0
           and seg.loc['xml_equivalent', 'COMPARISON_COMPLETE'] == 1, str(issues('xml_equivalent')))
    verify('four_array_levels_reordered', seg.loc['nested_reorder', 'N_DIFFS'] == 0
           and seg.loc['nested_reorder', 'COMPARISON_COMPLETE'] == 1)
    deep = rows('nested_reorder')
    deep = deep.loc[deep.PATH.str.contains('deep_array')]
    verify('extended_depth_composite_keys', not deep.empty and deep.DEPTH.max() > 10
           and deep.ARRAY_KEY.str.contains('%7C', regex=False).any()
           and deep.ARRAY_KEY.str.contains('%2B', regex=False).any()
           and deep.ARRAY_KEY.str.contains('%25', regex=False).any())
    vector = rows('index_vector')
    vector = vector.loc[vector.DIFF_FLAG.eq(1)]
    verify('vector_compared_by_index', len(vector) == 2 and vector.PATH.str.endswith('.vector').all()
           and set(vector.CHANGE_TYPE) == {'VALUE_CHANGED'})
    model = rows('named_model')
    model = model.loc[model.DIFF_FLAG.eq(1)]
    verify('model_compared_by_name', len(model) == 1 and model.iloc[0].PATH.endswith('.models.value')
           and 'M%7C1' in model.iloc[0].ARRAY_KEY)
    verify('duplicate_keys_diagnosed', 'DUPLICATE_KEY' in issues('duplicate_keys')
           and seg.loc['duplicate_keys', 'COMPARISON_COMPLETE'] == 0)
    verify('missing_array_key_diagnosed', 'ARRAY_KEY_MISSING' in issues('missing_array_key')
           and seg.loc['missing_array_key', 'COMPARISON_COMPLETE'] == 0)
    verify('fallback_is_not_silent', 'ARRAY_KEY_FALLBACK' in issues('array_fallback')
           and seg.loc['array_fallback', 'COMPARISON_COMPLETE'] == 0)
    verify('summary_has_diagnostics', summary['apps_with_quality_issues'] > 0
           and summary['verdict']['status'] != 'PASS')
    return checks


def run_synthetic(output):
    from engine.pipeline import run_pipeline
    output = Path(output)
    cfg = build_synthetic(output / 'dataset')
    before = input_hashes(cfg['dataset']['path'])
    run_dir = output / 'run'
    run_pipeline(cfg, run_dir)
    results = inspect_synthetic(run_dir)
    results.append({'name': 'source_files_unchanged', 'passed': before == input_hashes(cfg['dataset']['path']), 'details': ''})
    return {'passed': all(item['passed'] for item in results), 'checks': results,
            'run_dir': str(run_dir), 'config': cfg}


def inspect_artifacts(run_dir):
    """Invariants independent of the 2002/502/385 acceptance oracle."""
    import pandas as pd
    root = Path(run_dir)
    summary = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
    comp = pd.read_parquet(root / 'comparison.parquet')
    seg = pd.read_parquet(root / 'segments.parquet')
    facts = pd.read_parquet(root / 'facts.parquet')
    members = pd.read_parquet(root / 'fact_apps.parquet')
    expected = facts['FACT_ID'].map(members.groupby('FACT_ID')['APP_ID'].nunique())
    checks = {
        'one_segment_per_application': not seg['APP_ID'].duplicated().any() and len(seg) == summary['total_apps'],
        'comparison_keys_unique': not comp.duplicated(['APP_ID', 'PATH', 'ARRAY_KEY']).any(),
        'change_types_valid': comp['CHANGE_TYPE'].isin(['SAME', 'VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']).all(),
        'diff_flag_agrees_with_type': comp['DIFF_FLAG'].eq(comp['CHANGE_TYPE'].ne('SAME').astype(int)).all(),
        'summary_diff_count_matches_segments': summary['apps_with_diff'] == int(seg['HAS_DIFF'].sum()),
        'summary_decision_count_matches_segments': summary['apps_decision_changed'] == int(seg['DECISION_CHANGED'].sum()),
        'facts_cnt_matches_distinct_app_ids': facts['CNT'].eq(expected).all(),
        'fact_memberships_unique': not members.duplicated(['FACT_ID', 'APP_ID']).any(),
        'fact_memberships_known_ids': members['APP_ID'].isin(seg['APP_ID']).all(),
        'all_fact_ids_have_memberships': set(members['FACT_ID']) == set(facts['FACT_ID']),
    }
    return {'passed': all(checks.values()), 'checks': {k: bool(v) for k, v in checks.items()},
            'change_type_rows': {str(k): int(v) for k, v in comp['CHANGE_TYPE'].value_counts().items()},
            'applications_incomplete': int(seg['COMPARISON_COMPLETE'].eq(0).sum())}


def verify_public(summary, status):
    """Explicit acceptance oracle for the original open set, never engine logic."""
    expected = {'total_apps': 2002, 'apps_with_diff': 502, 'apps_decision_changed': 385}
    actual = {key: summary.get(key) for key in expected}
    return {'passed': actual == expected and not status.get('skipped_parse_app_ids'),
            'expected': expected, 'actual': actual,
            'skipped_parse_app_ids': status.get('skipped_parse_app_ids', [])}


def main():
    import yaml
    from engine.pipeline import run_pipeline
    from engine.steps import discover
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-dataset', help='Original 2002-pair dataset; enables 2002/502/385 verification')
    parser.add_argument('--config', default=str(ROOT / 'configs/default_spr.yaml'))
    parser.add_argument('--out', help='New output directory; never reuse old run outputs')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    output = Path(args.out or ROOT / 'runs' / f'p0_10_{stamp}_{uuid4().hex[:6]}').resolve()
    output.mkdir(parents=True, exist_ok=False)
    synthetic = run_synthetic(output / 'synthetic')
    protocol = {'synthetic': {k: v for k, v in synthetic.items() if k != 'config'},
                'public': {'status': 'NOT_RUN', 'reason': 'Pass --public-dataset for original-data verification'}}
    protocol['synthetic']['artifacts'] = inspect_artifacts(synthetic['run_dir'])
    if args.public_dataset:
        cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8-sig'))
        cfg['dataset']['path'] = str(Path(args.public_dataset).resolve())
        cfg['pool'] = {'mode': 'all'}
        pairs = discover(cfg['dataset'], cfg['pool'])
        full_pairs = sum(pair['file_before'] is not None and pair['file_after'] is not None for pair in pairs)
        inputs_before = input_hashes(cfg['dataset']['path'])
        start = time.perf_counter()
        def progress(event):
            if event['status'] == 'done':
                print(f'PUBLIC STAGE: {event["step"]} done', flush=True)
        result = run_pipeline(cfg, output / 'public', progress)
        protocol['public'] = {**verify_public(result['summary'], result['comparison_status']),
                              'status': 'VERIFIED', 'seconds': round(time.perf_counter() - start, 3),
                              'run_dir': str(output / 'public'), 'complete_file_pairs': full_pairs,
                              'source_files_unchanged': inputs_before == input_hashes(cfg['dataset']['path']),
                              'artifacts': inspect_artifacts(output / 'public')}
        protocol['public']['passed'] = (protocol['public']['passed'] and full_pairs == 2002
                                        and protocol['public']['source_files_unchanged']
                                        and protocol['public']['artifacts']['passed'])
        protocol['public']['status'] = 'PASS' if protocol['public']['passed'] else 'FAIL'
    protocol['passed'] = (synthetic['passed'] and protocol['synthetic']['artifacts']['passed']
                           and (not args.public_dataset or protocol['public']['passed']))
    path = output / 'acceptance.json'
    path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in synthetic['checks']:
        print(f'{"PASS" if item["passed"] else "FAIL"}: {item["name"]}', flush=True)
    print('PUBLIC: ' + json.dumps(protocol['public'], ensure_ascii=False), flush=True)
    label = 'P0-10' if args.public_dataset else 'P0-10 SYNTHETIC ONLY'
    print(f'{label} {"OK" if protocol["passed"] else "FAILED"}: {path}', flush=True)
    return 0 if protocol['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
