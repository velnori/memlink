"""Conversion pipeline + Compatibility Analysis.

Coordinates the flow between a source Reader and target Writer.
Provides structured ConversionAnalysis for CLI/GUI/API consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .models import Memory
from .plugin import Capabilities, FormatPlugin

# ── Capability registry ────────────────────────────────────────────

_CAPABILITY_META: dict[str, dict] = {
    "emotion": {
        "label": "Emotion fields (valence/arousal)",
        "lost_reason": "Target format has no valence/arousal fields",
        "preserved_reason": "Stored in metadata.memlink.original for roundtrip recovery",
    },
    "relationships": {
        "label": "Relationships",
        "lost_reason": "Target format does not support relationships",
        "preserved_reason": "Stored in metadata.memlink.relationships (v0 writer skip)",
    },
    "summary": {
        "label": "Summary/Description",
        "lost_reason": "Target format has no summary/description field",
        "preserved_reason": "Stored in metadata.memlink.original",
    },
    "importance_label": {
        "label": "Importance labels",
        "lost_reason": "Target only supports numeric importance",
        "preserved_reason": "Converted to importance_score",
    },
    "extensions": {
        "label": "Extensions",
        "lost_reason": "Target cannot preserve unknown extensions",
        "preserved_reason": "Extensions preserved in memory file",
    },
    "unsupported_kind": {
        "label": "Unsupported memory kinds",
        "lost_reason": "Target has limited kind support",
        "preserved_reason": "Falling back to dynamic",
    },
}


def _cap_meta(key: str) -> dict:
    return _CAPABILITY_META.get(key, {"label": key, "lost_reason": "Format limitation", "preserved_reason": ""})


# ── Structured types ───────────────────────────────────────────────

ImpactSeverity = Literal["lost", "degraded", "preserved"]


@dataclass
class FeatureImpact:
    feature: str            # e.g. "emotion"
    label: str              # Human label: "Emotion fields (valence/arousal)"
    count: int              # Number of field instances affected
    severity: ImpactSeverity
    reason: str
    recoverable: bool       # Can roundtrip recover this?


@dataclass
class ConversionAnalysis:
    impacts: list[FeatureImpact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Public API ─────────────────────────────────────────────────────

def check_compatibility(source: FormatPlugin, target: FormatPlugin) -> list[str]:
    """Return capability mismatch warnings (human-readable)."""
    warnings: list[str] = []
    sc, tc = source.capabilities, target.capabilities
    if sc.relationships and not tc.relationships:
        warnings.append("Target does not support relationships")
    if sc.emotion and not tc.emotion:
        warnings.append("Target does not support emotion fields (valence/arousal)")
    if sc.importance_label and not tc.importance_label:
        warnings.append("Target does not support importance labels")
    if not tc.preserve_unknown_fields:
        warnings.append("Target cannot preserve unknown extension fields")
    return warnings


def analyze_conversion(
    memories: list[Memory],
    src: FormatPlugin,
    dst: FormatPlugin,
) -> ConversionAnalysis:
    """Analyze what will happen before conversion — no side effects."""
    sc, tc = src.capabilities, dst.capabilities
    impacts: list[FeatureImpact] = []

    # Emotion
    emo_count = sum(1 for m in memories if m.valence is not None or m.arousal is not None)
    if emo_count and not tc.emotion:
        meta = _cap_meta("emotion")
        impacts.append(FeatureImpact(
            feature="emotion", label=meta["label"], count=emo_count,
            severity="preserved" if sc.emotion else "degraded",
            reason=meta["preserved_reason"], recoverable=True,
        ))

    # Relationships
    rel_count = sum(1 for m in memories if m.relationships)
    if rel_count and not tc.relationships:
        meta = _cap_meta("relationships")
        impacts.append(FeatureImpact(
            feature="relationships", label=meta["label"], count=rel_count,
            severity="preserved", reason=meta["preserved_reason"], recoverable=True,
        ))

    # Summary
    sum_count = sum(1 for m in memories if m.summary)
    if sum_count and not tc.summary:
        meta = _cap_meta("summary")
        impacts.append(FeatureImpact(
            feature="summary", label=meta["label"], count=sum_count,
            severity="preserved", reason=meta["preserved_reason"], recoverable=True,
        ))

    # Importance label → score
    lbl_count = sum(1 for m in memories if m.importance_label)
    if lbl_count and not tc.importance_label:
        meta = _cap_meta("importance_label")
        impacts.append(FeatureImpact(
            feature="importance_label", label=meta["label"], count=lbl_count,
            severity="degraded", reason=meta["preserved_reason"], recoverable=False,
        ))

    # Extensions
    ext_count = sum(1 for m in memories if m.extensions)
    if ext_count and not tc.preserve_unknown_fields:
        meta = _cap_meta("extensions")
        impacts.append(FeatureImpact(
            feature="extensions", label=meta["label"], count=ext_count,
            severity="lost", reason=meta["lost_reason"], recoverable=False,
        ))

    # Unsupported kinds
    kind_count = sum(1 for m in memories if tc.supported_kinds and m.kind not in tc.supported_kinds)
    if kind_count:
        meta = _cap_meta("unsupported_kind")
        supported = ", ".join(sorted(tc.supported_kinds)) if tc.supported_kinds else "none"
        impacts.append(FeatureImpact(
            feature="unsupported_kind", label=meta["label"],
            count=kind_count, severity="degraded",
            reason=f"Target only supports kinds: {supported} (falling back to dynamic)",
            recoverable=False,
        ))

    return ConversionAnalysis(impacts=impacts)


def convert(
    source: FormatPlugin,
    target: FormatPlugin,
    source_path: Path,
    target_path: Path,
    **filters,
) -> dict:
    """Run full conversion pipeline. Returns {memories, warnings, analysis}."""
    result = source.read(source_path)
    memories = result.memories

    # Analyze before writing
    analysis = analyze_conversion(memories, source, target)

    compat = check_compatibility(source, target)
    write_warnings = target.write(memories, target_path)

    return {
        "memories": memories,
        "warnings": result.warnings + compat + write_warnings,
        "analysis": analysis,
    }
