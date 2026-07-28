import pytest
from foa_pipeline.config import get_config
from foa_pipeline.ontology_store import OntologyStore
from foa_pipeline.tagger_pipeline import TaggerPipeline

def test_full_pipeline_tagging():
    """
    Test the full tagging pipeline including L1 and L2 taggers.
    """
    config = get_config()
    
    # Initialize store and tagger
    store = OntologyStore(config.app_db_path)
    store.load_all_csvs()
    
    tagger = TaggerPipeline(config, store)
    tagger.initialize()
    
    # Synthetic FOA record for testing
    foa_record = {
        "foa_id": "test-1234",
        "title": "Advanced Quantum Computing for Defense",
        "program_description": (
            "This funding opportunity from the Department of Defense aims to support "
            "foundational research in quantum computing algorithms. Projects should also "
            "explore cybersecurity implications and potential improvements in renewable energy "
            "efficiency for military bases."
        )
    }
    
    tags = tagger.tag_record(foa_record)
    
    # Verify that tags were generated
    assert len(tags) > 0, "Pipeline should generate at least one tag"
    
    # Verify the structure of the generated tags
    for tag in tags:
        assert "concept_id" in tag or "ontology_concept_id" in tag
        assert "label" in tag
        assert "category" in tag
        assert "source_layer" in tag
        assert "confidence" in tag
        assert "context_snippet" in tag
        
    # Check if specific L1/L2 expected tags are present (Defense, Energy)
    labels = [t["label"].lower() for t in tags]
    assert any("defense" in l for l in labels), "Expected 'Defense' tag missing"
    assert any("energy" in l for l in labels), "Expected 'Energy' tag missing"
