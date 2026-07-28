"""
FAISS Vector Index for Semantic Grant Matching.

Indexes FOA program descriptions using sentence-transformers.
Supports storing FAISS metadata mapping vector IDs to FOA IDs
in the SQLite database.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .database import Database

logger = logging.getLogger(__name__)


class VectorIndex:
    """FAISS-based vector search for FOAs."""

    def __init__(self, db: Database, model_name: str, cache_dir: Path):
        self.db = db
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.index = None
        self.model = None

    def load_model(self) -> None:
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                logger.info("Loaded embedding model for FAISS: %s", self.model_name)
            except ImportError:
                logger.error("sentence-transformers not installed.")
                raise

    def initialize_index(self, dimension: int = 768) -> None:
        """Create a new FAISS IndexFlatIP (Inner Product = Cosine if normalized)."""
        import faiss
        
        # Using IndexFlatIP for cosine similarity (assuming normalized vectors)
        self.index = faiss.IndexIDMap(faiss.IndexFlatIP(dimension))
        logger.info("Initialized FAISS index with dimension %d", dimension)

    def build_index(self) -> None:
        """Fetch all FOAs, embed their descriptions, and build the FAISS index."""
        self.load_model()
        assert self.model is not None
        
        # Get dimensionality
        dummy = self.model.encode(["test"])
        dimension = dummy.shape[1]
        
        self.initialize_index(dimension)
        assert self.index is not None
        
        # Clear existing metadata mapping
        self.db.conn.execute("DELETE FROM faiss_metadata")
        
        foas, _ = self.db.list_foas(status="open", page=1, size=10000)
        logger.info("Building vector index for %d open FOAs...", len(foas))
        
        if not foas:
            return
            
        texts = []
        foa_ids = []
        
        for foa in foas:
            desc = foa.get("program_description", "")
            title = foa.get("title", "")
            if not desc and not title:
                continue
                
            texts.append(f"{title}. {desc}")
            foa_ids.append(foa["foa_id"])
            
        # Encode all
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        
        # IDs for faiss must be integers
        faiss_ids = np.arange(len(embeddings), dtype=np.int64)
        
        # Add to index
        self.index.add_with_ids(embeddings, faiss_ids)
        
        # Save mapping to SQLite
        for fid, foa_id in zip(faiss_ids, foa_ids):
            self.db.conn.execute(
                "INSERT INTO faiss_metadata (faiss_id, foa_id) VALUES (?, ?)",
                (int(fid), str(foa_id))
            )
        self.db.conn.commit()
        
        # Save index to disk
        self._save_index()

    def _save_index(self) -> None:
        """Save FAISS index to disk."""
        import faiss
        if self.index:
            path = self.cache_dir / "foa_index.faiss"
            faiss.write_index(self.index, str(path))
            logger.info("Saved FAISS index to %s", path)

    def load_index(self) -> bool:
        """Load FAISS index from disk."""
        import faiss
        path = self.cache_dir / "foa_index.faiss"
        if not path.exists():
            return False
            
        try:
            self.index = faiss.read_index(str(path))
            logger.info("Loaded FAISS index with %d vectors", self.index.ntotal)
            return True
        except Exception as exc:
            logger.error("Failed to load FAISS index: %s", exc)
            return False

    def search(self, query: str, k: int = 10, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        Search the index for FOAs semantically similar to the query.
        Returns full FOA records with a 'similarity_score' injected.
        """
        if self.index is None:
            if not self.load_index():
                logger.warning("FAISS index not loaded/built. Cannot search.")
                return []
                
        self.load_model()
        assert self.model is not None
        assert self.index is not None
        
        query_emb = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        
        # Search
        scores, I = self.index.search(query_emb, k)
        
        results = []
        for score, faiss_id in zip(scores[0], I[0]):
            if faiss_id == -1 or score < threshold:
                continue
                
            # Lookup FOA ID
            row = self.db.conn.execute(
                "SELECT foa_id FROM faiss_metadata WHERE faiss_id = ?",
                (int(faiss_id),)
            ).fetchone()
            
            if row:
                foa = self.db.get_foa(row["foa_id"])
                if foa:
                    foa.pop("raw_payload", None)
                    foa["similarity_score"] = round(float(score), 4)
                    results.append(foa)
                    
        return results
