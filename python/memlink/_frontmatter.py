"""Bounded YAML frontmatter with exact line delimiters and unique keys."""

from __future__ import annotations

import re

import yaml

from .serialization import sanitize


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, (str, int, float, bool)) or key in result:
            raise ValueError("Duplicate or invalid YAML mapping key")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    delimiter = re.search(r"^---[ \t]*\r?$", text[4:], re.MULTILINE)
    if delimiter is None:
        raise ValueError("Unterminated YAML frontmatter")
    raw = text[4 : 4 + delimiter.start()]
    try:
        if sum(isinstance(t, yaml.tokens.AliasToken) for t in yaml.scan(raw)) > 50:
            raise ValueError("YAML alias resource limit exceeded")
        data = yaml.load(raw, Loader=_UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("YAML frontmatter must be an object")
    sanitize(data)
    return data, text[4 + delimiter.end() :]
