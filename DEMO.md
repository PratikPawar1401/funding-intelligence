# Funding Intelligence: Midterm Live Demo Script

Have this document open on a second monitor during your presentation. Copy and paste these commands into your terminal one block at a time.

---

### Step 0: Preparation
*Ensure your virtual environment is active before you start screen sharing.*
```bash
source .venv/bin/activate
```

---

### Step 1: Ingest & Normalise Data (Grants.gov + NSF)
**What to say:** *"To start from a clean slate, let's trigger the ingestion engine. This pulls live data from the Grants.gov API and scrapes legacy HTML/PDF data from the NSF website. Then we normalise it all into a single SQLite database schema."*
```bash
# Pull from Grants.gov
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli grants-poll

# Find new NSF URLs via RSS
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli nsf-rss-poll

# Scrape the pending NSF URLs
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli nsf-scrape

# Normalise scraped raw JSONL files into the SQLite database
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli normalise

# Download and parse linked PDFs for the legacy NSF grants
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli download-pdfs
```

---

### Step 2: Show the Raw Data in the Database
**What to say:** *"Let's look at the database. You'll see we have successfully merged structured API data with parsed PDF data into a unified canonical schema."*
```bash
# Show breakdown of where the FOAs came from
sqlite3 data/db/funding_intelligence.db "SELECT source, COUNT(*) FROM foa_records GROUP BY source;"
```

---

### Step 3: Load the Ontology (The Knowledge Base)
**What to say:** *"Now, we load our controlled vocabulary. We are using the GREAT Act categories, the UN SDGs, and we custom-built an NSF Directorates taxonomy. Watch how the system automatically expands these concepts with synonyms."*
```bash
# Loads CSVs and generates synonyms
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli setup-ontology
```

---

### Step 4: The Tagging Engine (L1 + L2 + L3)
**What to say:** *"Now for the core tagging engine. I'll clear old tags and run it live. It uses a 3-layer cascade: spaCy for exact keyword matches, Semantic Embeddings for implied concepts, and a local Mistral-7B LLM (Layer 3) to break ties and filter out false positives."*
```bash
# Clear old tags
sqlite3 data/db/funding_intelligence.db "DELETE FROM foa_tags;"

# Run the tagging pipeline (This will take ~60 seconds because Mistral is running locally)
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli tag-all
```

---

### Step 5: Show the Tagging Results
**What to say:** *"Tagging is complete. Let's see a breakdown of how many semantic tags were applied across our four different categories."*
```bash
# Show distribution of tags across categories
sqlite3 data/db/funding_intelligence.db "SELECT category, COUNT(*) FROM foa_tags GROUP BY category;"
```

---

### Step 6: Evaluation (The Proof)
**What to say:** *"Finally, we need to prove it works. We built a 20-FOA hand-labeled gold standard dataset. Let's run our evaluation engine to see our Precision, Recall, and F1 scores."*
```bash
# Run P/R/F1 evaluation
PYTHONPATH=src .venv/bin/python src/foa_pipeline/evaluate.py --gold
```
*(Point out the `RESEARCH_DISCIPLINE` score here, showing how your custom NSF Directorates outperformed the UN SDGs).*

---

### Step 7: Export to CSV for Data Analysts
**What to say:** *"Finally, the system exports the normalised, fully-tagged FOAs into a flat CSV file so data analysts and external systems can use it immediately."*
```bash
# Export the database to a flat CSV
PYTHONPATH=src .venv/bin/python -m foa_pipeline.cli export-csv
```

---

### Step 8: Automated Phase Tests (Optional)
**What to say:** *"I also built automated test scripts to ensure data integrity across all phases."*
```bash
bash phase-test-scripts/test_phase1.sh
bash phase-test-scripts/test_phase2.sh
```
