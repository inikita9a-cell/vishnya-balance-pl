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


def pivot_dimensions(run_dir: pathlib.Path) -> dict:
    """List permitted pivot dimensions from THIS run's real facts schema."""
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "facts", "fact_apps")
    con = _con(run_dir)
    try:
        return {"dimensions": sorted(_fact_dims(con))}
    finally:
        con.close()


def pivot_values(run_dir: pathlib.Path, field: str, limit: int = 200) -> dict:
    """Give frontend real filter choices, preserving distinct SQL NULL values."""
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "facts", "fact_apps")
    con = _con(run_dir)
    try:
        if field not in _fact_dims(con):
            raise ValueError(f"Unsupported pivot filter: {field!r}")
        if not 1 <= limit <= 500:
            raise ValueError("Invalid pivot values limit")
        values = con.execute(
            f"SELECT DISTINCT {_sql_col(field)} AS value "
            f"FROM facts AS f ORDER BY value LIMIT ?", [limit + 1]
        ).df()['value']
        values = values.astype(object).where(values.notna(), None).tolist()
        return {"field": field, "values": values[:limit], "has_more": len(values) > limit}
    finally:
        con.close()


def pivot_apps(run_dir: pathlib.Path, filters: dict, limit: int = 50,
               offset: int = 0) -> dict:
    """Server-paginated exact set of unique apps for one pivot cell."""
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "facts", "fact_apps", "segments")
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("Invalid pivot application pagination")
    con = _con(run_dir)
    try:
        where, params = _where(filters, _fact_dims(con))
        joined = f"FROM fact_apps AS fa JOIN facts AS f ON fa.FACT_ID = f.FACT_ID {where}"
        total = con.execute(f"SELECT COUNT(DISTINCT fa.APP_ID) {joined}", params).fetchone()[0]
        query = f"""
            SELECT selected.APP_ID, s.DECISION_BEFORE, s.DECISION_AFTER,
                   s.DECISION_TRANSITION, s.REASON_TRANSITION, s.N_DIFFS, s.CAUSE
            FROM (SELECT DISTINCT fa.APP_ID {joined}
                  ORDER BY fa.APP_ID LIMIT ? OFFSET ?) AS selected
            LEFT JOIN segments AS s ON s.APP_ID = selected.APP_ID
            ORDER BY selected.APP_ID
        """
        df = con.execute(query, [*params, limit, offset]).df()
        items = df.astype(object).where(df.notna(), None).to_dict(orient="records")
        return {"items": items, "total": int(total), "limit": limit, "offset": offset}
    finally:
        con.close()


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
        df = con.execute(sql, params).df()
        return df.astype(object).where(df.notna(), None).to_dict(orient="records")
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
        # Nullable numeric metadata becomes NaN in pandas. JSON cannot encode it;
        # preserve the SQL NULL instead of failing the entire application card.
        return df.astype(object).where(df.notna(), None).to_dict(orient="records")
    finally:
        con.close()


def get_sankey_data(run_dir: pathlib.Path, filters: dict | None = None) -> dict:
    """Acyclic BEFORE -> AFTER -> reason flows; unique applications per link."""
    import json
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "segments")
    con = _con(run_dir)
    try:
        allowed_dims = {"DECISION_BEFORE", "DECISION_AFTER", "DECISION_TRANSITION",
                        "REASON_BEFORE", "REASON_AFTER", "REASON_TRANSITION",
                        "CAUSE", "PARTNER_TYPE", "ROUTING_METHOD"}
        where, params = _where(filters, allowed_dims)
        rows = con.execute(f"""
            SELECT DECISION_BEFORE, DECISION_AFTER, REASON_TRANSITION,
                   COUNT(DISTINCT APP_ID) AS CNT
            FROM segments f {where}
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """, params).fetchall()
        nodes, links = {}, {}

        def node(stage, value, after=None):
            # IDs encode both stage and raw value: no BEFORE/AFTER cycles,
            # no collision between SQL NULL, the string 'NULL' and empty string.
            key = json.dumps([stage, after, value], ensure_ascii=False)
            field = ("DECISION_BEFORE", "DECISION_AFTER", "REASON_TRANSITION")[stage]
            label = "Нет данных" if value is None else "Пустая строка" if value == "" else str(value)
            label = {"APPROVE": "Одобрено", "REJECT": "Отказ"}.get(label, label) if stage < 2 else label
            exact_filters = {field: value}
            if stage == 2:
                exact_filters["DECISION_AFTER"] = after
            nodes[key] = {"name": key, "label": label, "depth": stage, "filters": exact_filters}
            return key

        for before, after, reason, count in rows:
            count = int(count)
            if count <= 0:
                continue
            source, target = node(0, before), node(1, after)
            pairs = [(source, target, {"DECISION_BEFORE": before, "DECISION_AFTER": after}),
                     (target, node(2, reason, after), {"DECISION_AFTER": after, "REASON_TRANSITION": reason})]
            for source, target, exact_filters in pairs:
                key = source, target
                if key not in links:
                    links[key] = {"source": source, "target": target, "value": 0, "filters": exact_filters}
                links[key]["value"] += count
        return {"nodes": list(nodes.values()), "links": list(links.values())}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Explorer API: fields / query / apps
