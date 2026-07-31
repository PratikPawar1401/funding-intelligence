import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Config:
    # ── Grants.gov API ──
    grants_gov_base_url: str
    grants_gov_search_endpoint: str
    grants_gov_fetch_endpoint: str
    grants_gov_page_size: int
    grants_gov_max_pages: int
    grants_gov_query: str

    # ── NSF ──
    nsf_rss_url: str
    nsf_scraper_rate_limit: float
    nsf_scraper_max_concurrent: int

    # ── Paths ──
    sqlite_db_path: Path
    app_db_path: Path
    raw_output_dir: Path
    normalised_output_dir: Path
    embeddings_cache_dir: Path
    ontology_dir: Path
    evaluation_dir: Path

    # ── Tagging ──
    spacy_model: str
    embedding_model: str
    cosine_thresholds: dict
    enable_layer3_llm: bool
    ollama_base_url: str
    ollama_model: str

    # ── API ──
    api_host: str
    api_port: int
    api_reload: bool

    # ── General ──
    log_level: str
    user_agent: str
    schema_version: str

    # ── API hardening (defaulted) ──
    # These carry defaults and sit last on purpose: most of the codebase builds
    # a Config without caring about API settings, and adding a required field
    # here breaks every one of those call sites at once.
    api_cors_origins: List[str] = field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"]
    )
    api_rate_limit_per_minute: int = 120
    api_export_max_rows: int = 10000


def get_config() -> Config:
    """Build Config from environment variables with sensible defaults."""
    return Config(
        # ── Grants.gov API ──
        grants_gov_base_url=_env("GRANTS_GOV_BASE_URL", "https://api.grants.gov/v1/api"),
        grants_gov_search_endpoint=_env("GRANTS_GOV_SEARCH_ENDPOINT", "search2"),
        grants_gov_fetch_endpoint=_env("GRANTS_GOV_FETCH_ENDPOINT", "fetchOpportunity"),
        grants_gov_page_size=int(_env("GRANTS_GOV_PAGE_SIZE", "25")),
        grants_gov_max_pages=int(_env("GRANTS_GOV_MAX_PAGES", "5")),
        grants_gov_query=_env("GRANTS_GOV_QUERY", '{"keyword": "NSF"}'),
        # ── NSF ──
        nsf_rss_url=_env("NSF_RSS_URL", "https://www.nsf.gov/rss/rss_www_funding.xml"),
        nsf_scraper_rate_limit=float(_env("NSF_SCRAPER_RATE_LIMIT", "1.0")),
        nsf_scraper_max_concurrent=int(_env("NSF_SCRAPER_MAX_CONCURRENT", "3")),
        # ── Paths ──
        sqlite_db_path=Path(_env("SQLITE_DB_PATH", "data/queues/nsf_queue.db")),
        app_db_path=Path(_env("APP_DB_PATH", "data/db/funding_intelligence.db")),
        raw_output_dir=Path(_env("RAW_OUTPUT_DIR", "data/raw")),
        normalised_output_dir=Path(_env("NORMALISED_OUTPUT_DIR", "data/normalised")),
        embeddings_cache_dir=Path(_env("EMBEDDINGS_CACHE_DIR", "data/embeddings")),
        ontology_dir=Path(_env("ONTOLOGY_DIR", "data/ontology")),
        evaluation_dir=Path(_env("EVALUATION_DIR", "data/evaluation")),
        # ── Tagging ──
        spacy_model=_env("SPACY_MODEL", "en_core_web_lg"),
        embedding_model=_env("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"),
        cosine_thresholds=__import__('json').loads(_env("COSINE_THRESHOLDS", '{"method": 0.40, "population": 0.35, "research_domain": 0.35, "research_discipline": 0.35, "sponsor_theme": 0.30, "default": 0.35, "method_25": 0.65}')),
        enable_layer3_llm=_env("ENABLE_LAYER3_LLM", "true").lower() == "true",
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=_env("OLLAMA_MODEL", "mistral:7b-instruct"),
        # ── API ──
        api_host=_env("API_HOST", "0.0.0.0"),
        api_port=int(_env("API_PORT", "8000")),
        api_reload=_env("API_RELOAD", "true").lower() == "true",
        # Comma-separated origins. The bundled frontend is served from the same
        # origin as the API, so it needs no entry here; this is for separately
        # hosted frontends. "*" is accepted but disables credentialed requests.
        api_cors_origins=[
            o.strip()
            for o in _env(
                "API_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
            ).split(",")
            if o.strip()
        ],
        api_rate_limit_per_minute=int(_env("API_RATE_LIMIT_PER_MINUTE", "120")),
        api_export_max_rows=int(_env("API_EXPORT_MAX_ROWS", "10000")),
        # ── General ──
        log_level=_env("LOG_LEVEL", "INFO"),
        user_agent=_env("USER_AGENT", "foa-pipeline/1.0"),
        schema_version=_env("SCHEMA_VERSION", "1.0"),
    )
