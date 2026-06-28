"""Shared YAML frontmatter parser — used by all Readers and validators."""

from __future__ import annotations

import yaml


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a Markdown file.

    Returns (frontmatter_dict, body_text).
    If no frontmatter found, returns ({}, text).
    If YAML is invalid, returns ({}, text) — never raises.
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return {}, text
        return fm, parts[2]
    except yaml.YAMLError:
        return {}, text
