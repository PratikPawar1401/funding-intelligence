# FOA Semantic Matching (Phase 4)

This document describes how the semantic tagging outputs and the FAISS vector index are combined to match researcher abstracts to Funding Opportunity Announcements (FOAs).

> **Implemented in `src/foa_pipeline/grant_matcher.py`.** Run it with:
>
> ```bash
> PYTHONPATH=src python -m foa_pipeline.cli search --profile "computational social science, housing policy" --k 10
> ```
>
> Requires the FAISS index to exist — run `tag-all` first to build it.

## The Hybrid Relevance Score Formula

To ensure researchers see the most relevant grants, matching should not rely solely on dense vector search (which can hallucinate abstract conceptual links) nor solely on explicit ontology tags (which can miss nuanced language). 

We recommend using a **Hybrid Relevance Score** combining both approaches:

```
Hybrid_Score = (0.7 * Cosine_Similarity) + (0.3 * Tag_Overlap_Ratio)
```

### 1. Cosine Similarity (Dense Vectors)
Query the `data/embeddings/foa_index.faiss` index with the researcher's embedded abstract. This yields a raw cosine similarity score for the FOA document.

### 2. Tag Overlap Ratio (Explicit Ontology)
Extract ontology tags from the researcher's profile/abstract using the `foa_pipeline` tagging engine (the same L1+L2+L3 cascade used on FOAs), then compute the overlap against the FOA's stored tags.

The implementation uses the **containment ratio** — `|profile ∩ foa| / |profile|` — rather than full Jaccard. A broad FOA that carries many extra tags should not be penalised for covering everything the researcher actually asked for; Jaccard would divide by the union and punish exactly the well-matched, wide-scope opportunities a research officer wants to see.

### Implementation Example
If a researcher is looking for "Machine Learning for Veterans Health":
- The FAISS index captures the general theme (Cosine_Sim = 0.82)
- The FOA is explicitly tagged with `Populations: Veterans` and `Methods: Machine Learning`. If the researcher's profile has 4 tags and matches these 2, `Tag_Overlap_Ratio = 2/4 = 0.5`.

`Hybrid_Score = (0.7 * 0.82) + (0.3 * 0.5) = 0.574 + 0.15 = 0.724`

Recommendations to ISSR Research Development Officers are sorted by this `Hybrid_Score`.

## Implementation Notes

- **Candidate pool.** FAISS is queried for `3 × k` candidates before re-ranking. Retrieving only `k` by cosine would make the tag-overlap term decorative — an FOA ranked `k+1` by vector similarity could never be promoted into the final list no matter how well its tags matched.
- **Explainability.** Every result carries `cosine_score`, `tag_overlap_ratio`, `matched_tags` (human-readable labels), and the combined `hybrid_score`, so a ranking can be justified to a user rather than presented as an opaque number — consistent with the tag-provenance design in `ONTOLOGY.md` §5.
- **Graceful degradation.** If the tagger is unavailable or fails to tag the profile, matching falls back to cosine-only ranking (`tag_overlap_ratio = 0.0`) instead of erroring, per the fallback strategy in the blueprint's risk register.
- **Weights** are module constants (`COSINE_WEIGHT`, `TAG_WEIGHT`) and overridable per call, so the 0.7/0.3 split can be re-tuned once real user-relevance feedback exists. The current split is the blueprint's proposed default and has **not** been empirically validated against human relevance judgements — doing so is future work.
