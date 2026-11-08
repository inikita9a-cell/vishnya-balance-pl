import asyncio
import json
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.main import app
from backend import db, auth
from backend.models import Config, Run
from backend.staging_access import password_hash
from engine.sandbox import execute_user_code

@pytest.fixture
def secured(monkeypatch):
    from backend.api import configs, runs_api, data_api, procedures, pools
    from backend import security_config
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in (db, auth, configs, runs_api, data_api, procedures, pools, security_config):
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(db, "engine", engine)
    with factory() as session:
        session.add(Config(id=987, name="private", owner="bob", yaml="{}"))
        session.add(Run(id="private", config_id=987, started_by="bob", config_snapshot="{}"))
        session.commit()
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_BASE_URL", "https://demo.onrender.com")
    salt = "12" * 16
    monkeypatch.setenv("STAGING_USERS_JSON", json.dumps({"alice": salt + ":" + password_hash("test-password", salt)}))
    yield
    engine.dispose()

def request(method, path, auth=True, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://demo.onrender.com") as client:
            return await client.request(method, path, auth=("alice", "test-password") if auth else None, **kwargs)
    return asyncio.run(run())

def test_closed_without_configuration(secured, monkeypatch):
    monkeypatch.delenv("STAGING_USERS_JSON")
    assert request("GET", "/").status_code == 503

def test_every_api_route_denies_anonymous(secured):
    for route in app.routes:
        if not getattr(route, "path", "").startswith("/api"):
            continue
        path = route.path.replace("{rid}", "private").replace("{cid}", "987").replace("{pid}", "1").replace("{app_id}", "1").replace("{step}", "step")
        for method in route.methods:
            assert request(method, path, auth=False, headers={"Cookie": "spr_user=bob", "X-Forwarded-User": "bob"}).status_code == 401
    for path in ("/", "/docs", "/openapi.json", "/assets/example.js"):
        assert request("GET", path, auth=False).status_code == 401

def test_identity_and_csrf(secured):
    assert request("GET", "/api/me", headers={"Cookie": "spr_user=bob"}).json()["name"] == "alice"
    assert request("POST", "/api/login", json={"name": "bob"}).status_code == 403
    assert request("POST", "/api/login", headers={"Origin": "https://demo.onrender.com"}, json={"name": "bob"}).json()["name"] == "alice"
    assert request("GET", "/healthz", auth=False).status_code == 200

def test_all_run_routes_deny_other_owner(secured):
    for route in app.routes:
        if "{rid}" not in getattr(route, "path", ""):
            continue
        path = route.path.replace("{rid}", "private").replace("{app_id}", "1").replace("{step}", "step")
        for method in route.methods:
            assert request(method, path, headers={"Origin": "https://demo.onrender.com"}, json={}).status_code == 404, path
    assert request("GET", "/api/runs").json() == []
    assert request("POST", "/api/configs/987/duplicate", headers={"Origin": "https://demo.onrender.com"}).status_code == 404
    assert request("POST", "/api/runs", headers={"Origin": "https://demo.onrender.com"}, json={"config_id":987}).status_code == 404

def test_python_and_paths(secured):
    from backend.auth import identifier, contained
    from fastapi import HTTPException
    from engine.platform_checks_adapter import validate_staging_checks
    from engine.checks_service import load_check
    assert not execute_user_code("raise Exception()", "entry", {})[0]
    assert request("POST", "/api/procedures/1/try", headers={"Origin": "https://demo.onrender.com"}, json={}).status_code == 403
    for cfg in ({"overrides":{"checks/x":"x"}}, {"checks":[{"id":"x", "code":"x"}]}, {"checks":["../../x"]}):
        with pytest.raises(ValueError): validate_staging_checks(cfg)
    with pytest.raises(ValueError): load_check("ar_drop_by_product", "data")
    for value in ("..", "../db", "a\\b", "/etc/passwd"):
        with pytest.raises(HTTPException): identifier(value)
    with pytest.raises(HTTPException): contained("runs", "db/app.db")


def test_wrong_password_and_non_allowlisted_user(secured):
    import base64
    for credentials in ("alice:wrong", "outsider:test-password"):
        header = "Basic " + base64.b64encode(credentials.encode()).decode()
        assert request("GET", "/api/me", auth=False, headers={"Authorization": header}).status_code == 401


def test_new_procedure_runtime_is_closed(monkeypatch):
    from engine.procedure_runtime import execute, ProcedureError
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ProcedureError, match="disabled"):
        execute("normalize", {})
