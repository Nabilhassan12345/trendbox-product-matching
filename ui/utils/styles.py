"""Backward-compatible facade — import from submodules for new code."""

from __future__ import annotations

from ui.utils.components import (
    badge_html,
    conf_bar_html,
    match_quality_chip_html,
    match_source_chip_html,
    product_kind_pill_html,
    progress_bar_html,
    show_offline_card,
    tags_html,
    weight_pill_html,
    weight_tone,
)
from ui.utils.layout import (
    health_status_label,
    render_divider,
    render_page_header,
    render_page_nav,
    render_section_header,
    review_stat_pills,
    section_label,
)
from ui.utils.theme import CANVAS_BG, inject_alive_interactions, inject_styles

__all__ = [
    "CANVAS_BG",
    "badge_html",
    "conf_bar_html",
    "health_status_label",
    "inject_alive_interactions",
    "inject_styles",
    "match_quality_chip_html",
    "match_source_chip_html",
    "product_kind_pill_html",
    "progress_bar_html",
    "render_divider",
    "render_page_header",
    "render_page_nav",
    "render_section_header",
    "review_stat_pills",
    "section_label",
    "show_offline_card",
    "tags_html",
    "weight_pill_html",
    "weight_tone",
]
