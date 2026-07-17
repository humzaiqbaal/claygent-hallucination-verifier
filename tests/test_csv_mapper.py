"""
Unit tests for app.csv_mapper: pure CSV parsing and column mapping, no
network, no LLM, no fixed header names assumed. Claim data is expected as N
separate pre-extracted columns, not one JSON blob column - a real Clay CSV
export never has data in the raw Claygent-response column (see
Memory/reference-clay-claygent-json-field-extraction.md).
"""

from pathlib import Path

from app.csv_mapper import map_rows, parse_csv_rows

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_csv_rows_preserves_all_columns_including_empty():
    csv_text = "name,company,note\nJane,Acme,\n"
    rows = parse_csv_rows(csv_text)
    assert rows == [{"name": "Jane", "company": "Acme", "note": ""}]


def test_parse_csv_rows_is_schema_agnostic():
    csv_text = "full_name,linkedin_bio\nJane,Ran growth at 3 startups\n"
    rows = parse_csv_rows(csv_text)
    assert rows == [{"full_name": "Jane", "linkedin_bio": "Ran growth at 3 startups"}]


def test_map_rows_pulls_claim_columns_and_source_by_configured_names():
    rows = [{"funding_series": "Series B", "is_confirmed": "CONFIRMED", "Link": "https://example.com", "other": "x"}]
    mapped = map_rows(rows, claim_columns=["funding_series", "is_confirmed"], source_url_column="Link")

    assert len(mapped) == 1
    assert mapped[0].row_index == 0
    assert mapped[0].claim_fields == {"funding_series": "Series B", "is_confirmed": "CONFIRMED"}
    assert mapped[0].source_url == "https://example.com"
    assert mapped[0].fields == rows[0]


def test_map_rows_works_with_arbitrary_column_names_and_count():
    # Manually-selected Claygent columns can be any name, any count.
    rows = [{"deal_size": "$40M", "signal_type": "funding", "news_url": "https://example.com/a"}]
    mapped = map_rows(rows, claim_columns=["deal_size", "signal_type"], source_url_column="news_url")
    assert mapped[0].claim_fields == {"deal_size": "$40M", "signal_type": "funding"}


def test_map_rows_raises_on_missing_claim_column():
    rows = [{"funding_series": "Series B", "Link": "https://example.com"}]
    try:
        map_rows(rows, claim_columns=["does_not_exist"], source_url_column="Link")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "does_not_exist" in str(e)


def test_map_rows_raises_on_missing_source_column():
    rows = [{"funding_series": "Series B"}]
    try:
        map_rows(rows, claim_columns=["funding_series"], source_url_column="missing_col")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "missing_col" in str(e)


def test_map_rows_handles_empty_row_list():
    assert map_rows([], claim_columns=["claim"], source_url_column="url") == []


def test_map_rows_against_sample_fixture():
    csv_text = (FIXTURES / "sample_claygent_export.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_columns=["funding_series", "is_confirmed"], source_url_column="source_url")

    assert len(mapped) == 3
    assert mapped[0].source_url == "https://example.com/news/acme-robotics-series-b"
    assert mapped[0].claim_fields == {"funding_series": "Series B", "is_confirmed": "CONFIRMED"}
    # The raw Claygent-response column is present in the export but blank -
    # mirroring the real-world export behavior this tool is built around.
    assert rows[0]["claygent_extraction"] == ""
