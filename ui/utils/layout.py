"""Page layout and navigation helpers."""

from __future__ import annotations

import streamlit as st

from ui.utils.theme import inject_alive_interactions

def section_label(text: str) -> None:
    """Render a small uppercase section label."""
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


def render_page_header(
    title: str,
    subtitle: str = "",
    *,
    eyebrow: str = "",
    meta: str = "",
    live: bool = False,
) -> None:
    """Page title block — primary hierarchy for each route."""
    eyebrow_html = f'<div class="tb-page-eyebrow">{eyebrow}</div>' if eyebrow else ""
    subtitle_html = f'<p class="tb-page-subtitle">{subtitle}</p>' if subtitle else ""
    if live:
        meta_html = (
            '<div class="tb-page-meta">'
            '<span class="live-dot"></span>Live data'
            f"{f' · {meta}' if meta else ''}"
            "</div>"
        )
    elif meta:
        meta_html = f'<div class="tb-page-meta">{meta}</div>'
    else:
        meta_html = ""
    st.markdown(
        f"""
        <div class="tb-page-header">
          {eyebrow_html}
          <h1 class="tb-page-title">{title}</h1>
          {subtitle_html}
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, description: str = "") -> None:
    """Section heading with optional helper text."""
    desc_html = f'<p class="tb-section-desc">{description}</p>' if description else ""
    st.markdown(
        f"""
        <div class="tb-section-header">
          <h2 class="tb-section-title">{title}</h2>
          {desc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_divider() -> None:
    """Horizontal rule between major page sections."""
    st.markdown('<hr class="tb-divider">', unsafe_allow_html=True)


def review_stat_pills(pending: int, approved: int, rejected: int) -> None:
    """Live queue stats for the Review top bar (display-only, always shows pending workflow)."""
    st.markdown(
        f"""
        <style>
        .review-stat-bar {{
          display: flex; gap: 6px; justify-content: center; flex-wrap: wrap;
        }}
        .review-stat-pill {{
          display: inline-flex; align-items: center; gap: 6px;
          padding: 6px 14px; border-radius: 8px; font-size: 13px;
          font-weight: 500; color: #6B7280; background: #F3F4F6;
          border: 1px solid #E5E7EB; transition: transform 0.15s ease;
        }}
        .review-stat-pill strong {{ color: #111827; font-weight: 700; }}
        .review-stat-pill .dot {{
          width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
        }}
        .review-stat-pill.pending {{
          background: #111827; color: #E5E7EB; border-color: #111827;
          animation: pendingPulse 2.4s ease-in-out infinite;
        }}
        .review-stat-pill.pending strong {{ color: #FFFFFF; }}
        .review-stat-pill.pending .dot {{ background: #10B981; }}
        .review-stat-pill.approved .dot {{ background: #10B981; }}
        .review-stat-pill.rejected .dot {{ background: #EF4444; }}
        </style>
        <div class="review-stat-bar">
          <div class="review-stat-pill pending">
            <span class="dot"></span>Pending <strong>{pending:,}</strong>
          </div>
          <div class="review-stat-pill approved">
            <span class="dot"></span>Approved <strong>{approved:,}</strong>
          </div>
          <div class="review-stat-pill rejected">
            <span class="dot"></span>Rejected <strong>{rejected:,}</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


PAGE_NAV_CSS = """
<style>
/* Paint the Streamlit column row as the dark nav shell (HTML wrappers can't wrap widgets). */
div[data-testid="stHorizontalBlock"]:has([class*="st-key-nav_"]) {
  background: #111827;
  border-radius: 10px;
  padding: 6px 10px;
  margin-bottom: 16px;
  border: 1px solid #1F2937;
  align-items: center;
  gap: 4px;
  transition: box-shadow 0.22s ease, transform 0.22s ease;
}
div[data-testid="stHorizontalBlock"]:has([class*="st-key-nav_"]):hover {
  box-shadow: 0 4px 18px rgba(17,24,39,0.24);
}
[class*="st-key-nav_go_"] button {
  transition: background 0.18s ease, color 0.18s ease, transform 0.15s ease !important;
}

/* ── Logo ── */
.st-key-nav_logo_active button,
.st-key-nav_go_logo button {
  background: #E8622A !important;
  color: #FFFFFF !important;
  font-weight: 800 !important;
  font-size: 15px !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 8px !important;
  height: 40px !important;
  min-height: 40px !important;
}
.st-key-nav_logo_active button:disabled {
  opacity: 1 !important;
  cursor: default !important;
}

/* ── Active page tab — white pill on dark bar ── */
[class*="st-key-nav_active_"] button {
  background: #FFFFFF !important;
  color: #111827 !important;
  font-weight: 600 !important;
  font-size: 14px !important;
  border: none !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.12) !important;
  border-radius: 8px !important;
  height: 40px !important;
  min-height: 40px !important;
}
[class*="st-key-nav_active_"] button:disabled {
  opacity: 1 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  cursor: default !important;
}

/* ── Inactive tabs — ghost on dark bar (no white Streamlit default) ── */
[class*="st-key-nav_go_"] button {
  background: transparent !important;
  color: #D1D5DB !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  border: none !important;
  box-shadow: none !important;
  border-radius: 8px !important;
  height: 40px !important;
  min-height: 40px !important;
}
[class*="st-key-nav_go_"] button:hover:not(:disabled) {
  background: #374151 !important;
  color: #FFFFFF !important;
}
</style>
"""


def render_page_nav(active: str, *, alive: bool = False) -> None:
    """Top navigation bar — uses ``st.switch_page`` (HTML ``<a href>`` breaks in Streamlit)."""
    if alive:
        inject_alive_interactions()
    st.markdown(PAGE_NAV_CSS, unsafe_allow_html=True)

    logo_col, home_col, review_col, analytics_col, pipeline_col, _ = st.columns(
        [0.45, 1, 1, 1, 1, 2], gap="small"
    )

    with logo_col:
        if active == "home":
            st.button("T", key="nav_logo_active", disabled=True, use_container_width=True)
        elif st.button("T", key="nav_go_logo", use_container_width=True, help="Home"):
            st.switch_page("app.py")

    nav_items = (
        (home_col, "home", "app.py", "Home"),
        (review_col, "review", "pages/01_Review.py", "Review"),
        (analytics_col, "analytics", "pages/02_Analytics.py", "Analytics"),
        (pipeline_col, "pipeline", "pages/03_Pipeline.py", "Pipeline"),
    )
    for col, key, path, label in nav_items:
        with col:
            if key == active:
                st.button(
                    label,
                    key=f"nav_active_{key}",
                    disabled=True,
                    use_container_width=True,
                )
            elif st.button(label, key=f"nav_go_{key}", use_container_width=True):
                st.switch_page(path)


def health_status_label(health: dict | None) -> tuple[str, str, str]:
    """Return display label, dot class, and value class for the STATUS card."""
    if not health:
        return "Offline", "offline-dot", "home-stat-status offline"
    status = str(health.get("status", "offline")).lower()
    if status == "ok":
        return "Online", "online-dot", "home-stat-status"
    if status == "degraded":
        return "Degraded", "offline-dot", "home-stat-status offline"
    return "Offline", "offline-dot", "home-stat-status offline"
