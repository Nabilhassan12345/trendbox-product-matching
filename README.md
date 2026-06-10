# trendbox-product-matching

Two-stage product matching for Turkish retail catalogue data: TF-IDF retrieval → multilingual embedding rerank → human review.

## Quick start (local)

```bash
pip install -r requirements.txt

# Build matcher index (first time only)
python3 -m src.matcher

# Load products + run matching via API, or use the Streamlit UI
uvicorn api.main:app --reload --port 8000
streamlit run ui/app.py --server.port 8501
```

- **UI:** http://localhost:8501  
- **API docs:** http://localhost:8000/docs  

## Deploy Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Set **Main file path** to `ui/app.py`.
4. Add a secret in app settings:

   ```toml
   TRENDBOX_API_URL = "https://your-deployed-api.example.com"
   ```

5. Deploy.

> **Note:** Streamlit Cloud hosts the UI only. Deploy the FastAPI backend separately (e.g. Railway, Render, Fly.io) and point `TRENDBOX_API_URL` at it. The backend needs the matcher index built on the server or loaded from storage.

## Project layout

| Path | Purpose |
|------|---------|
| `src/` | Matching pipeline, preprocessing, database |
| `api/` | FastAPI REST service |
| `ui/` | Streamlit multipage operator UI |
| `data/mix_products.csv` | Source catalogue (~100k products) |
| `tests/test_api.py` | API integration checks |

## Tests

```bash
python3 tests/test_api.py
```