#
# Aggregation is performed against the full run on the backend (DuckDB over
# comparison + segments), not over rows already loaded by the frontend.
# Filters accept the same names the caller can group by, plus CHANGE_TYPE
# and ARRAY_KEY. NULL and missing values are distinct because CHANGE_TYPE
# is computed by the engine (SAME / VALUE_CHANGED / ATTRIBUTE_NEW /
# ATTRIBUTE_LOST), and ADJUSTED_* store the serialized leaf value where
# missing is not equal to the string "NULL".
# ---------------------------------------------------------------------------

# Dimensions exposed for groupBy and filters on the comparison view.
# Keep in sync with SEGMENT_COLUMNS in engine/steps.py if you add new ones.
_EXPLORER_DIMENSIONS = (
    "PATH", "PREFIX", "CLASS", "SUFFIX", "KEY", "ARRAY_KEY", "DEPTH",
    "CHANGE_TYPE", "DIFF_FLAG",
    "ADJUSTED_BEFORE", "ADJUSTED_AFTER",
    "VALUE_BEFORE", "VALUE_AFTER",
    "DECISION_BEFORE", "DECISION_AFTER", "DECISION_TRANSITION",
    "REASON_TRANSITION", "CAUSE", "PARTNER_TYPE",
    "PRODUCTS", "TOP_OFFER_BEFORE", "TOP_OFFER_AFTER",
    "QUALITY_ISSUE", "COMPARISON_COMPLETE",
)
_EXPLORER_DIM_SET = set(_EXPLORER_DIMENSIONS)


def _explorer_where(filters: dict | None) -> tuple[str, list]:
    """Safe WHERE builder for explorer endpoints.

    Rules:
      * Only known dimensions are accepted. Unknown -> ValueError.
      * Column names are quoted; values are parameterized.
      * List values use IN; empty list means "match nothing".
      * A NULL filter means IS NULL (never "= 'NULL'").
    """
    clauses, params = [], []
    if filters is None:
        return "", params
    if not isinstance(filters, dict):
        raise ValueError("filters must be a JSON object")

    for field, raw in filters.items():
        if field not in _EXPLORER_DIM_SET:
            raise ValueError(f"Unsupported filter field: {field!r}")
        col = '"' + field.replace('"', '""') + '"'

        if isinstance(raw, (list, tuple, set)):
            values = list(raw)
            if not values:
                clauses.append("FALSE")
                continue
            non_null = [v for v in values if v is not None and not pd.isna(v)]
            alternatives = []
            if non_null:
                alternatives.append(f"{col} IN ({', '.join('?' for _ in non_null)})")
                params.extend(non_null)
            if any(v is None or pd.isna(v) for v in values):
                alternatives.append(f"{col} IS NULL")
            clauses.append("(" + " OR ".join(alternatives) + ")")
        elif raw is None or pd.isna(raw):
            clauses.append(f"{col} IS NULL")
        else:
            clauses.append(f"{col} = ?")
            params.append(raw)

    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _validate_group_columns(group_by: list[str]) -> list[str]:
    seen = []
    for col in group_by or []:
        if not isinstance(col, str) or col not in _EXPLORER_DIM_SET:
            raise ValueError(f"Unsupported groupBy column: {col!r}")
        if col not in seen:
            seen.append(col)
    return seen


def get_explorer_fields(run_dir: pathlib.Path) -> dict:
    """Field catalogue: unique paths with appsCount / changedAppsCount.

    Built from the full comparison view, so it's independent of any frontend
    state. hasArrayInstances is true when at least one row of that path has
    a non-empty ARRAY_KEY (i.e. the attribute lives inside an array element).
    """
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "comparison")
    con = _con(run_dir)
    try:
        sql = """
            SELECT
                PATH,
                MIN(DEPTH) AS depth,
                COUNT(DISTINCT APP_ID) AS apps_count,
                COUNT(DISTINCT CASE WHEN DIFF_FLAG = 1 THEN APP_ID END) AS changed_apps_count,
                MAX(CASE WHEN ARRAY_KEY IS NOT NULL AND ARRAY_KEY <> '' THEN 1 ELSE 0 END) AS has_array
            FROM comparison
            WHERE PATH IS NOT NULL
            GROUP BY PATH
            ORDER BY PATH
        """
        df = con.execute(sql).df()
        fields = [
            {
                "path": row["PATH"],
                "depth": int(row["depth"]) if pd.notna(row["depth"]) else None,
                "appsCount": int(row["apps_count"] or 0),
                "changedAppsCount": int(row["changed_apps_count"] or 0),
                "hasArrayInstances": bool(row["has_array"]),
            }
            for _, row in df.iterrows()
        ]
        return {
            "fields": fields,
            "dimensions": list(_EXPLORER_DIMENSIONS),
        }
    finally:
        con.close()


