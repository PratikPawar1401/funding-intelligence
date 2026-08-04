"""
Layer 1: Terminological Tagging (Exact Match / Synonym Expansion)

Uses spaCy's PhraseMatcher to find exact matches of ontology concepts
and their generated synonyms within FOA text (title + description + eligibility).

Confidence is always 1.0 for matches at this layer.
"""

import logging
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import spacy
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span
from spacy.util import filter_spans

from ..ontology.store import OntologyConcept, OntologyStore
from .evidence import TagEvidence

logger = logging.getLogger(__name__)


class L1Tagger:
    """Terminological tagger using spaCy PhraseMatcher."""

    NEGATION_TERMS = {"not", "no", "excluding", "without", "except", "outside", "non"}

    def __init__(self, spacy_model: str = "en_core_web_lg"):
        self.spacy_model = spacy_model
        self.nlp = None
        self.matcher = None
        self.concept_lookup: Dict[str, OntologyConcept] = {}

    def load_model(self) -> None:
        """Load the spaCy model if not already loaded."""
        if self.nlp is None:
            try:
                # Enable parser for dependency checking, disable ner to save time
                self.nlp = spacy.load(self.spacy_model, disable=["ner"])
            except OSError:
                logger.error(
                    "spaCy model '%s' not found. "
                    "Run: python -m spacy download %s",
                    self.spacy_model,
                    self.spacy_model,
                )
                raise

    def build_matcher(self, store: OntologyStore) -> None:
        """Build the PhraseMatcher from ontology concepts and synonyms."""
        self.load_model()
        assert self.nlp is not None

        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        self.concept_lookup = {}

        concepts = store.get_all_concepts()
        count = 0

        for concept in concepts:
            self.concept_lookup[concept.concept_id] = concept

            # Match label
            patterns = [self.nlp.make_doc(concept.label)]

            # Match synonyms
            for syn in concept.synonyms:
                if syn:
                    patterns.append(self.nlp.make_doc(syn))

            # Add patterns to matcher using concept_id as match ID
            self.matcher.add(concept.concept_id, patterns)
            count += len(patterns)

        logger.info(
            "Built L1 PhraseMatcher with %d patterns across %d concepts",
            count,
            len(concepts),
        )

    def tag_text(
        self,
        text: str,
        excluded_spans: Optional[List[Tuple[int, int, FrozenSet[str]]]] = None,
    ) -> List[TagEvidence]:
        """
        Scan text and return evidence for all matched concepts.

        `excluded_spans` suppresses categories over character ranges, given as
        `(start_char, end_char, categories)`, so a section can be disqualified
        from producing certain tags without being removed from the text —
        removing it would shift Layer 2's chunk boundaries.
        """
        if not text or not self.matcher or not self.nlp:
            return []

        doc: Doc = self.nlp(text)

        # Keep only the longest match where several overlap at one position.
        # The matcher reports both a concept's label and its synonyms, so
        # "rural communities" also produces a bare "rural" hit at the same
        # place. The bare hit is reported first, is correctly rejected by the
        # modifier check below as an adjective, and used to consume the
        # concept's one slot — silently hiding the full-label match that would
        # have been accepted. filter_spans prefers the longest span, so the
        # label wins over its own synonym.
        spans = [
            Span(doc, start, end, label=match_id)
            for match_id, start, end in self.matcher(doc)
        ]

        evidence_list: List[TagEvidence] = []
        seen_concepts: Set[str] = set()

        for span in filter_spans(spans):
            start, end = span.start, span.end
            concept_id = self.nlp.vocab.strings[span.label]

            # Only record the first occurrence per concept to avoid duplicate spam
            if concept_id in seen_concepts:
                continue

            concept = self.concept_lookup.get(concept_id)
            if not concept:
                continue

            # Checked before the concept is marked as seen, so a match falling
            # in an excluded region doesn't block a legitimate one later in the
            # document.
            if excluded_spans:
                match_start = doc[start].idx
                if any(
                    lo <= match_start < hi and concept.category in categories
                    for lo, hi, categories in excluded_spans
                ):
                    continue

            seen_concepts.add(concept_id)

            # Contextual Dependency Checks
            is_valid = True

            # 1. Dependency Negation Check
            # Look at the root of the match and its ancestors/children
            match_span = doc[start:end]
            root_token = match_span.root

            # Check immediate children of the root for a negation modifier ('neg')
            if any(child.dep_ == "neg" for child in root_token.children):
                is_valid = False

            # Also check if the head of the root is negated (e.g., "does not fund housing")
            if any(child.dep_ == "neg" for child in root_token.head.children):
                is_valid = False

            # 2. Metaphorical / Compound Modifier Check
            # Single-word terms that frequently appear as modifiers in compound nouns
            # where the concept doesn't actually apply. E.g. "food security" ≠ National Defense,
            # "machine learning" ≠ Quality Education, "housing insecure" ≠ Housing policy.
            #
            # Restricted to single-token matches, which is what the heuristic was
            # always described as covering. Without that guard it also rejected
            # multi-word exact label matches whenever the phrase's head noun
            # happened to be an ambiguous word: "machine learning" was discarded
            # because "learning" heads a compound, and the six-token match on
            # "good health and well-being" because "health" sits in a
            # prepositional phrase. A multi-word match is specific enough that
            # the surrounding syntax is not evidence against it.
            ambiguous_terms = {
                "ecosystem", "travel", "environment", "system", "space", "model",
                "security", "learning", "education", "equity", "housing",
                "survey", "poverty", "energy", "health", "defense",
                "rural", "urban", "student", "veteran",
                "statistics", "transportation", "transport",
            }
            if is_valid and len(match_span) == 1 and root_token.text.lower() in ambiguous_terms:
                # If the match is a single token used as a modifier/compound, reject it.
                # "npadvmod" catches hyphenated compound-adjective patterns like
                # "energy-efficient system components", where "energy" modifies
                # "efficient" rather than standing for the National Defense/Energy
                # concept itself.
                if root_token.dep_ in {"amod", "compound", "nmod", "pobj", "npadvmod"} or \
                   any(child.dep_ in {"amod", "compound"} for child in root_token.children):
                    is_valid = False

            if not is_valid:
                continue

            # Grab context window (up to 10 tokens before and after)
            context_start = max(0, start - 10)
            context_end = min(len(doc), end + 10)
            snippet = doc[context_start:context_end].text

            evidence_list.append(
                TagEvidence(
                    concept_id=concept.concept_id,
                    label=concept.label,
                    category=concept.category,
                    source_layer="layer_1_terminological",
                    confidence=1.0,  # Exact matches are always 1.0 confidence
                    context_snippet=snippet,
                    ontology_concept_id=concept.concept_id,
                )
            )

        return evidence_list
