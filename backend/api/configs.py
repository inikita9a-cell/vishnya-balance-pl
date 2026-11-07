# backend/api/configs.py
import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user
from ..db import SessionLocal
from ..models import Config
import pathlib

router = APIRouter(prefix="/api/configs", tags=["configs"])
DEFAULT = pathlib.Path("configs/default_spr.yaml")


class ConfigIn(BaseModel):
    name: str
    yaml: str | None = None


@router.get("")
def list_configs(user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        rows = db.query(Config).filter(Config.owner == user).all()
        return [{"id": c.id, "name": c.name, "yaml": c.yaml} for c in rows]
    finally:
        db.close()


@router.post("")
def create_config(body: ConfigIn, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        y = body.yaml or DEFAULT.read_text()
        yaml.safe_load(y)  # валидация
        c = Config(owner=user, name=body.name, yaml=y)
        db.add(c)
        db.commit()
        db.refresh(c)
        return {"id": c.id}
    finally:
        db.close()


@router.put("/{cid}")
def update_config(cid: int, body: ConfigIn, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        c = db.get(Config, cid)
        if not c or c.owner != user: raise HTTPException(404)
        if body.yaml is not None:
            yaml.safe_load(body.yaml);
            c.yaml = body.yaml
        c.name = body.name
        db.commit();
        return {"ok": True}
    finally:
        db.close()


@router.post("/{cid}/duplicate")
def duplicate(cid: int, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        c = db.get(Config, cid)
        if not c: raise HTTPException(404)
        new = Config(owner=user, name=c.name + " (copy)", yaml=c.yaml)
        db.add(new)
        db.commit()
        db.refresh(new)
        return {"id": new.id}
    finally:
        db.close()
