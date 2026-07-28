"""
Docker entry point for the API and frontend.
"""

# Include vector_index here so it's tracked in __all__
from .vector_index import VectorIndex

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
