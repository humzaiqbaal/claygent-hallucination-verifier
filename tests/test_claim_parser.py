"""
Unit tests for app.claim_parser. No network, no LLM, no JSON parsing - the
claim arrives as N already-extracted columns (a real Clay export never
carries data in a raw JSON blob column), so extraction is just filtering out
blanks and flagging the row as empty if nothing is left.
"""

from pathlib import Path

from app.claim_parser import extract_claim
from app.csv_mapper import map_rows, parse_csv_rows

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_claim_keeps_non_blank_fields():
    result = extract_claim({"company_name": "Acme", "funding_series": "Series B"})
    assert result.is_empty is False
    assert result.fields == {"company_name": "Acme", "funding_series": "Series B"}


def test_extract_claim_drops_blank_fields():
    result = extract_claim({"company_name": "Acme", "funding_series": ""})
    assert result.is_empty is False
    assert result.fields == {"company_name": "Acme"}


def test_extract_claim_drops_whitespace_only_fields():
    result = extract_claim({"company_name": "  \n  "})
    assert result.is_empty is True


def test_extract_claim_all_blank_is_empty():
    # The real-world signature of a failed Claygent extraction: nothing was
    # there to select in Clay's side panel, so every configured claim
    # column comes back blank for this row.
    result = extract_claim({"funding_series": "", "is_confirmed": ""})
    assert result.is_empty is True
    assert result.fields == {}


def test_extract_claim_empty_dict_is_empty():
    result = extract_claim({})
    assert result.is_empty is True


def test_extract_claim_against_no_claim_data_fixture():
    csv_text = (FIXTURES / "no_claim_data_row.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_columns=["funding_series", "is_confirmed"], source_url_column="source_url")

    result = extract_claim(mapped[0].claim_fields)
    assert result.is_empty is True


def test_extract_claim_against_sample_fixture_rows():
    csv_text = (FIXTURES / "sample_claygent_export.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_columns=["funding_series", "is_confirmed"], source_url_column="source_url")

    for row in mapped:
        result = extract_claim(row.claim_fields)
        assert result.is_empty is False
        assert "funding_series" in result.fields
