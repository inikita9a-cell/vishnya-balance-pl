import pathlib
import json
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from pydantic import BaseModel, Field
from ..db import SessionLocal
from ..models import Run
from ..auth import current_user, get_run_readable, contained, identifier, run_directory, staging, data_directory
from .. import duck

router = APIRouter(prefix="/api/runs", tags=["data"])


def _dir(rid: str) -> pathlib.Path:
    return run_directory(rid)


class PivotIn(BaseModel):
    rows: list[str] = Field(default_factory=list)
    cols: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)


class PivotAppsIn(BaseModel):
    filters: dict = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class ExplorerQueryIn(BaseModel):
    groupBy: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    includeUnchanged: bool = True
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class ExplorerAppsIn(BaseModel):
    filters: dict = Field(default_factory=dict)
    limit: int = Field(20, ge=1, le=500)
    offset: int = Field(0, ge=0)


# --- pivot / drilldown / sankey / explorer --------------------------------

@router.post("/{rid}/pivot")
def pivot(rid: str, body: PivotIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    if not _dir(rid).exists():
        raise HTTPException(404)
    try:
        return duck.pivot(_dir(rid), body.rows, body.cols, body.filters)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{rid}/pivot/dimensions")
def pivot_dimensions(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.pivot_dimensions(_dir(rid))
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))


@router.get("/{rid}/pivot/values")
def pivot_values(rid: str, field: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.pivot_values(_dir(rid), field)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{rid}/pivot/apps")
def pivot_apps(rid: str, body: PivotAppsIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.pivot_apps(_dir(rid), body.filters, body.limit, body.offset)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{rid}/drilldown")
def drilldown(rid: str, body: PivotIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    return duck.drilldown(_dir(rid), body.filters)


@router.post("/{rid}/sankey")
def sankey(rid: str, body: PivotIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.get_sankey_data(_dir(rid), body.filters)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{rid}/explorer/fields")
def explorer_fields(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.get_explorer_fields(_dir(rid))
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{rid}/explorer/query")
def explorer_query(rid: str, body: ExplorerQueryIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.explorer_query(
            _dir(rid), group_by=body.groupBy, filters=body.filters,
            include_unchanged=body.includeUnchanged,
            limit=body.limit, offset=body.offset,
        )
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{rid}/explorer/apps")
def explorer_apps(rid: str, body: ExplorerAppsIn, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    try:
        return duck.explorer_apps(_dir(rid), filters=body.filters,
                                  limit=body.limit, offset=body.offset)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# --- app-level rows / raw ------------------------------------------------

@router.get("/{rid}/apps/{app_id}")
def app_rows(rid: str, app_id: str, diff_only: int = Query(0),
             user: str = Depends(current_user)):
    get_run_readable(rid, user)
    from duckdb import Error as DuckDBError
    try:
        return duck.app_rows(_dir(rid), app_id, bool(diff_only))
    except (FileNotFoundError, ValueError, DuckDBError) as e:
        raise HTTPException(409, f'Не удалось загрузить атрибуты заявки: {e}') from e


@router.get("/{rid}/apps/{app_id}/raw")
def app_raw(rid: str, app_id: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    if not app_id or app_id in ('.', '..') or '/' in app_id or '\\' in app_id:
        raise HTTPException(400, 'invalid app id')
    d = _dir(rid)
    out = {}
    for tag in ("BEFORE_MASTER", "AFTER_BETA"):
        for ext in ("json", "xml"):
            p = d / "raw" / tag / f"{app_id}.{ext}"
            if p.exists():
                out[tag] = p.read_text(encoding="utf-8-sig")
                break
    if not out:
        db = SessionLocal()
        try:
            run = db.get(Run, rid)
            if not run:
                raise HTTPException(404)
            cfg = yaml.safe_load(run.config_snapshot) or {}
            dataset = cfg.get('dataset') or {}
            # Local configs may reference an external dataset (e.g. a Windows drive).
            # Staging still restricts all datasets to the server's data directory.
            base = pathlib.Path(dataset['path']).resolve()
            if staging():
                base = data_directory(base)
            for tag, key in [('BEFORE_MASTER', 'before_dir'), ('AFTER_BETA', 'after_dir')]:
                for ext in ('json', 'xml'):
                    candidate = contained(base, base / dataset[key] / f'{app_id}.{ext}')
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


# --- summary / blocks / quality -----------------------------------------

@router.get("/{rid}/summary")
def summary(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    p = _dir(rid) / "summary.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text(encoding='utf-8'))


@router.get("/{rid}/blocks")
def blocks(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    p = _dir(rid) / "blocks.parquet"
    if not p.exists():
        raise HTTPException(404)
    import pandas as pd
    return pd.read_parquet(p).head(500).to_dict(orient="records")


@router.get("/{rid}/quality")
def quality(rid: str, user: str = Depends(current_user)):
    get_run_readable(rid, user)
    p = _dir(rid) / "quality.parquet"
    if not p.exists():
        raise HTTPException(404)
    import pandas as pd
    return pd.read_parquet(p).head(500).to_dict(orient="records")
