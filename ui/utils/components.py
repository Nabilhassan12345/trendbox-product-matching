"""Reusable HTML component builders for Streamlit pages."""

from __future__ import annotations

import streamlit as st

def show_offline_card() -> None:
    """Show an amber offline warning and stop rendering."""
    st.markdown(
        """
        <div class="offline-banner">
          <strong>⚠️ Cannot connect to backend</strong><br>
          Make sure <code>pipeline.py</code> is running:
          <code>python pipeline.py</code>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


def badge_html(label: str, score: float) -> str:
    """Return an inline HTML confidence badge."""
    label = (label or "LOW").upper()
    cfg = {
        "HIGH":   ("badge-high",   "●"),
        "MEDIUM": ("badge-medium", "●"),
        "LOW":    ("badge-low",    "●"),
    }
    cls, dot = cfg.get(label, ("badge-low", "●"))
    pct = int(round(score * 100))
    return f'<span class="badge {cls}">{dot} {pct}% {label}</span>'


def conf_bar_html(label: str, score: float) -> str:
    """Animated confidence mini-bar + pill label for suggestion cards.

    Renders a thin horizontal bar that grows from 0 → score on card appearance,
    with a percentage readout and a colour-matched label pill.
    """
    label = (label or "LOW").upper()
    pct   = min(max(int(round(score * 100)), 0), 100)
    colors: dict[str, str] = {
        "HIGH":   "#10B981",
        "MEDIUM": "#F59E0B",
        "LOW":    "#EF4444",
    }
    badge_cls: dict[str, str] = {
        "HIGH":   "badge-high",
        "MEDIUM": "badge-medium",
        "LOW":    "badge-low",
    }
    color = colors.get(label, "#EF4444")
    cls   = badge_cls.get(label, "badge-low")
    return (
        '<div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">'
        # Track
        '<div style="flex:1; height:4px; background:#F3F4F6;'
        ' border-radius:3px; overflow:hidden;">'
        # Fill — scaleX animation from barGrow keyframe in styles.py
        f'<div style="width:{pct}%; height:100%; background:{color};'
        f' border-radius:3px; transform-origin:left;'
        f' animation:barGrow 0.45s ease-out both;"></div>'
        '</div>'
        # Percentage readout
        f'<span style="font-size:11px; font-weight:700; color:{color};'
        f' min-width:28px; text-align:right;">{pct}%</span>'
        # Label pill
        f'<span class="badge {cls}">● {label}</span>'
        '</div>'
    )


def tags_html(brand: str | None, weight: str | None) -> str:
    """Return HTML tag pills for brand and weight."""
    parts: list[str] = []
    if brand:
        parts.append(f'<span class="tag tag-brand">{brand}</span>')
    if weight:
        parts.append(f'<span class="tag tag-weight">{weight}</span>')
    return "".join(parts)


def product_kind_pill_html(product_kind: str | None) -> str:
    """Return a product-kind pill for the review product card."""
    kind = (product_kind or "unknown").lower()
    labels = {
        "fresh": "Fresh produce",
        "branded": "Branded FMCG",
        "unknown": "Unknown kind",
    }
    css = {
        "fresh": "tag-kind-fresh",
        "branded": "tag-kind-branded",
        "unknown": "tag-kind-unknown",
    }
    label = labels.get(kind, labels["unknown"])
    cls = css.get(kind, css["unknown"])
    return f'<span class="tag {cls}" style="font-size:13px; padding:4px 12px;">{label}</span>'


def match_source_chip_html(match_source: str | None) -> str:
    """Return a resolution-method chip for a suggestion card."""
    source = (match_source or "ml").lower()
    labels = {
        "stage0_exact": "Stage 0 · Exact",
        "stage0_fuzzy": "Stage 0 · Fuzzy",
        "ml": "ML match",
    }
    label = labels.get(source, labels["ml"])
    cls = "source-stage0" if source.startswith("stage0") else "source-ml"
    return f'<span class="source-chip {cls}">{label}</span>'


def progress_bar_html(
    value: float,
    height: int = 4,
    color: str = "#3B82F6",
    *,
    bar_id: str = "",
    animate_from_zero: bool = False,
) -> str:
    """Return a thin custom progress bar HTML."""
    pct = min(max(value * 100, 0), 100)
    width = 0.0 if animate_from_zero else pct
    id_attr = f' id="{bar_id}"' if bar_id else ""
    data_attr = f' data-target="{pct:.1f}"' if animate_from_zero and bar_id else ""
    return (
        f'<div class="lb-progress-track" style="height:{height}px;">'
        f'<div class="lb-progress-fill"{id_attr}{data_attr} '
        f'style="width:{width:.1f}%; background:{color};'
        f' transition:width 0.8s cubic-bezier(.4,0,.2,1);"></div>'
        f"</div>"
    )


