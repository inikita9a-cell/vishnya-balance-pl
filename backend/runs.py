"""Оркестратор: запускает s1..s15 из engine.steps в отдельном потоке,
пишет stage_logs в SQLite. Переживает перезагрузку страницы (статус в БД)."""
from __future__ import annotations
import json, time, traceback, uuid, pathlib, datetime as dt
import yaml

from .db import SessionLocal
from .models import Run, StageLog, CheckResult
from engine import steps as S

RUNS_DIR = pathlib.Path("runs")

# шаги и «человеческие» подписи
PIPELINE = [
    ("s1_discover", S.s1_discover),
    ("s2_load", S.s2_load),
    ("s3_flatten", S.s3_flatten),
    ("s4_bucketize", S.s4_bucketize),
    ("s5_union", S.s5_union),
    ("s6_check_keys", S.s6_check_keys),
    ("s7_compare", S.s7_compare),
    ("s8_quality", S.s8_quality),
    ("s9_segments", S.s9_segments),
    ("s10_blocks", S.s10_blocks),
    ("s11_facts", S.s11_facts),
    ("s12_checks", S.s12_checks),
    ("s13_summary", S.s13_summary),
    ("s15_report", S.s15_report_html),
]


def _log(db, run_id, step, status, **kw):
    row = StageLog(run_id=run_id, step=step, status=status, **kw)
    db.add(row);
    db.commit();
    db.refresh(row)
    return row


def start_run(config_id: int, user: str) -> str:
    db = SessionLocal()
    try:
        cfg = db.get(__import__("backend.models", fromlist=["Config"]).Config, config_id)
        if not cfg:
            raise ValueError("config not found")
        run_id = uuid.uuid4().hex[:12]
        RUNS_DIR.joinpath(run_id).mkdir(parents=True, exist_ok=True)
        run = Run(id=run_id, config_id=config_id, config_snapshot=cfg.yaml,
                  started_by=user, status="queued")
        db.add(run);
        db.commit()
        return run_id
    finally:
        db.close()


def run_pipeline(run_id: str, cfg: dict):
    """Вызывается в фоновом потоке (threading.Thread)."""
    db = SessionLocal()
    run = db.get(Run, run_id)
    run.status = "running";
    db.commit()
    run_dir = RUNS_DIR / run_id
    state: dict = {"cfg": cfg, "run_dir": str(run_dir)}
    started_by = run.started_by

    try:
        for step_name, fn in PIPELINE:
            t0 = time.time()
            log = _log(db, run_id, step_name, "running", started_by=started_by,
                       params=json.dumps(_safe_params(fn, state), default=str))
            try:
                import inspect
                code = inspect.getsource(fn)
                override = _find_override(step_name, cfg)
                if override:
                    code = f"# OVERRIDE from {override['origin']}\n{override['code']}\n\n# --- engine ---\n{code}"
                log.code_snapshot = code
                db.commit()

                out = fn(state)
                state[step_name] = out
                log.status = "done"
                log.rows_out = _rows_of(out)
                log.message = _msg_of(out)
            except Exception as e:
                log.status = "failed"
                log.message = traceback.format_exc()[-4000:]
                run.status = "failed";
                run.error = str(e)
                db.commit()
                return
            finally:
                log.finished_at = dt.datetime.utcnow()
                log.duration_ms = int((time.time() - t0) * 1000)
                db.commit()

        run.status = "done"
    except Exception as e:
        run.status = "failed";
        run.error = traceback.format_exc()[-4000:]
    finally:
        run.finished_at = dt.datetime.utcnow()
        db.commit();
        db.close()


def rerun_checks(run_id: str):
    """Перезапуск только проверок на готовом прогоне (демо новой проверки)."""
    db = SessionLocal()
    run = db.get(Run, run_id)
    cfg = yaml.safe_load(run.config_snapshot)
    state = {"cfg": cfg, "run_dir": str(RUNS_DIR / run_id)}
    log = _log(db, run_id, "s12_checks", "running", started_by=run.started_by,
               params=json.dumps({"rerun": True}))
    t0 = time.time()
    try:
        out = S.s12_checks(state)
        log.status = "done";
        log.message = _msg_of(out);
        log.rows_out = _rows_of(out)
    except Exception:
        log.status = "failed";
        log.message = traceback.format_exc()[-4000:]
    finally:
        log.finished_at = dt.datetime.utcnow()
        log.duration_ms = int((time.time() - t0) * 1000)
        db.commit();
        db.close()


# ---- helpers ----
def _safe_params(fn, state):
    try:
        import inspect
        sig = inspect.signature(fn)
        return {"args": [n for n in sig.parameters]}
    except Exception:
        return {}


def _rows_of(out):
    try:
        import pandas as pd
        if isinstance(out, pd.DataFrame): return int(len(out))
        if isinstance(out, (list, tuple)): return len(out)
    except Exception:
        pass
    return None


def _msg_of(out):
    if isinstance(out, dict):
        return json.dumps({k: v for k, v in out.items() if not hasattr(v, "shape")}, default=str)[:2000]
    return None


def _find_override(step_name, cfg):
    ov = (cfg.get("overrides") or {})
    key = step_name.replace("s", "", 1).split("_", 1)[-1]
    ref = ov.get(key) or ov.get(step_name)
    if not ref: return None
    p = pathlib.Path(ref)
    if p.exists():
        return {"origin": str(p), "code": p.read_text()}
    return None
