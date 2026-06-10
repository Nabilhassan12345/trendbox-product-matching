"""Shared API URL resolution and HTTP helpers for Streamlit pages."""

from __future__ import annotations

import os
from typing import Any

import requests
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


def is_connection_error(exc: BaseException) -> bool:
    """Return True when the API is unreachable."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.RequestException) and exc.response is None:
        return True
    return False


def api_get(path: str, timeout: int = 30) -> tuple[dict[str, Any] | None, bool]:
    """GET JSON from the API. Returns (data, api_offline)."""
    try:
        response = requests.get(f"{get_api_url()}{path}", timeout=timeout)
        response.raise_for_status()
        return response.json(), False
    except requests.RequestException as exc:
        return None, is_connection_error(exc)


def api_post(path: str, json: dict | None = None, timeout: int = 30) -> tuple[bool, bool]:
    """POST to the API. Returns (success, api_offline)."""
    try:
        response = requests.post(f"{get_api_url()}{path}", json=json, timeout=timeout)
        response.raise_for_status()
        return True, False
    except requests.RequestException as exc:
        return False, is_connection_error(exc)
