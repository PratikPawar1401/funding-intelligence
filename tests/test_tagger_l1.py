"""Tests for the Layer 1 spaCy PhraseMatcher tagger."""

from pathlib import Path

import pytest

from foa_pipeline.evidence_logger import TagEvidence
from foa_pipeline.ontology_store import OntologyStore
from foa_pipeline.synonym_expander import expand_synonyms_for_store
from foa_pipeline.tagger_l1_spacy import L1Tagger


@pytest.fixture(scope="module")
def ontology_with_synonyms(tmp_path_factory):
    """Build a small ontology store with concepts and synonyms.
    
    Module-scoped because spaCy model loading is expensive.
    """
    tmp = tmp_path_factory.mktemp("ontology")
    csv_path = tmp / "test_concepts.csv"
    csv_path.write_text(
        "concept_id,label,category,parent_id,description\n"
        "sdg_13,Climate Action,research_domain,,Take urgent action to combat climate change\n"
        "sdg_03,Good Health and Well-being,research_domain,,Ensure healthy lives and promote well-being\n"
        "sdg_01,No Poverty,research_domain,,End poverty in all its forms everywhere\n"
        "great_02,Health,sponsor_theme,,Biomedical and public health research\n"
        "meth_ml,Machine Learning,method,,Subset of AI for learning from data\n"
        "pop_rural,Rural Communities,population,,Rural and non-metropolitan populations\n"
    )
    store = OntologyStore(tmp / "test.db")
    store.load_from_csv(csv_path, "test")
    expand_synonyms_for_store(store)
    return store


@pytest.fixture(scope="module")
def l1_tagger(ontology_with_synonyms):
    """Build an L1 tagger with the test ontology."""
    tagger = L1Tagger(spacy_model="en_core_web_lg")
    tagger.build_matcher(ontology_with_synonyms)
    return tagger


class TestL1TaggerBasic:
    """Basic Layer 1 tagger functionality."""

    def test_empty_text_returns_no_tags(self, l1_tagger):
        """Empty text should produce no evidence."""
        result = l1_tagger.tag_text("")
        assert result == []

    def test_none_text_returns_no_tags(self, l1_tagger):
        """None text should produce no evidence."""
        result = l1_tagger.tag_text(None)
        assert result == []

    def test_returns_tag_evidence_objects(self, l1_tagger):
        """Results should be TagEvidence instances."""
        result = l1_tagger.tag_text("This program supports climate action research.")
        assert all(isinstance(ev, TagEvidence) for ev in result)


class TestL1TaggerMatching:
    """Test that the tagger finds expected concepts in text."""

    def test_finds_exact_label_match(self, l1_tagger):
        """Exact concept label should be matched."""
        result = l1_tagger.tag_text(
            "This program funds climate action initiatives to combat global warming."
        )
        concept_ids = {ev.concept_id for ev in result}
        assert "sdg_13" in concept_ids

    def test_finds_health_label(self, l1_tagger):
        """Health-related concepts should match."""
        result = l1_tagger.tag_text(
            "Research on good health and well-being in underserved communities."
        )
        concept_ids = {ev.concept_id for ev in result}
        assert "sdg_03" in concept_ids or "great_02" in concept_ids

    def test_finds_machine_learning(self, l1_tagger):
        """Method concepts should match."""
        result = l1_tagger.tag_text(
            "We will apply machine learning techniques to analyse survey data."
        )
        concept_ids = {ev.concept_id for ev in result}
        assert "meth_ml" in concept_ids

    def test_finds_population_match(self, l1_tagger):
        """Population concepts should match."""
        result = l1_tagger.tag_text(
            "The study focuses on rural communities in the American South."
        )
        concept_ids = {ev.concept_id for ev in result}
        assert "pop_rural" in concept_ids

    def test_synonym_matching(self, l1_tagger):
        """Synonyms should trigger matches.
        
        Note: 'ML' (2 chars) is filtered by the synonym expander's >2 char rule.
        We use 'deep learning' which maps to machine learning via ABBREVIATIONS,
        or 'global warming' which maps to Climate Action.
        """
        result = l1_tagger.tag_text(
            "Our study applies global warming mitigation strategies "
            "to vulnerable coastal ecosystems."
        )
        concept_ids = {ev.concept_id for ev in result}
        # "global warming" is a synonym of Climate Action (sdg_13)
        assert "sdg_13" in concept_ids

    def test_no_false_positives_on_unrelated_text(self, l1_tagger):
        """Unrelated text should produce few or no matches."""
        result = l1_tagger.tag_text(
            "The quick brown fox jumps over the lazy dog."
        )
        # Should produce zero or very few matches
        assert len(result) <= 1


class TestL1TaggerProperties:
    """Test properties of L1 tag evidence."""

    def test_confidence_is_always_one(self, l1_tagger):
        """Layer 1 should always assign confidence 1.0."""
        result = l1_tagger.tag_text(
            "This project researches climate action and machine learning."
        )
        for ev in result:
            assert ev.confidence == 1.0

    def test_source_layer_is_terminological(self, l1_tagger):
        """Source layer should be 'layer_1_terminological'."""
        result = l1_tagger.tag_text("Research on climate action.")
        for ev in result:
            assert ev.source_layer == "layer_1_terminological"

    def test_context_snippet_populated(self, l1_tagger):
        """Context snippet should contain text around the match."""
        result = l1_tagger.tag_text(
            "This program supports climate action in developing countries."
        )
        for ev in result:
            assert len(ev.context_snippet) > 0

    def test_concept_id_populated(self, l1_tagger):
        """Each evidence should have a concept_id."""
        result = l1_tagger.tag_text("Machine learning for health.")
        for ev in result:
            assert ev.concept_id is not None
            assert len(ev.concept_id) > 0

    def test_category_is_valid(self, l1_tagger):
        """Category should be one of the valid ontology categories."""
        valid = {"research_domain", "method", "population", "sponsor_theme"}
        result = l1_tagger.tag_text(
            "Climate action and machine learning for rural communities."
        )
        for ev in result:
            assert ev.category in valid


class TestL1TaggerDeduplication:
    """Test that repeated mentions don't produce duplicate tags."""

    def test_deduplicates_repeated_mentions(self, l1_tagger):
        """Same concept mentioned multiple times should only appear once."""
        text = (
            "Climate action is critical. Climate action must be taken now. "
            "We need more climate action research."
        )
        result = l1_tagger.tag_text(text)
        concept_ids = [ev.concept_id for ev in result]
        # Each concept should appear at most once
        assert len(concept_ids) == len(set(concept_ids))


class TestL1TaggerToTagRecord:
    """Test conversion to the FOA JSON schema tag format."""

    def test_to_tag_record_format(self, l1_tagger):
        """to_tag_record should produce a dict matching the schema spec."""
        result = l1_tagger.tag_text("Research on climate action.")
        if result:
            tag_record = result[0].to_tag_record()
            assert "tag_id" in tag_record
            assert "label" in tag_record
            assert "category" in tag_record
            assert "source_layer" in tag_record
            assert "confidence" in tag_record
            assert "context_snippet" in tag_record
            assert "ontology_concept_id" in tag_record
            # tag_id format: "layer_1_terminological:<concept_id>"
            assert tag_record["tag_id"].startswith("layer_1_terminological:")
