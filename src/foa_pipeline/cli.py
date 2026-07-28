import argparse
import json
import logging
import sys

from .config import get_config
from .grants_gov import poll_grants
from .logging_setup import setup_logging
from .nsf_rss import poll_nsf_rss


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ISSR Funding Intelligence Pipeline CLI"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without writing outputs"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── Ingestion ──
    subparsers.add_parser("grants-poll", help="Poll Grants.gov API")
    subparsers.add_parser("nsf-rss-poll", help="Poll NSF RSS feed")
    sub_scrape = subparsers.add_parser("nsf-scrape", help="Scrape pending NSF URLs")
    sub_scrape.add_argument(
        "--max-pages", type=int, default=50, help="Max pages to scrape"
    )

    # ── Normalisation ──
    subparsers.add_parser("normalise", help="Normalise raw records to canonical schema")
    subparsers.add_parser("enrich-foas", help="Download and parse FOA PDFs for Grants.gov and NSF")
    subparsers.add_parser("extract-budget", help="Extract complex budget tiers from FOA text using LLM")

    # ── Ontology ──
    subparsers.add_parser(
        "setup-ontology", help="Load ontology CSVs and expand synonyms"
    )
    mine_syn_p = subparsers.add_parser("mine-synonyms", help="Mine high-confidence L2 tags for WordNet synonyms")
    mine_syn_p.add_argument("--threshold", type=float, default=0.88, help="Minimum L2 confidence to consider for mining")

    # ── Tagging ──
    tag_all_p = subparsers.add_parser("tag-all", help="Run tagging pipeline on all FOAs")
    tag_all_p.add_argument("--limit", type=int, default=0, help="Limit number of FOAs to tag")

    # ── Embeddings ──
    subparsers.add_parser(
        "precompute-embeddings",
        help="Pre-compute ontology embeddings for Layer 2",
    )

    # ── Export ──
    sub_csv = subparsers.add_parser("export-csv", help="Export FOAs to CSV")
    sub_csv.add_argument("--output", "-o", default=None, help="Output file path")

    # ── Search ──
    sub_search = subparsers.add_parser(
        "search", help="Search FOAs by researcher profile"
    )
    sub_search.add_argument("--profile", required=True, help="Research profile text")
    sub_search.add_argument("--k", type=int, default=10, help="Number of results")

    # ── Server ──
    subparsers.add_parser("serve", help="Start the FastAPI server")

    # ── Evaluation ──
    subparsers.add_parser("evaluate", help="Run evaluation on labelled set")
    curate_p = subparsers.add_parser("curate-eval-set", help="Generate a stratified sample of FOAs for evaluation")
    curate_p.add_argument("--size", type=int, default=50, help="Number of FOAs to sample")

    # ── PDF Parse ──
    sub_pdf = subparsers.add_parser("pdf-parse", help="Parse a FOA PDF")
    sub_pdf.add_argument("pdf_path", help="Path to the PDF file")

    sub_dl = subparsers.add_parser("download-pdfs", help="Asynchronously download and parse pending PDFs")
    sub_dl.add_argument("--dry-run", action="store_true", help="Do not actually download")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = get_config()
    setup_logging(config.log_level)

    if args.command == "grants-poll":
        stats = poll_grants(config, dry_run=args.dry_run)
        logging.info("Grants.gov poll complete: %s", stats)

    elif args.command == "nsf-rss-poll":
        stats = poll_nsf_rss(config, dry_run=args.dry_run)
        logging.info("NSF RSS poll complete: %s", stats)

    elif args.command == "nsf-scrape":
        from .nsf_scraper import drain_nsf_queue

        stats = drain_nsf_queue(
            config, max_pages=args.max_pages, dry_run=args.dry_run
        )
        logging.info("NSF scrape complete: %s", stats)

    elif args.command == "normalise":
        _run_normalise(config, args)

    elif args.command == "enrich-foas":
        _run_enrich_foas(config)

    elif args.command == "extract-budget":
        _run_extract_budget(config)

    elif args.command == "setup-ontology":
        _run_setup_ontology(config)

    elif args.command == "tag-all":
        _run_tag_all(config, args)
        
    elif args.command == "mine-synonyms":
        _run_mine_synonyms(config, args)

    elif args.command == "curate-eval-set":
        _run_curate_eval_set(config, args)

    elif args.command == "precompute-embeddings":
        _run_precompute_embeddings(config)

    elif args.command == "export-csv":
        _run_export_csv(config, args)

    elif args.command == "search":
        logging.info("Search: requires FAISS index. Build it first with tag-all")

    elif args.command == "serve":
        _run_server(config)

    elif args.command == "evaluate":
        logging.info("Evaluation: requires labelled set at %s", config.evaluation_dir)

    elif args.command == "pdf-parse":
        _run_pdf_parse(args)

    elif args.command == "download-pdfs":
        _run_download_pdfs(config, args)


