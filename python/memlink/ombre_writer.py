"""Canonical Memory → Ombre Brain writer.

Writes ombre-buckets/{type}/{domain}/{id}.md.
Fixed frontmatter field order, comma-separated tags, no yaml.dump (Ombre style).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

from .models import Memory, sanitize_id
from .plugin import Capabilities, FormatPlugin

# ── Kind → Ombre type mapping ──────────────────────────────────────

_KIND_TO_TYPE: dict[str, str] = {
    "dynamic": "dynamic",
    "permanent": "permanent",
    "emotion": "feel",
}

# ── Importance label → score ───────────────────────────────────────

_LABEL_TO_SCORE: dict[str, int] = {
    "critical": 10,
    "high": 8,
    "medium": 5,
    "low": 3,
    "minimal": 1,
}


class OmbreWriter(FormatPlugin):
    name = "ombre"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=True,
        importance_label=False,  # Ombre uses 1-10 numeric only
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path):
        raise NotImplementedError("OmbreWriter is write-only")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        warnings: list[str] = []
        for mem in memories:
            try:
                self._write_one(mem, path, warnings)
            except Exception as e:
                warnings.append(f"{mem.id}: {e}")
        return warnings

    def validate(self, path):
        return []

    # ── Single memory write ───────────────────────────────────────

    def _write_one(self, mem: Memory, root: Path, warnings: list[str]) -> None:
        original = (mem.metadata.get("memlink") or {}).get("original") or {}

        # Kind → type (check original for roundtrip preservation)
        ombre_type = _KIND_TO_TYPE.get(mem.kind)
        if not ombre_type:
            # Try to recover from original metadata (e.g. archived)
            orig_type = original.get("type")
            if orig_type:
                ombre_type = str(orig_type)
            else:
                warnings.append(f"{mem.id}: Unknown kind '{mem.kind}' → 'dynamic'")
                ombre_type = "dynamic"

        # Domain → directory name (empty = no domain subdir)
        domain = _pick_domain(mem, warnings)

        # ID → bucket_id
        bucket_id = str(original.get("id") or original.get("bucket_id") or mem.id)

        # Create directory
        type_dir = root / ombre_type / domain if domain else root / ombre_type
        type_dir.mkdir(parents=True, exist_ok=True)

        # Build frontmatter (fixed order, Ombre style)
        fm_lines = ["---"]
        _add_field(fm_lines, "bucket_id", bucket_id)
        _add_field(fm_lines, "name", mem.name or "", quote_if_special=True)
        _add_field(fm_lines, "type", ombre_type, quote_if_special=True)
        if mem.domains:
            _add_field(fm_lines, "domain", _format_domains(mem.domains))
        _add_field(fm_lines, "tags", ", ".join(sorted(mem.tags)) if mem.tags else "")
        _add_field(fm_lines, "importance", _importance_for_ombre(mem, original, warnings))
        if mem.valence is not None:
            _add_field(fm_lines, "valence", mem.valence)
        if mem.arousal is not None:
            _add_field(fm_lines, "arousal", mem.arousal)
        _add_field(fm_lines, "created", _created_for_ombre(mem, original))
        if mem.pinned:
            _add_field(fm_lines, "pinned", True)
        fm_lines.append("---")

        # Body
        body = mem.body or ""
        content = "\n".join(fm_lines) + "\n\n" + body

        # Write
        safe_id = sanitize_id(bucket_id)
        filepath = type_dir / f"{safe_id}.md"
        filepath.write_text(content, encoding="utf-8")

        if mem.status == "archived":
            warnings.append(f"{mem.id}: Ombre has no archived concept — saved as active")


# ── Field helpers ──────────────────────────────────────────────────


def _pick_domain(mem: Memory, warnings: list[str]) -> str:
    """Pick domain directory name. Returns empty string if no domain."""
    if not mem.domains:
        return ""
    valid = [d for d in mem.domains if d != "_unknown"]
    return valid[0] if valid else ""


def _importance_for_ombre(mem: Memory, original: dict, warnings: list[str]) -> int:
    """Convert Canonical importance to Ombre 1-10 int."""
    # 1. Original value
    if "importance" in original:
        orig_imp = original["importance"]
        if isinstance(orig_imp, (int, float)) and not isinstance(orig_imp, bool) and 1 <= orig_imp <= 10:
            return int(orig_imp)

    # 2. Score → clamp to 1-10
    if mem.importance_score is not None:
        score = mem.importance_score
        if math.isnan(score) or math.isinf(score):
            warnings.append(f"{mem.id}: invalid importance {score} → default 5")
            return 5
        return max(1, min(10, int(round(score))))

    # 3. Label → lookup
    if mem.importance_label:
        label = str(mem.importance_label).lower()
        mapped = _LABEL_TO_SCORE.get(label)
        if mapped is not None:
            return mapped
        warnings.append(f"{mem.id}: unknown importance label '{mem.importance_label}' → default 5")

    # 4. Default
    return 5


def _created_for_ombre(mem: Memory, original: dict) -> str:
    """Get created timestamp, preferring original timezone string."""
    if "created_tz" in original:
        return str(original["created_tz"])
    if "created" in original and isinstance(original["created"], str):
        return original["created"]
    if mem.created_at is not None:
        return mem.created_at.isoformat()
    return ""


def _format_domains(domains: list[str]) -> str:
    """Format domains list as comma-separated string (Ombre style)."""
    return ", ".join(domains) if domains else "general"


def _add_field(lines: list[str], key: str, value, quote_if_special: bool = False) -> None:
    """Append a YAML field line. Ombre-style: comma-separated strings, no quotes unless needed."""
    if value is None or value == "":
        lines.append(f"{key}:")
    elif value is True:
        lines.append(f"{key}: true")
    elif value is False:
        lines.append(f"{key}: false")
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and value == int(value):
            lines.append(f"{key}: {int(value)}")
        else:
            lines.append(f"{key}: {value}")
    else:
        s = str(value)
        if quote_if_special and (":" in s or "#" in s or s.startswith(("-", "["))):
            lines.append(f'{key}: "{s}"')
        else:
            lines.append(f"{key}: {s}")
