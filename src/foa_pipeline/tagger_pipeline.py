"""
Orchestrator for the 3-Layer Semantic Tagging Engine.

Coordinates L1 (spaCy), L2 (sentence-transformers), and L3 (Ollama),
merges results, resolves hierarchies, and yields a unified list of tags
for each FOA record.
"""

import logging
from typing import Any, Dict, List, Set

from .config import Config
from .evidence_logger import TagEvidence
from .ontology_store import OntologyStore
from .tagger_cfda_crosswalk import apply_cfda_crosswalk
from .tagger_l1_spacy import L1Tagger
from .tagger_l2_embedding import L2Tagger
from .tagger_l3_llm import L3Tagger

logger = logging.getLogger(__name__)


class TaggerPipeline:
    """Coordinates the full semantic tagging pipeline."""

    def __init__(self, config: Config, store: OntologyStore):
        self.config = config
        self.store = store

        self.l1 = L1Tagger(spacy_model=config.spacy_model)
        self.l2 = L2Tagger(
            model_name=config.embedding_model,
            thresholds=config.cosine_thresholds,
            cache_dir=config.embeddings_cache_dir,
        )
        self.l3 = L3Tagger(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            prompt_template_path=config.raw_output_dir.parent / "prompts" / "disambiguation.txt"
        )

        self.is_initialized = False
        # Set definitively in initialize(); declared here so the attribute
        # always exists even if a caller inspects it beforehand.
        self.l3_active = False

    def initialize(self) -> None:
        """Load models and build indices. Call before tag_record."""
        if self.is_initialized:
            return

        logger.info("Initializing TaggerPipeline...")
        self.l1.build_matcher(self.store)
        self.l2.build_embeddings(self.store)

        # Tracked on the pipeline, not the config: Config is a frozen dataclass,
        # so assigning to it here raised FrozenInstanceError and crashed the
        # whole run on the one path this code exists to handle — L3 enabled but
        # Ollama unreachable, which is the default for anyone who hasn't
        # installed Ollama.
        self.l3_active = bool(self.config.enable_layer3_llm)
        if self.l3_active:
            if self.l3.is_available():
                logger.info("L3 LLM Tagging enabled and available.")
            else:
                logger.warning(
                    "L3 LLM Tagging enabled but Ollama is not available; "
                    "continuing with Layer 1 + Layer 2 only."
                )
                self.l3_active = False

        self.is_initialized = True

    def tag_record(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a single FOA record and return a list of tags (dict format).
        """
        if not self.is_initialized:
            self.initialize()

        # Combine fields to scan
        text_parts = [
            record.get("title", ""),
            record.get("program_description", ""),
            record.get("eligibility_description", ""),
            record.get("additional_info", ""),
        ]
        full_text = " ".join(p for p in text_parts if p)

        if not full_text.strip():
            return []

        # 1. Run L1 (Exact/Synonyms)
        l1_evidence = self.l1.tag_text(full_text)

        # 2. Run L2 (Semantic Embedding)
        l2_evidence = self.l2.tag_text(full_text)

        # 3. Merge and Disambiguate
        merged = self._merge_and_disambiguate(l1_evidence, l2_evidence, full_text)

        # 4. Propagate Hierarchies
        final_evidence = self._propagate_hierarchies(merged)

        # 5. Recall Backstop (CFDA Crosswalk)
        has_sponsor_theme = any(ev.category == "sponsor_theme" for ev in final_evidence)
        if not has_sponsor_theme:
            crosswalk_concept_id = apply_cfda_crosswalk(full_text)
            if crosswalk_concept_id:
                concept = self.store.get_concept_by_id(crosswalk_concept_id)
                if concept:
                    final_evidence.append(
                        TagEvidence(
                            concept_id=concept.concept_id,
                            label=concept.label,
                            category=concept.category,
                            source_layer="layer_4_cfda_crosswalk",
                            confidence=0.85, # Crosswalk confidence
                            context_snippet="[CFDA Crosswalk Match]",
                            ontology_concept_id=concept.concept_id,
                        )
                    )

        # Return serialized tags
        return [ev.to_tag_record() for ev in final_evidence]

    def _merge_and_disambiguate(
        self,
        l1_evidence: List[TagEvidence],
        l2_evidence: List[TagEvidence],
        full_text: str,
    ) -> List[TagEvidence]:
        """
        Merge L1 and L2 evidence with revised conflict resolution.

        Rules:
        1. If L1 found a concept, keep L1's evidence (confidence 1.0).
        2. L2 can contribute NEW concepts (not already found by L1) — even in
           categories where L1 already tagged something. The top-5 cap per
           category prevents runaway noise.
        3. If L2 found multiple closely-scored concepts in the same category,
           run L3 disambiguation (if enabled).
        4. Cap at top 5 tags per category.
        """
        merged_dict: Dict[str, TagEvidence] = {}
        l1_concept_ids: Set[str] = set()

        # Add L1 first (highest priority)
        for ev in l1_evidence:
            merged_dict[ev.concept_id] = ev
            l1_concept_ids.add(ev.concept_id)

        # Group L2 by category to detect ambiguities
        l2_by_cat: Dict[str, List[TagEvidence]] = {}
        for ev in l2_evidence:
            # Skip if L1 already found this exact concept
            if ev.concept_id in l1_concept_ids:
                continue
            l2_by_cat.setdefault(ev.category, []).append(ev)

        for cat, ev_list in l2_by_cat.items():
            # Sort by confidence
            ev_list.sort(key=lambda x: x.confidence, reverse=True)

            # Check for ambiguity (top 2 are very close)
            if len(ev_list) >= 2 and self.l3_active:
                top_1 = ev_list[0]
                top_2 = ev_list[1]

                # If within 0.05 similarity, it's ambiguous
                if (top_1.confidence - top_2.confidence) < 0.05:
                    logger.debug(
                        "Ambiguity detected in %s: %s vs %s",
                        cat,
                        top_1.label,
                        top_2.label,
                    )
                    resolved = self.l3.disambiguate(top_1, top_2, full_text)
                    merged_dict[resolved.concept_id] = resolved

                    # Add remaining non-ambiguous tags
                    for ev in ev_list[2:]:
                        merged_dict[ev.concept_id] = ev
                    continue

            # No ambiguity or L3 disabled, just add them all
            for ev in ev_list:
                merged_dict[ev.concept_id] = ev

        # Apply Top-5 Cap Per Category
        final_list = []
        final_by_cat: Dict[str, List[TagEvidence]] = {}
        for ev in merged_dict.values():
            final_by_cat.setdefault(ev.category, []).append(ev)

        for cat, ev_list in final_by_cat.items():
            # Sort by confidence (L1 = 1.0 always wins within the cap)
            ev_list.sort(key=lambda x: x.confidence, reverse=True)
            # Take top 3
            final_list.extend(ev_list[:3])

        return final_list

    def _propagate_hierarchies(self, evidence: List[TagEvidence]) -> List[TagEvidence]:
        """
        If a child concept is tagged, automatically tag its parents.
        e.g., Target 1.1 -> No Poverty (SDG 1)
        """
        final_dict: Dict[str, TagEvidence] = {ev.concept_id: ev for ev in evidence}
        parents_to_add: Dict[str, TagEvidence] = {}

        for ev in evidence:
            parent_chain = self.store.get_parent_chain(ev.concept_id)
            for parent_id in parent_chain:
                if parent_id not in final_dict and parent_id not in parents_to_add:
                    parent_concept = self.store.get_concept_by_id(parent_id)
                    if parent_concept:
                        parents_to_add[parent_id] = TagEvidence(
                            concept_id=parent_concept.concept_id,
                            label=parent_concept.label,
                            category=parent_concept.category,
                            # Propagated implies structural certainty
                            source_layer="layer_1_terminological",
                            confidence=ev.confidence,               # Inherit confidence of child
                            context_snippet=f"[Propagated from {ev.label}]",
                            ontology_concept_id=parent_concept.concept_id,
                        )

        final_dict.update(parents_to_add)
        return list(final_dict.values())