def _run_download_pdfs(config, args) -> None:
    """Run the async PDF downloader."""
    from .pdf_downloader import run_downloader
    stats = run_downloader(config)
    logging.info("PDF Downloader finished. Stats: %s", stats)


def _run_normalise(config, args) -> None:
    """Normalise all raw records from data/raw/ into data/normalised/."""
    from .normaliser import normalise_record
    from .validator import validate_record
    from .storage import ensure_dir
    from .database import Database

    ensure_dir(config.normalised_output_dir)
    db = Database(config.app_db_path)

    raw_dir = config.raw_output_dir
    total = 0
    valid = 0

    for jsonl_file in raw_dir.glob("*.jsonl"):
        source = "grants_gov" if "grants" in jsonl_file.stem else "nsf_scraper"
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total += 1
                try:
                    normalised = normalise_record(raw, source)
                    is_ok, errors = validate_record(normalised)
                    if is_ok:
                        db.upsert_foa(normalised)
                        valid += 1
                    else:
                        logging.warning(
                            "Validation errors for %s: %s",
                            normalised.get("foa_id"),
                            errors[:3],
                        )
                except Exception as exc:
                    logging.warning("Normalisation failed: %s", exc)

    db.close()
    logging.info("Normalised %d/%d records into database", valid, total)


def _run_enrich_foas(config) -> None:
    import urllib.request
    from pathlib import Path
    from .database import Database
    from .grants_gov import GrantsGovClient
    from .pdf_parser import parse_foa_pdf, extract_structured_fields

    # Boilerplate PDFs that are generic and don't describe a specific FOA
    SKIP_URLS = {
        "https://resources.research.gov/common/attachment/Common/Grants_govProposal_Processing_in_Research.pdf",
    }

    db = Database(config.app_db_path)
    client = GrantsGovClient(config)
    pdf_dir = Path("data/pdfs")

    records, total = db.list_foas(page=1, size=100000)
    enriched_count = 0
    skipped_count = 0
    error_count = 0

    logging.info("Scanning %d FOA records for PDF enrichment...", total)

    for idx, foa in enumerate(records):
        source = foa.get("source")
        raw_payload = foa.get("raw_payload", {})
        
        # Handle case where raw_payload was stored as a JSON string
        if isinstance(raw_payload, str):
            try:
                raw_payload = json.loads(raw_payload)
            except (json.JSONDecodeError, TypeError):
                raw_payload = {}

        # Check if already enriched
        if raw_payload.get("pdf_enriched"):
            skipped_count += 1
            continue

        all_pdf_text = []
        structured_fields = {}
        
        # GRANTS.GOV LOGIC
        if source == "grants_gov":
            extracted_pdf_ids = raw_payload.get("extracted_pdf_ids", [])
            if not extracted_pdf_ids:
                continue
            logging.info("[%d/%d] Enriching Grants.gov FOA %s (%s) with %d attachments",
                         idx + 1, total, foa["foa_id"], (foa.get("title") or "")[:50], len(extracted_pdf_ids))
            
            for att_id in extracted_pdf_ids:
                out_path = pdf_dir / "grants_gov" / f"{foa['foa_id']}_{att_id}.pdf"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if not out_path.exists():
                    success = client.download_attachment(att_id, out_path)
                    if not success:
                        error_count += 1
                        continue
                
                try:
                    result = parse_foa_pdf(out_path)
                    text_content = "\n".join([sec.content for sec in result.sections])
                    if len(text_content.strip()) > 50:  # Skip trivially small PDFs
                        all_pdf_text.append(text_content)
                    
                    fields = extract_structured_fields(result)
                    structured_fields.update(fields)
                except Exception as exc:
                    logging.warning("Failed to parse PDF %s: %s", out_path, exc)
                    error_count += 1

        # NSF LOGIC
        elif source == "nsf_scraper":
            pdf_links = raw_payload.get("pdf_links", [])
            # Filter out boilerplate PDFs
            pdf_links = [link for link in pdf_links if link not in SKIP_URLS]
            if not pdf_links:
                continue
            logging.info("[%d/%d] Enriching NSF FOA %s (%s) with %d PDF links",
                         idx + 1, total, foa["foa_id"], (foa.get("title") or "")[:50], len(pdf_links))
            
            for i, link in enumerate(pdf_links):
                out_path = pdf_dir / "nsf" / f"{foa['foa_id']}_{i}.pdf"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if not out_path.exists():
                    try:
                        urllib.request.urlretrieve(link, out_path)
                    except Exception as exc:
                        logging.warning("Failed to download NSF PDF %s: %s", link, exc)
                        error_count += 1
                        continue
                
                try:
                    result = parse_foa_pdf(out_path)
                    text_content = "\n".join([sec.content for sec in result.sections])
                    if len(text_content.strip()) > 50:
                        all_pdf_text.append(text_content)
                    
                    fields = extract_structured_fields(result)
                    structured_fields.update(fields)
                except Exception as exc:
                    logging.warning("Failed to parse PDF %s: %s", out_path, exc)
                    error_count += 1
        else:
            continue
            
        # Update FOA with text and structured fields
        if all_pdf_text:
            combined_text = "\n\n=== PDF ATTACHMENT ===\n\n".join(all_pdf_text)
            existing_info = foa.get("additional_info") or ""
            foa["additional_info"] = existing_info + "\n\n=== PDF ATTACHMENTS ===\n\n" + combined_text
            
            # Merge extracted structured fields (don't overwrite if already exists and is non-null)
            if "award_floor" in structured_fields and not foa.get("award_floor"):
                foa["award_floor"] = structured_fields["award_floor"]
            if "award_ceiling" in structured_fields and not foa.get("award_ceiling"):
                foa["award_ceiling"] = structured_fields["award_ceiling"]
            if "close_date_raw" in structured_fields and not foa.get("close_date"):
                foa["close_date"] = structured_fields["close_date_raw"]
                
        raw_payload["pdf_enriched"] = True
        foa["raw_payload"] = raw_payload
        db.upsert_foa(foa)
        enriched_count += 1
        
    logging.info("PDF Enrichment complete: %d enriched, %d skipped (already done), %d errors", enriched_count, skipped_count, error_count)



