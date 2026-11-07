"""DuckDB поверх artifacts. Имена таблиц/колонок — из сравнения (s7), не хардкодим пути."""
from __future__ import annotations
import pathlib, duckdb
import pandas as pd


def _con(run_dir: pathlib.Path):
    con = duckdb.connect()
    comp = run_dir / "comparison.parquet"
    seg = run_dir / "segments.parquet"
    if comp.exists(): con.execute(f"CREATE VIEW comparison AS SELECT * FROM read_parquet('{comp}')")
    if seg.exists():  con.execute(f"CREATE VIEW segments AS SELECT * FROM read_parquet('{seg}')")
    return con


_ALLOWED_MEASURES = {"CNT": "COUNT(DISTINCT APP_ID)", "ROWS": "COUNT(*)"}


def pivot(run_dir: pathlib.Path, rows: list[str], cols: list[str], filters: dict) -> dict:
    con = _con(run_dir)
    dims = [*rows, *cols]
    where, params = _where(filters)
    if not dims:
        dims = ["CHANGE_TYPE"]
    sel = ", ".join(dims) + ", COUNT(DISTINCT APP_ID) AS CNT"
    sql = f"SELECT {sel} FROM comparison {where} GROUP BY {', '.join(dims)} ORDER BY 1"
    df = con.execute(sql, params).df()
    return {"columns": list(df.columns), "rows": df.to_dict(orient="records")}


def drilldown(run_dir: pathlib.Path, filters: dict) -> list[dict]:
    con = _con(run_dir)
    where, params = _where(filters)
    sql = f"""
      SELECT c.APP_ID,
             s.DECISION_BEFORE, s.DECISION_AFTER, s.DECISION_TRANSITION,
             s.REASON_TRANSITION, s.N_DIFFS, s.CAUSE
      FROM (SELECT DISTINCT APP_ID FROM comparison {where}) c
      LEFT JOIN segments s USING (APP_ID)
      ORDER BY c.APP_ID
    """
    return con.execute(sql, params).df().to_dict(orient="records")


def app_rows(run_dir: pathlib.Path, app_id: str, diff_only: bool) -> list[dict]:
    con = _con(run_dir)
    cond = "AND DIFF_FLAG = 1" if diff_only else ""
    df = con.execute(
        f"SELECT * FROM comparison WHERE APP_ID = ? {cond} ORDER BY PATH, ARRAY_KEY", [app_id]
    ).df()
    return df.to_dict(orient="records")


def _where(filters: dict):
    """Простые равенства и IN. Имена колонок — валидируем regex'ом."""
    import re
    parts, params = [], []
    for k, v in (filters or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if isinstance(v, (list, tuple)):
            ph = ",".join(["?"] * len(v))
            parts.append(f"{k} IN ({ph})");
            params.extend(v)
        else:
            parts.append(f"{k} = ?");
            params.append(v)
    return ("WHERE " + " AND ".join(parts) if parts else ""), params
