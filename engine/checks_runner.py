# engine/checks_runner.py
"""Прогон проверок: выданные 5 + пользовательские (тот же контракт)."""
from __future__ import annotations
import json, pathlib, traceback
from .mart import Mart

DEFAULT_CHECKS = [
    {"id": "ar_drop_by_product", "label": "AR drop by product", "entrypoint": "check"},
    {"id": "attribute_new_loss", "label": "Attribute new/loss", "entrypoint": "check"},
    {"id": "external_score_drift", "label": "External score drift", "entrypoint": "check"},
    {"id": "stop_factor_disappeared", "label": "Stop factor disappeared", "entrypoint": "check"},
    {"id": "target_model_changed", "label": "Target model changed", "entrypoint": "check"},
]


def run_checks(state) -> str:
    """Platform interface: run selected checks and return checks.json path.

    The adapter executes the real CHECK scripts against prepared Parquet data.
    Keep this signature because backend/runs.py imports run_checks(state).
    """
    from .platform_checks_adapter import run_checks as run_real_checks
    return run_real_checks(state)


def _code_for(chk, cfg):
    ref = (cfg.get("overrides") or {}).get(f"checks/{chk['id']}")
    if ref and pathlib.Path(ref).exists():
        return pathlib.Path(ref).read_text()
    # встроенная заглушка: возвращает PASS, чтобы UI был живым
    return f"""
def check(mart, params):
    return {{"LABEL": {chk['label']!r}, "SOURCE": "BEFORE", "ARGUMENT": "",
             "CNT": 0, "TOTAL": mart.total_apps(), "METRIC": 0.0,
             "APP_IDS": [], "RESULT": "PASS", "CONFIDENCE": "HIGH"}}
"""
