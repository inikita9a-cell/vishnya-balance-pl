"""Check-only revision proof in a private SQLite DB and synthetic output tree."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECK_CODE = '''def check(mart, params):
    ids = mart.app_ids(diff_flag=1)
    total = mart.total_apps()
    return [{"LABEL": "P0-04 CUSTOM CHECK", "SOURCE": "AFTER", "ARGUMENT": "diff_flag=1",
             "CNT": len(ids), "TOTAL": total, "METRIC": len(ids)/total if total else 0,
             "APP_IDS": ids, "RESULT": "FAIL" if ids else "PASS", "CONFIDENCE": "HIGH"}]
'''


def main():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import yaml
    from backend import runs
    from backend.db import Base
    from backend.models import Config, Procedure, Run
    from engine.check_jobs import attach_check, queue_checks, execute_job

    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    output = ROOT / 'runs' / f'p0_04_smoke_{stamp}_{uuid4().hex[:6]}'
    output.mkdir(parents=True, exist_ok=False)
    dataset = output / 'demo_dataset'
    shutil.copytree(ROOT / 'notebooks/demo_data', dataset)
    cfg = yaml.safe_load((ROOT / 'configs/default_spr.yaml').read_text(encoding='utf-8'))
    cfg['dataset']['path'] = str(dataset)
    database = create_engine(f'sqlite:///{output / "demo.db"}')
    Base.metadata.create_all(database)
    runs.SessionLocal = sessionmaker(bind=database)
    runs.RUNS_DIR = output / 'runs'
    with runs.SessionLocal() as db:
        config = Config(owner='p004_demo', name='demo', yaml=yaml.safe_dump(cfg))
        proc = Procedure(owner='p004_demo', kind='check', source='workspace', code=CHECK_CODE)
        db.add_all([config, proc])
        db.commit()
        cid, pid = config.id, proc.id
    rid = runs.start_run(cid, 'p004_demo')
    with runs.SessionLocal() as db:
        original = db.get(Run, rid).config_snapshot
    assert runs.run_pipeline(rid, yaml.safe_load(original)) is not None
    root = runs.RUNS_DIR / rid
    def hashes():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.parquet')}
    before = hashes()
    with runs.SessionLocal() as db:
        attach_check(db, 'p004_demo', pid, cid, check_id='my_new_check')
    job = queue_checks(rid, 'p004_demo', config_id=cid)
    assert job['status'] == 'queued'
    shutil.rmtree(dataset)  # The rerun must need only prepared Parquet.
    status = execute_job(rid, job['job_id'])
    assert status['status'] == 'done', status
    rows = json.loads((root / 'checks.json').read_text(encoding='utf-8'))
    assert set(cfg['checks']) | {'my_new_check'} == {row['CHECK_ID'] for row in rows}
    assert hashes() == before
    assert 'P0-04 CUSTOM CHECK' in (root / 'report.html').read_text(encoding='utf-8')
    with runs.SessionLocal() as db:
        assert db.get(Run, rid).config_snapshot == original
    print('P0-04 OK: five standard checks + custom check, Parquet unchanged, HTML updated')
    print(json.dumps({'job_status': status['status'], 'checks_selected': len(status['check_ids']),
                      'rows': len(rows), 'results': status['counts'], 'parquet_unchanged': True,
                      'html_updated': True, 'output': str(root)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
