"""Shared API URL resolution for local dev and Streamlit Community Cloud."""

from __future__ import annotations

import os

import streamlit as st


def get_api_url() -> str:
    """Resolve backend URL from env var, Streamlit secrets, or localhost default."""
    env_url = os.getenv("TRENDBOX_API_URL")
    if env_url:
        return env_url.rstrip("/")

    try:
        if "TRENDBOX_API_URL" in st.secrets:
            return str(st.secrets["TRENDBOX_API_URL"]).rstrip("/")
    except Exception:
        pass

    return "http://localhost:8000"
