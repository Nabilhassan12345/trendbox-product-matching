# Match Quality — demo prep (ops)

Ops-only checklist for presenting the **Quality** tab to stakeholders (e.g. Sude).  
Assumes macOS/Linux shell; API on **8000**, Streamlit on **8501**.

---

## 1. Stop old servers

Free ports before a clean start (ignore errors if nothing is listening):

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null; lsof -ti :8501 | xargs kill -9 2>/dev/null
```

Confirm ports are free:

```bash
lsof -i :8000 -i :8501
# (no output = OK)
```

---

## 2. Start the stack

### Option A — Full refresh (recommended first demo of the day)

Rebuilds TF-IDF + FAISS, reloads catalogue, **re-runs batch** (repopulates `size_verdict`), starts API + UI:

```bash
cd /path/to/trendbox-product-matching
python3 pipeline.py --rebuild
```

First run after model download can take several minutes.

### Option B — Indexes unchanged, only refresh match quality data

If `data/matcher_index/` is already current and you only need fresh matches + quality fields:

```bash
cd /path/to/trendbox-product-matching
# Terminal 1 — batch only (no UI), ~1–3 min typical
python3 scripts/run_batch.py

# Terminal 2 — API + UI without re-matching
python3 pipeline.py --skip-batch
```

Or API/UI manually after batch:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
streamlit run ui/app.py --server.port 8501
```

**Do not** use `pipeline.py --skip-batch` alone if the DB still has stale quality metadata (see §3).

---

## 3. Stale DB: `size_verdict` all `size_unknown`?

**Symptom:** `python3 scripts/audit_size_quality.py` shows `size_unknown` ≈ 100% of rank-1 rows, `size_verified` / `size_conflict` = 0, `catalog_integrity_pct` = 0%.

**Cause:** Match rows were created **before** Match Quality (Phases 1–5) or before a batch run with the current matcher/triage code. The schema columns exist (migration adds them), but **values are only written during batch** (`run_full_batch` → `replace_matches`).

**Fix — full re-batch is required:**

| Action | Updates `size_verdict`? |
|--------|-------------------------|
| `run_full_batch` / `python3 scripts/run_batch.py` / `POST /batch_process` | **Yes** — replaces all match rows |
| `pipeline.py` without `--skip-batch` | **Yes** (runs batch in step 7) |
| `pipeline.py --skip-batch` | **No** |
| Restart API only | **No** |
| `--rebuild` alone (with `--skip-batch`) | **No** |

Re-batch **deletes all existing `matches` and `decisions`** and rebuilds from scratch. Plan demo accordingly (no preserved operator decisions).

After re-batch, verify:

```bash
python3 scripts/audit_size_quality.py
```

Expect non-zero `size_verified` and/or `size_conflict`, and `size_conflict + auto_approved` = **0**.

---

## 4. Verify `/quality/summary`

With API running:

```bash
curl -s http://localhost:8000/quality/summary | python3 -m json.tool
```

Example shape:

```json
{
  "size_verified_count": 12345,
  "size_conflict_count": 234,
  "size_unknown_count": 17890,
  "catalog_integrity_pct": 0.9812,
  "guardrail_blocked_count": 234
}
```

**Healthy demo signals:**

| Field | Expect |
|-------|--------|
| `size_verified_count` + `size_conflict_count` + `size_unknown_count` | ≈ rank-1 product count (~38k–42k unmatched triaged) |
| `guardrail_blocked_count` | = `size_conflict_count` (rank-1) |
| `catalog_integrity_pct` | **0.85–1.0** when verified+conflict > 0 (ratio of matching pack sizes among *known* pairs) |
| `size_conflict_count` with `auto_approved` | **0** (audit script or Quality UI — conflicts must not be auto-approved) |

If all counts are zero except `size_unknown` ≈ total → re-batch (§3).

---

## 5. Expected KPI ranges (ballpark)

Based on catalogue profile (`~45%` unmatched rows missing weight in `data/reports/catalog_profile.json`):

