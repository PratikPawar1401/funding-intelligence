"""
Docker entry point for the API and frontend.
"""

import os

# faiss and spaCy/torch each ship their own OpenMP runtime. On macOS, loading
# both in one process aborts with "OMP: Error #15: Initializing libomp.dylib,
# but found libomp.dylib already initialized" (a hard SIGSEGV, no traceback) —
# which is exactly what the grant matcher does when it tags a profile with
# spaCy and then searches the FAISS index. Capping OpenMP threads before any
# of those libraries load avoids the duplicate-runtime abort. setdefault so a
# deployment can still override it.
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Re-exported for convenience; not "unused" despite appearances.
# E402: must follow the OMP_NUM_THREADS setting above to be effective.
from .vector_index import VectorIndex  # noqa: E402,F401

__all__ = [
    "config",
    "grants_gov",
    "nsf_rss",
    "nsf_scraper",
    "schema",
    "storage",
    "normaliser",
    "validator",
    "ontology_store",
    "synonym_expander",
    "evidence_logger",
    "pdf_parser",
    "database",
    "csv_exporter",
    "evaluation",
    "vector_index",
]
__version__ = "1.0.0"
