import sys
from foa_pipeline.config import get_config
from foa_pipeline.ontology_store import OntologyStore
from foa_pipeline.tagger_l2_embedding import L2Tagger
from foa_pipeline.tagger_l2_embedding import cosine_similarity

config = get_config()
store = OntologyStore(config.app_db_path)
tagger = L2Tagger(model_name=config.embedding_model, cache_dir=config.embeddings_cache_dir, thresholds=config.cosine_thresholds)
tagger.build_embeddings(store)

text = "This funding opportunity focuses on advanced energy storage and cybersecurity research for naval applications. It strongly encourages HBCU and MSI participation."
chunks = tagger.chunk_text(text)
chunk_embs = tagger.model.encode(chunks, convert_to_numpy=True)
for i, chunk_emb in enumerate(chunk_embs):
    print(f"Chunk {i}: {chunks[i]}")
    scores = []
    for cid, cemb in tagger.concept_embeddings.items():
        sim = cosine_similarity(chunk_emb, cemb)
        scores.append((cid, sim))
    scores.sort(key=lambda x: x[1], reverse=True)
    for cid, sim in scores[:5]:
        print(f"  - {cid}: {sim:.3f}")
