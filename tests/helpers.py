"""Shared assertion helpers for pytest test modules."""

from __future__ import annotations


def check_eq(name: str, expected: object, actual: object) -> None:
    assert expected == actual, f"{name}: expected {expected!r}, got {actual!r}"


def check_true(name: str, condition: bool, detail: str = "") -> None:
    suffix = f": {detail}" if detail else ""
    assert condition, f"{name}{suffix}"
