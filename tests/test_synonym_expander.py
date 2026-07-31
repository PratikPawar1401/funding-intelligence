"""Tests for the synonym expander module."""

from pathlib import Path

import pytest

from foa_pipeline.ontology_store import OntologyStore
from foa_pipeline.synonym_expander import (
    ABBREVIATIONS,
    expand_synonyms_for_store,
)


@pytest.fixture
def ontology_store(tmp_path):
    """Create a small ontology store with known concepts for testing."""
    csv_path = tmp_path / "test_concepts.csv"
    csv_path.write_text(
        "concept_id,label,category,parent_id,description\n"
        "test_ai,Artificial Intelligence,method,,Research using AI techniques\n"
        "test_ml,Machine Learning,method,test_ai,Subset of AI for learning from data\n"
        "test_climate,Climate Action,research_domain,,Climate change research\n"
        "test_poverty,No Poverty,research_domain,,End poverty in all forms\n"
        "test_health,Good Health and Well-being,research_domain,,Promote well-being\n"
    )
    store = OntologyStore(tmp_path / "test_ontology.db")
    store.load_from_csv(csv_path, "test")
    return store


class TestExpandSynonyms:
    """Test the synonym expansion pipeline."""

    def test_expansion_returns_stats(self, ontology_store):
        """expand_synonyms_for_store should return per-concept counts."""
        stats = expand_synonyms_for_store(ontology_store)
        assert isinstance(stats, dict)
        assert "test_ai" in stats
        assert "test_climate" in stats

    def test_synonyms_are_added_to_store(self, ontology_store):
        """After expansion, concepts should have synonyms in the DB."""
        expand_synonyms_for_store(ontology_store)
        concept = ontology_store.get_concept_by_id("test_climate")
        assert concept is not None
        assert len(concept.synonyms) > 0

    def test_abbreviation_matching(self, ontology_store):
        """Abbreviations from the ABBREVIATIONS dict should be added.
        
        Note: The expander filters synonyms <= 2 chars, so 'ai' and 'ml'
        are filtered out. We test with 'climate action' which maps to
        longer abbreviations like 'climate change', 'global warming'.
        """
        expand_synonyms_for_store(ontology_store)
        climate = ontology_store.get_concept_by_id("test_climate")
        assert climate is not None
        synonyms_lower = [s.lower() for s in climate.synonyms]
        # "climate action" maps to ["climate change", "global warming", "climate adaptation"]
        assert "climate change" in synonyms_lower or "global warming" in synonyms_lower

    def test_original_label_excluded(self, ontology_store):
        """The concept's own label should not appear as a synonym."""
        expand_synonyms_for_store(ontology_store)
        ai_concept = ontology_store.get_concept_by_id("test_ai")
        assert ai_concept is not None
        synonyms_lower = [s.lower() for s in ai_concept.synonyms]
        assert "artificial intelligence" not in synonyms_lower

    def test_wordnet_produces_synonyms(self, ontology_store):
        """WordNet should produce at least some synonyms for 'climate'."""
        expand_synonyms_for_store(ontology_store)
        climate_concept = ontology_store.get_concept_by_id("test_climate")
        assert climate_concept is not None
        # WordNet should find something related to "climate" or "action"
        assert len(climate_concept.synonyms) > 0

    def test_synonym_count_method(self, ontology_store):
        """Store's synonym_count should increase after expansion."""
        before = ontology_store.synonym_count()
        expand_synonyms_for_store(ontology_store)
        after = ontology_store.synonym_count()
        assert after > before

    def test_short_synonyms_filtered(self, ontology_store):
        """Synonyms with 2 or fewer characters should be filtered out."""
        expand_synonyms_for_store(ontology_store)
        all_concepts = ontology_store.get_all_concepts()
        for concept in all_concepts:
            for syn in concept.synonyms:
                assert len(syn) > 2, f"Short synonym '{syn}' found for {concept.label}"


class TestAbbreviationsDictionary:
    """Test the ABBREVIATIONS constant."""

    def test_has_ai_abbreviation(self):
        assert "artificial intelligence" in ABBREVIATIONS
        assert "ai" in ABBREVIATIONS["artificial intelligence"]

    def test_has_ml_abbreviation(self):
        assert "machine learning" in ABBREVIATIONS
        assert "ml" in ABBREVIATIONS["machine learning"]

    def test_has_sdg_abbreviation(self):
        assert "sustainable development goals" in ABBREVIATIONS
        assert "sdg" in ABBREVIATIONS["sustainable development goals"]

    def test_has_population_abbreviations(self):
        """Key population terms should have expansions."""
        assert "rural communities" in ABBREVIATIONS
        assert "children and youth" in ABBREVIATIONS
        assert "older adults" in ABBREVIATIONS

    def test_all_abbreviations_are_lowercase(self):
        """All abbreviation values should be lowercase."""
        for key, values in ABBREVIATIONS.items():
            for v in values:
                assert v == v.lower(), f"Non-lowercase abbreviation: {v}"
