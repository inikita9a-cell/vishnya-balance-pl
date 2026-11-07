# backend/api/pools.py
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import current_user
from ..db import SessionLocal
from ..models import Pool

router = APIRouter(prefix="/api/pools", tags=["pools"])


class PoolIn(BaseModel):
    name: str
    payload: dict


@router.get("")
def list_pools(user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        return [{"id": p.id, "name": p.name, "payload": json.loads(p.payload)}
                for p in db.query(Pool).filter(Pool.owner == user)]
    finally:
        db.close()


@router.post("")
def create_pool(body: PoolIn, user: str = Depends(current_user)):
    db = SessionLocal()
    try:
        p = Pool(owner=user, name=body.name, payload=json.dumps(body.payload))
        db.add(p);
        db.commit();
        db.refresh(p)
        return {"id": p.id}
    finally:
        db.close()
