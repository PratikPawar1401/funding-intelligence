"""
LLM-generated match explanations.

Turns a match's hybrid_score/cosine_score/tag_overlap_ratio triple into a
plain-language justification a research development officer can read without
decoding the numbers, and asks the same call for a coarse relevance judgement
used to break ties within the reviewed window (see `annotate_with_explanations`).

Bounded to the top `explain_top_k` results per request: a local Ollama round
trip runs one to a few seconds, so explaining all `k` candidates would not
scale the way scoring them does. Every failure mode — Ollama unreachable, a
timeout, a malformed response — falls back to a deterministic templated
sentence built from the already-computed scores, so a match request never
errors and never blocks on the LLM being unavailable. This is the same
fallback contract `layer3_llm.py` uses for tag disambiguation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Order defines the sort key in annotate_with_explanations: lower sorts first.
RELEVANCE_ORDER = {"strong": 0, "moderate": 1, "weak": 2}

_MAX_EXPLANATION_CHARS = 400
_MAX_SNIPPET_CHARS = 600
_MAX_PROFILE_CHARS = 800

_FALLBACK_TEMPLATE = (
    "Researcher profile:\n{profile}\n\n"
    "Funding opportunity: {title}\nExcerpt: {snippet}\n\n"
    "Shared tags: {matched_tags}\nTopic similarity: {cosine:.2f}\n"
    "Tag overlap: {tag_overlap:.2f}\n\n"
    'Respond with JSON: {{"explanation": "<one sentence>", '
    '"relevance": "strong"|"moderate"|"weak"}}'
)


def _fallback_explanation(foa: Dict[str, Any]) -> str:
    """
    A deterministic sentence built from scores alone, used whenever the LLM
    path is unavailable or fails. Never references facts the LLM might have
    invented — only numbers the pipeline itself computed.
    """
    matched = foa.get("matched_tags") or []
    if matched:
        return (
            f"Matches on {', '.join(matched[:4])} "
            f"(tag overlap {foa.get('tag_overlap_ratio', 0.0):.0%}, "
            f"topic similarity {foa.get('cosine_score', 0.0):.0%})."
        )
    cosine = foa.get("cosine_score", 0.0)
    return f"Thematically similar per vector search (topic similarity {cosine:.0%})."


class MatchExplainer:
    """Ollama-backed explanation generator for grant-match results."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "mistral:7b-instruct",
        prompt_template_path: Optional[Path] = None,
        timeout: float = 20.0,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

        if prompt_template_path and prompt_template_path.exists():
            self.prompt_template = prompt_template_path.read_text(encoding="utf-8")
        else:
            self.prompt_template = _FALLBACK_TEMPLATE

    def is_available(self) -> bool:
        """Check if Ollama is reachable. Mirrors L3Tagger.is_available."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2.0)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                if self.model in models or f"{self.model}:latest" in models:
                    return True
                logger.warning("Ollama is running, but model '%s' not found.", self.model)
        except requests.RequestException:
            logger.warning("Ollama server not reachable at %s", self.base_url)
        return False

    def explain_one(self, profile_text: str, foa: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Returns {"explanation": str, "relevance": "strong"|"moderate"|"weak"|None}.

        `relevance` is None whenever the model's response could not be
        parsed into one of the three tiers — the explanation string is still
        returned (real text beats no text), it just does not participate in
        the relevance-based reordering.
        """
        prompt = self.prompt_template.format(
            profile=(profile_text or "")[:_MAX_PROFILE_CHARS],
            title=foa.get("title") or "",
            snippet=(foa.get("program_description") or "")[:_MAX_SNIPPET_CHARS],
            matched_tags=", ".join(foa.get("matched_tags") or []) or "none",
            cosine=float(foa.get("cosine_score", 0.0)),
            tag_overlap=float(foa.get("tag_overlap_ratio", 0.0)),
        )

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
            parsed = json.loads(raw)

            explanation = str(parsed.get("explanation", "")).strip()[:_MAX_EXPLANATION_CHARS]
            if not explanation:
                raise ValueError("LLM returned an empty explanation")

            relevance: Optional[str] = str(parsed.get("relevance", "")).strip().lower()
            if relevance not in RELEVANCE_ORDER:
                relevance = None

            return {"explanation": explanation, "relevance": relevance}

        except Exception as exc:
            logger.warning(
                "Match explanation failed for foa_id=%s: %s", foa.get("foa_id"), exc
            )
            return {"explanation": _fallback_explanation(foa), "relevance": None}


def annotate_with_explanations(
    profile_text: str,
    ranked_foas: List[Dict[str, Any]],
    explainer: Optional[MatchExplainer],
    explain_top_k: int,
) -> Dict[str, Any]:
    """
    Add `match_explanation` and `llm_relevance` to the top `explain_top_k`
    results, then stably re-sort that window by relevance tier (strong >
    moderate > weak > unscored), keeping hybrid_score as the tiebreaker.

    Results beyond the window are untouched and keep their position after it
    — the LLM never reviewed them, so it should not be able to move them.
    This bounds both latency (at most `explain_top_k` Ollama calls) and the
    LLM's influence (it can only reorder candidates the hybrid score already
    judged good enough to review).

    Availability is checked once per request, not once per candidate.
    """
    if not ranked_foas:
        return {"items": ranked_foas, "llm_available": False}

    window = ranked_foas[:explain_top_k]
    rest = ranked_foas[explain_top_k:]

    # Guarded so explain_top_k=0 (or an empty ranked_foas slice) never pings
    # Ollama at all -- there would be nothing to do with the answer.
    llm_available = bool(window) and bool(explainer and explainer.is_available())

    for foa in window:
        if llm_available:
            assert explainer is not None  # for type checkers; guarded by llm_available
            result = explainer.explain_one(profile_text, foa)
        else:
            result = {"explanation": _fallback_explanation(foa), "relevance": None}
        foa["match_explanation"] = result["explanation"]
        foa["llm_relevance"] = result["relevance"]

    if llm_available:
        window.sort(
            key=lambda f: (
                RELEVANCE_ORDER.get(f["llm_relevance"], len(RELEVANCE_ORDER)),
                -f["hybrid_score"],
            )
        )

    return {"items": window + rest, "llm_available": llm_available}
