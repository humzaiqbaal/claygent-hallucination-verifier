"""
Deterministic CSV loading and column mapping.

A real Clay CSV export never carries the raw Claygent JSON response with
data in it - that column exports blank. Only the columns a user manually
added from the side panel (picking which JSON keys to expose) actually have
values. So a row's claim isn't one blob column to parse; it's however many
pre-extracted columns the user picked, under whatever names they gave them.
This module never assumes a header name or a fixed column count - callers
always pass the column names explicitly.
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
    claim_columns: list[str],
    source_url_column: str,
) -> list[MappedRow]:
    """Pull the claim column values and source URL out of each row by name.

    Raises KeyError up front (before any network/LLM cost is spent) if any
    configured column is missing from the CSV's actual headers.
    """
    if rows:
        headers = set(rows[0])
        missing = (set(claim_columns) | {source_url_column}) - headers
        if missing:
            raise KeyError(f"column(s) {sorted(missing)} not found in CSV headers: {sorted(headers)}")

    return [
        MappedRow(
            row_index=index,
            fields=row,
            claim_fields={column: row.get(column, "") for column in claim_columns},
            source_url=row.get(source_url_column, ""),
        )
        for index, row in enumerate(rows)
    ]
