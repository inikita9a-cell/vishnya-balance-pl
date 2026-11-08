import yaml
from fastapi import HTTPException
from .auth import staging, contained, data_directory
from .db import SessionLocal
from .models import Config, Run

def validate_config(cfg):
    if not staging():
        return
    from engine.platform_checks_adapter import validate_staging_checks
    try:
        validate_staging_checks(cfg)
        dataset = cfg["dataset"]
        base = data_directory(dataset["path"])
        contained(base, base / "manifest.json")
        for key in ("before_dir", "after_dir"):
            directory = contained(base, base / dataset[key])
            if not directory.is_dir():
                raise ValueError("Dataset directory missing")
            for item in directory.rglob("*"):
                contained(base, item)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, "Invalid staging configuration")

def validate_saved_config(cid, user):
    with SessionLocal() as db:
        row = db.get(Config, cid)
        if row is None or row.owner != user:
            raise HTTPException(404)
        validate_config(yaml.safe_load(row.yaml))

def validate_run_config(rid):
    with SessionLocal() as db:
        row = db.get(Run, rid)
        if row is None:
            raise HTTPException(404)
        validate_config(yaml.safe_load(row.config_snapshot))
