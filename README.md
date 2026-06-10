# Trendbox Product Matching System

Trendbox Product Matching is an end-to-end ML system that links unmatched Turkish retail product names to a barcoded reference catalogue of ~100,000 items. Retail teams spend hours manually pairing supplier descriptions with internal SKUs; this pipeline automates the easy cases, surfaces uncertain matches for human review, and rejects low-confidence suggestions—cutting manual effort while keeping catalogue quality under operator control.

---

## System Architecture

```
RAW DATA → PREPROCESSING → [BARCODED: FAISS INDEX] + [UNMATCHED: EMBEDDING MODEL]
    → TWO-STAGE PIPELINE → CONFIDENCE SCORING → AUTO-APPROVE / REVIEW / REJECT
    → OPERATOR UI → FEEDBACK LOOP
```

| Stage | Component | Role |
|-------|-----------|------|
| **Raw data** | `data/mix_products.csv` | Pipe-separated catalogue: barcoded reference rows and unmatched rows needing links |
| **Preprocessing** | `src/preprocess.py` | Strips `^` markers, normalises Turkish text, extracts brand/weight features |
| **Barcoded: FAISS index** | `src/embedding_reranker.py` | Pre-computed multilingual embeddings for 58,434 reference products, indexed for fast vector search |
| **Unmatched: embedding model** | `paraphrase-multilingual-MiniLM-L12-v2` | Encodes each query product at match time for semantic comparison |
| **Two-stage pipeline** | `src/tfidf_retriever.py` + `src/matcher.py` | Stage 1: TF-IDF retrieves top 50 candidates; Stage 2: embeddings rerank to top 3 |
| **Confidence scoring** | `src/confidence.py` | Blends TF-IDF (50%) + embedding (50%) scores with brand/weight bonuses and mismatch penalties |
| **Auto-approve / review / reject** | `src/database.py`, `api/main.py` | Routes matches by confidence: >0.90 auto-approve, 0.60–0.90 pending review, <0.60 auto-reject |
| **Operator UI** | `ui/` (Streamlit) | Review queue, analytics dashboard, approve/reject workflow |
| **Feedback loop** | `POST /decision/{id}` | Operator decisions persist to SQLite and feed analytics for quality monitoring |

---

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Data processing | **pandas** | Load and clean 100k+ row pipe-delimited CSV efficiently |
| Stage 1 retrieval | **scikit-learn** (TF-IDF) | Fast character-level candidate filtering for Turkish product names |
| Stage 2 reranking | **sentence-transformers** | Multilingual semantic similarity without per-language models |
| Vector search | **FAISS** | Sub-second nearest-neighbour search over 58k reference embeddings |
| Persistence | **SQLAlchemy** + **SQLite** | Lightweight local DB for products, matches, and operator decisions |
| API layer | **FastAPI** + **Pydantic** | Typed REST endpoints for matching, stats, and review workflow |
| Operator UI | **Streamlit** + **Altair** | Multipage review interface with live analytics charts |
| Index caching | **joblib** | Persist TF-IDF vectoriser and FAISS metadata between runs |
| Testing | **FastAPI TestClient** | Integration tests for every API endpoint |

---

## Installation

Requires **Python 3.10+**.

```bash
git clone https://github.com/Nabilhassan12345/trendbox-product-matching.git && cd trendbox-product-matching
pip install -r requirements.txt
python pipeline.py
```

The pipeline loads data, builds or restores cached indexes, runs batch matching, starts the API on **http://localhost:8000**, and opens the UI on **http://localhost:8501**.

Configuration is optional — every variable has a sensible default. To override (e.g. for deployment), copy the template and edit it:

```bash
cp .env.example .env
```

To skip batch matching when results already exist in the database:

```bash
python pipeline.py --skip-batch
```

---

## How It Works

### 1. Two-Stage Retrieve-Then-Rerank Pipeline

Matching 42,000 unmatched products against 58,000 references with a single embedding model would be too slow. The system splits the problem:

**Stage 1 — TF-IDF retrieval (top 50)**  
Each unmatched product name is normalised (Turkish character folding, unit standardisation, lowercase). A TF-IDF vectoriser scores all barcoded products and returns the 50 most similar candidates in milliseconds.

**Stage 2 — Embedding rerank (top 3)**  
The query and top-50 candidates are encoded with `paraphrase-multilingual-MiniLM-L12-v2`. Cosine similarity reranks them; the three highest-scoring matches are returned with TF-IDF score, embedding score, and a plain-language explanation.

### 2. Confidence Scoring

Each candidate receives an ensemble confidence score, which also ranks the
candidates (so brand/size mismatches are demoted, not just flagged):

```
confidence = (0.50 × TF-IDF) + (0.50 × embedding)
             + brand/weight match bonus (+0.05 each)
             − brand/weight mismatch penalty (−0.30 brand, −0.20 weight)
```

| Band | Threshold | Action |
|------|-----------|--------|
| High | > 0.90 | Auto-approved — linked without human review |
| Medium | 0.60 – 0.90 | Pending — sent to operator review queue |
| Low | < 0.60 | Auto-rejected — not shown as a viable match |

