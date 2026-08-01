"""Tests for the tagging pipeline orchestrator.

Uses a mock L2 tagger to avoid downloading the full sentence-transformers model
in unit tests. The L1 tagger uses the real spaCy model for accuracy.
"""

from unittest.mock import MagicMock

import pytest

from foa_pipeline.config import Config
from foa_pipeline.ontology.store import OntologyStore
from foa_pipeline.ontology.synonyms import expand_synonyms_for_store
from foa_pipeline.tagging.evidence import TagEvidence
from foa_pipeline.tagging.pipeline import TaggerPipeline


@pytest.fixture(scope="module")
def ontology_store(tmp_path_factory):
    """Build a test ontology with concepts and synonyms."""
    tmp = tmp_path_factory.mktemp("pipeline_ontology")
    csv_path = tmp / "test_concepts.csv"
    csv_path.write_text(
        "concept_id,label,category,parent_id,description\n"
        "sdg_13,Climate Action,research_domain,,Take urgent action to combat climate change\n"
        "sdg_03,Good Health and Well-being,research_domain,,"
        "Ensure healthy lives and promote well-being\n"
        "sdg_01,No Poverty,research_domain,,End poverty in all its forms everywhere\n"
        "great_02,Health,sponsor_theme,,Biomedical and public health research\n"
        "meth_ml,Machine Learning,method,,Subset of AI for learning from data\n"
        "pop_rural,Rural Communities,population,,Rural and non-metropolitan populations\n"
        # Hierarchical: sdg_13_1 is a child of sdg_13
        "sdg_13_1,Climate Adaptation,research_domain,sdg_13,Adapting to climate change impacts\n"
    )
    store = OntologyStore(tmp / "test.db")
    store.load_from_csv(csv_path, "test")
    expand_synonyms_for_store(store)
    return store


@pytest.fixture(scope="module")
def pipeline_config(tmp_path_factory):
    """Minimal config for pipeline tests."""
    tmp = tmp_path_factory.mktemp("config")
    return Config(
        grants_gov_base_url="https://api.grants.gov/v1/api",
        grants_gov_search_endpoint="search2",
        grants_gov_fetch_endpoint="fetchOpportunity",
        grants_gov_page_size=25,
        grants_gov_max_pages=1,
        grants_gov_query="{}",
        nsf_rss_url="https://example.com/rss",
        nsf_scraper_rate_limit=10.0,
        nsf_scraper_max_concurrent=1,
        sqlite_db_path=tmp / "queue.db",
        app_db_path=tmp / "app.db",
        raw_output_dir=tmp / "raw",
        normalised_output_dir=tmp / "normalised",
        embeddings_cache_dir=tmp / "embeddings",
        ontology_dir=tmp / "ontology",
        evaluation_dir=tmp / "evaluation",
        spacy_model="en_core_web_lg",
        embedding_model="sentence-transformers/all-mpnet-base-v2",
        cosine_thresholds={"default": 0.75},
        enable_layer3_llm=False,
        ollama_base_url="http://localhost:11434",
        ollama_model="mistral:7b-instruct",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        log_level="DEBUG",
        user_agent="test-agent",
        schema_version="1.0",
    )


@pytest.fixture(scope="module")
def pipeline(pipeline_config, ontology_store):
    """Build a TaggerPipeline with L2 mocked out.

    We mock L2 so unit tests don't download the 420MB model.
    L1 uses the real spaCy model for accuracy.
    """
    p = TaggerPipeline(pipeline_config, ontology_store)

    # Mock L2 to return a fixed set of evidence
    mock_l2 = MagicMock()
    mock_l2.tag_text.return_value = [
        TagEvidence(
            concept_id="sdg_01",
            label="No Poverty",
            category="research_domain",
            source_layer="layer_2_embedding",
            confidence=0.82,
            context_snippet="economic disadvantage in rural areas",
            ontology_concept_id="sdg_01",
        ),
    ]
    mock_l2.build_embeddings = MagicMock()
    p.l2 = mock_l2

    # Initialize L1 (real)
    p.l1.build_matcher(ontology_store)
    p.is_initialized = True
    return p


