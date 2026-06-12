"""Operator review interface — Labelbox-style design."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
import streamlit as st
import streamlit.components.v1 as components

from ui.api_client import api_get, api_post, api_post_json, get_api_url, is_connection_error
from ui.utils.styles import (
    conf_bar_html,
    inject_styles,
    match_source_chip_html,
    product_kind_pill_html,
    progress_bar_html,
    render_page_header,
    render_page_nav,
    render_section_header,
    section_label,
    show_offline_card,
)
from ui.utils.tables import render_match_history_table

ADVANCE_DELAY = 0.4
# Sentinel stored in session_state.current to mean "loaded — but queue was empty".
# Distinguishes "never fetched" (None) from "fetched and got nothing" so the
# first-load trigger doesn't spin forever when the queue is exhausted.
QUEUE_EMPTY: str = "__queue_empty__"

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Review · Trendbox",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

# Inline the animation + skeleton CSS directly in the page so they're
# never stale due to Python module-cache issues on the shared styles module.
st.markdown(
    """
    <style>
    /* ── Product name entrance animation ── */
    @keyframes name-flash {
      0%   { opacity: 0.12; transform: translateY(6px); }
      100% { opacity: 1;    transform: translateY(0);   }
    }
    .product-name-animate {
      animation: name-flash 0.35s ease-out 1 both;
    }

    /* ── Skeleton shimmer (200% approach — responsive, no fixed px width) ── */
    @keyframes shimmer {
      0%   { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
    .skeleton-line {
      background: linear-gradient(
        90deg,
        #F3F4F6 25%,
        #E5E7EB 50%,
        #F3F4F6 75%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
      border-radius: 6px;
    }

    /* ── Bottom bar button hovers ── */
    .st-key-approve_top button:hover {
      background: #374151 !important;
      box-shadow: 0 0 0 3px rgba(17,24,39,0.18) !important;
    }
    .st-key-reject_all button:hover {
      background: #FEE2E2 !important;
      color: #DC2626 !important;
    }

    @keyframes cardSlideIn {
      from { opacity: 0; transform: translateY(10px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }
  @keyframes tabPop {
    from { transform: scale(0.96); }
    to   { transform: scale(1); }
  }
  [data-testid="stRadio"] label:has(input:checked) {
    animation: tabPop 0.22s ease-out;
  }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────

def _init() -> None:
    defaults: dict = {
        "current": None,
        "initial_pending": None,
        "reviewed_count": 0,
        "approved_today": 0,
        "rejected_today": 0,
        "transition": None,        # None | "skeleton" | "load"
        "last_toast": "",
        "operator_note": "",
        "new_product_loaded": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init()

# ── API helpers ───────────────────────────────────────────────────────────────

def _load_next() -> tuple[dict | None, bool]:
    try:
        r = requests.get(f"{get_api_url()}/match/next", timeout=30)
        if r.status_code == 404:
            return None, False
        r.raise_for_status()
        return r.json(), False
    except requests.RequestException as exc:
        return None, is_connection_error(exc)


def _decide(match_id: int, decision: str, note: str = "") -> tuple[bool, bool]:
    ok, offline = api_post(
        f"/decision/{match_id}",
        json={"decision": decision, "note": note or None},
        timeout=30,
    )
    if ok:
        if decision == "approved":
            st.session_state.approved_today += 1
        else:
            st.session_state.rejected_today += 1
        st.session_state.reviewed_count += 1
    return ok, offline


# ── Skeleton renderer ─────────────────────────────────────────────────────────

def _render_skeleton() -> None:
    """Animated shimmer placeholder shown while next product loads."""
    st.markdown(
        """
        <div style="display:flex; gap:24px; padding:0 8px;">

          <div style="flex:4;">
            <div class="lb-card" style="min-height:200px; padding:20px 24px;">
              <div class="section-label" style="opacity:0.35; margin-bottom:16px;">
                ⟳ Loading next...
              </div>
              <span class="skeleton-line" style="height:26px; width:78%; display:block;
                           margin-bottom:12px;"></span>
              <span class="skeleton-line" style="height:26px; width:56%; display:block;
                           margin-bottom:18px;"></span>
              <span class="skeleton-line" style="height:18px; width:34%; display:block;
                           margin-bottom:8px;"></span>
              <span class="skeleton-line" style="height:18px; width:44%; display:block;">
              </span>
            </div>
          </div>

          <div style="flex:6;">
            <div class="section-label" style="opacity:0.35; margin-bottom:12px;">
              AI SUGGESTIONS
            </div>
            <div class="lb-card" style="padding:14px 16px; margin-bottom:10px;">
              <span class="skeleton-line" style="height:22px; width:28%; display:block;
                           margin-bottom:10px;"></span>
              <span class="skeleton-line" style="height:16px; width:82%; display:block;
                           margin-bottom:8px;"></span>
              <span class="skeleton-line" style="height:12px; width:52%; display:block;">
              </span>
            </div>
            <div class="lb-card" style="padding:14px 16px; margin-bottom:10px;">
              <span class="skeleton-line" style="height:22px; width:28%; display:block;
                           margin-bottom:10px;"></span>
              <span class="skeleton-line" style="height:16px; width:75%; display:block;
                           margin-bottom:8px;"></span>
              <span class="skeleton-line" style="height:12px; width:46%; display:block;">
              </span>
            </div>
            <div class="lb-card" style="padding:14px 16px;">
              <span class="skeleton-line" style="height:22px; width:28%; display:block;
                           margin-bottom:10px;"></span>
              <span class="skeleton-line" style="height:16px; width:68%; display:block;
                           margin-bottom:8px;"></span>
              <span class="skeleton-line" style="height:12px; width:40%; display:block;">
              </span>
            </div>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


# ── State machine Phase 2: "load" ─────────────────────────────────────────────
# Runs BEFORE stats and the top bar for a fast early-exit rerun.
# Stores QUEUE_EMPTY so an exhausted queue doesn't re-trigger the skeleton loop.

if (
    st.session_state.transition == "load"
    and st.session_state.get("review_view", "pending") == "pending"
):
    nxt, offline = _load_next()
    if offline:
        st.session_state.transition = None
        show_offline_card()
    st.session_state.current = nxt if nxt is not None else QUEUE_EMPTY
    st.session_state.new_product_loaded = nxt is not None
    st.session_state.transition = None
    if st.session_state.last_toast:
        st.toast(st.session_state.last_toast)
    st.session_state.last_toast = ""
    st.rerun()

# ── Load stats ────────────────────────────────────────────────────────────────

stats, stats_offline = api_get("/stats", timeout=5)
if stats_offline:
    show_offline_card()
if stats is None:
    st.error("Could not load statistics from the API.")
    st.stop()

pending_total = int(stats.get("pending", 0))
auto_approved = int(stats.get("auto_approved", 0))
operator_approved = int(stats.get("operator_approved", 0))
approved_total = auto_approved + operator_approved
rejected = int(stats.get("rejected", 0))

if st.session_state.initial_pending is None:
    st.session_state.initial_pending = pending_total

render_page_nav("review", alive=True)

render_page_header(
    "Operator review",
    "Approve or reject AI-suggested product matches. Use keyboard shortcuts for speed.",
    eyebrow="Trendbox",
    live=True,
)

# ── First load ─────────────────────────────────────────────────────────────────
# Only triggers when current is truly None (not QUEUE_EMPTY).
# QUEUE_EMPTY means we already fetched and the queue was empty → show empty state.

if (
    st.session_state.current is None
    and st.session_state.transition is None
    and st.session_state.get("review_view", "pending") == "pending"
):
    st.session_state.transition = "skeleton"
    st.rerun()

# Resolve the QUEUE_EMPTY sentinel → None so the empty-state check below works.
_raw = st.session_state.current
current = None if _raw == QUEUE_EMPTY else _raw

# Consume the animation flag immediately so it fires exactly once per load.
animate_product = st.session_state.new_product_loaded
st.session_state.new_product_loaded = False

# ── Queue toolbar ─────────────────────────────────────────────────────────────

_tab_labels = {
    "pending": f"Pending ({pending_total:,})",
    "approved": f"Approved ({approved_total:,})",
    "rejected": f"Rejected ({rejected:,})",
}

tab_col, refresh_col = st.columns([6, 1], gap="small")
with tab_col:
    st.radio(
        "Queue",
        options=list(_tab_labels.keys()),
        format_func=lambda key: _tab_labels[key],
        horizontal=True,
        label_visibility="collapsed",
        key="review_view",
    )
with refresh_col:
    if st.button("Refresh", key="top_refresh", use_container_width=True, help="Reload queue"):
        st.session_state.current = None
        st.session_state.transition = None
        st.rerun()

# ── State machine Phase 1: "skeleton" ─────────────────────────────────────────
# Placed AFTER the top bar so the navigation stays visible during loading.

if (
    st.session_state.transition == "skeleton"
    and st.session_state.get("review_view", "pending") == "pending"
):
    _render_skeleton()
    time.sleep(ADVANCE_DELAY)
    st.session_state.transition = "load"
    st.rerun()

# ── APPROVED / REJECTED HISTORY (read-only) ───────────────────────────────────

_review_view = st.session_state.get("review_view", "pending")
if _review_view in ("approved", "rejected"):
    history, hist_offline = api_get(
        "/matches/recent",
        timeout=10,
        params={"outcome": _review_view, "limit": 200},
    )
    if hist_offline:
        show_offline_card()
    title = (
        "AUTO-APPROVED & OPERATOR-APPROVED MATCHES"
        if _review_view == "approved"
        else "AUTO-REJECTED & OPERATOR-REJECTED MATCHES"
    )
    empty = (
        "No approved matches recorded yet."
        if _review_view == "approved"
        else "No rejected matches recorded yet."
    )
    render_section_header(
        "Match history",
        "Read-only log of resolved matches from the live database.",
    )
    def _reopen_match(match_id: int) -> None:
        data, offline = api_post_json(f"/matches/{match_id}/reopen", timeout=30)
        if offline:
            show_offline_card()
            return
        if data:
            st.session_state.last_toast = "Match re-queued for review"
            st.rerun()

    with st.container(border=True):
        render_match_history_table(
            history or [],
            title=title,
            empty_message=empty,
            allow_reopen=_review_view == "rejected",
            on_reopen=_reopen_match if _review_view == "rejected" else None,
        )
    if _review_view == "approved":
        st.caption(
            f"{auto_approved:,} auto-approved · {operator_approved:,} operator-approved "
            "from live database"
        )
    else:
        st.caption(f"{rejected:,} total rejected outcomes from live database")
    st.stop()

# ── EMPTY / SUCCESS STATE ─────────────────────────────────────────────────────

if current is None:
    total_matches = auto_approved + rejected + pending_total
    if total_matches == 0:
        st.markdown(
            """
            <div class="lb-card" style="text-align:center; padding:56px 24px;
                max-width:560px; margin:48px auto;">
              <div style="font-size:36px; margin-bottom:12px;">📭</div>
              <div style="font-size:17px; font-weight:700; color:#111827; margin-bottom:8px;">
                No match records yet
              </div>
              <div style="font-size:13px; color:#6B7280;">
                Go to the <strong>Home</strong> page and click
                <strong>Run batch process</strong> to populate the review queue.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        empty_col1, empty_col2, empty_col3 = st.columns([1, 1.2, 1])
        with empty_col2:
            st.markdown(
                """
                <div style="text-align:center; padding:48px 0 20px;">
                  <div style="width:72px; height:72px; border-radius:50%;
                               background:#D1FAE5; display:flex; align-items:center;
                               justify-content:center; margin:0 auto 24px;
                               font-size:32px; color:#059669; font-weight:700;">✓</div>
                  <div style="font-size:24px; font-weight:700; color:#111827;
                               margin-bottom:10px;">All caught up!</div>
                  <div style="font-size:14px; color:#6B7280; margin-bottom:20px;">
                    No products pending review.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("View Analytics →", key="empty_analytics", use_container_width=True):
                st.switch_page("pages/02_Analytics.py")
    st.stop()

# ── Session progress ────────────────────────────────────────────────────────

render_section_header(
    "Session progress",
    f"{pending_total:,} products still in the review queue.",
)

initial = st.session_state.initial_pending or 1
reviewed = st.session_state.reviewed_count
total_q = max(initial, reviewed + pending_total)
pct = reviewed / total_q if total_q else 0.0

st.markdown(
    f"""
    <div class="lb-card" style="padding:16px 24px; margin:0 0 20px 0;">
      <div style="display:flex; justify-content:space-between; align-items:center;
                  margin-bottom:10px;">
        <div>
          <div class="section-label" style="margin-bottom:2px;">REVIEW PROGRESS</div>
          <div style="font-size:15px; font-weight:600; color:#111827;">
            {reviewed:,} of {total_q:,} products reviewed
          </div>
        </div>
        <div style="font-size:24px; font-weight:700; color:#6B7280;">{pct:.1%}</div>
      </div>
      {progress_bar_html(pct, bar_id="review-progress", animate_from_zero=True)}
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Match workspace (input → output) ────────────────────────────────────────

render_section_header(
    "Current match",
    "Source product on the left · ranked suggestions on the right.",
)

left_col, right_col = st.columns([2, 3], gap="large")

product_name = current.get("product_name", "")
product_id = current.get("product_id", "")
brand = current.get("brand") or ""
weight = current.get("weight") or ""
product_kind = current.get("product_kind", "unknown")
suggestions = [s for s in current.get("suggestions", []) if s.get("match_id")][:3]

# De-duplicate by barcode
seen_barcodes: set[str] = set()
unique_suggestions: list[dict] = []
for s in suggestions:
    bc = str(s.get("barcode", ""))
    if bc not in seen_barcodes:
        seen_barcodes.add(bc)
        unique_suggestions.append(s)
suggestions = unique_suggestions[:3]

# ── Left: product card ────────────────────────────────────────────────────────

def _tags_html_lg(b: str, w: str) -> str:
    """Larger tags: 13px font, 4px 12px padding."""
    parts: list[str] = []
    if b:
        parts.append(
            f'<span class="tag tag-brand"'
            f' style="font-size:13px; padding:4px 12px;">{b}</span>'
        )
    if w:
        parts.append(
            f'<span class="tag tag-weight"'
            f' style="font-size:13px; padding:4px 12px;">{w}</span>'
        )
    return "".join(parts)


# Add animation class only on the render immediately after a new product loads.
name_class = "product-name-animate" if animate_product else ""

with left_col:
    st.markdown(
        f"""
        <div class="lb-card" style="min-height:220px;">
          <div class="section-label">PRODUCT TO MATCH</div>
          <hr style="border:none; border-top:1px solid #E5E7EB; margin:0 0 14px 0;">
          <div class="{name_class}"
               style="font-size:22px; font-weight:700; color:#111827;
                      line-height:1.35; margin-bottom:14px;">
            {product_name}
          </div>
          <div style="margin-bottom:14px;">
            {product_kind_pill_html(product_kind)}
            {_tags_html_lg(brand, weight)}
          </div>
          <hr style="border:none; border-top:1px solid #E5E7EB; margin:0 0 10px 0;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:11px; color:#9CA3AF;">ID: #{product_id}</span>
            <span style="font-size:11px; color:#9CA3AF; font-style:italic;">
              Select a match →
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Right: suggestions ────────────────────────────────────────────────────────

CONF_COLORS = {"HIGH": "#10B981", "MEDIUM": "#F59E0B", "LOW": "#EF4444"}

with right_col:
    section_label("AI SUGGESTIONS")

    if not suggestions:
        st.markdown(
            '<div class="lb-card" style="color:#6B7280; text-align:center; padding:32px;">'
            "No suggestions available for this product."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        for idx, suggestion in enumerate(suggestions):
            label = (suggestion.get("confidence_label") or "LOW").upper()
            score = float(suggestion.get("confidence_score", 0))
            name = suggestion.get("name", "")
            barcode = suggestion.get("barcode", "")
            explanation = suggestion.get("explanation", "")
            match_id = suggestion.get("match_id")
            match_source = suggestion.get("match_source", "ml")
            tfidf_score = float(suggestion.get("tfidf_score", 0))
            embedding_score = float(suggestion.get("embedding_score", 0))
            source_chip = match_source_chip_html(match_source)
            scores_html = (
                f'<div style="font-size:11px; color:#6B7280; margin-top:4px;">'
                f"TF-IDF {tfidf_score:.2f} · Embedding {embedding_score:.2f}</div>"
            )

            border = CONF_COLORS.get(label, "#EF4444")
            hover_color = border
            stagger = f"animation:cardSlideIn 0.4s ease-out {0.07 * (idx + 1):.2f}s both;"

            # Explanation: single line, ellipsis truncation, full text in tooltip
            expl_safe = explanation.replace('"', "&quot;")
            expl_html = (
                f'<div style="font-size:11px; font-style:italic; color:#9CA3AF;'
                f' margin-top:6px; overflow:hidden; text-overflow:ellipsis;'
                f' white-space:nowrap;" title="{expl_safe}">'
                f"{explanation}</div>"
                if explanation
                else ""
            )

            info_col, btn_col = st.columns([7, 2])

            with info_col:
                st.markdown(
                    f"""
                    <div class="suggestion-card" id="scard-{match_id}"
                         style="border-left:3px solid {border}; {stagger}">
                      {source_chip}
                      {conf_bar_html(label, score)}
                      <div style="font-size:15px; font-weight:600; color:#111827;
                                  margin-bottom:4px;">{name}</div>
                      {scores_html}
                      <div style="font-family:monospace; font-size:12px;
                                  color:#9CA3AF; margin-bottom:2px;">{barcode}</div>
                      {expl_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with btn_col:
                st.markdown(
                    f"""
                    <style>
                    .st-key-sel_{match_id} button:hover {{
                      background: {hover_color} !important;
                      color: #FFFFFF !important;
                      border-color: {hover_color} !important;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div style="display:flex; align-items:center;'
                    ' height:100%; padding-top:8px;">',
                    unsafe_allow_html=True,
                )
                if match_id and st.button(
                    "Select",
                    key=f"sel_{match_id}",
                    use_container_width=True,
                ):
                    note_val = st.session_state.get("operator_note", "")
                    ok, offline = _decide(match_id, "approved", note_val)
                    if offline:
                        show_offline_card()
                    if ok:
                        st.session_state.last_toast = f"✓ Approved: {name[:40]}"
                        st.session_state.transition = "skeleton"
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

# ── Decision panel ────────────────────────────────────────────────────────────

top_match = next(
    (s for s in suggestions if s.get("rank") == 1),
    suggestions[0] if suggestions else None,
)

with st.container(border=True):
    render_section_header(
        "Record decision",
        "Add an optional note, then approve the top match or reject all suggestions.",
    )
    note_col, prog_col, reject_col, approve_col = st.columns([4, 2, 2, 2], gap="small")

    with note_col:
        st.text_input(
            "Operator note",
            placeholder="Optional note for audit trail…",
            label_visibility="collapsed",
            key="operator_note",
        )

    with prog_col:
        st.markdown(
            f"""
            <div style="text-align:center; padding-top:4px;">
              <div style="font-size:11px; color:#9CA3AF; margin-bottom:4px;">
                {reviewed:,} / {total_q:,} reviewed
              </div>
              {progress_bar_html(pct, height=4)}
              <div style="font-size:10px; color:#D1D5DB; margin-top:6px;
                          letter-spacing:0.04em;">
                A approve · R reject · 1–3 select
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with reject_col:
        if st.button("Reject all", key="reject_all", use_container_width=True):
            if top_match and top_match.get("match_id"):
                ok, offline = _decide(
                    top_match["match_id"],
                    "rejected",
                    st.session_state.get("operator_note", ""),
                )
                if offline:
                    show_offline_card()
                if ok:
                    st.session_state.last_toast = "Match rejected"
                    st.session_state.transition = "skeleton"
                    st.rerun()
            else:
                st.error("Nothing to reject.")

    with approve_col:
        if st.button(
            "Approve top match",
            key="approve_top",
            type="primary",
            use_container_width=True,
        ):
            if top_match and top_match.get("match_id"):
                ok, offline = _decide(
                    top_match["match_id"],
                    "approved",
                    st.session_state.get("operator_note", ""),
                )
                if offline:
                    show_offline_card()
                if ok:
                    st.session_state.last_toast = "✓ Match approved"
                    st.session_state.transition = "skeleton"
                    st.rerun()
            else:
                st.error("No match available.")

# ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────────
# A → Approve Top Match · R → Reject All · 1/2/3 → Select suggestion

_ids = [str(s.get("match_id", "")) for s in suggestions]
_s1 = _ids[0] if len(_ids) > 0 else ""
_s2 = _ids[1] if len(_ids) > 1 else ""
_s3 = _ids[2] if len(_ids) > 2 else ""

components.html(
    f"""
    <script>
    (function() {{
      var doc = window.parent.document;

      // ── Keyboard shortcuts — register only ONCE per page lifetime ──────────
      if (!doc._trendboxKB) {{
        doc._trendboxKB = true;

        function click(sel) {{
          var btn = doc.querySelector(sel);
          if (btn) btn.click();
        }}

        doc.addEventListener('keydown', function(e) {{
          var tag = ((doc.activeElement || {{}}).tagName || '').toUpperCase();
          if (tag === 'INPUT' || tag === 'TEXTAREA') return;
          if (e.ctrlKey || e.metaKey || e.altKey) return;

          switch (e.key) {{
            case 'a': case 'A':
              e.preventDefault(); click('.st-key-approve_top button'); break;
            case 'r': case 'R':
              e.preventDefault(); click('.st-key-reject_all button'); break;
            case '1':
              if ('{_s1}') {{ e.preventDefault(); click('.st-key-sel_{_s1} button'); }} break;
            case '2':
              if ('{_s2}') {{ e.preventDefault(); click('.st-key-sel_{_s2} button'); }} break;
            case '3':
              if ('{_s3}') {{ e.preventDefault(); click('.st-key-sel_{_s3} button'); }} break;
          }}
        }});
      }}

      // ── Success flash — re-attach on EVERY render (React recreates buttons) ─
      function flashCard(mid) {{
        var card = doc.getElementById('scard-' + mid);
        if (card) {{
          card.classList.remove('card-flash-approve');
          // Force reflow so re-adding the class restarts the animation
          void card.offsetWidth;
          card.classList.add('card-flash-approve');
        }}
      }}

      function attachFlash() {{
        // "Approve Top Match" button → flash the first visible suggestion card
        var approveBtn = doc.querySelector('.st-key-approve_top button');
        if (approveBtn && !approveBtn._flashBound) {{
          approveBtn._flashBound = true;
          approveBtn.addEventListener('click', function() {{
            var firstCard = doc.querySelector('[id^="scard-"]');
            if (firstCard) {{
              firstCard.classList.remove('card-flash-approve');
              void firstCard.offsetWidth;
              firstCard.classList.add('card-flash-approve');
            }}
          }});
        }}

        // "Select" buttons → flash corresponding card by match-id
        doc.querySelectorAll('[class*="st-key-sel_"] button').forEach(function(btn) {{
          if (btn._flashBound) return;
          btn._flashBound = true;
          var parent = btn.closest('[class*="st-key-sel_"]');
          if (!parent) return;
          var cls = Array.from(parent.classList).find(function(c) {{
            return c.startsWith('st-key-sel_');
          }});
          if (!cls) return;
          var mid = cls.replace('st-key-sel_', '');
          btn.addEventListener('click', function() {{ flashCard(mid); }});
        }});
      }}

      // Animate progress bar fill on load
      function animateProgress() {{
        var bar = doc.getElementById('review-progress');
        if (bar && bar.dataset.target) {{
          setTimeout(function() {{ bar.style.width = bar.dataset.target + '%'; }}, 60);
        }}
      }}

      attachFlash();
      animateProgress();
      setTimeout(function() {{ attachFlash(); animateProgress(); }}, 450);
    }})();
    </script>
    """,
    height=0,
)
