"""Conversion pipeline + Compatibility Analysis + Compare Engine.

Coordinates the flow between a source Reader and target Writer.
Provides structured ConversionAnalysis for CLI/GUI/API consumption.
Compare Engine shared by diff, validate, and roundtrip.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from .models import Memory
from .plugin import FormatPlugin, Severity, ValidationIssue

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
    feature: str  # e.g. "emotion"
    label: str  # Human label: "Emotion fields (valence/arousal)"
    count: int  # Number of field instances affected
    severity: ImpactSeverity
    reason: str
    recoverable: bool  # Can roundtrip recover this?


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
        impacts.append(
            FeatureImpact(
                feature="emotion",
                label=meta["label"],
                count=emo_count,
                severity="preserved" if sc.emotion else "degraded",
                reason=meta["preserved_reason"],
                recoverable=True,
            )
        )

    # Relationships
    rel_count = sum(1 for m in memories if m.relationships)
    if rel_count and not tc.relationships:
        meta = _cap_meta("relationships")
        impacts.append(
            FeatureImpact(
                feature="relationships",
                label=meta["label"],
                count=rel_count,
                severity="preserved",
                reason=meta["preserved_reason"],
                recoverable=True,
            )
        )

    # Summary
    sum_count = sum(1 for m in memories if m.summary)
    if sum_count and not tc.summary:
        meta = _cap_meta("summary")
        impacts.append(
            FeatureImpact(
                feature="summary",
                label=meta["label"],
                count=sum_count,
                severity="preserved",
                reason=meta["preserved_reason"],
                recoverable=True,
            )
        )

    # Importance label → score
    lbl_count = sum(1 for m in memories if m.importance_label)
    if lbl_count and not tc.importance_label:
        meta = _cap_meta("importance_label")
        impacts.append(
            FeatureImpact(
                feature="importance_label",
                label=meta["label"],
                count=lbl_count,
                severity="degraded",
                reason=meta["preserved_reason"],
                recoverable=False,
            )
        )

    # Extensions
    ext_count = sum(1 for m in memories if m.extensions)
    if ext_count and not tc.preserve_unknown_fields:
        meta = _cap_meta("extensions")
        impacts.append(
            FeatureImpact(
                feature="extensions",
                label=meta["label"],
                count=ext_count,
                severity="lost",
                reason=meta["lost_reason"],
                recoverable=False,
            )
        )

    # Unsupported kinds
    kind_count = sum(1 for m in memories if tc.supported_kinds and m.kind not in tc.supported_kinds)
    if kind_count:
        meta = _cap_meta("unsupported_kind")
        supported = ", ".join(sorted(tc.supported_kinds)) if tc.supported_kinds else "none"
        impacts.append(
            FeatureImpact(
                feature="unsupported_kind",
                label=meta["label"],
                count=kind_count,
                severity="degraded",
                reason=f"Target only supports kinds: {supported} (falling back to dynamic)",
                recoverable=False,
            )
        )

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


# ═══════════════════════════════════════════════════════════════════
# Compare Engine — shared by diff, validate, roundtrip
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CompareOptions:
    """Configurable comparison rules for Memory fields."""

    ignore: set[str] = field(
        default_factory=lambda: {
            "relationships",
            "updated_at",
            "source",
            "checksum",
            "metadata",
            "extensions",
            "schema_version",
        }
    )
    normalize_unicode: bool = True  # NFC normalization
    normalize_newlines: bool = True  # CRLF → LF
    sort_lists: bool = True  # tags, domains
    time_epsilon: timedelta = field(default_factory=lambda: timedelta(seconds=1))
    casefold_tags: bool = True

    # Fields compared as-is (no normalization)
    exact_fields: set[str] = field(default_factory=lambda: {"id", "kind", "name"})

    # Fields compared with strip()
    strip_fields: set[str] = field(default_factory=lambda: {"body", "summary"})


def compare_memories(
    original: list[Memory] | dict[str, Memory],
    restored: list[Memory] | dict[str, Memory],
    options: CompareOptions | None = None,
) -> list[ValidationIssue]:
    """Compare two sets of Memories — shared by diff, validate, roundtrip.

    Uses automatic field iteration over dataclass fields.
    One place to maintain — new Canonical fields covered automatically.
    """
    opts = options or CompareOptions()

    # Normalize to dict
    if isinstance(original, list):
        original = {m.id: m for m in original}
    if isinstance(restored, list):
        restored = {m.id: m for m in restored}

    issues: list[ValidationIssue] = []
    orig_ids = set(original)
    rest_ids = set(restored)

    # Lost memories
    for mid in sorted(orig_ids - rest_ids):
        issues.append(
            ValidationIssue(
                code="ML400",
                severity=Severity.ERROR,
                memory_id=mid,
                field="id",
                message="Memory lost in roundtrip",
            )
        )
    # Unexpected memories
    for mid in sorted(rest_ids - orig_ids):
        issues.append(
            ValidationIssue(
                code="ML400",
                severity=Severity.ERROR,
                memory_id=mid,
                field="id",
                message="Unexpected memory in roundtrip",
            )
        )

    # Compare common memories — iterate dataclass fields automatically
    for mid in sorted(orig_ids & rest_ids):
        o, r = original[mid], restored[mid]
        for fld in Memory.__dataclass_fields__:
            if fld in opts.ignore:
                continue
            ov = getattr(o, fld, None)
            rv = getattr(r, fld, None)

            # Checksum shortcut for body
            if fld == "body" and o.checksum and r.checksum and o.checksum == r.checksum:
                continue

            diff = _compare_field(fld, ov, rv, opts)
            if diff:
                issues.append(
                    ValidationIssue(
                        code=_field_error_code(fld),
                        severity=Severity.WARNING if fld in {"tags", "importance_score"} else Severity.ERROR,
                        memory_id=mid,
                        field=fld,
                        message=diff,
                    )
                )

    return issues


def _compare_field(name: str, ov, rv, opts: CompareOptions) -> str | None:
    """Compare a single field value. Returns diff string or None if equal."""
    # Exact match
    if name in opts.exact_fields:
        return f"{name}: {_fmt(ov)} != {_fmt(rv)}" if ov != rv else None

    # Float comparison
    if isinstance(ov, (int, float)) and isinstance(rv, (int, float)):
        if name == "importance_score" and abs(ov - rv) <= 0.01:
            return None
        if ov != rv:
            return f"{name}: {_fmt(ov)} != {_fmt(rv)}"

    # Datetime comparison
    from datetime import datetime
    from datetime import timezone as tz

    if isinstance(ov, datetime) and isinstance(rv, datetime):
        dt_ov = ov.astimezone(tz.utc) if ov.tzinfo else ov.replace(tzinfo=tz.utc)
        dt_rv = rv.astimezone(tz.utc) if rv.tzinfo else rv.replace(tzinfo=tz.utc)
        if abs((dt_ov - dt_rv).total_seconds()) > opts.time_epsilon.total_seconds():
            return f"{name}: {_fmt(ov)} != {_fmt(rv)}"
        return None

    # List comparison (tags, domains)
    if isinstance(ov, list) and isinstance(rv, list):
        ov_norm = _normalize_list(ov, opts)
        rv_norm = _normalize_list(rv, opts)
        if ov_norm != rv_norm:
            return f"{name}: {ov_norm} != {rv_norm}"
        return None

    # String comparison
    if isinstance(ov, str) and isinstance(rv, str):
        s_ov = _normalize_str(ov, opts, strip=(name in opts.strip_fields))
        s_rv = _normalize_str(rv, opts, strip=(name in opts.strip_fields))
        if s_ov != s_rv:
            # Show first differing position
            for i, (a, b) in enumerate(zip(s_ov, s_rv, strict=False)):
                if a != b:
                    ctx = max(0, i - 20)
                    return f"{name}: ...{s_ov[ctx : i + 30]}... != ...{s_rv[ctx : i + 30]}..."
            return f"{name}: lengths {len(s_ov)} != {len(s_rv)}"
        return None

    # General
    if ov != rv:
        return f"{name}: {_fmt(ov)} != {_fmt(rv)}"
    return None


def _normalize_str(s: str, opts: CompareOptions, strip: bool = False) -> str:
    if opts.normalize_unicode:
        s = unicodedata.normalize("NFC", s)
    if opts.normalize_newlines:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
    if strip:
        s = s.strip()
    return s


def _normalize_list(lst: list, opts: CompareOptions) -> list:
    result = []
    for item in lst:
        if isinstance(item, str):
            s = _normalize_str(item, opts)
            if opts.casefold_tags:
                s = s.casefold()
            result.append(s)
        else:
            result.append(item)
    if opts.sort_lists:
        result = sorted(result, key=str)
    return result


def _field_error_code(field: str) -> str:
    codes = {
        "kind": "ML401",
        "body": "ML402",
        "importance_score": "ML403",
        "importance_label": "ML403",
        "created_at": "ML404",
        "updated_at": "ML404",
        "id": "ML400",
        "name": "ML401",
        "tags": "ML401",
        "domains": "ML401",
    }
    return codes.get(field, "ML401")


def _fmt(v) -> str:
    if isinstance(v, str) and len(v) > 60:
        return repr(v[:57] + "...")
    return repr(v)


# ═══════════════════════════════════════════════════════════════════
# Roundtrip
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RoundtripReport:
    total: int
    matched: int
    partial: int  # warnings only (degraded)
    failed: int  # errors (lost / content mismatch)
    only_in_original: list[str]
    only_in_restored: list[str]
    issues: list[ValidationIssue]
    duration: float = 0.0
    warnings: list[str] = field(default_factory=list)
    schema_version: str = "1"

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "matched": self.matched,
            "partial": self.partial,
            "failed": self.failed,
            "only_in_original": self.only_in_original,
            "only_in_restored": self.only_in_restored,
            "duration": self.duration,
            "warnings": self.warnings,
            "schema_version": self.schema_version,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "memory_id": i.memory_id,
                    "field": i.field,
                    "message": i.message,
                }
                for i in self.issues
            ],
        }


def run_roundtrip(
    source_path: Path,
    source_format: str,
    intermediate_format: str = "openclaw",
    keep_temp: Path | None = None,
) -> RoundtripReport:
    """Run full roundtrip: source → intermediate → source, returning structured report.

    Uses registry only — no hardcoded format classes.
    """
    from .registry import get_reader, get_writer

    start = time.perf_counter()
    all_warnings: list[str] = []

    # Validate formats
    try:
        reader = get_reader(source_format)
    except Exception as e:
        return RoundtripReport(
            total=0,
            matched=0,
            partial=0,
            failed=1,
            only_in_original=[],
            only_in_restored=[],
            issues=[ValidationIssue(code="ML301", severity=Severity.ERROR, message=str(e))],
        )

    # Read original
    try:
        result = reader.read(source_path)
    except Exception as e:
        return RoundtripReport(
            total=0,
            matched=0,
            partial=0,
            failed=1,
            only_in_original=[],
            only_in_restored=[],
            issues=[ValidationIssue(code="ML200", severity=Severity.ERROR, message=f"Read failed: {e}")],
        )

    all_warnings.extend(result.warnings)
    original = {m.id: m for m in result.memories}
    if not original:
        return RoundtripReport(
            total=0, matched=0, partial=0, failed=0, only_in_original=[], only_in_restored=[], issues=[]
        )

    # Roundtrip
    import shutil
    import tempfile

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp()
        tmp = Path(tmp_dir)

        # source → intermediate
        try:
            iw = get_writer(intermediate_format)
            if intermediate_format == "openclaw":
                iw = get_writer(intermediate_format, output_mode="structured")
        except Exception as e:
            return RoundtripReport(
                total=len(original),
                matched=0,
                partial=0,
                failed=len(original),
                only_in_original=[],
                only_in_restored=[],
                issues=[ValidationIssue(code="ML301", severity=Severity.ERROR, message=str(e))],
            )

        iw.write(result.memories, tmp / "intermediate")

        # intermediate → Canonical
        ir = get_reader(intermediate_format)
        back_result = ir.read(tmp / "intermediate")
        all_warnings.extend(back_result.warnings)
        im = back_result.memories

        # Canonical → source
        sw = get_writer(source_format)
        sw.write(im, tmp / "restored")

        # Read back
        restored_result = reader.read(tmp / "restored")
        all_warnings.extend(restored_result.warnings)
        restored = {m.id: m for m in restored_result.memories}

        if keep_temp:
            shutil.copytree(tmp, keep_temp, dirs_exist_ok=True)

    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Compare
    issues = compare_memories(original, restored)

    orig_ids = set(original)
    rest_ids = set(restored)
    common = orig_ids & rest_ids

    matched = 0
    partial = 0
    failed = len(orig_ids - rest_ids) + len(rest_ids - orig_ids)

    for mid in common:
        mem_issues = [i for i in issues if i.memory_id == mid]
        errors = [i for i in mem_issues if i.severity == Severity.ERROR]
        if errors:
            failed += 1
        elif mem_issues:
            partial += 1
        else:
            matched += 1

    return RoundtripReport(
        total=len(original),
        matched=matched,
        partial=partial,
        failed=failed,
        only_in_original=sorted(orig_ids - rest_ids),
        only_in_restored=sorted(rest_ids - orig_ids),
        issues=issues,
        warnings=all_warnings,
        duration=time.perf_counter() - start,
        schema_version="1",
    )
