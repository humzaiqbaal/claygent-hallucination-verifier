"""
Unit tests for app.engine, using a FakeClaimVerifier double instead of the
real Claude API: fast, offline, deterministic, and free. Source-URL fetches
go through the real fetcher.fetch_source, but requests_mock intercepts the
actual HTTP call - no real network, no unmocked URL slips through silently
(requests_mock raises on any URL that wasn't explicitly registered).
"""

from pathlib import Path

from app.engine import estimate_batch_cost, run_batch, write_csv_output
from app.csv_mapper import parse_csv_rows
from app.schema import FETCH_FAILED, MALFORMED_JSON, MATCH, UNVERIFIABLE, VerificationVerdict
from app.verifiers import ClaimVerifier

FIXTURES = Path(__file__).parent / "fixtures"

ARTICLE_HTML = """
<html><body><article>
<p>Acme Robotics announced today it has closed a $40 million Series B round
led by Northlight Ventures, with participation from three existing investors.
The company plans to use the funding to expand its warehouse automation
platform into new markets across North America and Europe over the next
eighteen months, according to a statement from the company's CEO.</p>
</article></body></html>
"""


class FakeClaimVerifier(ClaimVerifier):
    """Returns a canned verdict per call; records what it was called with."""

    def __init__(self, canned_verdict: VerificationVerdict | None = None):
        self.calls: list[tuple[dict, str]] = []
        self.canned_verdict = canned_verdict or VerificationVerdict(
            verdict=MATCH,
            confidence_note="page text confirms the claimed funding series",
            checked_fields=["funding_series"],
            input_tokens=50,
            output_tokens=20,
        )

    def verify(self, claim: dict[str, str], page_text: str) -> VerificationVerdict:
        self.calls.append((claim, page_text))
        return self.canned_verdict


def _sample_rows() -> list[dict[str, str]]:
    csv_text = (FIXTURES / "sample_claygent_export.csv").read_text(encoding="utf-8")
    return parse_csv_rows(csv_text)


def _malformed_rows() -> list[dict[str, str]]:
    csv_text = (FIXTURES / "malformed_json_row.csv").read_text(encoding="utf-8")
    return parse_csv_rows(csv_text)


def test_run_batch_all_match(requests_mock):
    rows = _sample_rows()
    for row in rows:
        requests_mock.get(row["source_url"], text=ARTICLE_HTML, status_code=200)

    verifier = FakeClaimVerifier()
    batch = run_batch(rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=verifier)

    assert len(batch.results) == 3
    assert all(r.verdict == MATCH for r in batch.results)
    assert len(verifier.calls) == 3
    assert batch.total_input_tokens == 150
    assert batch.total_output_tokens == 60


def test_run_batch_malformed_json_never_reaches_fetcher_or_verifier(requests_mock):
    # Deliberately no requests_mock registration for the malformed row's URL:
    # if the engine tried to fetch it, requests_mock would raise, failing
    # the test - this proves malformed JSON short-circuits before fetching.
    rows = _malformed_rows()
    verifier = FakeClaimVerifier()
    batch = run_batch(rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=verifier)

    assert len(batch.results) == 1
    assert batch.results[0].verdict == MALFORMED_JSON
    assert len(verifier.calls) == 0


def test_run_batch_fetch_failed_skips_verifier(requests_mock):
    rows = _sample_rows()[:1]
    requests_mock.get(rows[0]["source_url"], status_code=404)

    verifier = FakeClaimVerifier()
    batch = run_batch(rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=verifier)

    assert batch.results[0].verdict == FETCH_FAILED
    assert "404" in batch.results[0].failure_detail
    assert len(verifier.calls) == 0


def test_run_batch_claim_fields_filters_what_verifier_sees(requests_mock):
    rows = _sample_rows()[:1]
    requests_mock.get(rows[0]["source_url"], text=ARTICLE_HTML, status_code=200)

    verifier = FakeClaimVerifier()
    run_batch(
        rows,
        claim_column="claygent_extraction",
        source_url_column="source_url",
        verifier=verifier,
        claim_fields=["funding_series"],
    )

    claim_seen, _ = verifier.calls[0]
    assert claim_seen == {"funding_series": "Series B"}


def test_run_batch_empty_claim_after_filtering_is_unverifiable(requests_mock):
    rows = _sample_rows()[:1]
    verifier = FakeClaimVerifier()
    batch = run_batch(
        rows,
        claim_column="claygent_extraction",
        source_url_column="source_url",
        verifier=verifier,
        claim_fields=["field_not_present_in_claim"],
    )

    assert batch.results[0].verdict == UNVERIFIABLE
    assert len(verifier.calls) == 0


def test_verdict_counts(requests_mock):
    rows = _sample_rows()
    for row in rows:
        requests_mock.get(row["source_url"], text=ARTICLE_HTML, status_code=200)

    batch = run_batch(
        rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=FakeClaimVerifier()
    )
    assert batch.verdict_counts() == {MATCH: 3}


def test_batch_estimated_cost_known_model(requests_mock):
    rows = _sample_rows()[:1]
    requests_mock.get(rows[0]["source_url"], text=ARTICLE_HTML, status_code=200)
    batch = run_batch(
        rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=FakeClaimVerifier()
    )
    cost = batch.estimated_cost("claude-sonnet-5")
    expected = 50 * 3.00 / 1_000_000 + 20 * 15.00 / 1_000_000
    assert cost == expected


def test_batch_estimated_cost_unknown_model_returns_none(requests_mock):
    rows = _sample_rows()[:1]
    requests_mock.get(rows[0]["source_url"], text=ARTICLE_HTML, status_code=200)
    batch = run_batch(
        rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=FakeClaimVerifier()
    )
    assert batch.estimated_cost("some-unknown-model") is None


def test_estimate_batch_cost_scales_with_row_count():
    rows = [{"a": "x" * 400, "b": "y"}]
    single = estimate_batch_cost(rows, "claude-sonnet-5")
    double = estimate_batch_cost(rows * 2, "claude-sonnet-5")
    assert double == single * 2


def test_estimate_batch_cost_unknown_model_returns_none():
    assert estimate_batch_cost([{"a": "b"}], "unknown-model") is None


def test_write_csv_output_includes_verification_columns(requests_mock):
    rows = _sample_rows()
    for row in rows:
        requests_mock.get(row["source_url"], text=ARTICLE_HTML, status_code=200)

    batch = run_batch(
        rows, claim_column="claygent_extraction", source_url_column="source_url", verifier=FakeClaimVerifier()
    )
    csv_text = write_csv_output(rows, batch)

    assert "verification_verdict" in csv_text
    assert "verification_confidence_note" in csv_text
    assert "Acme Robotics" in csv_text
    assert csv_text.count(MATCH) == 3
