"""Shared Plotly chart builders for Streamlit analytics pages."""

from __future__ import annotations

import plotly.graph_objects as go


def base_layout(height: int = 160, show_legend: bool = False) -> dict:
    """Default Plotly layout matching the Trendbox UI design system."""
    return dict(
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=0, r=0, t=8, b=0),
        showlegend=show_legend,
        transition=dict(duration=500, easing="cubic-in-out"),
        hoverlabel=dict(
            bgcolor="#111827",
            font_size=12,
            font_color="white",
            bordercolor="#111827",
        ),
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            size=11,
            color="#6B7280",
        ),
        xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=10)),
        yaxis=dict(
            showgrid=True,
            gridcolor="#F3F4F6",
            gridwidth=1,
            showline=False,
            tickfont=dict(size=10),
        ),
        height=height,
    )


def chart_pipeline_method_split(pipeline_stats: dict, *, height: int = 180) -> go.Figure:
    """Bar chart of rank-1 resolution methods from live database counts."""
    labels = ["Stage 0 · Exact", "Stage 0 · Fuzzy", "ML"]
    values = [
        int(pipeline_stats.get("stage0_exact", 0)),
        int(pipeline_stats.get("stage0_fuzzy", 0)),
        int(pipeline_stats.get("ml_resolved", 0)),
    ]
    colors = ["#10B981", "#34D399", "#3B82F6"]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            marker_line_width=0,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        )
    )
    layout = base_layout(height=height)
    layout["yaxis"]["showgrid"] = True
    fig.update_layout(**layout)
    return fig
