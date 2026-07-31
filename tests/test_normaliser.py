"""Tests for the normaliser module."""

import pytest

from foa_pipeline.normaliser import (
    _extract_cfda,
    _extract_eligibility_types,
    _map_funding_instrument,
    _safe_int,
    infer_status,
    normalise_date,
    normalise_record,
    normalise_text,
    parse_award_amount,
)


class TestNormaliseDate:
    def test_iso_format(self):
        assert normalise_date("2025-06-15") == "2025-06-15"

    def test_us_format(self):
        assert normalise_date("06/15/2025") == "2025-06-15"

    def test_long_month(self):
        assert normalise_date("June 15, 2025") == "2025-06-15"

    def test_short_month(self):
        assert normalise_date("Jun 15, 2025") == "2025-06-15"

    def test_none(self):
        assert normalise_date(None) is None

    def test_empty(self):
        assert normalise_date("") is None

    def test_epoch_ms(self):
        # 2025-01-01 00:00:00 UTC in ms
        result = normalise_date("1735689600000")
        assert result is not None

    def test_garbage(self):
        assert normalise_date("not-a-date") is None


class TestNormaliseText:
    def test_html_entities(self):
        assert normalise_text("R&amp;D &amp; Innovation") == "R&D & Innovation"

    def test_whitespace(self):
        assert normalise_text("  too   many   spaces  ") == "too many spaces"

    def test_none(self):
        assert normalise_text(None) is None

    def test_empty(self):
        assert normalise_text("") is None

    def test_newlines(self):
        assert normalise_text("line1\n\nline2\t\ttab") == "line1 line2 tab"


class TestParseAwardAmount:
    def test_dollar_with_commas(self):
        assert parse_award_amount("$1,000,000") == 1000000.0

    def test_plain_number(self):
        assert parse_award_amount("500000") == 500000.0

    def test_with_decimals(self):
        assert parse_award_amount("$50,000.00") == 50000.0

    def test_none(self):
        assert parse_award_amount(None) is None

    def test_empty_string(self):
        assert parse_award_amount("") is None

    def test_non_numeric(self):
        assert parse_award_amount("varies") is None


class TestInferStatus:
    def test_open(self):
        assert infer_status("2020-01-01", "2099-12-31") == "open"

    def test_closed(self):
        assert infer_status("2020-01-01", "2020-06-01") == "closed"

    def test_forecasted(self):
        assert infer_status("2099-01-01", "2099-12-31") == "forecasted"

    def test_no_close_date(self):
        assert infer_status("2020-01-01", None) == "open"


class TestNormaliseRecord:
    def test_grants_gov(self, sample_raw_grants_gov):
        result = normalise_record(sample_raw_grants_gov, "grants_gov")

        assert result["schema_version"] == "1.0"
        assert result["source"] == "grants_gov"
        assert result["source_id"] == "789012"
        assert result["title"] is not None
        assert result["agency_code"] == "HHS"
        assert result["posted_date"] == "2025-06-15"
        assert result["close_date"] == "2025-09-30"
        assert result["award_floor"] == 50000.0
        assert result["award_ceiling"] == 500000.0
        assert result["foa_id"] is not None
        assert result["tags"] == []

    def test_unknown_source(self):
        with pytest.raises(ValueError, match="Unknown source"):
            normalise_record({}, "unknown_source")

    def test_pdf_upload(self):
        raw = {
            "source_path": "/tmp/test.pdf",
            "title": "PDF FOA",
            "posted_date": "2025-01-01",
            "close_date": "2025-12-31",
            "funding_instrument": "grant",
        }
        result = normalise_record(raw, "pdf_upload")
        assert result["source"] == "pdf_upload"
        assert result["title"] == "PDF FOA"
        assert result["source_id"] == "/tmp/test.pdf"
        assert result["funding_instrument"] == "grant"


class TestHelperFunctions:
    def test_extract_cfda_legacy_string(self):
        details = {"cfdaNumber": "93.103; 47.075 ; "}
        assert _extract_cfda(details) == ["93.103", "47.075"]

    def test_extract_cfda_legacy_list(self):
        details = {"cfdaNumber": ["93.103", "47.075"]}
        assert _extract_cfda(details) == ["93.103", "47.075"]

    def test_extract_cfda_empty(self):
        assert _extract_cfda({}) == []

    def test_extract_eligibility_types_legacy_string(self):
        synopsis = {"eligibleApplicants": "Universities; Non-profits ; "}
        assert _extract_eligibility_types(synopsis) == ["Universities", "Non-profits"]

    def test_extract_eligibility_types_legacy_list(self):
        synopsis = {"eligibleApplicants": ["Universities", "", None]}
        assert _extract_eligibility_types(synopsis) == ["Universities"]

    def test_extract_eligibility_types_empty(self):
        assert _extract_eligibility_types({}) == []

    def test_map_funding_instrument(self):
        assert _map_funding_instrument("Grant") == "grant"
        assert _map_funding_instrument("g") == "grant"
        assert _map_funding_instrument("Cooperative Agreement") == "cooperative_agreement"
        assert _map_funding_instrument("ca") == "cooperative_agreement"
        assert _map_funding_instrument("Procurement Contract") == "procurement_contract"
        assert _map_funding_instrument("pc") == "procurement_contract"
        assert _map_funding_instrument("Unknown") == "other"
        assert _map_funding_instrument(None) is None

    def test_safe_int(self):
        assert _safe_int("10") == 10
        assert _safe_int(10) == 10
        assert _safe_int(None) is None
        assert _safe_int("not-a-number") is None
        assert _safe_int({"dict": "value"}) is None
