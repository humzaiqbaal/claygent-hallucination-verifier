"""
Shared dataclasses passed between csv_mapper -> claim_parser -> fetcher ->
verifiers -> engine. Kept in one module so every stage imports the same
shapes instead of redefining ad-hoc dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Verdicts a row can end up with. NO_CLAIM_DATA and FETCH_FAILED are
# first-class outcomes, not exceptions: a row with nothing extracted, or a
# source URL that can't be fetched, is exactly the kind of failure this tool
# exists to surface, not swallow.
MATCH = "MATCH"
MISMATCH = "MISMATCH"
UNVERIFIABLE = "UNVERIFIABLE"
NO_CLAIM_DATA = "NO_CLAIM_DATA"
FETCH_FAILED = "FETCH_FAILED"


@dataclass
class MappedRow:
    """One CSV row with the claim columns and source column pulled out by name.

    claim_fields holds the raw (possibly-blank) values from whichever
    columns were configured as claim columns - a real Clay export has claim
    data spread across several already-extracted columns, not one JSON blob
    column, so this is a dict from the start rather than a single string.
    """

    row_index: int
    fields: dict[str, str]
    claim_fields: dict[str, str]
    source_url: str


@dataclass
class ClaimExtraction:
    """Result of pulling non-blank values out of a row's configured claim columns.

    is_empty=True means every configured claim column was blank for this row
    - the real-world signature of a failed Claygent extraction (see
    Memory/reference-clay-claygent-json-field-extraction.md: a Clay export
    never carries a parseable raw JSON blob, so a failed extraction shows up
    as empty pre-selected columns, not invalid JSON text).
    """

    fields: dict[str, str] = field(default_factory=dict)
    is_empty: bool = False


@dataclass
class FetchResult:
    """Result of fetching a row's source URL."""

    status: str  # OK | UNREACHABLE | TIMEOUT | NON_200 | LIKELY_PAYWALLED | LIKELY_JS_RENDERED
    page_text: str = ""
    detail: str = ""


@dataclass
class VerificationVerdict:
    """Output of a ClaimVerifier.verify() call."""

    verdict: str  # MATCH | MISMATCH | UNVERIFIABLE
    confidence_note: str
    checked_fields: list[str]
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class RowResult:
    """Final per-row outcome, ready to be written back out as CSV columns."""

    row_index: int
    verdict: str
    failure_detail: str = ""
    checked_fields: str = ""
    confidence_note: str = ""
    source_url: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
