"""
Shared dataclasses passed between csv_mapper -> claim_parser -> fetcher ->
verifiers -> engine. Kept in one module so every stage imports the same
shapes instead of redefining ad-hoc dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Verdicts a row can end up with. MALFORMED_JSON and FETCH_FAILED are
# first-class outcomes, not exceptions: a Claygent blob that isn't JSON, or a
# source URL that can't be fetched, is exactly the kind of failure this tool
# exists to surface, not swallow.
MATCH = "MATCH"
MISMATCH = "MISMATCH"
UNVERIFIABLE = "UNVERIFIABLE"
MALFORMED_JSON = "MALFORMED_JSON"
FETCH_FAILED = "FETCH_FAILED"


@dataclass
class MappedRow:
    """One CSV row with the claim/source columns pulled out by name."""

    row_index: int
    fields: dict[str, str]
    claim_raw: str
    source_url: str


@dataclass
class ClaimExtraction:
    """Result of parsing a row's raw claim text as JSON.

    parse_error=True means the text wasn't valid JSON (e.g. Claygent
    returned a narrative sentence instead of the requested JSON blob) -
    the caller reports MALFORMED_JSON rather than crashing.
    """

    fields: dict[str, str] = field(default_factory=dict)
    parse_error: bool = False
    raw_text: str = ""


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
