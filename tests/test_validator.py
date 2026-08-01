"""Tests for the validator module."""

from foa_pipeline.normalisation.validator import validate_batch, validate_record


def test_valid_record(sample_foa):
    is_valid, errors = validate_record(sample_foa)
    assert is_valid, f"Validation errors: {errors}"
    assert errors == []


def test_missing_required_field():
    record = {"schema_version": "1.0", "source": "grants_gov"}
    is_valid, errors = validate_record(record)
    assert not is_valid
    assert len(errors) > 0


def test_invalid_status(sample_foa):
    sample_foa["status"] = "invalid_status"
    is_valid, errors = validate_record(sample_foa)
    assert not is_valid


def test_empty_title(sample_foa):
    sample_foa["title"] = ""
    is_valid, errors = validate_record(sample_foa)
    assert not is_valid


def test_batch_validation(sample_foa):
    good = sample_foa.copy()
    bad = {"schema_version": "1.0"}  # Missing required fields

    results = validate_batch([good, bad])
    assert results["total"] == 2
    assert results["valid"] == 1
    assert results["invalid"] == 1
    assert len(results["errors"]) == 1
