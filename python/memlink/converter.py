"""Shared offline conversion, scoped merge, broadcast and strict comparison."""

from __future__ import annotations

import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from .codec import identity, identity_key, memory_dict, parse_time, stable_json
from .models import Memory
from .plugin import FormatPlugin, Severity, ValidationIssue
from .transaction import TransactionError, execute_output

ImpactSeverity = Literal["lost", "degraded", "preserved"]


@dataclass
class FeatureImpact:
    feature: str
    label: str
    count: int
    severity: ImpactSeverity
    reason: str
    recoverable: bool


@dataclass
class ConversionAnalysis:
    impacts: list[FeatureImpact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def analyze_conversion(memories: list[Memory], src: FormatPlugin, dst: FormatPlugin) -> ConversionAnalysis:
    impacts = []
    checks = {
        "emotion": lambda m: m.valence is not None or m.arousal is not None,
        "relationships": lambda m: bool(m.relationships),
        "summary": lambda m: m.summary is not None,
        "importance_label": lambda m: m.importance_label is not None,
        "extensions": lambda m: bool(m.extensions),
        "unsupported_kind": lambda m: (
            dst.capabilities.supported_kinds is not None and m.kind not in dst.capabilities.supported_kinds
        ),
    }
    for key, test in checks.items():
        count = sum(bool(test(m)) for m in memories)
        supported = getattr(dst.capabilities, "preserve_unknown_fields" if key == "extensions" else key, False)
        if count and (key == "unsupported_kind" or not supported):
            severity: ImpactSeverity = "lost" if key == "extensions" and not supported else "degraded"
            impacts.append(
                FeatureImpact(
                    key, key, count, severity, "Preflight estimate only; serialization and readback are required", False
                )
            )
    return ConversionAnalysis(impacts)


def check_compatibility(source: FormatPlugin, target: FormatPlugin) -> list[str]:
    return [
        f"Preflight: target native mapping lacks {f}"
        for f in ("emotion", "relationships", "summary", "importance_label")
        if getattr(source.capabilities, f) and not getattr(target.capabilities, f)
    ]


def read_source(source: FormatPlugin, path: Path, **filters) -> tuple[list[Memory], dict, list[dict], list[str]]:
    result = source.read(path)
    if result.errors or not result.memories and not result.valid_empty:
        raise TransactionError(
            "Source is invalid/unsupported or has no parsed records: " + "; ".join(result.errors + result.warnings),
            {
                "schema": "memlink-receipt",
                "version": "1",
                "status": "failed",
                "errors": result.errors or ["No parsed records"],
                "warnings": result.warnings,
                "source_stats": result.stats,
                "sources": [
                    {
                        "format": source.name,
                        "root": path.name,
                        "variant": result.variant,
                        "stats": result.stats,
                        "files": result.files,
                        "records": result.records,
                        "valid_empty": result.valid_empty,
                    }
                ],
            },
            4 if any("changed during read" in e for e in result.errors) else 2,
        )
    selected = []
    excluded = []
    kinds = filters.get("kind")
    domains = filters.get("domain")
    status = filters.get("status")
    kinds = {kinds} if isinstance(kinds, str) else set(kinds or [])
    domains = {domains} if isinstance(domains, str) else set(domains or [])
    include_archived = filters.get("all", False) or filters.get("include_archived", False) or status == "archived"
    for memory in result.memories:
        reason = None
        if kinds and memory.kind not in kinds:
            reason = "kind filter"
        elif domains and not domains.intersection(memory.domains):
            reason = "domain filter"
        elif status and memory.status != status:
            reason = "status filter"
        elif not include_archived and memory.status == "archived":
            reason = "archived excluded"
        if reason:
            excluded.append({"identity": identity(memory), "id": memory.id, "reason": reason, "outcome": "excluded"})
        else:
            selected.append(memory)
    if not selected and result.memories and not filters.get("dry_run", False):
        raise TransactionError(
            "No records selected by filters",
            {"status": "failed", "errors": ["No selected records"], "warnings": result.warnings, "excluded": excluded},
            2,
        )
    context = {
        "format": source.name,
        "variant": result.variant,
        "recognition": {
            "selection": getattr(source, "selection", "explicit"),
            "basis": "Adapter parsed and validated the reported native variant",
        },
        "root": path.name,
        "approved_scope": "Only the supplied root/file; no home discovery",
        "files": result.files,
        "snapshot_sha256": __import__("hashlib").sha256(stable_json(result.files).encode("utf-8")).hexdigest(),
        "stats": result.stats,
        "records": result.records,
        "selected": len(selected),
        "excluded": len(excluded),
        "valid_empty": result.valid_empty,
        "warnings": result.warnings,
    }
    return selected, context, excluded, result.warnings


def convert(source: FormatPlugin, target: FormatPlugin, source_path: Path, target_path: Path, **filters) -> dict:
    memories, context, excluded, warnings = read_source(source, source_path, **filters)
    receipt = _execute_selection(memories, context, excluded, target, source_path, target_path, filters)
    return {
        "memories": memories,
        "warnings": receipt["warnings"],
        "analysis": analyze_conversion(memories, source, target),
        "receipt": receipt,
    }


def _execute_selection(memories, context, excluded, target, source_path, target_path, filters) -> dict:
    transaction_keys = {"mode", "conflict", "strict", "dry_run", "allow_changes"}
    options = {k: v for k, v in filters.items() if k in transaction_keys}
    if filters.get("strict") and (context["stats"].get("invalid", 0) or context["stats"].get("unsupported", 0)):
        raise TransactionError(
            "Strict conversion blocks invalid source records",
            {
                "status": "failed",
                "errors": ["Invalid source records"],
                "warnings": context["warnings"],
                "sources": [context],
            },
            5,
        )
    return execute_output(
        memories,
        target,
        target_path,
        sources=[source_path],
        source_contexts=[context],
        filters={k: v for k, v in filters.items() if k not in transaction_keys},
        exclusions=excluded,
        **options,
    )


def resolve_conflict(existing: Memory, incoming: Memory, strategy: str) -> bool:
    if strategy == "first":
        return True
    if strategy == "last":
        return False
    e = existing.updated_at or existing.created_at
    i = incoming.updated_at or incoming.created_at
    if i is None:
        return True
    if e is None:
        return False
    e = parse_time(e)
    i = parse_time(i)
    assert e is not None and i is not None
    return i <= e if strategy == "newest" else i >= e


def merge(
    sources: list[tuple[FormatPlugin, Path]],
    target: FormatPlugin,
    target_path: Path,
    *,
    on_conflict: str = "newest",
    link_by_id: bool = False,
    **options,
) -> dict:
    all_memories = []
    contexts = []
    excluded = []
    warnings = []
    for reader, path in sources:
        memories, context, exclusions, notes = read_source(reader, path, **options)
        all_memories.extend(memories)
        contexts.append(context)
        excluded.extend(exclusions)
        warnings.extend(notes)
    if options.get("strict") and any(
        c["stats"].get("invalid", 0) or c["stats"].get("unsupported", 0) for c in contexts
    ):
        raise TransactionError(
            "Strict merge blocks invalid/unsupported source records",
            {"status": "failed", "sources": contexts, "warnings": warnings},
            5,
        )
    merged: dict[str, Memory] = {}
    conflicts = []
    for memory in all_memories:
        key = memory.id if link_by_id else identity_key(memory)
        if key in merged:
            previous = merged[key]
            kept = previous if resolve_conflict(previous, memory, on_conflict) else memory
            rejected = memory if kept is previous else previous
            merged[key] = kept
            conflicts.append(
                {
                    "identity": identity(rejected),
                    "id": rejected.id,
                    "outcome": "conflict",
                    "reason": "merge " + on_conflict,
                    "explicit_link_by_id": link_by_id,
                }
            )
        else:
            merged[key] = memory
    receipt = execute_output(
        list(merged.values()),
        target,
        target_path,
        sources=[p for _, p in sources],
        source_contexts=contexts,
        exclusions=excluded + conflicts,
        details={
            "merge": {
                "strategy": on_conflict,
                "link_by_id": link_by_id,
                "total": len(all_memories),
                "unique": len(merged),
                "conflicts": conflicts,
            }
        },
        **{k: v for k, v in options.items() if k in {"strict", "dry_run", "mode", "conflict", "allow_changes"}},
    )
    return {"memories": list(merged.values()), "warnings": receipt["warnings"], "receipt": receipt}


def broadcast(source: FormatPlugin, source_path: Path, targets: list[tuple[FormatPlugin, Path]], **options) -> dict:
    results: list[dict] = []
    memories, context, excluded, _ = read_source(source, source_path, **options)
    for writer, path in targets:
        try:
            receipt = _execute_selection(memories, context, excluded, writer, source_path, path, options)
            results.append({"target": writer.name, "path": path.name, "exit_code": 0, "receipt": receipt})
        except TransactionError as exc:
            results.append(
                {"target": writer.name, "path": path.name, "exit_code": exc.exit_code, "receipt": exc.receipt}
            )
    return {
        "status": "failed"
        if any(r["exit_code"] for r in results)
        else "partial"
        if any(r["receipt"]["status"] == "partial" for r in results)
        else "success",
        "targets": results,
    }


@dataclass
class CompareOptions:
    ignore: set[str] = field(default_factory=set)
    normalize_unicode: bool = False
    normalize_newlines: bool = False
    sort_lists: bool = False
    time_epsilon: timedelta = field(default_factory=lambda: timedelta(0))
    casefold_tags: bool = False
    exact_fields: set[str] = field(default_factory=set)
    strip_fields: set[str] = field(default_factory=set)


def compare_memories(
    original: list[Memory] | dict[str, Memory],
    restored: list[Memory] | dict[str, Memory],
    options: CompareOptions | None = None,
) -> list[ValidationIssue]:
    opts = options or CompareOptions()
    issues = []
    original = list(original.values()) if isinstance(original, dict) else original
    restored = list(restored.values()) if isinstance(restored, dict) else restored
    groups1 = defaultdict(list)
    groups2 = defaultdict(list)
    for m in original:
        groups1[identity_key(m)].append(m)
    for m in restored:
        groups2[identity_key(m)].append(m)
    for key in sorted(set(groups1) | set(groups2)):
        a, b = groups1[key], groups2[key]
        if len(a) != len(b):
            issues.append(
                ValidationIssue(
                    "ML400",
                    Severity.ERROR,
                    memory_id=(a or b)[0].id,
                    field="identity",
                    message=f"Record multiplicity differs: {len(a)} != {len(b)}",
                )
            )
        for first, second in zip(a, b, strict=False):
            da, db = memory_dict(first), memory_dict(second)
            for fld in Memory.__dataclass_fields__:
                if fld in opts.ignore:
                    continue
                ov, rv = da[fld], db[fld]
                if opts.normalize_newlines and isinstance(ov, str) and isinstance(rv, str):
                    ov = ov.replace("\r\n", "\n")
                    rv = rv.replace("\r\n", "\n")
                if stable_json(ov) != stable_json(rv):
                    issues.append(
                        ValidationIssue(
                            "ML402" if fld == "body" else "ML401",
                            Severity.ERROR,
                            memory_id=first.id,
                            field=fld,
                            message=f"{fld}: values differ",
                        )
                    )
    return issues


@dataclass
class RoundtripReport:
    total: int
    matched: int
    partial: int
    failed: int
    only_in_original: list[str]
    only_in_restored: list[str]
    issues: list[ValidationIssue]
    duration: float = 0.0
    warnings: list[str] = field(default_factory=list)
    schema_version: str = "1"

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


def run_roundtrip(
    source_path: Path,
    source_format: str,
    intermediate_format: str = "openclaw",
    keep_temp: Path | None = None,
    *,
    output_mode: str = "daily-notes",
) -> RoundtripReport:
    from .registry import get_reader, get_writer

    start = time.perf_counter()
    original = []
    warnings = []
    try:
        reader = get_reader(source_format)
        source_result = reader.read(source_path)
        original = source_result.memories
        warnings.extend(source_result.warnings)
        if source_result.errors or source_result.stats.get("invalid", 0) or source_result.stats.get("unsupported", 0):
            raise ValueError(
                "Roundtrip source contains invalid/unsupported records: "
                + "; ".join(source_result.errors + source_result.warnings)
            )
        if not original:
            raise ValueError("Roundtrip requires at least one parsed record")
        writer = get_writer(
            intermediate_format, **({"output_mode": output_mode} if intermediate_format == "openclaw" else {})
        )
        source_writer = get_writer(source_format)
        with tempfile.TemporaryDirectory(prefix="memlink-roundtrip-") as td:
            root = Path(td)
            step1 = convert(reader, writer, source_path, root / "intermediate", all=True)
            warnings.extend(step1["warnings"])
            step2 = convert(
                get_reader(intermediate_format), source_writer, root / "intermediate", root / "restored", all=True
            )
            warnings.extend(step2["warnings"])
            restored = get_reader(source_format).read(root / "restored").memories
            if keep_temp:
                if keep_temp.exists() and any(keep_temp.iterdir()):
                    raise ValueError("keep_temp destination must be empty")
                __import__("shutil").copytree(root, keep_temp, dirs_exist_ok=True)
        issues = compare_memories(original, restored)
        failed_ids = {i.memory_id for i in issues}
        matched = sum(m.id not in failed_ids for m in original)
        return RoundtripReport(
            len(original), matched, 0, len(original) - matched, [], [], issues, time.perf_counter() - start, warnings
        )
    except Exception as exc:
        issues = [ValidationIssue("ML303", Severity.ERROR, message=str(exc))]
        return RoundtripReport(
            len(original), 0, 0, max(1, len(original)), [], [], issues, time.perf_counter() - start, warnings
        )
