"""Regression: pivot cell count == exact distinct drill-down application IDs.

SQLite shim validates all real SQL semantics without installing DuckDB in CI.
An additional end-to-end Parquet/DuckDB test runs when both are installed.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from backend import duck


def sample_tables():
    # One APP_ID can be in several PATH and SOURCE groups. Summing CNT is wrong.
    records = [
        (1, "risk.age", "BEFORE (MASTER)", "VALUE_CHANGED", "LOGIC", None, "A", "B"),
        (2, "risk.age", "AFTER (BETA)", "VALUE_CHANGED", "LOGIC", None, "A", "B"),
        (3, "risk.model", "BEFORE (MASTER)", "VALUE_CHANGED", "LOGIC", "model", "A"),
        (4, "risk.model", "AFTER (BETA)", "VALUE_CHANGED", "LOGIC", "model", "A"),
        (5, "risk.same", "BEFORE (MASTER)", "SAME", "NONE", None, "C"),
        (6, "risk.same", "AFTER (BETA)", "SAME", "NONE", None, "C"),
        (7, "risk.o'brien", "AFTER (BETA)", "ATTRIBUTE_NEW", None, "quote", "D"),
    ]
    facts, members = [], []
    for fact_id, path, source, change, cause, array_key, *apps in records:
        facts.append({"FACT_ID": fact_id, "PATH": path, "SOURCE": source,
                      "CHANGE_TYPE": change, "CAUSE": cause,
                      "ARRAY_KEY": array_key, "CNT": len(apps)})
        members.extend({"FACT_ID": fact_id, "APP_ID": app} for app in apps)
    # A duplicated membership should not inflate COUNT DISTINCT.
    members.append({"FACT_ID": 1, "APP_ID": "A"})
    seg = pd.DataFrame([
        {"APP_ID": app, "DECISION_BEFORE": old, "DECISION_AFTER": new,
         "DECISION_TRANSITION": f"{old}->{new}", "REASON_TRANSITION": "none",
         "N_DIFFS": diffs, "CAUSE": cause}
        for app, old, new, diffs, cause in [
            ("A", "NO", "YES", 2, "LOGIC"),
            ("B", "NO", "NO", 1, "LOGIC"),
            ("C", "YES", "YES", 0, "NONE"),
            ("D", "NO", "YES", 1, None),
        ]
    ])
    comparison = pd.DataFrame([
        {"APP_ID": "A", "PATH": "risk.age", "ARRAY_KEY": "", "DIFF_FLAG": 1},
        {"APP_ID": "A", "PATH": "risk.model", "ARRAY_KEY": "", "DIFF_FLAG": 1},
        {"APP_ID": "B", "PATH": "risk.age", "ARRAY_KEY": "", "DIFF_FLAG": 1},
        {"APP_ID": "C", "PATH": "risk.same", "ARRAY_KEY": "", "DIFF_FLAG": 0},
        {"APP_ID": "D", "PATH": "risk.o'brien", "ARRAY_KEY": "", "DIFF_FLAG": 1},
    ])
    return {"facts": pd.DataFrame(facts), "fact_apps": pd.DataFrame(members),
            "segments": seg, "comparison": comparison}


class SQLiteShim:
    """Tiny connection adapter to test the same ANSI SQL used with DuckDB."""

    def __init__(self, tables):
        self.conn = sqlite3.connect(":memory:")
        for name, frame in tables.items():
            frame.to_sql(name, self.conn, index=False)
        self.cursor = None
        self.description = None

    def execute(self, sql, params=None):
        self.cursor = self.conn.execute(sql, list(params or []))
        self.description = self.cursor.description
        return self

    def df(self):
        return pd.DataFrame(self.cursor.fetchall(),
                            columns=[column[0] for column in self.description])

    def close(self):
        self.conn.close()


@pytest.fixture
def run(monkeypatch, tmp_path):
    tables = sample_tables()
    for name in tables:
        (tmp_path / f"{name}.parquet").write_bytes(b"test shim")
    monkeypatch.setattr(duck, "_con", lambda _: SQLiteShim(tables))
    return tmp_path


def _rows_by_change(data):
    return {row["CHANGE_TYPE"]: row["CNT"] for row in data["rows"]}


def test_not_additive_across_source_and_paths(run):
    result = duck.pivot(run, ["CHANGE_TYPE"], [], {})
    assert result["columns"] == ["CHANGE_TYPE", "CNT"]
    assert result["dims"] == ["CHANGE_TYPE"]
    assert _rows_by_change(result) == {"VALUE_CHANGED": 2, "SAME": 1, "ATTRIBUTE_NEW": 1}
    assert len(duck.drilldown(run, {"CHANGE_TYPE": "VALUE_CHANGED"})) == 2


def test_click_every_cell_exactly_matches_pivot(run):
    for rows, cols, global_filters in [
        (["CHANGE_TYPE"], ["SOURCE"], {}),
        (["PATH", "CHANGE_TYPE"], ["SOURCE"], {}),
        (["CAUSE"], [], {}),
        (["CHANGE_TYPE"], ["SOURCE"], {"CAUSE": ["LOGIC", None]}),
        (["PATH"], [], {"SOURCE": "AFTER (BETA)"}),
    ]:
        table = duck.pivot(run, rows, cols, global_filters)
        for cell in table["rows"]:
            clicked = {**global_filters, **{key: cell[key] for key in table["dims"]}}
            ids = [row["APP_ID"] for row in duck.drilldown(run, clicked)]
            assert len(ids) == cell["CNT"], (clicked, ids, cell)
            assert len(ids) == len(set(ids))


def test_null_pivot_cell_roundtrips_through_drilldown(run):
    # A missing CAUSE becomes NaN when pandas materializes a SQL NULL;
    # it must be returned as JSON null and match via SQL IS NULL.
    table = duck.pivot(run, ["CAUSE"], [], {})
    null_cells = [r for r in table["rows"] if r["CAUSE"] is None]
    assert len(null_cells) == 1
    assert null_cells[0]["CNT"] == 1
    assert [x["APP_ID"] for x in duck.drilldown(run, {"CAUSE": None})] == ["D"]


def test_nan_from_pandas_is_treated_like_null(run):
    nan = float("nan")
    assert [r["APP_ID"] for r in duck.drilldown(run, {"CAUSE": nan})] == ["D"]
    assert [r["APP_ID"] for r in duck.drilldown(run, {"CAUSE": [nan, "NONE"]})] == ["C", "D"]
    filtered = duck.pivot(run, ["PATH"], [], {"CAUSE": nan})
    assert [(r["PATH"], r["CNT"]) for r in filtered["rows"]] == [("risk.o'brien", 1)]


def test_filter_list_null_and_empty(run):
    assert _rows_by_change(duck.pivot(run, [], [],
                                      {"SOURCE": ["BEFORE (MASTER)", "AFTER (BETA)"]})) == {
        "VALUE_CHANGED": 2, "SAME": 1, "ATTRIBUTE_NEW": 1}
    assert duck.pivot(run, [], [], {"SOURCE": []})["rows"] == []
    assert duck.drilldown(run, {"SOURCE": []}) == []
    assert [row["APP_ID"] for row in duck.drilldown(run, {"CAUSE": None})] == ["D"]
    assert [row["APP_ID"] for row in duck.drilldown(run, {"CAUSE": [None, "NONE"]})] == ["C", "D"]


def test_source_exclusion_and_safe_quote(run):
    # ATTRIBUTE_NEW has only the AFTER slice.
    rows = duck.pivot(run, ["CHANGE_TYPE"], [], {"SOURCE": "BEFORE (MASTER)"})
    assert "ATTRIBUTE_NEW" not in _rows_by_change(rows)
    assert [r["APP_ID"] for r in duck.drilldown(run, {"PATH": "risk.o'brien"})] == ["D"]


def test_dynamic_dimensions_and_deduplicated_dimensions(run):
    result = duck.pivot(run, ["ARRAY_KEY", "PATH"], ["PATH"], {})
    assert result["dims"] == ["ARRAY_KEY", "PATH"]
    assert all("ARRAY_KEY" in row for row in result["rows"])


@pytest.mark.parametrize("filters", [
    {"PATH; DROP TABLE facts": "anything"},
    {"FACT_ID": 1},
    {"CNT": 99},
    {"NON_EXISTENT": "x"},
])
def test_unsupported_filter_does_not_silently_change_answer(run, filters):
    with pytest.raises(ValueError, match="Unsupported pivot filter"):
        duck.drilldown(run, filters)


def test_injection_dimension_is_rejected(run):
    with pytest.raises(ValueError, match="Unsupported pivot dimension"):
        duck.pivot(run, ["PATH) UNION SELECT 1"], [], {})


def test_missing_fact_apps_fails_instead_of_inexact_fallback(run):
    (run / "fact_apps.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="fact_apps"):
        duck.pivot(run, ["PATH"], [], {})
    with pytest.raises(FileNotFoundError, match="fact_apps"):
        duck.drilldown(run, {"PATH": "risk.age"})


def test_app_rows_contract_stays_unchanged(run):
    all_rows = duck.app_rows(run, "A", False)
    assert [x["PATH"] for x in all_rows] == ["risk.age", "risk.model"]
    only_diff = duck.app_rows(run, "C", True)
    assert only_diff == []


def test_actual_duckdb_parquet_roundtrip(tmp_path):
    pytest.importorskip("duckdb")
    pytest.importorskip("pyarrow")
    for name, frame in sample_tables().items():
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    group = duck.pivot(tmp_path, ["CHANGE_TYPE"], ["SOURCE"], {})
    for cell in group["rows"]:
        clicked = {key: cell[key] for key in group["dims"]}
        matches = duck.drilldown(tmp_path, clicked)
        assert len(matches) == cell["CNT"]
    assert len(duck.drilldown(tmp_path, {"CHANGE_TYPE": "VALUE_CHANGED"})) == 2
