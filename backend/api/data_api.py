# backend/api/data_api.py
import pathlib
from fastapi import APIRouter, Depends, HTTPException
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
    if not out: raise HTTPException(404)
    return out


@router.get("/{rid}/summary")
def summary(rid: str, user: str = Depends(current_user)):
    p = _dir(rid) / "summary.json"
    if not p.exists(): raise HTTPException(404)
    return p.read_text()


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
