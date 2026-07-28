# ISSR AI-Powered Funding Intelligence

> An end-to-end system that automatically discovers, parses, normalises, and semantically tags federal Funding Opportunity Announcements (FOAs) — built as a **Google Summer of Code 2026** project for the [HumanAI Foundation](https://humanai.foundation/) / [University of Alabama ISSR](https://issr.ua.edu/).

**The goal**: A "Simpler Grants.gov" — an intelligent, searchable platform that replaces the manual, fragmented process research development officers use to find funding opportunities.

---

## Architecture

```
Data Sources          Ingestion             Processing              Storage            Serving
┌──────────┐    ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐    ┌──────────┐
│Grants.gov│───>│ API Poller      │───>│ Normaliser       │───>│ SQLite DB   │───>│ FastAPI  │
│ REST API │    │ (retry+backoff) │    │ (date/text/amt)  │    │ (FTS5)      │    │ Backend  │
└──────────┘    ├─────────────────┤    ├──────────────────┤    ├─────────────┤    ├──────────┤
┌──────────┐    │ RSS Detector    │    │ JSON Schema      │    │ FAISS Index │    │   Web    │
│  NSF.gov │───>│ + Playwright    │───>│ Validator        │    │ (vectors)   │    │ Frontend │
│  Website │    │   Scraper       │    ├──────────────────┤    └─────────────┘    └──────────┘
└──────────┘    ├─────────────────┤    │ L1: spaCy        │
┌──────────┐    │ Layout-Aware    │    │ L2: Embeddings   │
│ FOA PDFs │───>│ PDF Parser      │    │ L3: LLM (stretch)│
└──────────┘    └─────────────────┘    └──────────────────┘
```

---

## Features

| Feature | Description | Status |
|---|---|---|
| **Grants.gov Ingestion** | Polls the Grants.gov REST API with pagination, retry backoff, and deduplication | ✅ Complete |
| **NSF Web Scraping** | RSS feed detection → headless Playwright scraping of JS-rendered NSF pages | ✅ Complete |
| **Layout-Aware PDF Parsing** | pymupdf4llm preserves column reading order; pdfplumber extracts tables | ✅ Complete |
| **Data Normalisation** | Harmonises dates, amounts, text encoding across all sources into a canonical schema | ✅ Complete |
| **JSON Schema Validation** | Draft-7 validation enforcing required fields, date formats, and enum values | ✅ Complete |
| **Ontology Store** | SQLite-backed taxonomy with GREAT Act categories, UN SDGs, research methods, populations | ✅ Complete |
| **Synonym Expansion** | WordNet-based expansion for improved recall in terminological matching | ✅ Complete |
| **Layer 1 Tagging (spaCy)** | spaCy PhraseMatcher for exact/synonym terminological matching | ✅ Complete |
| **Layer 2 Tagging (Embeddings)** | all-mpnet-base-v2 cosine similarity for semantic gap-filling | ✅ Complete |
| **Layer 3 Tagging (LLM)** | Mistral-7B via Ollama for ambiguous/cross-domain disambiguation (stretch goal) | ⏳ Stretch Goal |
| **Evaluation Framework** | Gold standard P/R/F1 evaluation with per-category error analysis | ✅ Complete |
| **PDF Downloader** | Async aiohttp downloader for linked PDFs with auto-parsing | ✅ Complete |
| **Vector Search** | FAISS IndexFlatIP for semantic similarity search across FOA embeddings | ⏳ Stretch Goal |
| **FastAPI Backend** | REST API with CRUD, search, tag, and export endpoints | ✅ Complete |
| **Web Frontend** | Search interface with faceted filtering — the "Simpler Grants.gov" | 🔨 In Progress |
| **CSV/JSON Export** | Structured export with tag evidence provenance | ✅ Complete |
| **Docker Deployment** | Full-stack containerisation with docker-compose | 🔨 In Progress |

---

## GSoC Timeline & Progress

| Phase | Timeline | Deliverable | Status |
|---|---|---|---|
| **Phase 0** | Community Bonding | Ontology setup, directory structure, dev environment | ✅ Done |
| **Phase 1** | Weeks 1–3 | Hybrid ingestion engine + PDF parser + normalisation | ✅ Done |
| **Phase 2** | Weeks 4–6 | Schema enforcement + Layer 1 spaCy tagger + evaluation | ✅ Done |
| **Phase 3** | Weeks 7–8 | Embedding layer (L2) + merge integration | ✅ Done |
| **Phase 4** | Week 9 | Evaluation metrics (P/R/F1) + matching foundation | 🔨 Active |
| **Phase 5** | Weeks 10–12 | Integration testing + Docker + API + frontend | ⏳ Upcoming |
| **Phase 6** | Week 13 | Final report + documentation + handoff | ⏳ Upcoming |

---

## Quickstart

### Prerequisites

- Python 3.11+
- [Playwright browsers](https://playwright.dev/python/docs/intro) (for NSF scraping)

### Installation

```bash
# Clone the repository
git clone https://github.com/PratikPawar1401/funding-intelligence.git
cd funding-intelligence

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install NLP models
python -m spacy download en_core_web_lg
python -m nltk.downloader wordnet omw-1.4

# Install Playwright browsers (for NSF scraping)
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env as needed
```

### Run the Pipeline

```bash
# Full ingestion → normalisation → tagging pipeline
make pipeline

# Or run individual steps:
make ingest-grants       # Poll Grants.gov API
make ingest-nsf-rss      # Poll NSF RSS feed
make ingest-nsf-scrape   # Scrape pending NSF URLs via Playwright
make normalise           # Normalise + validate + load into SQLite
make setup-ontology      # Load ontology concepts into store
make tag                 # Run semantic tagging (L1 + L2)
make export-csv          # Export tagged records to CSV
```

### Run the API Server

```bash
make serve
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Run Tests

```bash
pip install -r requirements-dev.txt
make test

# With coverage report
PYTHONPATH=src pytest --cov=src/foa_pipeline tests/
```

### Docker

```bash
make docker-up     # Build and start all services
make docker-down   # Stop services
```

---

## Project Structure

```
funding-intelligence/
├── src/foa_pipeline/
│   ├── cli.py                  # CLI entry point (12 subcommands)
│   ├── config.py               # Environment-based configuration
│   │
│   ├── # ── Ingestion ──
│   ├── grants_gov.py           # Grants.gov REST API client
│   ├── nsf_rss.py              # NSF RSS feed change detector
│   ├── nsf_scraper.py          # Playwright headless scraper
│   │
│   ├── # ── Parsing ──
│   ├── pdf_parser.py           # Layout-aware PDF extraction
│   │
│   ├── # ── Normalisation ──
│   ├── normaliser.py           # Multi-source data normalisation
│   ├── validator.py            # JSON Schema validation
│   ├── schema.py               # Record builder
│   │
│   ├── # ── Ontology ──
│   ├── ontology_store.py       # SQLite taxonomy management
│   ├── synonym_expander.py     # WordNet synonym expansion
│   │
│   ├── # ── Tagging ──
│   ├── tagger_l1_spacy.py      # Layer 1: spaCy PhraseMatcher
│   ├── tagger_l2_embedding.py  # Layer 2: Sentence embeddings
│   ├── tagger_l3_llm.py        # Layer 3: LLM disambiguation
│   ├── tagger_pipeline.py      # L1 → L2 → L3 orchestrator
│   ├── evidence_logger.py      # Tag provenance tracking
│   │
│   ├── # ── Search & Matching ──
│   ├── vector_index.py         # FAISS vector index
│   │
│   ├── # ── Storage & Export ──
│   ├── database.py             # SQLite DB with FTS5
│   ├── storage.py              # JSONL utilities
│   ├── csv_exporter.py         # CSV export with evidence
│   ├── evaluation.py           # P/R/F1 metrics
│   │
│   └── api/                    # FastAPI backend
│       ├── app.py              # Application factory
│       ├── deps.py             # Dependency injection
│       └── routes/             # REST endpoints
│           ├── opportunities.py
│           ├── search.py
│           ├── tags.py
│           ├── export.py
│           └── health.py
│
├── frontend/                   # Web UI ("Simpler Grants.gov")
│   ├── index.html
│   ├── css/
│   └── js/
│
├── data/
│   ├── ontology/               # Taxonomy source CSVs
│   ├── raw/                    # Ingested JSONL (gitignored)
│   ├── normalised/             # Processed output
│   ├── db/                     # SQLite database
│   ├── embeddings/             # Cached vectors
│   └── evaluation/             # Hand-labelled test set
│
├── tests/                      # 92 tests, 85%+ coverage
├── Documentation/              # Blueprint, proposal, reports
├── scraper_config/             # Per-domain scraping rules (YAML)
├── prompts/                    # LLM prompt templates
├── phase-test-scripts/         # End-to-end test scripts
│
├── Dockerfile
├── docker-compose.yml
├── Makefile                    # 15 convenience targets
├── requirements.txt
└── pyproject.toml
```

---

## Data Schema

Every FOA record is normalised into a canonical JSON schema (`data/foa_schema.json`):

| Field | Type | Description |
|---|---|---|
| `foa_id` | `string` (UUID) | Unique identifier |
| `source` | `string` | `grants_gov`, `nsf_scraper`, or `pdf_upload` |
| `title` | `string` | Opportunity title |
| `agency` | `string` | Funding agency name |
| `posted_date` | `string` (ISO 8601) | Publication date |
| `close_date` | `string` (ISO 8601) | Application deadline |
| `status` | `enum` | `open`, `closed`, `forecasted`, `archived` |
| `program_description` | `string` | Full program description |
| `eligibility_description` | `string` | Eligibility criteria |
| `award_floor` / `award_ceiling` | `number` | Funding range |
| `cfda_numbers` | `array` | Assistance listing numbers |
| `tags` | `array` | Semantic tags with evidence and confidence |

---

## Semantic Tagging Architecture

The tagging engine uses a three-layer cascade:

1. **Layer 1 — Terminological (spaCy PhraseMatcher)**: Exact and synonym matching against ontology concepts. High precision, used as ground truth.
2. **Layer 2 — Semantic (all-mpnet-base-v2)**: Sentence-transformer embeddings with cosine similarity scoring. Fills gaps missed by exact matching.
3. **Layer 3 — LLM Disambiguation (Mistral-7B)**: Stretch goal. Handles ambiguous cross-domain tags using structured prompting via Ollama.

Each tag carries provenance metadata:
```json
{
  "label": "climate_change",
  "category": "research_area",
  "layer": "layer_2_embedding",
  "confidence": 0.87,
  "context_snippet": "...impacts of climate variability on agricultural systems..."
}
```

---

## Ontology Categories

| Category | Source | Concepts |
|---|---|---|
| Research Domains | UN Sustainable Development Goals | 17 goals |
| Sponsor Themes | GREAT Act Mission Categories | 14 categories |
| Research Methods | Custom vocabulary | 25 method concepts |
| Target Populations | Custom vocabulary | 20 population concepts |
| **Total** | | **76 concepts** |

For full design rationale, category definitions, and tagging logic, see [ONTOLOGY.md](ONTOLOGY.md).

For evaluation methodology and metrics, see [EVALUATION.md](EVALUATION.md).

---

## Contributing

This project is developed as part of GSoC 2026 under the HumanAI Foundation. Contributions and feedback are welcome.

**Mentor**: Dr. Christopher Cotropia (University of Alabama)

## License

Apache 2.0 — See [LICENSE](LICENSE) for details.

## Author

**Pratik Ramchandra Pawar** — GSoC 2026 Contributor
- GitHub: [@PratikPawar1401](https://github.com/PratikPawar1401)
- Email: pratikpawar1565@gmail.com
