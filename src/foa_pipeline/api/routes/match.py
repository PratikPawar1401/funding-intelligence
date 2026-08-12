"""
Grant matching: researcher profile -> ranked FOA recommendations.

Wraps matching/matcher.py's hybrid score (0.7 cosine similarity + 0.3 ontology
tag overlap, MATCHING.md) and, when a local LLM is reachable, layers a
plain-language explanation and a coarse relevance judgement onto the top
results via matching/explain.py. The hybrid ranking itself never depends on
the LLM being available -- explanations are additive and degrade to a
deterministic templated sentence, so this endpoint never 5xxs because Ollama
is down.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...matching.explain import annotate_with_explanations
from ...matching.matcher import match_profile_to_foas
from ...storage.database import Database
from ..deps import (
    get_app_config,
    get_db,
    get_match_explainer,
    get_tagger_pipeline,
    get_vector_index,
)

router = APIRouter()


class MatchRequest(BaseModel):
    profile_text: str = Field(..., min_length=10, max_length=5000)
    k: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum cosine similarity for the FAISS candidate pool, pre hybrid re-rank.",
    )
    status: Optional[str] = "open"
    explain: bool = Field(
        default=True,
        description=(
            "Generate an LLM explanation and relevance rating for the top "
            "results (see MATCH_EXPLAIN_TOP_K). Ranking itself is unaffected "
            "by this flag either way."
        ),
    )


@router.post("")
def match_profile(req: MatchRequest, db: Database = Depends(get_db)):
    """
    Rank FOAs against a free-text researcher profile.

    Base ranking is the hybrid score: dense vector similarity from FAISS
    combined with explicit ontology-tag overlap between the profile and each
    FOA. If `explain` is true and results were found, the top
    `MATCH_EXPLAIN_TOP_K` are additionally annotated with a `match_explanation`
    sentence and an `llm_relevance` tier, and that window is re-sorted by
    relevance (hybrid_score breaks ties) -- so the LLM can refine the order of
    candidates the hybrid score already surfaced, but cannot promote a
    candidate it never reviewed.
    """
    index = get_vector_index()

    if index.index is None:
        return {
            "items": [],
            "total": 0,
            "llm_available": False,
            "message": "FAISS index not found. Run `make precompute-embeddings` then `make tag`.",
        }

    tagger = get_tagger_pipeline()
    results = match_profile_to_foas(
        req.profile_text, db, index, tagger=tagger, k=req.k, threshold=req.threshold
    )

    if req.status:
        results = [r for r in results if r.get("status") == req.status]

    llm_available = False
    if req.explain and results:
        config = get_app_config()
        explainer = get_match_explainer()
        outcome = annotate_with_explanations(
            req.profile_text, results, explainer, config.match_explain_top_k
        )
        results = outcome["items"]
        llm_available = outcome["llm_available"]

    return {
        "items": results,
        "total": len(results),
        "llm_available": llm_available,
        "message": "Match successful" if results else "No matching FOAs found for this profile.",
    }
