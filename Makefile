.PHONY: install dev test lint run ingest tag serve docker-up \
        harvest-nsf-awards benchmark-disciplines diagnose-separation \
        harvest-openalex annotate-eval-set

install:
	pip install -r requirements.txt
	python -m spacy download en_core_web_lg
	python -m nltk.downloader wordnet omw-1.4

dev:
	pip install -r requirements-dev.txt

test:
	PYTHONPATH=src pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/
	mypy src/foa_pipeline/

# ── Pipeline Commands ──

ingest-grants:
	PYTHONPATH=src python -m foa_pipeline.cli grants-poll

ingest-nsf-rss:
	PYTHONPATH=src python -m foa_pipeline.cli nsf-rss-poll

ingest-nsf-scrape:
	PYTHONPATH=src python -m foa_pipeline.cli nsf-scrape

parse-pdf:
	PYTHONPATH=src python -m foa_pipeline.cli pdf-parse $(pdf_path)

normalise:
	PYTHONPATH=src python -m foa_pipeline.cli normalise

enrich-grants:
	PYTHONPATH=src python -m foa_pipeline.cli enrich-grants

setup-ontology:
	PYTHONPATH=src python -m foa_pipeline.cli setup-ontology

tag:
	PYTHONPATH=src python -m foa_pipeline.cli tag-all

export-csv:
	PYTHONPATH=src python -m foa_pipeline.cli export-csv

precompute-embeddings:
	PYTHONPATH=src python -m foa_pipeline.cli precompute-embeddings

# ── Evaluation ──

# Harvests NSF awards as a directorate-labelled corpus. Awards are written to
# the evaluation directory only -- they are not FOAs and must never enter the
# FOA database. See src/foa_pipeline/ingestion/nsf_awards.py.
harvest-nsf-awards:
	PYTHONPATH=src python -m foa_pipeline.cli harvest-nsf-awards

# Vendors the CC0 OpenAlex field taxonomy to data/ontology/. The resulting CSV
# is staged, NOT loaded: see EVALUATION.md 4g before registering it.
harvest-openalex:
	PYTHONPATH=src python -m foa_pipeline.cli harvest-openalex

benchmark-disciplines:
	PYTHONPATH=src python -m foa_pipeline.cli benchmark-disciplines

diagnose-separation:
	PYTHONPATH=src python -m foa_pipeline.cli diagnose-separation

# Drafts SILVER labels for eval_set_50.json with the local LLM. Never the gold
# set, and never a reported metric -- tuning signal only.
annotate-eval-set:
	PYTHONPATH=src python -m foa_pipeline.cli annotate-eval-set

# ── Full Pipeline ──

pipeline: ingest-grants ingest-nsf-rss normalise enrich-grants tag export-csv

# ── Server ──

serve:
	PYTHONPATH=src uvicorn foa_pipeline.api.app:app --reload --port 8000

# ── Docker ──

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down
