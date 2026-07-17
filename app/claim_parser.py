"""
Deterministic extraction of the usable claim from a row's pre-extracted
claim columns.

Earlier versions of this tool expected one column holding a raw Claygent
JSON blob and parsed it with json.loads(). That assumption was wrong: a real
Clay CSV export never carries data in the raw-response column - only the
columns a user manually selected from Claygent's side panel are populated.
So there's no JSON to parse here; the "extraction" is just filtering out
whichever configured claim columns came back blank for a given row.

A row where every configured claim column is blank is this tool's signal
for "Claygent's extraction failed" (e.g. it returned narrative text instead
of a usable response, so nothing was there to select in Clay's UI) - that's
reported as NO_CLAIM_DATA, not silently skipped or crashed on.
"""

from __future__ import annotations

from app.schema import ClaimExtraction


def extract_claim(claim_fields: dict[str, str]) -> ClaimExtraction:
    """Drop blank claim columns; flag the row as empty if nothing is left."""
    non_blank = {key: value for key, value in claim_fields.items() if value and value.strip()}
    return ClaimExtraction(fields=non_blank, is_empty=not non_blank)
