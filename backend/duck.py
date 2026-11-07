"""DuckDB поверх artifacts. Использует facts и fact_apps для сводной и провала."""
from __future__ import annotations
import pathlib, duckdb
import pandas as pd
import re

# Разрешенные измерения из facts (чтобы не было SQL-инъекций)
_FACT_DIMS = {
    "PREFIX", "CLASS", "SUFFIX", "KEY", "PATH", "VALUE_ADJUSTED",
    "DIFF_FLAG", "CHANGE_TYPE", "SOURCE",
    "DECISION_BEFORE", "DECISION_AFTER", "DECISION_TRANSITION",
    "REASON_TRANSITION", "CAUSE", "PARTNER_TYPE",
}


def _con(run_dir: pathlib.Path):
    con = duckdb.connect()
    # Создаем вьюхи для всех артефактов
    for name in ("comparison", "segments", "facts", "fact_apps"):
        p = run_dir / f"{name}.parquet"
        if p.exists():
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{p}')")
    return con


def _check_dim(col: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col)) and col in _FACT_DIMS


def _where(filters: dict, allow=set()):
    parts, params = [], []
    for k, v in (filters or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if allow and k not in allow:
            continue
        if isinstance(v, (list, tuple, set)):
            ph = ",".join(["?"] * len(v))
            parts.append(f"{k} IN ({ph})")
            params.extend(v)
        else:
            parts.append(f"{k} = ?")
            params.append(v)
    return ("WHERE " + " AND ".join(parts) if parts else ""), params


def pivot(run_dir: pathlib.Path, rows: list[str], cols: list[str], filters: dict) -> dict:
    """Сводная по facts. Мера — SUM(CNT)."""
    con = _con(run_dir)
    dims = [d for d in [*rows, *cols] if _check_dim(d)]
    if not dims:
        dims = ["CHANGE_TYPE"]
    where, params = _where(filters, allow=_FACT_DIMS)
    sel = ", ".join(dims) + ", SUM(CNT) AS CNT"
    # Если facts нет, падаем с понятной ошибкой
    sql = f"SELECT {sel} FROM facts {where} GROUP BY {', '.join(dims)} ORDER BY 1"
    try:
        df = con.execute(sql, params).df()
    except duckdb.CatalogException:
        raise ValueError("facts.parquet not found. Run pipeline first.")
    return {"columns": list(df.columns), "rows": df.to_dict(orient="records"), "dims": dims}


def drilldown(run_dir: pathlib.Path, filters: dict) -> list[dict]:
    """Список заявок по фильтрам. Через fact_apps (точный distinct) + segments."""
    con = _con(run_dir)
    where, params = _where(filters, allow=_FACT_DIMS)
    # Проверяем, есть ли fact_apps
    try:
        con.execute("SELECT 1 FROM fact_apps LIMIT 1")
        base = f"""
          SELECT DISTINCT fa.APP_ID
          FROM fact_apps fa
          JOIN facts f ON f.fact_id = fa.fact_id
          {where.replace('APP_ID', 'fa.APP_ID') if where else ''}
        """
    except duckdb.CatalogException:
        # Fallback: если fact_apps нет, пробуем по comparison (медленнее)
        base = f"SELECT DISTINCT APP_ID FROM comparison {where}"

    sql = f"""
      SELECT c.APP_ID,
             s.DECISION_BEFORE, s.DECISION_AFTER, s.DECISION_TRANSITION,
             s.REASON_TRANSITION, s.N_DIFFS, s.CAUSE
      FROM ({base}) c
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
