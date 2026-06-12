# Trendbox Product Matching

An end-to-end ML system that links unmatched Turkish retail product names to a barcoded reference catalogue of ~100k items. It auto-approves confident matches, routes uncertain ones to a human reviewer, and rejects weak ones — turning days of manual SKU matching into minutes, without giving up control over catalogue quality.

```
RAW DATA → PREPROCESS → TF-IDF RETRIEVE (top 50) → EMBEDDING RERANK (top 3)
         → CONFIDENCE SCORE → AUTO-APPROVE / REVIEW / REJECT → OPERATOR UI
```

## Quick Start

Requires **Python 3.10+**.

```bash
git clone https://github.com/Nabilhassan12345/trendbox-product-matching.git
cd trendbox-product-matching
pip install -r requirements.txt
pip install -e .          # optional: editable install (removes sys.path hacks)
python pipeline.py
```

`pipeline.py` loads the data, builds or restores cached indexes, runs batch matching, starts the API on `:8000`, and opens the UI on `:8501`. Add `--skip-batch` to start the app without re-matching when the database is already populated.

| Service | URL |
|---------|-----|
| Operator UI | http://localhost:8501 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

## How It Works

**Two-stage retrieve-then-rerank.** Comparing 42k unmatched products against 58k references with an embedding model alone is too slow. Stage 1 uses character-level TF-IDF to retrieve the 50 closest candidates in milliseconds; Stage 2 reranks them with the multilingual `paraphrase-multilingual-MiniLM-L12-v2` model for semantic accuracy.

**Confidence scoring drives triage.** Each candidate gets an ensemble score that also ranks results, so brand/size mismatches are demoted rather than just flagged:

```
confidence = 0.50·TF-IDF + 0.50·embedding
           + brand/weight match bonus  (+0.05 each)
           − brand/weight mismatch penalty  (−0.30 brand, −0.20 weight)
```

| Confidence | Action |
|-----------|--------|
| > 0.90 | Auto-approved — linked without review |
| 0.60 – 0.90 | Pending — sent to the operator queue |
| < 0.60 | Auto-rejected |

The 50/50 weighting and mismatch penalties are evidence-based: evaluation showed the embedding model scores brand/size/flavour-swapped near-duplicates very highly, so TF-IDF is given equal weight and explicit mismatches are penalised — a different brand or pack size almost always means a different barcode.

**Human-in-the-loop.** Medium-confidence matches surface in the Streamlit **Review** page with ranked suggestions and explanations; operators approve or reject, decisions persist to SQLite, and the **Analytics** page tracks match rate, confidence distribution, and throughput.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Retrieval (Stage 1) | scikit-learn TF-IDF (char n-grams) |
| Reranking (Stage 2) | sentence-transformers + FAISS |
| Persistence | SQLAlchemy + SQLite |
| API | FastAPI + Pydantic |
| UI | Streamlit + Plotly |
| Data / caching | pandas, joblib |

## Project Structure

```
pipeline.py              # Single entry point: load → index → batch → API → UI
pyproject.toml           # Package metadata + `trendbox` CLI entry point
src/
  config.py              # Central paths, ports, env overrides
  db/                    # ORM models, session, catalog, matches, analytics
  index_builder.py       # TF-IDF / FAISS build + cache (data/matcher_index/)
  preprocess.py          # Turkish normalisation, brand/weight extraction, product kind
  reference_catalog.py   # Canonical DB rows vs full alias search index
  blocking.py            # Stage 0 exact/fuzzy name resolver
  data_profile.py        # Catalogue quality metrics
  tfidf_retriever.py     # Stage 1: TF-IDF retrieval
  embedding_reranker.py  # Stage 2: embeddings, FAISS, batched rerank
  confidence.py          # Ensemble scoring + triage bands
  matcher.py             # Orchestrates the two-stage pipeline
  batch.py               # Product-level batch triage (shared by pipeline + API)
  database.py            # SQLAlchemy models + persistence
api/                     # FastAPI app (main.py) + Pydantic schemas
ui/
  app.py                 # Streamlit home
  pages/01_Review.py     # Operator review queue
  pages/02_Analytics.py  # Match-rate and confidence dashboards
  pages/03_Pipeline.py   # Catalog quality and pipeline stats
  utils/theme.py         # CSS design tokens
  utils/components.py    # HTML badge/chip builders
  utils/layout.py        # Page headers and navigation
  utils/charts.py        # Shared Plotly chart builders
notebooks/               # 01_exploration, 02_experiments
scripts/                 # evaluate.py, profile_data.py, run_batch.py
tests/                   # Unit + API integration suites
docs/                    # DATA_PIPELINE.md, CALISMA_RAPORU.md (Turkish report)
data/reports/            # Generated JSON reports (catalog profile, evaluation)
```

## Testing & Evaluation

```bash
pytest tests/                                 # unit + API integration tests
python tests/run_all_tests.py                 # full verification (files + imports + pytest)
python scripts/evaluate.py --max-queries 1000 # recall@k + precision/coverage sweep
python scripts/profile_data.py                # write data/reports/catalog_profile.json
python scripts/run_batch.py                   # re-run matching without starting API/UI
```

The evaluation mines ground truth from the catalogue itself (products sharing a barcode but spelled differently), holds each spelling out of the index, and checks whether the pipeline recovers the correct barcode. It reports **Recall@1/@3** for each approach plus a **precision-vs-coverage sweep** — the evidence behind the confidence thresholds.

## Data pipeline

Catalogue ingestion uses a **cascaded resolver** rather than ML-only matching:

1. **Profile** — `python scripts/profile_data.py` quantifies duplicates, collisions, and dedupe loss
2. **Normalize + enrich** — Turkish folding, units, brand/weight, product kind (`fresh` vs `branded`)
3. **Alias index** — all 58k barcoded spellings indexed; SQLite keeps one canonical row per barcode
4. **Stage 0** — exact/fuzzy name blocking before TF-IDF (see [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md))
5. **Stages 1–2** — TF-IDF retrieval + embedding rerank (unchanged architecture)
6. **Kind-aware confidence** — fresh produce skips false brand-mismatch penalties

After changing reference data or blocking rules, rebuild indexes:

```bash
python pipeline.py --rebuild
```

## Configuration

All variables are optional (sensible defaults). Copy `.env.example` to `.env` to override:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TRENDBOX_DATA_CSV` | `data/mix_products.csv` | Source catalogue CSV |
| `TRENDBOX_DB_PATH` | `data/matching.db` | SQLite database path |
| `TRENDBOX_MATCHER_INDEX` | `data/matcher_index` | Matcher index directory (API load path) |
| `TRENDBOX_CATALOG_PROFILE` | `data/reports/catalog_profile.json` | Catalog quality report |
| `TRENDBOX_API_URL` | `http://localhost:8000` | API base URL for the UI |
| `TRENDBOX_API_PORT` | `8000` | API port when started by `pipeline.py` |
| `TRENDBOX_UI_PORT` | `8501` | Streamlit port when started by `pipeline.py` |

## License

Released under the [MIT License](LICENSE).
