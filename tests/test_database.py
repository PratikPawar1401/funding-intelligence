"""Tests for the database module."""

from foa_pipeline.database import Database


def test_upsert_and_get(tmp_path, sample_foa):
    """Test inserting and retrieving a FOA record."""
    db = Database(tmp_path / "test.db")

    is_new = db.upsert_foa(sample_foa)
    assert is_new is True

    # Retrieve
    record = db.get_foa(sample_foa["foa_id"])
    assert record is not None
    assert record["title"] == sample_foa["title"]
    assert record["agency_code"] == "NSF"
    assert "47.075" in record["cfda_numbers"]
    assert "Universities" in record["eligibility"]

    # Update (same foa_id)
    sample_foa["title"] = "Updated Title"
    is_new = db.upsert_foa(sample_foa)
    assert is_new is False

    updated = db.get_foa(sample_foa["foa_id"])
    assert updated["title"] == "Updated Title"

    db.close()


def test_list_with_filters(tmp_path, sample_foa):
    """Test listing FOAs with filters."""
    db = Database(tmp_path / "test.db")
    db.upsert_foa(sample_foa)

    # List all
    records, total = db.list_foas()
    assert total == 1
    assert len(records) == 1

    # Filter by status
    records, total = db.list_foas(status="open")
    assert total == 1

    records, total = db.list_foas(status="closed")
    assert total == 0

    # Filter by agency
    records, total = db.list_foas(agency_code="NSF")
    assert total == 1

    records, total = db.list_foas(agency_code="NIH")
    assert total == 0

    db.close()


def test_fts_search(tmp_path, sample_foa):
    """Test full-text search."""
    db = Database(tmp_path / "test.db")
    db.upsert_foa(sample_foa)

    # Search by keyword in title
    records, total = db.search_fts("climate")
    assert total >= 1

    # Search by keyword in description
    records, total = db.search_fts("rural communities")
    assert total >= 1

    # No results
    records, total = db.search_fts("quantum computing")
    assert total == 0

    db.close()


def test_tag_operations(tmp_path, sample_foa):
    """Test saving and retrieving tags."""
    db = Database(tmp_path / "test.db")
    db.upsert_foa(sample_foa)

    tags = [
        {
            "concept_id": "sdg_13",
            "label": "Climate Action",
            "category": "research_domain",
            "source_layer": "layer_1_terminological",
            "confidence": 1.0,
            "context_snippet": "climate change impacts on rural communities",
        },
        {
            "concept_id": "pop_01",
            "label": "Rural Communities",
            "category": "population",
            "source_layer": "layer_1_terminological",
            "confidence": 1.0,
            "context_snippet": "rural communities",
        },
    ]

    count = db.save_tags(sample_foa["foa_id"], tags)
    assert count == 2

    # Retrieve tags
    retrieved = db.get_tags_for_foa(sample_foa["foa_id"])
    assert len(retrieved) == 2
    labels = {t["label"] for t in retrieved}
    assert "Climate Action" in labels
    assert "Rural Communities" in labels

    # Get FOAs by tag
    records, total = db.get_foas_by_tag("sdg_13")
    assert total == 1

    db.close()


def test_stats(tmp_path, sample_foa):
    """Test summary statistics."""
    db = Database(tmp_path / "test.db")
    db.upsert_foa(sample_foa)

    stats = db.get_stats()
    assert stats["total_foas"] == 1
    assert stats["open_foas"] == 1
    assert stats["total_tags"] == 0

    db.close()
