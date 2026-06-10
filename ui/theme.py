"""Shared Trendbox UI theme and layout helpers."""

from __future__ import annotations

import streamlit as st

OFFLINE_MESSAGE = (
    "⚠️ Cannot connect to backend. Make sure the API is running "
    "(`uvicorn api.main:app --port 8000`) or set `TRENDBOX_API_URL`."
)

THEME_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
        max-width: 1180px;
    }

    .trendbox-hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0ea5e9 120%);
        border-radius: 14px;
        padding: 1.35rem 1.6rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
    }

    .trendbox-hero h1 {
        color: #f8fafc !important;
        font-size: 1.55rem !important;
        font-weight: 700 !important;
        margin: 0 0 0.35rem 0 !important;
        letter-spacing: -0.02em;
    }

    .trendbox-hero p {
        color: #cbd5e1;
        margin: 0;
        font-size: 0.95rem;
    }

    .trendbox-panel {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }

    .trendbox-panel-title {
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 0.65rem;
    }

    .product-title {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        line-height: 1.3 !important;
        margin: 0.25rem 0 0.75rem 0 !important;
    }

    .product-meta {
        color: #94a3b8;
        font-size: 0.82rem;
        margin-top: 0.75rem;
    }

    .tag {
        display: inline-block;
        padding: 0.28rem 0.7rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-right: 0.4rem;
        margin-bottom: 0.35rem;
    }

    .tag-brand { background: #e0f2fe; color: #0369a1; }
    .tag-weight { background: #fef3c7; color: #b45309; }

    .confidence-pill {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        color: #fff;
        margin-bottom: 0.5rem;
    }

    .suggestion-name {
        font-size: 1.05rem;
        font-weight: 600;
        color: #0f172a;
        margin: 0.35rem 0;
    }

    .suggestion-barcode {
        color: #64748b;
        font-size: 0.85rem;
        font-family: ui-monospace, monospace;
    }

    .suggestion-explanation {
        color: #475569;
        font-size: 0.88rem;
        font-style: italic;
        margin-top: 0.5rem;
        line-height: 1.45;
    }

    .offline-banner {
        background: #fff7ed;
        border: 1px solid #fdba74;
        border-radius: 10px;
        padding: 1rem 1.1rem;
        color: #9a3412;
        font-weight: 500;
        margin: 1rem 0;
    }

    .impact-card {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border: 1px solid #6ee7b7;
        border-radius: 12px;
        padding: 1.25rem 1.4rem;
        margin-top: 0.5rem;
    }

    .impact-card p {
        color: #065f46;
        font-size: 1.05rem;
        margin: 0;
        font-weight: 500;
    }

    .section-label {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0.5rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #e2e8f0;
    }

    .st-key-reject_all button {
        background: #dc2626 !important;
        color: #fff !important;
        border: none !important;
    }

    .st-key-reject_all button:hover {
        background: #b91c1c !important;
        color: #fff !important;
    }

    div[data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }

    div[data-testid="stMetric"] {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.65rem 0.75rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
</style>
"""


def inject_theme() -> None:
    """Inject global Trendbox CSS."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def page_hero(title: str, subtitle: str = "") -> None:
    """Render a branded page header."""
    st.markdown(
        f'<div class="trendbox-hero"><h1>{title}</h1>'
        f'<p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def show_offline() -> None:
    """Display a consistent offline warning and stop the page."""
    st.markdown(f'<div class="offline-banner">{OFFLINE_MESSAGE}</div>', unsafe_allow_html=True)
    st.stop()


def confidence_pill(label: str, score: float, color: str) -> str:
    """Build HTML for a coloured confidence badge."""
    emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(label.upper(), "⚪")
    return (
        f'<span class="confidence-pill" style="background:{color};">'
        f"{emoji} {label.upper()} · {score:.3f}</span>"
    )


def render_tags(brand: str | None, weight: str | None) -> None:
    """Render brand and weight tag pills."""
    parts = []
    if brand:
        parts.append(f'<span class="tag tag-brand">🏷 {brand}</span>')
    if weight:
        parts.append(f'<span class="tag tag-weight">⚖ {weight}</span>')
    if parts:
        st.markdown("".join(parts), unsafe_allow_html=True)
