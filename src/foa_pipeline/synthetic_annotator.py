"""
Synthetic Annotator v2 — Per-Category Prompting Strategy.

Instead of one mega-prompt with all 76 concepts, we run 4 focused prompts
per FOA (one per ontology category). Each prompt contains only 14-25 concepts,
making it far easier for a 7B model to return valid JSON.

Also includes the enriched text (program_description + additional_info) for 
better coverage.
"""

import json
import logging
from pathlib import Path

import requests

from foa_pipeline.config import get_config
from foa_pipeline.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


CATEGORY_PROMPTS = {
    "sponsor_theme": (
        "You are a US federal grants analyst. Read this grant program description and identify "
        "which GREAT Act mission categories apply. A category applies ONLY if the grant explicitly "
        "funds research or activities in that area.\n\n"
        "Available Categories:\n{concepts}\n\n"
        "Grant Description:\n{text}\n\n"
        "Return a JSON list of the matching concept IDs. If none match, return []. "
        "Example: [\"great_01\", \"great_05\"]\n"
        "JSON:"
    ),
    "research_domain": (
        "You are a UN Sustainable Development Goals expert. Read this grant program description "
        "and identify which UN SDGs are directly addressed. An SDG applies ONLY if the grant "
        "explicitly funds work related to that goal.\n\n"
        "Available SDGs:\n{concepts}\n\n"
        "Grant Description:\n{text}\n\n"
        "Return a JSON list of the matching concept IDs. If none match, return []. "
        "Example: [\"sdg_04\", \"sdg_13\"]\n"
        "JSON:"
    ),
    "method": (
        "You are a research methodology expert. Read this grant program description and identify "
        "which research methods are explicitly required or encouraged. A method applies ONLY if "
        "the grant specifically mentions or requires that research approach.\n\n"
        "Available Methods:\n{concepts}\n\n"
        "Grant Description:\n{text}\n\n"
        "Return a JSON list of the matching concept IDs. If none match, return []. "
        "Example: [\"method_01\", \"method_15\"]\n"
        "JSON:"
    ),
    "population": (
        "You are a demographics and equity expert. Read this grant program description and identify "
        "which target populations are explicitly mentioned as focus groups, beneficiaries, or required "
        "study subjects. A population applies ONLY if the grant explicitly targets that group.\n\n"
        "Available Populations:\n{concepts}\n\n"
        "Grant Description:\n{text}\n\n"
        "Return a JSON list of the matching concept IDs. If none match, return []. "
        "Example: [\"pop_03\", \"pop_12\"]\n"
        "JSON:"
    ),
}


def get_concepts_by_category(db: Database):
    """Get all concepts grouped by category."""
    query = "SELECT concept_id, label, category FROM ontology_concepts ORDER BY category, concept_id"
    rows = db.conn.execute(query).fetchall()

    by_cat = {}
    for r in rows:
        cat = r["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append({"id": r["concept_id"], "label": r["label"]})
    return by_cat


def call_ollama(base_url, model, prompt, max_retries=2):
    """Call Ollama with retry logic."""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "num_predict": 256}
                },
                timeout=120.0
            )
            resp.raise_for_status()
            result_text = resp.json().get("response", "").strip()

            parsed = json.loads(result_text)

            # Handle dict responses. Two shapes observed from the model:
            #   {"tags": ["great_01", "great_05"]}        -> concept IDs in a list value
            #   {"great_05": ["chemical synthesis", ...]}  -> concept ID as the key itself
            # Collect candidates from both shapes; the caller filters against
            # valid_ids, so over-collecting here is harmless.
            if isinstance(parsed, dict):
                candidates = list(parsed.keys())
                for v in parsed.values():
                    if isinstance(v, list):
                        candidates.extend(str(x) for x in v)
                return candidates

            if isinstance(parsed, list):
                return [str(x) for x in parsed]

            return []

        except json.JSONDecodeError:
            if attempt < max_retries:
                logging.debug("JSON parse failed, retrying (%d/%d)", attempt + 1, max_retries)
                continue
            return []
        except Exception as e:
            if attempt < max_retries:
                logging.debug("Request error, retrying (%d/%d): %s", attempt + 1, max_retries, e)
                continue
            logging.error("Ollama call failed after %d attempts: %s", max_retries + 1, e)
            return []


def annotate_foas():
    config = get_config()
    db = Database(config.app_db_path)

    eval_file = config.evaluation_dir / "eval_set_50.json"
    if not eval_file.exists():
        logging.error(f"{eval_file} not found. Run curate-eval-set first.")
        return

    with open(eval_file) as f:
        foas = json.load(f)

    concepts_by_cat = get_concepts_by_category(db)

    base_url = config.ollama_base_url
    model = config.ollama_model

    logging.info("Annotating %d FOAs using %s with per-category prompts...", len(foas), model)

    for i, foa in enumerate(foas):
        # Skip if already annotated with non-empty tags
        if foa.get("human_tags") and len(foa["human_tags"]) > 0:
            logging.info("[%d/%d] FOA %s: SKIPPED (already has %d tags)",
                        i + 1, len(foas), foa["foa_id"][:8], len(foa["human_tags"]))
            continue

        # Build text from all available fields (enriched content)
        text_parts = [
            foa.get("title", ""),
            foa.get("program_description", ""),
            foa.get("eligibility_description", ""),
            foa.get("additional_info", ""),
        ]
        text = " ".join(p for p in text_parts if p)

        if not text.strip():
            foa["human_tags"] = []
            continue

        # Truncate to keep prompt manageable
        text_truncated = text[:4000]

        all_tags = []

        # Run one prompt per category
        for cat, prompt_template in CATEGORY_PROMPTS.items():
            if cat not in concepts_by_cat:
                continue

            concept_list = "\n".join(
                f"- {c['id']}: {c['label']}" for c in concepts_by_cat[cat]
            )

            prompt = prompt_template.format(concepts=concept_list, text=text_truncated)

            tags = call_ollama(base_url, model, prompt)

            # Validate that returned tags are actual concept IDs in this category
            valid_ids = {c["id"] for c in concepts_by_cat[cat]}
            validated = list(dict.fromkeys(t for t in tags if t in valid_ids))

            # Sanity guard: a model that echoes back most/all of the category's
            # concept list (seen in practice on long/complex FOA text) is a
            # failure mode, not a genuine multi-label judgement. Discard it
            # rather than let it pollute the silver-standard set.
            if len(valid_ids) >= 4 and len(validated) > 0.5 * len(valid_ids):
                logging.warning(
                    "  [%s] discarded %d/%d concepts (looks like a full-list echo, not a real selection)",
                    cat, len(validated), len(valid_ids),
                )
                continue

            all_tags.extend(validated)

        foa["human_tags"] = all_tags

        logging.info("[%d/%d] FOA %s: %s", i + 1, len(foas), foa["foa_id"][:8], all_tags)

        # Checkpoint every 5 FOAs
        if (i + 1) % 5 == 0:
            with open(eval_file, "w") as f:
                json.dump(foas, f, indent=2)

    # Final save
    with open(eval_file, "w") as f:
        json.dump(foas, f, indent=2)

    # Print summary
    labelled = sum(1 for f in foas if f.get("human_tags"))
    total_tags = sum(len(f.get("human_tags", [])) for f in foas)
    logging.info("Annotation complete: %d/%d FOAs labelled, %d total tags", labelled, len(foas), total_tags)


if __name__ == "__main__":
    annotate_foas()
