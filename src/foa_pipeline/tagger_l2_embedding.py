"""
Layer 2: Semantic Embedding Tagging

Uses sentence-transformers to map FOA text chunks and ontology concept
descriptions into a shared embedding space. Tags are assigned based on
cosine similarity exceeding a configurable threshold.

Includes precomputation utilities to cache ontology embeddings.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .evidence_logger import TagEvidence
from .ontology_store import OntologyConcept, OntologyStore

logger = logging.getLogger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class L2Tagger:
    """Semantic tagger using dense embeddings."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        thresholds: Optional[Dict[str, float]] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.model_name = model_name
        self.thresholds = thresholds or {"default": 0.75}
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.concept_embeddings: Dict[str, np.ndarray] = {}
        self.concept_lookup: Dict[str, OntologyConcept] = {}

    def load_model(self) -> None:
        """Load the sentence-transformer model."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                logger.info("Loaded embedding model: %s", self.model_name)
            except ImportError:
                logger.error("sentence-transformers not installed.")
                raise

    def build_embeddings(self, store: OntologyStore, force_recompute: bool = False) -> None:
        """
        Build embeddings for all ontology concepts.
        Caches to disk if cache_dir is provided.
        """
        self.load_model()
        assert self.model is not None

        cache_path_npy = self.cache_dir / "concept_embeddings.npy" if self.cache_dir else None
        cache_path_json = self.cache_dir / "concept_ids.json" if self.cache_dir else None

        concepts = store.get_all_concepts()
        self.concept_lookup = {c.concept_id: c for c in concepts}

        if (
            not force_recompute
            and cache_path_npy
            and cache_path_npy.exists()
            and cache_path_json
            and cache_path_json.exists()
        ):
            # Load from cache
            try:
                emb_matrix = np.load(cache_path_npy)
                with open(cache_path_json) as f:
                    concept_ids = json.load(f)

                if len(concept_ids) == len(concepts):
                    for cid, emb in zip(concept_ids, emb_matrix):
                        self.concept_embeddings[cid] = emb
                    logger.info("Loaded %d concept embeddings from cache", len(concept_ids))
                    return
                else:
                    logger.info("Cache size mismatch, recomputing embeddings.")
            except Exception as exc:
                logger.warning("Failed to load embeddings cache: %s", exc)

        # Compute embeddings
        logger.info("Computing embeddings for %d concepts...", len(concepts))
        texts_to_embed = []
        concept_ids = []

        for concept in concepts:
            # Embed label + description + synonyms for a richer representation
            text = concept.label
            if concept.description:
                text += ". " + concept.description
            if concept.synonyms:
                text += ". Synonyms: " + ", ".join(concept.synonyms[:5])

            texts_to_embed.append(text)
            concept_ids.append(concept.concept_id)

        emb_matrix = self.model.encode(texts_to_embed, convert_to_numpy=True)

        for cid, emb in zip(concept_ids, emb_matrix):
            self.concept_embeddings[cid] = emb

        # Save to cache
        if cache_path_npy and cache_path_json:
            np.save(cache_path_npy, emb_matrix)
            with open(cache_path_json, "w") as f:
                json.dump(concept_ids, f)
            logger.info("Saved embeddings cache to %s", self.cache_dir)

    def chunk_text(self, text: str, chunk_size: int = 250, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks (words)."""
        words = text.split()
        if not words:
            return []

        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            if i + chunk_size >= len(words):
                break
        return chunks

    def tag_text(self, text: str) -> List[TagEvidence]:
        """
        Embed text chunks and find ontology concepts above threshold.
        """
        if not text or not self.model or not self.concept_embeddings:
            return []

        chunks = self.chunk_text(text)
        if not chunks:
            return []

        # Embed all chunks at once
        chunk_embs = self.model.encode(chunks, convert_to_numpy=True)

        evidence_dict: Dict[str, TagEvidence] = {}

        # Compare each chunk against all concepts
        for i, chunk_emb in enumerate(chunk_embs):
            for concept_id, concept_emb in self.concept_embeddings.items():
                sim = cosine_similarity(chunk_emb, concept_emb)

                concept = self.concept_lookup[concept_id]

                # Determine threshold: per-concept override takes priority
                # over the category default (e.g. a concept that is
                # persistently over-triggered by generic boilerplate can
                # be tightened without raising the threshold for its whole
                # category and losing recall on other concepts in it).
                threshold = self.thresholds.get(
                    concept_id,
                    self.thresholds.get(concept.category, self.thresholds.get("default", 0.75)),
                )

                if sim >= threshold:
                    # Keep the chunk that gave the highest similarity for this concept
                    existing = evidence_dict.get(concept_id)
                    if existing is None or sim > existing.confidence:
                        # Truncate snippet if too long
                        snippet = chunks[i][:500] + ("..." if len(chunks[i]) > 500 else "")

                        evidence_dict[concept_id] = TagEvidence(
                            concept_id=concept.concept_id,
                            label=concept.label,
                            category=concept.category,
                            source_layer="layer_2_embedding",
                            confidence=sim,
                            context_snippet=snippet,
                            ontology_concept_id=concept.concept_id,
                        )

        return list(evidence_dict.values())
