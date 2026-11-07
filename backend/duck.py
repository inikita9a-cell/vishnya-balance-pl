"""DuckDB queries for pivot and exact application drill-down.

facts.parquet stores distinct APP_ID counts *per full fact dimension combination*.
Those CNT values are not additive over PATH, SOURCE or other dimensions.
The membership bridge fact_apps.parquet (FACT_ID, APP_ID) is the source of
truth for both pivot cells and the corresponding drill-down results.

Public signatures/response shapes intentionally match the platform API:
  pivot(run_dir, rows, cols, filters) -> {columns, rows, dims}
  drilldown(run_dir, filters) -> [{APP_ID, ...}]
  app_rows(run_dir, app_id, diff_only) -> [{...}]
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NON_DIMENSIONS = {"FACT_ID", "APP_ID", "CNT"}


def _con(run_dir: pathlib.Path):
    """Connection with views over available run artifacts, no persisted DB."""
    import duckdb

    con = duckdb.connect()
    for name in ("comparison", "segments", "facts", "fact_apps"):
        path = pathlib.Path(run_dir) / f"{name}.parquet"
        if path.is_file():
            # Escape SQL string literals, including apostrophes in Windows paths.
            quoted_path = path.resolve().as_posix().replace("'", "''")
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{quoted_path}')")
    return con


def _require_files(run_dir: pathlib.Path, *names: str) -> None:
    for name in names:
        path = pathlib.Path(run_dir) / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Required pivot/drill-down artifact is missing: {path}")


def _fact_dims(con) -> set[str]:
    """Discover dimensions from the *actual* facts schema.

    This supports configurable segment dimensions and optional ARRAY_KEY, but
    excludes internal identifiers/measures. Column names are SQL-quoted later.
    """
    fields = [item[0] for item in con.execute("SELECT * FROM facts LIMIT 0").description]
    return {col for col in fields if _IDENTIFIER.fullmatch(col) and col.upper() not in _NON_DIMENSIONS}


def _sql_col(col: str) -> str:
    # Only called after validating membership in _fact_dims.
    return 'f."' + col.replace('"', '""') + '"'


def _dimensions(rows: list[str], cols: list[str], allowed: set[str]) -> list[str]:
    result = []
    for dim in [*(rows or []), *(cols or [])]:
        if not isinstance(dim, str) or dim not in allowed:
            raise ValueError(f"Unsupported pivot dimension: {dim!r}")
        if dim not in result:
            result.append(dim)
    if not result:
        if "CHANGE_TYPE" not in allowed:
            raise ValueError("No pivot dimensions selected and CHANGE_TYPE not present in facts")
        result = ["CHANGE_TYPE"]
    return result


def _is_null(value) -> bool:
    """Recognize missing scalar values in API JSON and pandas pivot cells.

    Pandas turns NULL group keys into float('nan') when converting a DataFrame
    to records. Both None and NaN must mean SQL IS NULL, not f.col = ?.
    """
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # Arrays and other unsupported filter values are not NULL scalars.
        return False


def _where(filters: dict | None, allowed: set[str]) -> tuple[str, list]:
    """Build parameterized WHERE with AND across dimensions, OR within lists.

    Null values are matched via IS NULL. Empty lists intentionally match none.
    Invalid filters fail clearly instead of silently returning wrong counts.
    """
    clauses, params = [], []
    if not isinstance(filters or {}, dict):
        raise ValueError("Pivot filters must be an object/dict")
    for field, raw in (filters or {}).items():
        if not isinstance(field, str) or field not in allowed:
            raise ValueError(f"Unsupported pivot filter: {field!r}")
        col = _sql_col(field)
        if isinstance(raw, (list, tuple, set)):
            values = list(raw)
            if not values:
                clauses.append("FALSE")
                continue
            values_non_null = [value for value in values if not _is_null(value)]
            alternatives = []
            if values_non_null:
                alternatives.append(f"{col} IN ({', '.join('?' for _ in values_non_null)})")
                params.extend(values_non_null)
            if any(_is_null(value) for value in values):
                alternatives.append(f"{col} IS NULL")
            clauses.append("(" + " OR ".join(alternatives) + ")")
        elif _is_null(raw):
            clauses.append(f"{col} IS NULL")
        else:
            clauses.append(f"{col} = ?")
            params.append(raw)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def pivot(run_dir: pathlib.Path, rows: list[str], cols: list[str], filters: dict) -> dict:
    """Counts DISTINCT applications, not additive fact-row counts.

    Group dimensions are returned unchanged, so the frontend can combine the
    chosen row/column values and the global filters for /drilldown.
    """
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "facts", "fact_apps")
    con = _con(run_dir)
    try:
        allowed = _fact_dims(con)
        dims = _dimensions(rows, cols, allowed)
        where, params = _where(filters, allowed)
        grouping = ", ".join(_sql_col(dim) for dim in dims)
        sql = f"""
            SELECT {grouping}, COUNT(DISTINCT fa.APP_ID) AS CNT
            FROM facts AS f
            INNER JOIN fact_apps AS fa ON fa.FACT_ID = f.FACT_ID
            {where}
            GROUP BY {grouping}
            ORDER BY 1
        """
        df = con.execute(sql, params).df()
        # Keep public response shape used by backend/api/data_api.py.
        # JSON has no NaN value. Emit None for NULL dimension keys, so a
        # clicked cell can pass them back as JSON null to drilldown().
        records = df.astype(object).where(df.notna(), None).to_dict(orient="records")
        return {"columns": list(df.columns), "rows": records, "dims": dims}
    finally:
        con.close()


def drilldown(run_dir: pathlib.Path, filters: dict) -> list[dict]:
    """Exactly the distinct APP_IDs counted by pivot for these filters.

    Caller must merge global pivot filters with all dimensions/value pairs of
    the clicked cell (including SOURCE when it's a column dimension).
    """
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "facts", "fact_apps", "segments")
    con = _con(run_dir)
    try:
        where, params = _where(filters, _fact_dims(con))
        sql = f"""
            SELECT selected.APP_ID,
                   s.DECISION_BEFORE, s.DECISION_AFTER,
                   s.DECISION_TRANSITION, s.REASON_TRANSITION,
                   s.N_DIFFS, s.CAUSE
            FROM (
                SELECT DISTINCT fa.APP_ID
                FROM fact_apps AS fa
                INNER JOIN facts AS f ON fa.FACT_ID = f.FACT_ID
                {where}
            ) AS selected
            LEFT JOIN segments AS s ON s.APP_ID = selected.APP_ID
            ORDER BY selected.APP_ID
        """
        return con.execute(sql, params).df().to_dict(orient="records")
    finally:
        con.close()


def app_rows(run_dir: pathlib.Path, app_id: str, diff_only: bool) -> list[dict]:
    """Keep existing application detail response and sorted comparison rows."""
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "comparison")
    con = _con(run_dir)
    try:
        cond = "AND DIFF_FLAG = 1" if diff_only else ""
        df = con.execute(
            f"SELECT * FROM comparison WHERE APP_ID = ? {cond} ORDER BY PATH, ARRAY_KEY",
            [app_id],
        ).df()
        return df.to_dict(orient="records")
    finally:
        con.close()
