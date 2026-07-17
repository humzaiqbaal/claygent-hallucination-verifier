"""
Unit tests for app.claim_parser. No network, no LLM - pure JSON parsing plus
the malformed-input handling this tool exists to catch.
"""

from pathlib import Path

from app.claim_parser import parse_claim
from app.csv_mapper import map_rows, parse_csv_rows

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_claim_valid_json_object():
    result = parse_claim('{"company_name": "Acme", "funding_series": "Series B"}')
    assert result.parse_error is False
    assert result.fields == {"company_name": "Acme", "funding_series": "Series B"}


def test_parse_claim_narrative_response_is_malformed():
    # The documented OneWell failure mode: Claygent ignores "JSON only" and
    # returns a sentence instead.
    result = parse_claim("Sorry, I could not determine the funding series from the given data.")
    assert result.parse_error is True
    assert result.fields == {}
    assert "Sorry" in result.raw_text


def test_parse_claim_empty_string_is_malformed():
    result = parse_claim("")
    assert result.parse_error is True


def test_parse_claim_whitespace_only_is_malformed():
    result = parse_claim("   \n  ")
    assert result.parse_error is True


def test_parse_claim_truncated_json_is_malformed():
    result = parse_claim('{"company_name": "Acme", "funding_series":')
    assert result.parse_error is True


def test_parse_claim_json_array_is_malformed():
    # Claygent's contract is "one JSON object" - a bare array doesn't satisfy
    # that even though it's technically valid JSON.
    result = parse_claim('["Acme", "Series B"]')
    assert result.parse_error is True


def test_parse_claim_drops_non_string_fields():
    result = parse_claim('{"company_name": "Acme", "valuation": 500000000, "confirmed": true}')
    assert result.parse_error is False
    assert result.fields == {"company_name": "Acme"}


def test_parse_claim_against_malformed_fixture():
    csv_text = (FIXTURES / "malformed_json_row.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_column="claygent_extraction", source_url_column="source_url")

    result = parse_claim(mapped[0].claim_raw)
    assert result.parse_error is True


def test_parse_claim_against_sample_fixture_rows():
    csv_text = (FIXTURES / "sample_claygent_export.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_column="claygent_extraction", source_url_column="source_url")

    for row in mapped:
        result = parse_claim(row.claim_raw)
        assert result.parse_error is False
        assert "company_name" in result.fields
