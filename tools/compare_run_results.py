"""Read-only comparison of two saved runs. Never executes or rewrites a run."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pyarrow.parquet as pq
import yaml

TABLES = ('union', 'comparison', 'quality', 'segments', 'blocks', 'facts', 'fact_apps')
COUNTS = ('total_apps', 'apps_with_diff', 'apps_decision_changed',
          'apps_comparison_incomplete', 'comparison_rows', 'diff_rows')


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def parquet_signature(path):
    source = pq.ParquetFile(path)
    schema = sorted((f.name, str(f.type)) for f in source.schema_arrow)
    counts = Counter()
    for batch in source.iter_batches(batch_size=10000):
        for row in batch.to_pylist():
            counts[hashlib.sha256(stable(row).encode('utf-8')).hexdigest()] += 1
    return schema, source.metadata.num_rows, counts


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def check_signature(path):
    # Runtime and traceback locations are not business results; retain every other field.
    return Counter(stable({k:v for k,v in row.items() if k not in ('DURATION_MS','TRACEBACK')})
                   for row in read_json(path))


def metadata(db_path, run_id):
    uri = db_path.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        row = db.execute('SELECT status, config_snapshot FROM runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise ValueError(f'Run metadata not found: {run_id}')
        cfg = yaml.safe_load(row[1]) or {}
        cfg.pop('_meta', None)
        stages = {}
        for step, status, code, params in db.execute(
                'SELECT step,status,code_snapshot,params FROM stage_logs WHERE run_id=? ORDER BY id', (run_id,)):
            if step not in stages:
                stages[step] = {'status':status, 'code':code, 'params':json.loads(params) if params else None}
        return {'status':row[0], 'config':cfg, 'stages':stages}


def compare(before, after, db_path=None):
    report = {'status':'INCOMPLETE', 'files':{}, 'metadata':{}, 'summary_counts':{}}
    for name in TABLES:
        a, b = before / (name+'.parquet'), after / (name+'.parquet')
        if not a.is_file() or not b.is_file():
            report['files'][name] = {'equal':False, 'issue':'required artifact missing'}
            continue
        sa, na, ca = parquet_signature(a)
        sb, nb, cb = parquet_signature(b)
        report['files'][name] = {'equal':sa==sb and ca==cb, 'rows_before':na, 'rows_after':nb,
                                 'rows_removed':sum((ca-cb).values()), 'rows_added':sum((cb-ca).values())}
    for name in ('checks.json','procedures_snapshot.json','summary.json'):
        a, b = before/name, after/name
        if not a.is_file() or not b.is_file():
            report['files'][name] = {'equal':False,'issue':'required artifact missing'}
            continue
        if name == 'checks.json':
            va, vb = check_signature(a), check_signature(b)
            details = {'rows_before':sum(va.values()), 'rows_after':sum(vb.values())}
        else:
            va, vb = read_json(a), read_json(b)
            details = {}
            if name == 'summary.json':
                report['summary_counts'] = {k:{'before':va.get(k),'after':vb.get(k)} for k in COUNTS}
                va = {k:v for k,v in va.items() if k not in ('run_id','summary_seconds')}
                vb = {k:v for k,v in vb.items() if k not in ('run_id','summary_seconds')}
        report['files'][name] = {'equal':va==vb, **details}
    report['artifacts_equal'] = all(v['equal'] for v in report['files'].values())
    if db_path and db_path.is_file():
        try:
            a, b = metadata(db_path,before.name), metadata(db_path,after.name)
            report['metadata'] = {
                'config_equal':a['config']==b['config'],
                'executed_stages_equal':bool(a['stages']) and a['stages']==b['stages'] and
                    all(stage['status']=='done' for stage in a['stages'].values()),
                'both_done':a['status']==b['status']=='done',
                'stage_count_before':len(a['stages']), 'stage_count_after':len(b['stages']),
            }
            meta_ok = all(report['metadata'][k] for k in ('config_equal','executed_stages_equal','both_done'))
            report['status'] = 'PASS' if report['artifacts_equal'] and meta_ok else 'FAIL'
        except (sqlite3.Error,ValueError) as exc:
            report['metadata']['issue'] = str(exc)
    else:
        report['metadata']['issue'] = 'DB unavailable: config and executed code NOT_VERIFIED'
    # Fewer or different results are a finding even if metadata is unavailable.
    if not report['artifacts_equal']:
        report['status'] = 'FAIL'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path)
    parser.add_argument('--db',type=Path,default=Path('db/app.db'))
    args = parser.parse_args()
    result = compare(args.before,args.after,args.db)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return {'PASS':0,'FAIL':1,'INCOMPLETE':2}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
