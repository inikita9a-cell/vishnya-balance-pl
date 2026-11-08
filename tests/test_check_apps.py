"""P0-07 tests: expansion of truncated check rows and owner isolation."""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _make_run(tmp_path: pathlib.Path, rows: list[dict], apps: list[str]) -> tuple[pathlib.Path, str]:
    run_id = "run_test"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "checks.json").write_text(json.dumps(rows), encoding="utf-8")
    # comparison.parquet with APP_ID and fake columns for FILTERS
    df = pd.DataFrame({"APP_ID": apps, "PATH": ["p"] * len(apps), "CHANGE_TYPE": ["SAME"] * len(apps)})
    df.to_parquet(run_dir / "comparison.parquet", index=False)
    (run_dir / "segments.parquet").write_text("", encoding="utf-8")
    return run_dir, run_id


def _client(monkeypatch, owned: bool = True):
    from backend.main import app
    from backend import auth

    class FakeRun:
        started_by = "alice"

    def fake_owned(rid, user):
        if not owned:
            from fastapi import HTTPException
            raise HTTPException(404, "run not found")
        return FakeRun()

    monkeypatch.setattr(auth, "get_run_owned", fake_owned)
    # also patch the symbol imported inside check_apps_api
    import backend.api.check_apps_api as mod
    monkeypatch.setattr(mod, "get_run_owned", fake_owned)
    return TestClient(app)


def test_expand_full_rows_only(tmp_path, monkeypatch):
    rows = [{"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
             "APP_IDS": ["x", "y"], "CNT": 2, "FILTERS": None}]
    _make_run(tmp_path, rows, ["x", "y"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps",
                    json={"result": "FAIL", "argument": "A"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2
    assert r.json()["truncated"] is False


def test_expand_truncated_rows_with_filters(tmp_path, monkeypatch):
    rows = [{"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
             "APP_IDS": ["x", "y"], "CNT": 3,
             "FILTERS": {"app_ids": ["x", "y", "z"]}}]
    _make_run(tmp_path, rows, ["x", "y", "z"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 3
    assert data["truncated"] is False
    assert set(data["items"]) == {"x", "y", "z"}


def test_mixed_full_and_truncated_rows(tmp_path, monkeypatch):
    rows = [
        {"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
         "APP_IDS": ["x", "y"], "CNT": 2, "FILTERS": None},
        {"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "B",
         "APP_IDS": ["z"], "CNT": 2, "FILTERS": {"app_ids": ["z", "w"]}},
    ]
    _make_run(tmp_path, rows, ["x", "y", "z", "w"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 4
    assert set(data["items"]) == {"x", "y", "z", "w"}


def test_truncated_without_filters_returns_422(tmp_path, monkeypatch):
    rows = [
        {"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
         "APP_IDS": ["x", "y"], "CNT": 2, "FILTERS": None},
        {"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "B",
         "APP_IDS": ["z"], "CNT": 2, "FILTERS": None},  # truncated, no FILTERS
    ]
    _make_run(tmp_path, rows, ["x", "y", "z"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps", json={})
    assert r.status_code == 422
    assert "no FILTERS" in r.json()["detail"]


def test_filters_count_mismatch_returns_422(tmp_path, monkeypatch):
    rows = [{"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
             "APP_IDS": ["x"], "CNT": 5,
             "FILTERS": {"app_ids": ["x", "y"]}}]  # only 2, CNT=5
    _make_run(tmp_path, rows, ["x", "y"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps", json={})
    assert r.status_code == 422
    assert "recovered 2" in r.json()["detail"]


def test_pagination_truncated_flag(tmp_path, monkeypatch):
    apps = [f"a{i:03d}" for i in range(25)]
    rows = [{"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
             "APP_IDS": apps[:5], "CNT": 25,
             "FILTERS": {"app_ids": apps}}]
    _make_run(tmp_path, rows, apps)
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch)
    r = client.post("/api/runs/run_test/checks/c1/apps",
                    json={"limit": 10, "offset": 0})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 25
    assert data["truncated"] is True
    assert len(data["items"]) == 10
    r2 = client.post("/api/runs/run_test/checks/c1/apps",
                     json={"limit": 100, "offset": 20})
    assert r2.status_code == 200
    assert set(r2.json()["items"]) == set(apps[20:])


def test_foreign_run_returns_404(tmp_path, monkeypatch):
    rows = [{"CHECK_ID": "c1", "RESULT": "FAIL", "ARGUMENT": "A",
             "APP_IDS": ["x"], "CNT": 1, "FILTERS": None}]
    _make_run(tmp_path, rows, ["x"])
    monkeypatch.chdir(tmp_path)
    client = _client(monkeypatch, owned=False)
    r = client.post("/api/runs/run_test/checks/c1/apps", json={})
    assert r.status_code == 404