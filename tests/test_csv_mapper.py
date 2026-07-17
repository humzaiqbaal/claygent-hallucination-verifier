"""
Unit tests for app.csv_mapper: pure CSV parsing and column mapping, no
network, no LLM, no fixed header names assumed.
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


def test_map_rows_pulls_claim_and_source_by_configured_column_name():
    rows = [{"claygent_extraction": '{"a": "b"}', "Link": "https://example.com", "other": "x"}]
    mapped = map_rows(rows, claim_column="claygent_extraction", source_url_column="Link")

    assert len(mapped) == 1
    assert mapped[0].row_index == 0
    assert mapped[0].claim_raw == '{"a": "b"}'
    assert mapped[0].source_url == "https://example.com"
    assert mapped[0].fields == rows[0]


def test_map_rows_works_with_arbitrary_column_names():
    # Manually-selected Claygent columns won't be named like OneWell's -
    # the mapping must work for any header the user points it at.
    rows = [{"ai_claim_blob": '{"x": 1}', "news_url": "https://example.com/a"}]
    mapped = map_rows(rows, claim_column="ai_claim_blob", source_url_column="news_url")
    assert mapped[0].claim_raw == '{"x": 1}'
    assert mapped[0].source_url == "https://example.com/a"


def test_map_rows_raises_on_missing_column():
    rows = [{"claygent_extraction": "{}", "Link": "https://example.com"}]
    try:
        map_rows(rows, claim_column="does_not_exist", source_url_column="Link")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "does_not_exist" in str(e)


def test_map_rows_handles_empty_row_list():
    assert map_rows([], claim_column="claim", source_url_column="url") == []


def test_map_rows_against_sample_fixture():
    csv_text = (FIXTURES / "sample_claygent_export.csv").read_text(encoding="utf-8")
    rows = parse_csv_rows(csv_text)
    mapped = map_rows(rows, claim_column="claygent_extraction", source_url_column="source_url")

    assert len(mapped) == 3
    assert mapped[0].source_url == "https://example.com/news/acme-robotics-series-b"
    assert '"funding_series": "Series B"' in mapped[0].claim_raw
