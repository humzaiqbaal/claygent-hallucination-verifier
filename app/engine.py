"""
Core batch-verification engine.

Pure orchestration: maps rows -> parses claims -> fetches sources -> calls a
ClaimVerifier -> aggregates results and cost. No CLI or MCP code lives here;
both interfaces call into this module and nothing else, so they can never
drift out of sync with each other.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.claim_parser import extract_claim
from app.csv_mapper import map_rows, parse_csv_rows
from app.fetcher import fetch_source
from app.schema import FETCH_FAILED, NO_CLAIM_DATA, RowResult
from app.verifiers import ClaimVerifier

# Rough $/1M token pricing for cost estimation. Update as pricing changes;
# this is a static reference table, not a live-pricing API call. See
# ai-personalization-engine/app/engine.py for the same caveat this table
# inherits: verify against https://www.anthropic.com/pricing before relying
# on it for real budgeting decisions.
MODEL_PRICING_PER_MILLION = {
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}

CHARS_PER_TOKEN_ESTIMATE = 4  # rough heuristic for pre-flight estimates, not exact


@dataclass
class BatchResult:
    results: list[RowResult] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
        return counts

    def estimated_cost(self, model: str) -> float | None:
        pricing = MODEL_PRICING_PER_MILLION.get(model)
        if not pricing:
            return None
        return (
            self.total_input_tokens * pricing["input"] / 1_000_000
            + self.total_output_tokens * pricing["output"] / 1_000_000
        )


def estimate_batch_cost(
    rows: list[dict[str, str]],
    model: str,
    avg_output_tokens: int = 150,
) -> float | None:
    """Rough pre-flight cost estimate before spending anything.

    Character-count heuristic (~4 chars/token), not an exact token count -
    purpose is to let a user sanity-check "will this batch cost $0.50 or
    $50" before running it, same credit-conscious pattern used across this
    portfolio's other tools.
    """
    pricing = MODEL_PRICING_PER_MILLION.get(model)
    if not pricing:
        return None

    total_input_tokens = 0
    for row in rows:
        row_char_count = sum(len(k) + len(v) for k, v in row.items())
        total_input_tokens += row_char_count // CHARS_PER_TOKEN_ESTIMATE

    total_output_tokens = len(rows) * avg_output_tokens

    return (
        total_input_tokens * pricing["input"] / 1_000_000
        + total_output_tokens * pricing["output"] / 1_000_000
    )


def run_batch(
    rows: list[dict[str, str]],
    claim_columns: list[str],
    source_url_column: str,
    verifier: ClaimVerifier,
) -> BatchResult:
    """Verify each row's pre-extracted claim columns against its source URL.

    Per row: pull non-blank values out of the configured claim columns
    (NO_CLAIM_DATA if every one of them is blank) -> fetch the source URL
    (FETCH_FAILED on any non-OK fetch status) -> ask the verifier whether the
    page text supports the claim. Each row produces exactly one RowResult,
    in input order, so callers can zip(rows, batch.results).
    """
    mapped_rows = map_rows(rows, claim_columns=claim_columns, source_url_column=source_url_column)
    batch = BatchResult()

    for mapped in mapped_rows:
        extraction = extract_claim(mapped.claim_fields)
        if extraction.is_empty:
            batch.results.append(
                RowResult(
                    row_index=mapped.row_index,
                    verdict=NO_CLAIM_DATA,
                    failure_detail=f"claim columns {sorted(mapped.claim_fields)} were all blank for this row",
                    source_url=mapped.source_url,
                )
            )
            continue

        claim = extraction.fields
        fetch_result = fetch_source(mapped.source_url)
        if fetch_result.status != "OK":
            batch.results.append(
                RowResult(
                    row_index=mapped.row_index,
                    verdict=FETCH_FAILED,
                    failure_detail=f"{fetch_result.status}: {fetch_result.detail}",
                    checked_fields=";".join(claim),
                    source_url=mapped.source_url,
                )
            )
            continue

        outcome = verifier.verify(claim, fetch_result.page_text)
        batch.results.append(
            RowResult(
                row_index=mapped.row_index,
                verdict=outcome.verdict,
                confidence_note=outcome.confidence_note,
                checked_fields=";".join(outcome.checked_fields),
                source_url=mapped.source_url,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
            )
        )
        batch.total_input_tokens += outcome.input_tokens
        batch.total_output_tokens += outcome.output_tokens

    return batch


def write_csv_output(rows: list[dict[str, str]], batch: BatchResult) -> str:
    """Re-emit the original rows plus verification_* columns appended."""
    all_fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in all_fieldnames:
                all_fieldnames.append(key)
    all_fieldnames += [
        "verification_verdict",
        "verification_detail",
        "verification_confidence_note",
        "verification_checked_fields",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_fieldnames)
    writer.writeheader()

    for row, result in zip(rows, batch.results):
        out_row = dict(row)
        out_row["verification_verdict"] = result.verdict
        out_row["verification_detail"] = result.failure_detail
        out_row["verification_confidence_note"] = result.confidence_note
        out_row["verification_checked_fields"] = result.checked_fields
        writer.writerow(out_row)

    return output.getvalue()


__all__ = [
    "BatchResult",
    "estimate_batch_cost",
    "parse_csv_rows",
    "run_batch",
    "write_csv_output",
]