The weighting and penalties are evidence-based: evaluation (`scripts/evaluate.py`)
showed the embedding model assigns very high similarity to brand/size/flavour-
swapped near-duplicates, so the blend gives TF-IDF equal weight and penalises
explicit brand/weight mismatches — a different brand or pack size almost always
means a different barcode.

### 3. Human-in-the-Loop Review

Medium-confidence matches land in the Streamlit **Review** page. Operators see the unmatched product, up to three ranked suggestions with confidence pills and explanations, and approve or reject each match. Decisions are saved via `POST /decision/{id}` to SQLite and reflected in the **Analytics** dashboard (match rates, confidence distribution, approval timeline). High-confidence matches flow straight through; low-confidence ones are filtered out—keeping the review queue focused on cases where human judgment adds value.

---

## Project Structure

```
trendbox-product-matching/
├── pipeline.py                  # Single entry point: load → index → batch → API → UI
├── requirements.txt             # Pinned Python dependencies
├── .env.example                 # Template for optional environment configuration
├── README.md                    # This file
│
├── data/
│   ├── mix_products.csv         # Source catalogue (~100,585 rows, pipe-separated)
│   ├── matching.db              # SQLite database (created at runtime)
│   ├── tfidf_cache/             # Cached TF-IDF vectoriser (created at runtime)
│   ├── faiss_cache/             # Cached FAISS index + embeddings (created at runtime)
│   └── matcher_index/           # Unified matcher snapshot for API startup (created at runtime)
│
├── src/
│   ├── preprocess.py            # CSV loading, ^ stripping, Turkish normalisation, brand/weight extraction
│   ├── tfidf_retriever.py       # Stage 1: TF-IDF fit, search, and cache I/O
│   ├── embedding_reranker.py    # Stage 2: SentenceTransformer encode, FAISS index, rerank
│   ├── confidence.py            # Ensemble scoring, triage bands, UI colour tokens
│   ├── matcher.py               # Orchestrates two-stage pipeline; build/load/save index
│   └── database.py              # SQLAlchemy models, product load, match persistence, stats
│
├── api/
│   ├── main.py                  # FastAPI app: health, stats, analytics, match queue, decisions, batch
│   └── schemas.py               # Pydantic request/response models
│
├── ui/
│   ├── app.py                   # Streamlit home page (health metrics, batch trigger)
│   ├── api_client.py            # Shared API URL config and HTTP helpers
│   ├── theme.py                 # Shared CSS and layout components
│   ├── _bootstrap.py            # Adds project root to sys.path for Streamlit imports
│   └── pages/
│       ├── 01_Review.py         # Operator review queue (approve / reject)
│       └── 02_Analytics.py      # Dashboard: match rates, charts, recent decisions
│
├── notebooks/
│   ├── 01_exploration.ipynb     # EDA: data quality, Turkish text patterns, architecture rationale
│   └── 02_experiments.ipynb     # Prototype TF-IDF + embedding experiments and threshold tuning
│
├── tests/
│   ├── run_all_tests.py         # Full verification: files, imports, data load, API tests
│   └── test_api.py              # 30 integration checks for every FastAPI endpoint
│
├── scripts/
│   ├── evaluate.py              # Held-out recall@k + confidence threshold sweep
│   └── run_batch.py             # Run batch matching only (no API/UI)
└── .streamlit/
    └── config.toml              # Streamlit theme and server settings
```

---

## Running Tests

```bash
python tests/run_all_tests.py
```

This runs six verification suites: required-file checks, module import smoke tests, CSV load validation (100,585 rows), preprocessing unit tests, matcher end-to-end tests, and API integration tests. All must pass before submission.

To run a single suite:

```bash
python tests/test_preprocess.py   # fast, no model required
python tests/test_matcher.py      # builds a small matcher (needs the embedding model)
python tests/test_api.py          # FastAPI endpoint integration tests
```

---

## Evaluation

Accuracy is measured against ground truth mined from the catalogue itself:
products that share a barcode but are spelled differently are, by definition, the
same product. Each run holds one spelling out of the reference index and checks
whether the pipeline recovers the correct barcode.

```bash
python scripts/evaluate.py --max-queries 1000 --target-precision 0.95
```

It reports **Recall@1 / Recall@3** for TF-IDF only, embeddings only, and the
two-stage pipeline, plus a **precision-vs-coverage sweep** over the rank-1
confidence score — the evidence used to set the auto-approve / auto-reject
thresholds. The reference index reuses cached embeddings, so a run takes about a
minute on CPU after the one-time model load.

---

## Quick Reference

| Service | URL |
|---------|-----|
| Streamlit UI | http://localhost:8501 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

**Environment variables** (optional):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TRENDBOX_DB_PATH` | `data/matching.db` | SQLite database path |
| `TRENDBOX_MATCHER_INDEX` | `data/matcher_index` | Matcher index directory |
| `TRENDBOX_API_URL` | `http://localhost:8000` | API base URL for Streamlit UI |
