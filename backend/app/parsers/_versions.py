"""Lightweight package version strings for parser metadata."""

from __future__ import annotations


def package_version(dist_name: str) -> str:
    try:
        from importlib.metadata import version

        return version(dist_name)
    except Exception:
        return "unknown"


__all__ = ["package_version"]
