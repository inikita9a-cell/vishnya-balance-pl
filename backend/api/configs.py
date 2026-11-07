import pathlib, yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from ..auth import current_user
from ..db import SessionLocal
from ..models import Config
from ..validation import validate_config

router = APIRouter(prefix="/api/configs", tags=["configs"])
DEFAULT = pathlib.Path("configs/default_spr.yaml")


class ConfigIn(BaseModel):
    name: str
    yaml: str | None = None
    check_dataset: bool = True


class ValidateIn(BaseModel):
    yaml: str
    check_dataset: bool = True


def _load_default_template() -> str:
    if not DEFAULT.is_file():
        raise HTTPException(500, "default_spr.yaml missing on server")
    return DEFAULT.read_text(encoding="utf-8")


@router.get("/template")
def get_template():
    """Ready-to-edit config skeleton for the 'Create from template' button."""
    return {"yaml": _load_default_template()}


@router.post("/validate")
def validate(body: ValidateIn, user: str = Depends(current_user)):
    """Validate arbitrary YAML (editor preview). Does not persist anything."""
    try:
        cfg = yaml.safe_load(body.yaml) or {}
    except yaml.YAMLError as e:
        return {"valid": False, "errors": [{"path": "", "message": f"YAML error: {e}", "level": "error"}],
                "warnings": []}
    return validate_config(cfg, check_dataset=body.check_dataset)


@router.post("/upload")
async def upload(file: UploadFile = File(...), user: str = Depends(current_user)):
    """Import a YAML file. Returns the parsed YAML string; saving is a separate step."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 (with or without BOM)")
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    return {"yaml": text, "name": pathlib.Path(file.filename or "uploaded.yaml").stem}


@router.get("")
def list_configs(user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        rows = db.query(Config).filter(Config.owner == user).all()
        return [{"id": c.id, "name": c.name, "yaml": c.yaml,
                 "created_at": c.created_at} for c in rows]
    finally:
        db.close()


@router.get("/{cid}")
def get_config(cid: int, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        c = db.get(Config, cid)
        if not c or c.owner != user:
            raise HTTPException(404)
        return {"id": c.id, "name": c.name, "yaml": c.yaml, "created_at": c.created_at}
    finally:
        db.close()


@router.post("")
def create_config(body: ConfigIn, user: str = Depends(current_user)):
    """Create new config. `yaml=null` -> empty skeleton; `yaml` string -> as-is."""
    text = body.yaml if body.yaml is not None else "dataset:\n  path: data\nflatten:\n  max_depth: 10\n"
    try:
        cfg = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    report = validate_config(cfg, check_dataset=body.check_dataset)
    if not report["valid"]:
        raise HTTPException(422, {"detail": "Invalid config", "report": report})
    db = SessionLocal()
    try:
        c = Config(owner=user, name=body.name.strip() or "Untitled", yaml=text)
        db.add(c)
        db.commit()
        db.refresh(c)
        return {"id": c.id, "warnings": report["warnings"]}
    finally:
        db.close()


@router.put("/{cid}")
def update_config(cid: int, body: ConfigIn, user: str = Depends(current_user)):
    text = body.yaml if body.yaml is not None else ""
    try:
        cfg = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    report = validate_config(cfg, check_dataset=body.check_dataset)
    if not report["valid"]:
        raise HTTPException(422, {"detail": "Invalid config", "report": report})
    db = SessionLocal()
    try:
        c = db.get(Config, cid)
        if not c or c.owner != user:
            raise HTTPException(404)
        c.name = body.name.strip() or c.name
        c.yaml = text
        db.commit()
        return {"ok": True, "warnings": report["warnings"]}
    finally:
        db.close()


@router.post("/{cid}/duplicate")
def duplicate(cid: int, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        src = db.get(Config, cid)
        if not src or src.owner != user:
            raise HTTPException(404)
        new = Config(owner=user, name=f"{src.name} (copy)", yaml=src.yaml)
        db.add(new)
        db.commit()
        db.refresh(new)
        return {"id": new.id, "name": new.name}
    finally:
        db.close()


@router.delete("/{cid}")
def delete_config(cid: int, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        c = db.get(Config, cid)
        if not c or c.owner != user:
            raise HTTPException(404)
        db.delete(c)
        db.commit()
        return {"ok": True}
    finally:
        db.close()