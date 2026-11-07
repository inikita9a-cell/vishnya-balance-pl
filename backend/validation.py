"""Server-side config validation. Keeps all schema rules in one place."""
from __future__ import annotations
import pathlib
from typing import Any

ALLOWED_DATASET_FORMATS = {"json", "xml"}
ALLOWED_POOL_MODES = {"all", "list", "filter"}
ALLOWED_ARRAY_MODES = {"field", "index", "value"}
REQUIRED_TOP_KEYS = ("dataset", "flatten")


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _err(errors: list[dict], path: str, message: str, level: str = "error"):
    errors.append({"path": path, "message": message, "level": level})


def validate_config(cfg: dict, *, check_dataset: bool = True) -> dict:
    """Return {valid: bool, errors: [{path, message, level}], warnings: [...]}.

    `level` is "error" (blocks save/run) or "warning" (saved but highlighted).
    `check_dataset=False` skips filesystem existence checks (useful for the
    frontend "Save without dataset mounted" case during development).
    """
    errors: list[dict] = []
    if not isinstance(cfg, dict) or not cfg:
        _err(errors, "", "Config must be a non-empty YAML object")
        return {"valid": False, "errors": errors, "warnings": []}

    for key in REQUIRED_TOP_KEYS:
        if key not in cfg:
            _err(errors, key, f"Required section missing: {key}")

    # --- dataset ---------------------------------------------------------
    ds = cfg.get("dataset") or {}
    if not isinstance(ds, dict):
        _err(errors, "dataset", "Must be an object")
    else:
        for key in ("path", "before_dir", "after_dir"):
            if not _is_str(ds.get(key)):
                _err(errors, f"dataset.{key}", "Must be a non-empty string")
        formats = ds.get("formats")
        if formats is not None:
            if not isinstance(formats, list) or not formats:
                _err(errors, "dataset.formats", "Must be a non-empty list")
            else:
                bad = [f for f in formats if f not in ALLOWED_DATASET_FORMATS]
                if bad:
                    _err(errors, "dataset.formats",
                         f"Unsupported formats: {bad}. Allowed: {sorted(ALLOWED_DATASET_FORMATS)}")
        if check_dataset and _is_str(ds.get("path")):
            base = pathlib.Path(ds["path"])
            if not base.is_dir():
                _err(errors, "dataset.path",
                     f"Dataset path does not exist: {base}", level="warning")
            else:
                for side in ("before_dir", "after_dir"):
                    sub = ds.get(side)
                    if _is_str(sub) and not (base / sub).is_dir():
                        _err(errors, f"dataset.{side}",
                             f"Directory not found: {base / sub}", level="warning")

    # --- pool ------------------------------------------------------------
    pool = cfg.get("pool") or {}
    if not isinstance(pool, dict):
        _err(errors, "pool", "Must be an object")
    else:
        mode = pool.get("mode", "all")
        if mode not in ALLOWED_POOL_MODES:
            _err(errors, "pool.mode", f"Allowed: {sorted(ALLOWED_POOL_MODES)}")
        if mode == "list":
            ids = pool.get("app_ids")
            if not isinstance(ids, list) or not ids:
                _err(errors, "pool.app_ids", "Required when mode=list (non-empty list of strings)")
            elif any(not isinstance(x, str) or not x for x in ids):
                _err(errors, "pool.app_ids", "Every entry must be a non-empty string")
        if mode == "filter" and not _is_str(pool.get("filter")):
            _err(errors, "pool.filter", "Required when mode=filter")

    # --- flatten ---------------------------------------------------------
    fl = cfg.get("flatten") or {}
    if not isinstance(fl, dict):
        _err(errors, "flatten", "Must be an object")
    else:
        max_depth = fl.get("max_depth", 10)
        if not isinstance(max_depth, int) or max_depth < 1:
            _err(errors, "flatten.max_depth", "Must be a positive integer")
        for key in ("exclude_paths", "include_paths"):
            v = fl.get(key)
            if v is not None and (not isinstance(v, list) or any(not isinstance(x, str) for x in v)):
                _err(errors, f"flatten.{key}", "Must be a list of strings")
        arrays = fl.get("arrays")
        if arrays is not None:
            if not isinstance(arrays, dict):
                _err(errors, "flatten.arrays", "Must be an object {template_path: {mode, key}}")
            else:
                for tpl, rule in arrays.items():
                    if not isinstance(tpl, str) or not tpl:
                        _err(errors, "flatten.arrays", "Empty array template path")
                        continue
                    if not isinstance(rule, dict):
                        _err(errors, f"flatten.arrays.{tpl}", "Rule must be an object")
                        continue
                    mode = rule.get("mode")
                    if mode not in ALLOWED_ARRAY_MODES:
                        _err(errors, f"flatten.arrays.{tpl}.mode",
                             f"Allowed: {sorted(ALLOWED_ARRAY_MODES)}")
                    if mode == "field":
                        keys = rule.get("key")
                        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
                            _err(errors, f"flatten.arrays.{tpl}.key",
                                 "mode=field requires a non-empty list of key paths")
        akc = fl.get("auto_key_candidates")
        if akc is not None and (not isinstance(akc, list) or any(not isinstance(x, str) for x in akc)):
            _err(errors, "flatten.auto_key_candidates", "Must be a list of strings")

    # --- buckets ---------------------------------------------------------
    bc = cfg.get("buckets") or {}
    if bc and not isinstance(bc, dict):
        _err(errors, "buckets", "Must be an object")
    elif bc:
        for key in ("default_unit", "default_num"):
            edges = bc.get(key)
            if edges is None:
                continue
            if not isinstance(edges, list) or len(edges) < 2:
                _err(errors, f"buckets.{key}", "Must be a list of at least 2 numbers")
                continue
            try:
                nums = [float(x) for x in edges]
            except (TypeError, ValueError):
                _err(errors, f"buckets.{key}", "All boundaries must be numbers")
                continue
            if any(b <= a for a, b in zip(nums, nums[1:])):
                _err(errors, f"buckets.{key}", "Boundaries must be strictly increasing")
        by_path = bc.get("by_path") or {}
        if not isinstance(by_path, dict):
            _err(errors, "buckets.by_path", "Must be an object {path_template: [edges]}")
        else:
            for path, edges in by_path.items():
                if not isinstance(path, str) or not path:
                    _err(errors, "buckets.by_path", "Empty path template")
                if not isinstance(edges, list) or len(edges) < 2:
                    _err(errors, f"buckets.by_path.{path}", "Must be at least 2 numbers")

    # --- segments --------------------------------------------------------
    seg = cfg.get("segments") or {}
    if seg and not isinstance(seg, dict):
        _err(errors, "segments", "Must be an object")
    elif seg:
        for key in ("input_paths", "logic_paths"):
            v = seg.get(key)
            if v is not None and (not isinstance(v, list) or any(not isinstance(x, str) for x in v)):
                _err(errors, f"segments.{key}", "Must be a list of path templates")
        for key in ("decision", "reject_reason", "reject_code", "products",
                    "top_offer", "partner_type", "routing", "pd_model", "cutoff", "score_okb"):
            v = seg.get(key)
            if v is not None and not _is_str(v):
                _err(errors, f"segments.{key}", "Must be a non-empty path string")

    # --- quality ---------------------------------------------------------
    qc = cfg.get("quality") or {}
    if qc and not isinstance(qc, dict):
        _err(errors, "quality", "Must be an object")
    elif qc:
        rp = qc.get("required_paths")
        if rp is not None and (not isinstance(rp, list) or any(not isinstance(x, str) for x in rp)):
            _err(errors, "quality.required_paths", "Must be a list of paths")
        rules = qc.get("reason_rules")
        if rules is not None:
            if not isinstance(rules, list):
                _err(errors, "quality.reason_rules", "Must be a list")
            else:
                for i, rule in enumerate(rules):
                    if not isinstance(rule, dict) or "when" not in rule or "require" not in rule:
                        _err(errors, f"quality.reason_rules[{i}]",
                             "Each rule needs 'when' and 'require'")

    # --- checks ----------------------------------------------------------
    checks = cfg.get("checks")
    if checks is not None:
        if not isinstance(checks, list) or any(
                not (isinstance(x, str) or (isinstance(x, dict) and "id" in x))
                for x in checks):
            _err(errors, "checks", "Must be a list of check IDs or {id, ...} objects")
    cp = cfg.get("check_params")
    if cp is not None and not isinstance(cp, dict):
        _err(errors, "check_params", "Must be an object")

    return {
        "valid": not any(e["level"] == "error" for e in errors),
        "errors": [e for e in errors if e["level"] == "error"],
        "warnings": [e for e in errors if e["level"] == "warning"],
    }