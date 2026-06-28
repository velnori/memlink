"""Conversion pipeline: Normalize → Field Mapping → Transform → Validation.

Coordinates the flow between a source Reader and target Writer.
Handles capability checking and Feature Loss Reporting.
"""

from pathlib import Path

from .plugin import FormatPlugin


def check_compatibility(
    source: FormatPlugin,
    target: FormatPlugin,
) -> list[str]:
    """Check capability compatibility between source and target formats.

    Returns warnings for features that the target cannot preserve.
    """
    warnings: list[str] = []
    sc = source.capabilities
    tc = target.capabilities

    if sc.relationships and not tc.relationships:
        warnings.append("Target does not support relationships")
    if sc.emotion and not tc.emotion:
        warnings.append("Target does not support emotion fields (valence/arousal)")
    if sc.importance_label and not tc.importance_label:
        warnings.append("Target does not support importance labels")
    if not tc.preserve_unknown_fields:
        warnings.append("Target cannot preserve unknown extension fields")

    return warnings


def convert(
    source: FormatPlugin,
    target: FormatPlugin,
    source_path: Path,
    target_path: Path,
    **filters,
) -> dict:
    """Run the full conversion pipeline.

    Returns a dict with keys: memories, warnings, feature_loss.
    """
    # 1. Read
    result = source.read(source_path)

    # 2. Filter (TODO: apply --domain, --kind, --status filters)
    memories = result.memories

    # 3. Capability check
    compat_warnings = check_compatibility(source, target)

    # 4. Write
    write_warnings = target.write(memories, target_path)

    # 5. Feature Loss Report
    loss: dict[str, int] = {}
    if source.capabilities.relationships and not target.capabilities.relationships:
        loss["relationships"] = sum(1 for m in memories if m.relationships)
    if source.capabilities.emotion and not target.capabilities.emotion:
        loss["emotion"] = sum(
            1 for m in memories if m.valence is not None or m.arousal is not None
        )

    return {
        "memories": memories,
        "warnings": result.warnings + compat_warnings + write_warnings,
        "feature_loss": loss,
    }
