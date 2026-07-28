# FOA Semantic Matching (Phase 4)

This document outlines how downstream integrators should use the semantic tagging outputs and the FAISS vector index to match researcher abstracts to Funding Opportunity Announcements (FOAs).

## The Hybrid Relevance Score Formula

To ensure researchers see the most relevant grants, matching should not rely solely on dense vector search (which can hallucinate abstract conceptual links) nor solely on explicit ontology tags (which can miss nuanced language). 

We recommend using a **Hybrid Relevance Score** combining both approaches:

```
Hybrid_Score = (0.7 * Cosine_Similarity) + (0.3 * Tag_Overlap_Ratio)
```

### 1. Cosine Similarity (Dense Vectors)
Query the `data/embeddings/foa_index.faiss` index with the researcher's embedded abstract. This yields a raw cosine similarity score for the FOA document.

### 2. Tag Overlap Ratio (Explicit Ontology)
Extract ontology tags from the researcher's profile/abstract using the `foa_pipeline` tagging engine. Compute the Jaccard similarity (or subset ratio) between the researcher's tags and the FOA's tags (found in `foa_records.tags` or `foa_normalised.csv`).

### Implementation Example
If a researcher is looking for "Machine Learning for Veterans Health":
- The FAISS index captures the general theme (Cosine_Sim = 0.82)
- The FOA is explicitly tagged with `Populations: Veterans` and `Methods: Machine Learning`. If the researcher's profile has 4 tags and matches these 2, `Tag_Overlap_Ratio = 2/4 = 0.5`.

`Hybrid_Score = (0.7 * 0.82) + (0.3 * 0.5) = 0.574 + 0.15 = 0.724`

Sort your final recommendations to the ISSR Research Development Officers based on this `Hybrid_Score`.