| KPI | Typical range | Notes |
|-----|---------------|--------|
| **SIZE UNKNOWN** | **40–55%** of rank-1 matches | One or both sides lack parseable pack size — not a bug |
| **SIZE CONFLICTS** | **~0.5–5%** of rank-1 | Both sides have weight and they differ |
| **CATALOG INTEGRITY** | **85–99%** | Among pairs with known sizes only; 0% if no verified/conflict yet |
| **GUARDRAIL BLOCKS** | = conflict count | Conflicts blocked from auto-approve |

Home footer **Integrity %** and **Size conflicts** use the same `/quality/summary` endpoint.

---

## 6. Five-minute demo script — Quality page

**0:00 — Context (Home)**  
Open http://localhost:8501 → **Home**. Point to **Integrity %** and **Size conflicts** in the Catalog snapshot footer.  
*“These update live from rank-1 pack-size checks on every match.”*

**0:30 — Open Quality**  
Nav → **Quality**.  
*“This is the audit view for pack-size guardrails across the whole catalogue.”*

**1:00 — KPI row (top)**  
Walk the four cards:

1. **Catalog integrity** — share of known-size pairs that agree  
2. **Size conflicts** — mismatches that need attention (red if > 0)  
3. **Guardrail blocks** — conflicts prevented from auto-approve  
4. **Size unknown** — incomplete weight metadata (often large)

**1:30 — Size conflicts tab**  
Show side-by-side source vs suggestion; red left border; weight pills (green/red).  
*“Operator sees exactly which pack size disagrees before approving anything.”*  
If a **pending** row exists: click **Reject match** → toast → row leaves queue.  
If **auto_rejected** under conflict policy: show **Reopen**.

**2:30 — Verified tab**  
*“Pairs where we extracted the same pack size — low risk for size-driven mistakes.”*

**3:00 — Incomplete tab**  
*“Missing weight on one or both names — we don’t guess; these stay unknown.”*  
→ Use talking point in §7.

**3:30 — Review cross-link (optional)**  
**Review** tab → pending item with `size_conflict` → amber banner *“Pack size mismatch — source X vs suggestion Y”*.

**4:30 — Audit CLI (optional, terminal)**  

```bash
python3 scripts/audit_size_quality.py
```

*“Offline check that no conflict is still auto-approved — should print `(none — OK)`.”*

**5:00 — Close**  
*“Guardrail: conflicts never auto-approve. Policy `TRENDBOX_SIZE_CONFLICT_POLICY=review` sends them to operators; `reject` auto-rejects. Retrieval now filters obvious weight mismatches before rerank.”*

---

## 7. If `size_unknown` is high (~45%)

**What to say:**

> “About half our unmatched catalogue doesn’t have a reliable pack size in the product name — that’s a **data enrichment** gap, not a matcher failure. For those rows we mark **size unknown** and **don’t** apply a size-based auto-approve block. Integrity % only measures rows where **both** sides have a parseable weight. Improving names or adding a weight column in source data would shrink the unknown band and raise confidence in integrity metrics.”

**Supporting fact:** `catalog_profile.json` reports `unmatched_missing_weight_pct` ≈ **45%**.

**Do not say:** “Unknown means the matcher failed.”

---

## 8. Pre-demo smoke (2 minutes)

```bash
python3 -m pytest tests/ -q
python3 scripts/audit_size_quality.py
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8000/quality/summary | python3 -m json.tool
```

---

## 9. Environment reminder

| Variable | Demo default | Effect |
|----------|--------------|--------|
| `TRENDBOX_SIZE_CONFLICT_POLICY` | `review` | Conflicts → pending queue |
| | `reject` | Conflicts → auto_rejected (show **Reopen** on Quality) |

Set in `.env` before `pipeline.py` if you want to demo the reject policy.

---

## 10. Security note (stakeholder Q&A)

Demo on **localhost only** (`127.0.0.1`). API has no auth in this build — fine for a laptop demo, not for shared hosting without hardening.