class TestTaggerPipelineIntegration:
    """Integration tests for the full tagging pipeline."""

    def test_tags_sample_foa(self, pipeline, sample_foa):
        """Pipeline should produce tags for a well-described FOA."""
        tags = pipeline.tag_record(sample_foa)
        assert isinstance(tags, list)
        assert len(tags) > 0

    def test_returns_dicts(self, pipeline, sample_foa):
        """Pipeline output should be list of dicts (not TagEvidence)."""
        tags = pipeline.tag_record(sample_foa)
        for tag in tags:
            assert isinstance(tag, dict)

    def test_tag_schema_format(self, pipeline, sample_foa):
        """Each tag dict should have required keys matching the JSON schema."""
        tags = pipeline.tag_record(sample_foa)
        required_keys = {
            "tag_id", "label", "category", "source_layer",
            "confidence", "context_snippet", "ontology_concept_id"
        }
        for tag in tags:
            for key in required_keys:
                assert key in tag, f"Missing key: {key}"

    def test_l1_tags_have_full_confidence(self, pipeline, sample_foa):
        """L1 terminological tags should have confidence 1.0."""
        tags = pipeline.tag_record(sample_foa)
        l1_tags = [t for t in tags if t["source_layer"] == "layer_1_terminological"]
        for tag in l1_tags:
            assert tag["confidence"] == 1.0

    def test_l2_tags_have_cosine_confidence(self, pipeline, sample_foa):
        """L2 embedding tags should have confidence < 1.0."""
        tags = pipeline.tag_record(sample_foa)
        l2_tags = [t for t in tags if t["source_layer"] == "layer_2_embedding"]
        for tag in l2_tags:
            assert 0 < tag["confidence"] < 1.0

    def test_category_values_valid(self, pipeline, sample_foa):
        """All tags should have valid category values."""
        valid_categories = {"research_domain", "method", "population", "sponsor_theme"}
        tags = pipeline.tag_record(sample_foa)
        for tag in tags:
            assert tag["category"] in valid_categories

    def test_empty_foa_produces_no_tags(self, pipeline):
        """FOA with no text fields should produce no tags."""
        empty_foa = {
            "foa_id": "empty-test",
            "title": "",
            "program_description": "",
            "eligibility_description": "",
        }
        tags = pipeline.tag_record(empty_foa)
        assert tags == []


class TestTaggerPipelineHierarchy:
    """Test hierarchical propagation in the pipeline."""

    def test_child_tag_propagates_to_parent(self, pipeline):
        """If a child SDG target is tagged, the parent goal should also be tagged."""
        foa_with_child = {
            "foa_id": "hierarchy-test",
            "title": "Climate Adaptation Research",
            "program_description": (
                "This research focuses on climate adaptation strategies "
                "in coastal communities threatened by rising sea levels."
            ),
            "eligibility_description": "",
        }
        tags = pipeline.tag_record(foa_with_child)
        concept_ids = {t["ontology_concept_id"] for t in tags}

        # If sdg_13_1 (Climate Adaptation) is tagged, sdg_13 (Climate Action) should propagate
        if "sdg_13_1" in concept_ids:
            assert "sdg_13" in concept_ids, "Parent SDG not propagated from child"


class TestTaggerPipelineMerging:
    """Test L1/L2 merge logic."""

    def test_l1_takes_priority(self, pipeline):
        """If L1 and L2 both find the same concept, L1 should take priority."""
        # Create a FOA that will match both L1 and the mocked L2
        foa = {
            "foa_id": "merge-test",
            "title": "No Poverty Research Program",
            "program_description": (
                "This program addresses no poverty through "
                "community development and economic growth."
            ),
            "eligibility_description": "",
        }
        tags = pipeline.tag_record(foa)
        # Check that sdg_01 (No Poverty) appears — it could come from L1 (exact) or L2 (mock)
        poverty_tags = [t for t in tags if t["ontology_concept_id"] == "sdg_01"]
        if poverty_tags:
            # L1 should take priority with confidence 1.0
            assert poverty_tags[0]["source_layer"] == "layer_1_terminological"
            assert poverty_tags[0]["confidence"] == 1.0
