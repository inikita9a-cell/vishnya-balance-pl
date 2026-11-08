"""Stable, distinct identifiers for rows in a unified checks report.

Works with both new checks.json files and historic reports without ROW_ID.
The identifier is based on row content, not the CHECK_ID/RESULT/ARGUMENT
triple (which is *not* unique). It deliberately excludes DURATION_MS, so a
rerun of unchanged checks produces the same identifiers. Identical rows receive
an occurrence suffix and are still independently addressable.
"""
from __future__ import annotations

import hashlib
import json


_SIGNATURE_FIELDS = (
    'CHECK_ID', 'LABEL', 'SOURCE', 'ARGUMENT', 'CNT', 'TOTAL',
    'METRIC', 'APP_IDS', 'FILTERS', 'RESULT', 'CONFIDENCE', 'ERROR',
)


def assign_check_row_ids(rows: list[dict]) -> list[dict]:
    """Assign authoritative ROW_IDs in place, return the same list.

    Never trust an existing ROW_ID in user-supplied check output. Calling this
    for older reports makes their IDs addressable without rewriting the file.
    """
    if not isinstance(rows, list):
        raise ValueError('checks.json must be a list of result rows')
    occurrences: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('each check result row must be a JSON object')
        signature = {name: row.get(name) for name in _SIGNATURE_FIELDS}
        canonical = json.dumps(signature, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), default=str)
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        row['ROW_ID'] = f'cr_{digest}_{occurrence}'
    return rows
