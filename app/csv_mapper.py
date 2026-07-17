"""
Deterministic CSV loading and column mapping.

Clay exports don't have a fixed shape: which column holds the Claygent claim
data and which holds the source URL is whatever the user picked when they
built their table (see README - Claygent output can land in a raw JSON blob
column via a JSON_EXTRACT formula, or as manually-selected fields via Clay's
response side panel, or both). This module never assumes a header name -
callers always pass the column names explicitly.
"""

from __future__ import annotations

import csv
import io

from app.schema import MappedRow


def parse_csv_rows(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV text into a list of row dicts, preserving every column.

    Unlike a "drop empty fields" parse, this keeps the full row shape so the
    original columns can be re-emitted unchanged in the output CSV.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    return [{key.strip(): value for key, value in raw_row.items() if key} for raw_row in reader]


def map_rows(
    rows: list[dict[str, str]],
    claim_column: str,
    source_url_column: str,
) -> list[MappedRow]:
    """Pull the claim text and source URL out of each row by column name.

    Raises KeyError up front (before any network/LLM cost is spent) if either
    configured column is missing from the CSV's actual headers.
    """
    if rows:
        headers = set(rows[0])
        missing = {claim_column, source_url_column} - headers
        if missing:
            raise KeyError(f"column(s) {sorted(missing)} not found in CSV headers: {sorted(headers)}")

    return [
        MappedRow(
            row_index=index,
            fields=row,
            claim_raw=row.get(claim_column, ""),
            source_url=row.get(source_url_column, ""),
        )
        for index, row in enumerate(rows)
    ]
