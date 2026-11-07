"""Indexed, read-only MartAPI over comparison and segments (MartAPI check contract).

The engine knows only the standardized mart column names, never input JSON paths.
Filtering is an AND of the supplied filters. Count counts rows; app_ids returns
unique application IDs, including when multiple array elements match.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


_ALLOWED = {
    'path': 'PATH',
    'path_prefix': 'PATH',
    'key': 'KEY',
    'array_key': 'ARRAY_KEY',
    'diff_flag': 'DIFF_FLAG',
    'change_type': 'CHANGE_TYPE',
    'value_before': 'VALUE_BEFORE',
    'value_after': 'VALUE_AFTER',
    'app_ids': 'APP_ID',
}
# The most common lookups get O(1) cached inverted indexes.
_INDEX_FIELDS = ('PATH', 'CHANGE_TYPE', 'DIFF_FLAG', 'KEY', 'ARRAY_KEY', 'APP_ID')
_REQUIRED_COMPARISON = {'APP_ID', 'PATH', 'ARRAY_KEY', 'KEY', 'DIFF_FLAG',
                        'CHANGE_TYPE', 'VALUE_BEFORE', 'VALUE_AFTER'}
_REQUIRED_SEGMENTS = {'APP_ID'}


def _scalar(value):
    """Convert pandas/numpy scalars to plain Python values for user checks."""
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _values(value, *, text=False):
    if isinstance(value, (list, tuple, set, frozenset)):
        result = list(value)
    else:
        result = [value]
    if text:
        result = [str(v) for v in result]
    return result


class MartAPI:
    """In-memory indexed implementation of the published checks MartAPI contract.

    Construct once per run, pass the same object to all five check scripts.
    A copy of the two input frames is kept to avoid mutating the originals.
    Indexes for commonly filtered columns are built lazily and reused.
    """

    def __init__(self, comparison: pd.DataFrame, segments: pd.DataFrame):
        missing_c = _REQUIRED_COMPARISON.difference(comparison.columns)
        missing_s = _REQUIRED_SEGMENTS.difference(segments.columns)
        if missing_c or missing_s:
            raise ValueError(f'MartAPI: missing columns in comparison={sorted(missing_c)}, '
                             f'segments={sorted(missing_s)}')
        self._comparison = comparison.reset_index(drop=True).copy(deep=False)
        self._segments = segments.reset_index(drop=True).copy(deep=False)
        if self._segments['APP_ID'].isna().any() or self._segments['APP_ID'].duplicated().any():
            raise ValueError('MartAPI: segments must contain unique non-null APP_ID')
        self._indices: dict[str, dict[object, np.ndarray]] = {}
        self._row_columns = tuple(self._comparison.columns)
        self._seg_columns = tuple(self._segments.columns)
        self._all = np.arange(len(self._comparison), dtype=np.int64)
        self._path_prefix = lru_cache(maxsize=64)(self._match_prefix)

    @classmethod
    def from_run(cls, run_dir: str | Path) -> 'MartAPI':
        base = Path(run_dir)
        return cls(pd.read_parquet(base / 'comparison.parquet'),
                   pd.read_parquet(base / 'segments.parquet'))

    def _index(self, col):
        if col not in self._indices:
            # Groupby.indices skips nulls; null matching is added below if requested.
            groups = self._comparison.groupby(col, dropna=False, sort=False).indices
            self._indices[col] = {
                _scalar(key): np.asarray(positions, dtype=np.int64)
                for key, positions in groups.items()
            }
        return self._indices[col]

    def _match_prefix(self, prefix):
        grouped = self._index('PATH')
        matching = [positions for path, positions in grouped.items()
                    if isinstance(path, str) and path.startswith(prefix)]
        return np.concatenate(matching) if matching else np.empty(0, dtype=np.int64)

    def _select(self, **filters) -> np.ndarray:
        invalid = set(filters).difference(_ALLOWED)
        if invalid:
            raise TypeError(f'MartAPI: unknown filter(s): {sorted(invalid)}')
        if not filters:
            return self._all
        selections = []
        for name, requested in filters.items():
            if name == 'path_prefix':
                if not isinstance(requested, str):
                    raise TypeError('path_prefix must be a string')
                selections.append(self._path_prefix(requested))
                continue
            col = _ALLOWED[name]
            values = _values(requested, text=(name == 'app_ids'))
            if not values:
                return np.empty(0, dtype=np.int64)
            if name == 'diff_flag':
                values = [int(v) for v in values]
            if col in _INDEX_FIELDS:
                lookup = self._index(col)
                found = [lookup.get(v) for v in values]
                found = [arr for arr in found if arr is not None]
                selections.append(np.concatenate(found) if found else np.empty(0, dtype=np.int64))
            else:
                # Rare value filters are run on the current candidates below,
                # rather than building potentially enormous indexes of unique scores.
                selections.append((col, values))
        indexed = [part for part in selections if isinstance(part, np.ndarray)]
        candidates = self._all if not indexed else np.unique(min(indexed, key=len))
        for part in indexed:
            if not len(candidates):
                break
            if part is not candidates:
                candidates = np.intersect1d(candidates, part, assume_unique=False)
        for part in selections:
            if isinstance(part, tuple) and len(candidates):
                col, values = part
                series = self._comparison.iloc[candidates][col]
                null_requested = any(_scalar(v) is None for v in values)
                ordinary = [v for v in values if _scalar(v) is not None]
                matching = series.isin(ordinary)
                if null_requested:
                    matching = matching | series.isna()
                candidates = candidates[matching.to_numpy(dtype=bool)]
        return candidates

    def rows(self, **filters) -> Iterable[dict]:
        """Iterate mart rows matching every filter; no side effects on source data."""
        positions = self._select(**filters)
        columns = self._row_columns
        for row in self._comparison.iloc[positions].itertuples(index=False, name=None):
            yield {name: _scalar(v) for name, v in zip(columns, row)}

    def count(self, **filters) -> int:
        """Number of matching attribute rows, NOT unique applications."""
        return int(len(self._select(**filters)))

    def app_ids(self, **filters) -> list[str]:
        """Sorted unique APP_IDs with at least one matching attribute row."""
        indexes = self._select(**filters)
        if not len(indexes):
            return []
        return sorted(str(x) for x in self._comparison.iloc[indexes]['APP_ID'].dropna().unique())

    def segments(self) -> Iterable[dict]:
        """Iterate the per-application segment table (including broken pairs)."""
        for row in self._segments.itertuples(index=False, name=None):
            yield {name: _scalar(v) for name, v in zip(self._seg_columns, row)}

    def total_apps(self) -> int:
        """Count all applications in segments, including those with no comparable rows."""
        return int(len(self._segments))
