# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project was developed for Google Summer of Code 2026 under the HumanAI
Foundation, for the University of Alabama's Institute for Social Science
Research (ISSR).

---

## [Unreleased]

### Added
- `ingestion/nsf_awards.py` — NSF Award Search connector producing an
  agency-labelled evaluation corpus (~1,250 abstracts whose research directorate
  NSF assigned itself). Written to the evaluation directory only: awards are a
  different genre from FOAs and must never enter `foa_records`. Crosswalks are
  explicit rather than derived from abbreviations, because NSF reports `CSE` for
  Computer & Information Science and `O/D` for the Office of the Director.
- `evaluation/discipline_benchmark.py` — ranks the eight directorates per award
  and reports top-1/top-3 accuracy, MRR, macro F1 and a confusion matrix. Strict
  scoring uses the managing directorate; lenient also accepts a co-funder, since
  9.9% of awards are co-funded. Includes a deterministic `tune`/`eval` split so
  concept-description edits are never reported on the awards that motivated them.
- `normalisation/boilerplate.py` — administrative boilerplate removal before
  tagging. Only HTML markup stripping is enabled by default; the text-level
  pattern groups (eligibility blocks, deadline tables, PAPPG references) are
  retained but disabled because measurement showed they don't improve tagging.
  See `EVALUATION.md` §4b for why, and the module docstring for per-group
  numbers.
- `grant_matcher.py` — researcher profile → ranked FOA matching using the hybrid
  relevance score (`0.7 × cosine + 0.3 × tag_overlap`) documented in
  `MATCHING.md`. Retrieves a wider FAISS candidate pool than requested before
  re-ranking, so tag overlap can genuinely promote results rather than only
  reorder the top-k. Every result carries `cosine_score`, `tag_overlap_ratio`,
  `matched_tags`, and `hybrid_score` so a ranking can be explained.
- `ANNOTATION_CODEBOOK.md` — annotation guidelines and inter-annotator agreement
  protocol for producing a multi-annotator gold standard.
- `tests/test_api.py` — 29 tests covering the previously untested FastAPI layer
  (routes, filtering, pagination, validation, export, OpenAPI registration).
- `tests/test_grant_matcher.py` — 19 tests for the hybrid matching logic.
- Per-concept cosine threshold overrides in `config.py`'s `cosine_thresholds`,
  checked ahead of the per-category threshold.
- `LICENSE` (Apache 2.0) and this changelog.

### Changed
- `cli search` and `cli evaluate` now perform real work. Both previously
  accepted their arguments and only logged a message.
- FAISS index and embedding model are cached per process in the API layer
  instead of being reloaded on every `/api/search/semantic` request
  (~3.3s → ~0.015s per request).
- `VectorIndex.search()` accepts an optional per-call `Database`, so a shared
  cached index can use request-scoped connections rather than holding one
  (SQLite connections cannot cross threads).
- `ONTOLOGY.md` documents the `research_discipline` (NSF Directorates) category
  and records that it supersedes UN SDGs for domain classification, with the
  measured F1 gap as justification. Concept count corrected 76 → 84.
- `EVALUATION.md` documents `eval_set_50.json` as an LLM-generated *silver*
  standard that cannot substitute for a second human annotator.
- Enriched `research_methods.csv` descriptions for concepts that were producing
  false negatives.

### Fixed
- **Stale tags corrupted every evaluation comparison.** `tag-all` never cleared
  `foa_tags` before re-tagging, and `save_tags` uses `INSERT OR REPLACE` keyed
  on `(foa_id, concept_id, source_layer)` — so any concept that stopped being
  emitted after a threshold or synonym change left its old row behind forever.
- **Stale synonyms likewise persisted.** `setup-ontology` never cleared
  `ontology_synonyms`, and `add_synonyms` uses `INSERT OR IGNORE`, so removing a
  synonym in code had no effect on the database.
- **Cross-category synonym leakage.** `synonym_expander.py` matched
  `ABBREVIATIONS` by substring (`label_lower in full_form`), so e.g. the GREAT
  Act concept "Health" silently inherited synonyms authored for the unrelated
  SDG "Good Health and Well-being". Now requires an exact match.
