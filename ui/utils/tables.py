"""Shared HTML table renderers for review and analytics pages."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from ui.utils.styles import badge_html, section_label


def format_timestamp(ts: str) -> str:
    """Format an ISO UTC timestamp for display in the viewer's local timezone."""
    if not ts or ts == "—":
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Database stores naive UTC from _utcnow().
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%b %d, %H:%M")
    except Exception:
        return ts


def render_match_history_table(
    rows: list[dict],
    *,
    title: str,
    empty_message: str,
) -> None:
    """Render a read-only match history table backed by /matches/recent."""
    section_label(title)

    if not rows:
        st.markdown(
            f'<div class="lb-card" style="color:#6B7280; text-align:center; padding:32px;">'
            f"{empty_message}"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        """
        <style>
        .decision-row { transition: background 0.1s ease; }
        .decision-row:hover { background: #F9FAFB !important; cursor: default; }
        .source-pill {
          display:inline-block; padding:2px 8px; border-radius:999px;
          font-size:10px; font-weight:600; text-transform:uppercase;
          letter-spacing:0.04em;
        }
        .source-auto { background:#EFF6FF; color:#1D4ED8; }
        .source-operator { background:#F3F4F6; color:#374151; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="border:1px solid #E5E7EB; border-radius:8px; overflow:hidden;">
        <div class="lb-table-header" style="display:grid;
             grid-template-columns:1fr 1fr 120px 90px 110px 130px;
             gap:8px; padding:8px 15px;">
          <span>Product Name</span>
          <span>Matched To</span>
          <span>Confidence</span>
          <span>Source</span>
          <span>Outcome</span>
          <span>Time</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for i, row in enumerate(rows):
        product = row.get("product_name", "—")
        matched = row.get("matched_to", "—")
        conf = float(row.get("confidence", 0))
        source = str(row.get("source", "auto"))
        status = str(row.get("status", ""))
        ts = format_timestamp(str(row.get("time", "")))

        approved = status in {"auto_approved", "approved"} or row.get("decision") == "approved"
        left_border = "#10B981" if approved else "#EF4444"
        outcome = "Approved" if approved else "Rejected"
        outcome_color = "#065F46" if approved else "#991B1B"
        bg = "#FAFAFA" if i % 2 == 0 else "#FFFFFF"
        conf_label = row.get("confidence_label") or (
            "HIGH" if conf >= 0.9 else ("MEDIUM" if conf >= 0.6 else "LOW")
        )
        conf_badge = badge_html(str(conf_label).upper(), conf)
        source_cls = "source-auto" if source == "auto" else "source-operator"
        source_label = "Auto" if source == "auto" else "Operator"

        st.markdown(
            f"""
            <div class="decision-row" style="
                 display:grid;
                 grid-template-columns:1fr 1fr 120px 90px 110px 130px;
                 gap:8px; padding:10px 12px; border-top:1px solid #F3F4F6;
                 border-left:3px solid {left_border};
                 background:{bg}; font-size:13px; color:#374151; align-items:center;">
              <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
                    title="{product}">{product[:42]}</span>
              <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
                    title="{matched}">{matched[:42]}</span>
              <span>{conf_badge}</span>
              <span><span class="source-pill {source_cls}">{source_label}</span></span>
              <span style="font-weight:600; color:{outcome_color};">{outcome}</span>
              <span style="color:#9CA3AF;">{ts}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="lb-table-total" style="display:grid;
             grid-template-columns:1fr 1fr 120px 90px 110px 130px;
             gap:8px; padding:10px 15px; border-top:1px solid #E5E7EB;">
          <span>Showing {len(rows):,} most recent</span>
          <span></span><span></span><span></span><span></span><span></span>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