def _run_extract_budget(config) -> None:
    from .database import Database
    from .llm_extractor import BudgetTierExtractor
    
    db = Database(config.app_db_path)
    extractor = BudgetTierExtractor(base_url=config.ollama_base_url, model=config.ollama_model)
    
    if not extractor.is_available():
        logging.warning("Ollama is not available. Ensure it is running and model %s is pulled.", config.ollama_model)
        logging.warning("Run: ollama serve && ollama pull %s", config.ollama_model)
        return

    records, _ = db.list_foas(page=1, size=100000)
    count = 0
    for record in records:
        if record.get("funding_tiers"):
            continue
        text = record.get("additional_info")
        if not text:
            continue
            
        logging.info("Extracting budget tiers for FOA %s", record["foa_id"])
        tiers = extractor.extract_tiers(text)
        if tiers:
            record["funding_tiers"] = tiers
            db.upsert_foa(record)
            count += 1
            logging.info("  Found %d tiers", len(tiers))
            
    logging.info("Extracted budget tiers for %d records", count)


def _run_setup_ontology(config) -> None:
    """Load all ontology CSVs and run synonym expansion."""
    from .ontology_store import OntologyStore
    from .synonym_expander import expand_synonyms_for_store

    store = OntologyStore(config.app_db_path)
    stats = store.load_all_ontologies(config.ontology_dir)
    logging.info("Ontology load stats: %s", stats)

    logging.info("Running synonym expansion...")
    syn_stats = expand_synonyms_for_store(store)
    total_syns = sum(syn_stats.values())
    logging.info(
        "Synonym expansion complete: %d synonyms for %d concepts",
        total_syns,
        len(syn_stats),
    )

    logging.info(
        "Ontology store: %d concepts, %d synonyms",
        store.concept_count(),
        store.synonym_count(),
    )
    store.close()


def _run_tag_all(config, args) -> None:
    """Run the 3-layer semantic tagging pipeline and build the vector index."""
    from .database import Database
    from .ontology_store import OntologyStore
    from .tagger_pipeline import TaggerPipeline
    from .vector_index import VectorIndex

    db = Database(config.app_db_path)
    store = OntologyStore(config.app_db_path)
    pipeline = TaggerPipeline(config, store)
    
    pipeline.initialize()

    # Get all untagged FOAs (or all FOAs if forcing)
    # For simplicity here, we re-tag everything that is open
    foas, total = db.list_foas(status="open", page=1, size=100000)
    
    if args.limit > 0:
        foas = foas[:args.limit]
        
    logging.info("Tagging %d open FOAs...", len(foas))

    tagged_count = 0
    total_tags_saved = 0

    for i, foa in enumerate(foas, 1):
        try:
            tags = pipeline.tag_record(foa)
            if tags:
                saved = db.save_tags(foa["foa_id"], tags)
                total_tags_saved += saved
            tagged_count += 1
            if i % 100 == 0:
                logging.info("Tagged %d/%d FOAs...", i, len(foas))
        except Exception as exc:
            logging.error("Failed to tag FOA %s: %s", foa["foa_id"], exc)

    logging.info("Tagging complete. Saved %d tags across %d FOAs.", total_tags_saved, tagged_count)

    # Build vector index
    logging.info("Building vector index...")
    index = VectorIndex(db, config.embedding_model, config.embeddings_cache_dir)
    index.build_index()
    logging.info("Vector index built successfully.")

    store.close()
    db.close()