def explorer_query(
    run_dir: pathlib.Path,
    group_by: list[str],
    filters: dict | None,
    include_unchanged: bool,
    limit: int,
    offset: int,
) -> dict:
    """Universal aggregation over comparison. Returns per-group counts.

    appsCount         = COUNT(DISTINCT APP_ID) inside the group.
    occurrencesCount  = COUNT(*) inside the group (differs from appsCount
                        for arrays where one app has multiple elements).

    When include_unchanged is False, DIFF_FLAG=0 rows are excluded from
    aggregation so the result matches the "differences only" view.

    drilldownFilters merges the caller's filters with the row's own
    dimension values (as single-element lists), so the frontend can post them
    verbatim to /explorer/apps.
    """
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "comparison")
    con = _con(run_dir)

    try:
        dims = _validate_group_columns(group_by)
        if not dims:
            raise ValueError("groupBy must contain at least one column")

        where, params = _explorer_where(filters)
        if not include_unchanged:
            where = where + (" AND " if where else "WHERE ") + "DIFF_FLAG = 1"

        grouping = ", ".join('"' + d.replace('"', '""') + '"' for d in dims)
        base_sql = f"""
            SELECT {grouping},
                   COUNT(DISTINCT APP_ID) AS apps_count,
                   COUNT(*) AS occurrences_count
            FROM comparison
            {where}
            GROUP BY {grouping}
            ORDER BY apps_count DESC, occurrences_count DESC
        """

        count_sql = f"SELECT COUNT(*) FROM ({base_sql}) AS grouped"
        total_groups = int(con.execute(count_sql, params).fetchone()[0] or 0)

        page_sql = base_sql + " LIMIT ? OFFSET ?"
        df = con.execute(page_sql, params + [int(limit), int(offset)]).df()

        rows = []
        for _, row in df.iterrows():
            values = {}
            drilldown = dict(filters or {})
            if not include_unchanged:
                # Preserve the implicit differences-only scope when replaying a group.
                drilldown['DIFF_FLAG'] = [1]
            for d in dims:
                v = row[d]
                if pd.isna(v):
                    v = None
                values[d] = v
                # Every grouped value becomes a single-element filter for drill-down.
                drilldown[d] = [v] if v is not None else [None]
            rows.append({
                "values": values,
                "appsCount": int(row["apps_count"] or 0),
                "occurrencesCount": int(row["occurrences_count"] or 0),
                "drilldownFilters": drilldown,
            })

        return {
            "totalGroups": total_groups,
            "rows": rows,
            "limit": int(limit),
            "offset": int(offset),
        }
    finally:
        con.close()


def explorer_apps(
    run_dir: pathlib.Path,
    filters: dict | None,
    limit: int,
    offset: int,
) -> dict:
    """Drill-down to unique APP_IDs that match the filters.

    Filter application is identical to explorer_query, so the count here
    always equals the group's appsCount for the same filters.
    """
    run_dir = pathlib.Path(run_dir)
    _require_files(run_dir, "comparison", "segments")
    con = _con(run_dir)
    try:
        where, params = _explorer_where(filters)

        total_sql = f"SELECT COUNT(DISTINCT APP_ID) FROM comparison {where}"
        total = int(con.execute(total_sql, params).fetchone()[0] or 0)

        sql = f"""
            SELECT c.APP_ID,
                   s.DECISION_BEFORE, s.DECISION_AFTER,
                   s.N_DIFFS, s.COMPARISON_COMPLETE
            FROM (
                SELECT DISTINCT APP_ID FROM comparison {where}
            ) AS c
            LEFT JOIN segments AS s ON s.APP_ID = c.APP_ID
            ORDER BY c.APP_ID
            LIMIT ? OFFSET ?
        """
        df = con.execute(sql, params + [int(limit), int(offset)]).df()

        items = []
        for _, row in df.iterrows():
            items.append({
                "APP_ID": row["APP_ID"],
                "DECISION_BEFORE": None if pd.isna(row["DECISION_BEFORE"]) else row["DECISION_BEFORE"],
                "DECISION_AFTER": None if pd.isna(row["DECISION_AFTER"]) else row["DECISION_AFTER"],
                "N_DIFFS": int(row["N_DIFFS"]) if pd.notna(row["N_DIFFS"]) else 0,
                "COMPARISON_COMPLETE": int(row["COMPARISON_COMPLETE"]) if pd.notna(row["COMPARISON_COMPLETE"]) else 0,
            })

        return {
            "total": total,
            "items": items,
            "limit": int(limit),
            "offset": int(offset),
        }
    finally:
        con.close()