- **Segfault when tagging and vector search ran in one process.** faiss and
  spaCy/torch each ship an OpenMP runtime; loading both aborts on macOS with
  `OMP: Error #15` and no traceback (exit 139). OpenMP threads are now capped in
  the package `__init__` before those libraries load.
- **Synthetic annotator silently produced empty labels.** Its Ollama response
  parser only read dict *values*, but the model sometimes returns
  `{concept_id: [...]}` with the ID as the *key*, so every tag failed validation.
  Only 16 of 46 eval entries had labels before this fix. A guard was also added
  to discard responses that echo back more than half a category's concept list.
- Removed noisy synonyms confirmed as false-positive triggers: `equity`
  (financial/DEI homonym), bare `learning` (matched inside "machine learning"),
  bare `statistics` (matched organisation names), `job creation`.
- `tagger_l1_spacy.py` now rejects the `npadvmod` dependency, catching
  hyphenated compound-adjective false positives such as "energy-efficient".
- `tagger_l3_llm.py` parses Ollama JSON mode instead of substring-matching raw
  generation text, with the old heuristic retained as a fallback.
- `mine-synonyms` queried a non-existent `tag_evidence` table (real table:
  `foa_tags`).
- Removed a dead duplicate `prompts/disambiguation.txt`; the pipeline reads
  `data/prompts/disambiguation.txt`.

### Evaluation
Gold-standard metrics (20-FOA hand-labelled set) across this work:

| Metric | Before | After |
|---|---|---|
| Precision | 0.371 | 0.427 |
| Recall | 0.642 | 0.654 |
| F1 | 0.471 | **0.517** |

Layer 2 separation AUC 0.633 → 0.666 (added as a second metric because F1 on an
81-tag set cannot resolve changes this small — see `EVALUATION.md` §4c).

Largest per-category gain: `method` F1 0.250 → 0.462. See `EVALUATION.md` §4a,
§4b, and §4c for the per-change breakdown, including several candidate changes
that were tested and rejected for making held-out F1 worse.

#### Discipline benchmark (NSF award corpus, 1,248 awards)

A second, independent benchmark added because the gold set carries only ~3
examples per NSF directorate — too few for any per-concept claim. Layer 2 ranking
over the eight directorates:

| Metric | Value |
|---|---|
| Top-1 accuracy (strict) | 0.639 |
| Top-3 accuracy (strict) | 0.884 |
| Mean reciprocal rank | 0.774 |
| Macro F1 | 0.572 |

This immediately surfaced a defect invisible at gold-set scale: **Engineering
recall 0.014** (2 of 146), with its concept vector ranking sixth of eight on
awards NSF itself labelled Engineering. See `EVALUATION.md` §4e.

Rewriting the Engineering description fixed it, measured on a held-out half of
the corpus that played no part in choosing the wording (n=615):

| Metric | Before | After |
|---|---|---|
| Top-3 accuracy (strict) | 0.885 | 0.911 |
| Macro F1 | 0.553 | 0.568 |
| Engineering F1 | 0.026 | 0.154 |
| Engineering recall | 0.013 | 0.092 |

Rewriting *all eight* directorate descriptions was tried first and **rejected**:
it redistributed error rather than reducing it (four categories better, four
worse, top-1 0.639 → 0.613), and its apparent Engineering gain came largely from
degrading Engineering's competitors. See `EVALUATION.md` §4f.

---

## [1.0.0] — 2026-07-05 (midterm)

### Added
- Hybrid ingestion: Grants.gov REST API poller, NSF RSS change detector, and
  Playwright-based NSF scraper.
- Layout-aware PDF parsing (pymupdf4llm primary, pdfplumber for tables,
  pdfminer.six fallback) plus an async PDF downloader.
- Schema normalisation across sources with Draft-7 JSON Schema validation.
- SQLite-backed ontology store with WordNet synonym expansion.
- Three-layer semantic tagging: spaCy PhraseMatcher (L1), all-mpnet-base-v2
  embeddings (L2), Mistral-7B disambiguation via Ollama (L3), with CFDA
  crosswalk recall backstop and full tag provenance.
- FAISS `IndexFlatIP` vector index.
- SQLite application database with FTS5 full-text search.
- FastAPI backend and a vanilla HTML/CSS/JS frontend.
- CSV/JSON export with tag evidence.
- Evaluation framework with per-category precision/recall/F1 and error logs.
- Docker and docker-compose deployment.
