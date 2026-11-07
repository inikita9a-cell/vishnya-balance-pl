# backend/api/data_api.py
import pathlib
import json
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from ..db import SessionLocal
from ..models import Run
from pydantic import BaseModel
from ..auth import current_user
from .. import duck

router = APIRouter(prefix="/api/runs", tags=["data"])


def _dir(rid): return pathlib.Path("runs") / rid


class PivotIn(BaseModel):
    rows: list[str] = []
    cols: list[str] = []
    filters: dict = {}


@router.post("/{rid}/pivot")
def pivot(rid: str, body: PivotIn, user: str = Depends(current_user)):
    if not _dir(rid).exists(): raise HTTPException(404)
    return duck.pivot(_dir(rid), body.rows, body.cols, body.filters)


@router.post("/{rid}/drilldown")
def drilldown(rid: str, body: PivotIn, user: str = Depends(current_user)):
    return duck.drilldown(_dir(rid), body.filters)


@router.get("/{rid}/apps/{app_id}")
def app_rows(rid: str, app_id: str, diff_only: int = Query(0), user: str = Depends(current_user)):
    return duck.app_rows(_dir(rid), app_id, bool(diff_only))


@router.get("/{rid}/apps/{app_id}/raw")
def app_raw(rid: str, app_id: str, user: str = Depends(current_user)):
    d = _dir(rid)
    out = {}
    for tag in ("BEFORE_MASTER", "AFTER_BETA"):
        for ext in ("json", "xml"):
            p = d / "raw" / tag / f"{app_id}.{ext}"
            if p.exists():
                out[tag] = p.read_text()
                break
    if not out:
        # Do not duplicate 4004 JSON/XML source files per run. Read the dataset
        # referenced by the immutable configuration snapshot instead.
        if pathlib.Path(app_id).name != app_id or app_id in ('.', '..'):
            raise HTTPException(400, 'invalid app id')
        db = SessionLocal()
        try:
            run = db.get(Run, rid)
            if not run:
                raise HTTPException(404)
            cfg = yaml.safe_load(run.config_snapshot) or {}
            dataset = cfg.get('dataset') or {}
            base = pathlib.Path(dataset['path'])
            for tag, key in [('BEFORE_MASTER', 'before_dir'), ('AFTER_BETA', 'after_dir')]:
                for ext in ('json', 'xml'):
                    candidate = base / dataset[key] / f'{app_id}.{ext}'
                    if candidate.is_file():
                        out[tag] = candidate.read_text(encoding='utf-8-sig')
                        break
        except (KeyError, TypeError):
            raise HTTPException(404, 'dataset not configured')
        finally:
            db.close()
    if not out:
        raise HTTPException(404)
    return out


@router.get("/{rid}/summary")
def summary(rid: str, user: str = Depends(current_user)):
    p = _dir(rid) / "summary.json"
    if not p.exists(): raise HTTPException(404)
    return json.loads(p.read_text(encoding='utf-8'))


@router.get("/{rid}/blocks")
def blocks(rid: str, user: str = Depends(current_user)):
    p = _dir(rid) / "blocks.parquet"
    if not p.exists(): raise HTTPException(404)
    import pandas as pd
    return pd.read_parquet(p).head(500).to_dict(orient="records")


@router.get("/{rid}/quality")
def quality(rid: str, user: str = Depends(current_user)):
    p = _dir(rid) / "quality.parquet"
    if not p.exists(): raise HTTPException(404)
    import pandas as pd
    return pd.read_parquet(p).head(500).to_dict(orient="records")


@router.post("/{rid}/sankey")
def sankey(rid: str, body: PivotIn, user: str = Depends(current_user)):
    """
    Возвращает данные для диаграммы Санкей (ECharts).
    Принимает те же фильтры, что и /pivot.
    """
    if not _dir(rid).exists():
        raise HTTPException(404)
    return duck.get_sankey_data(_dir(rid), body.filters)