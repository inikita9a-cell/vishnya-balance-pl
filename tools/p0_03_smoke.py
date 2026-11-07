"""Synthetic P0-03 proof, no edits to the project's dataset, configs or database."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import pandas as pd
    from engine.pipeline import run_pipeline
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', help='New directory for demo inputs and outputs')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    out = Path(args.out or ROOT / 'runs' / f'p0_03_smoke_{stamp}_{uuid4().hex[:6]}').resolve()
    out.mkdir(parents=True, exist_ok=False)
    dataset = out / 'demo_dataset'
    for side, score in [('BEFORE_MASTER', 1), ('AFTER_BETA', 2)]:
        folder = dataset / 'RESULTS' / side
        folder.mkdir(parents=True)
        (folder / 'demo.json').write_text(json.dumps({'risk': {'score': score}, 'decision': 'YES'}), encoding='utf-8')
    cfg = {'dataset': {'path': str(dataset), 'before_dir': 'RESULTS/BEFORE_MASTER',
                       'after_dir': 'RESULTS/AFTER_BETA', 'formats': ['json']},
           'quality': {}, 'segments': {'decision': 'decision', 'approve_value': 'YES'},
           'checks': []}
    baseline = run_pipeline(cfg, out / 'builtin')
    specs = {}
    for kind, params in [('normalize', {'marker': 'P003'}),
                         ('compare', {'ignore_path': 'risk.score'}),
                         ('facts', {'dimension': 'chosen'})]:
        specs[kind] = {'source': 'file', 'path': str(ROOT / 'examples/p0_03' / f'{kind}.py'), 'params': params}
    cfg['procedures'] = specs
    cfg['checks'] = [{'id': 'demo_check', 'source': 'file',
                      'path': str(ROOT / 'examples/p0_03/check.py'), 'params': {'label': 'USER CODE EXECUTED'}}]
    events = []
    selected = run_pipeline(cfg, out / 'selected', events.append)
    assert baseline['summary']['apps_with_diff'] == 1
    assert selected['summary']['apps_with_diff'] == 0
    united = pd.read_parquet(out / 'selected/union.parquet')
    assert set(united.loc[united.PATH.eq('custom_marker'), 'VALUE']) == {'P003'}
    assert pd.read_parquet(out / 'selected/facts.parquet').CUSTOM_DIMENSION.eq('chosen').all()
    rows = json.loads((out / 'selected/checks.json').read_text(encoding='utf-8'))
    assert rows[0]['LABEL'] == 'USER CODE EXECUTED' and rows[0]['RESULT'] == 'PASS'
    assert sum('code_snapshot' in event for event in events) == 4
    print('P0-03 OK: normalize / compare / facts / checks execute selected Python')
    print(json.dumps({'builtin_apps_with_diff': 1, 'selected_apps_with_diff': 0,
                      'custom_normalize': 'P003', 'custom_facts': 'chosen', 'check': rows[0]['RESULT'],
                      'source_snapshots': 4, 'output': str(out)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