def _run_precompute_embeddings(config) -> None:
    """Precompute embeddings for all ontology concepts."""
    from .ontology_store import OntologyStore
    from .tagger_l2_embedding import L2Tagger

    store = OntologyStore(config.app_db_path)
    tagger = L2Tagger(
        model_name=config.embedding_model,
        cache_dir=config.embeddings_cache_dir
    )
    
    logging.info("Starting embedding precomputation...")
    tagger.build_embeddings(store, force_recompute=True)
    logging.info("Embeddings precomputed and cached.")
    store.close()


def _run_export_csv(config, args) -> None:
    """Export all FOAs from the database to CSV."""
    from .database import Database
    from .csv_exporter import export_foas_to_csv

    db = Database(config.app_db_path)
    records, total = db.list_foas(page=1, size=100000)
    db.close()

    output = args.output or str(config.normalised_output_dir / "foa_normalised.csv")
    export_foas_to_csv(records, output)
    logging.info("Exported %d FOAs to %s", len(records), output)


def _run_server(config) -> None:
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "foa_pipeline.api.app:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.api_reload,
    )


def _run_pdf_parse(args) -> None:
    """Parse a single PDF file and print results."""
    from .pdf_parser import parse_foa_pdf, extract_structured_fields
    from pathlib import Path

    result = parse_foa_pdf(Path(args.pdf_path))
    logging.info("Parsed %s (%s)", args.pdf_path, result.parse_method)
    logging.info("Pages: %d", result.page_count)
    logging.info("Sections found: %d", len(result.sections))
    for sec in result.sections:
        logging.info(
            "  [%s] %s (%d chars)",
            sec.section_type,
            sec.heading[:60],
            len(sec.content),
        )
    logging.info("Tables found: %d", len(result.tables))

    fields = extract_structured_fields(result)
    if fields:
        logging.info("Extracted fields: %s", json.dumps(fields, indent=2))

def _run_mine_synonyms(config, args) -> None:
    import csv
    from .database import Database
    
    db = Database(config.app_db_path)
    
    query = """
    SELECT concept_id, label, category, confidence, context_snippet
    FROM tag_evidence
    WHERE source_layer = 'layer_2_embedding'
      AND confidence >= ?
    ORDER BY category, confidence DESC
    """
    
    results = db.conn.execute(query, (args.threshold,)).fetchall()
    
    out_path = config.ontology_dir / "suggested_synonyms.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["concept_id", "label", "category", "confidence", "suggested_synonym_source"])
        for row in results:
            writer.writerow([
                row["concept_id"],
                row["label"],
                row["category"],
                round(row["confidence"], 3),
                row["context_snippet"].replace('\n', ' ')
            ])
            
    logging.info("Mined %d potential synonyms to %s", len(results), out_path)

def _run_curate_eval_set(config, args) -> None:
    import json
    import random
    from .database import Database
    
    db = Database(config.app_db_path)
    
    # Simple stratified sampling: get half from grants_gov and half from nsf_scraper
    half_size = args.size // 2
    
    records = []
    
    # Sample from Grants.gov
    gg_foas = db.conn.execute(
        "SELECT foa_id, title, program_description, eligibility_description, additional_info, source FROM foa_records WHERE source = 'grants_gov' ORDER BY RANDOM() LIMIT ?",
        (half_size,)
    ).fetchall()
    
    # Sample from NSF
    nsf_foas = db.conn.execute(
        "SELECT foa_id, title, program_description, eligibility_description, additional_info, source FROM foa_records WHERE source = 'nsf_scraper' ORDER BY RANDOM() LIMIT ?",
        (args.size - len(gg_foas),)
    ).fetchall()
    
    for r in gg_foas + nsf_foas:
        records.append({
            "foa_id": r["foa_id"],
            "title": r["title"],
            "source": r["source"],
            "program_description": r["program_description"],
            "eligibility_description": r["eligibility_description"],
            "additional_info": r["additional_info"],
            "human_tags": []  # Placeholder for annotation
        })
        
    random.shuffle(records)
    
    config.evaluation_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.evaluation_dir / f"eval_set_{args.size}.json"
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
        
    logging.info("Curated stratified eval set of %d FOAs to %s", len(records), out_path)

if __name__ == "__main__":
    main()
