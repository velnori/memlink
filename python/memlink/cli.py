"""CLI entry point — argparse-based command routing.

Minimal v0.1 CLI: convert / validate / inspect.
"""

from __future__ import annotations

import argparse
import sys
import time
from enum import IntEnum
from pathlib import Path


class ExitCode(IntEnum):
    SUCCESS = 0
    DIFF_FOUND = 1
    VALIDATION_ERROR = 2
    IO_ERROR = 3
    CONCURRENT_MODIFICATION = 4
    FORMAT_INCOMPATIBLE = 5
    USER_ABORT = 130


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(ExitCode.SUCCESS)

    try:
        _dispatch(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(ExitCode.USER_ABORT)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(ExitCode.IO_ERROR)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(ExitCode.IO_ERROR)


# ── Parser ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memlink",
        description="AI Memory Interchange Layer — bridge AI memory formats",
    )
    from . import __version__

    parser.add_argument("--version", action="version", version=f"memlink {__version__}")
    sub = parser.add_subparsers(dest="command")

    # convert
    p = sub.add_parser("convert", help="Convert between memory formats")
    p.add_argument("--from", "-f", dest="from_fmt", required=True, help="Source format (ombre, openclaw)")
    p.add_argument("--to", "-t", dest="to_fmt", required=True, help="Target format (ombre, openclaw)")
    p.add_argument("--source", "-s", type=Path, required=True, help="Source directory")
    p.add_argument("--target", "-T", type=Path, required=True, help="Target directory")
    p.add_argument(
        "--output-mode",
        choices=["daily-notes", "structured"],
        default="daily-notes",
        help="OpenClaw output mode (default: daily-notes)",
    )
    p.add_argument("--kind", "-k", nargs="+", help="Only convert specific kind(s)")
    p.add_argument("--dry-run", action="store_true", help="Parse only, don't write")
    p.add_argument("--include-archived", action="store_true")
    p.add_argument(
        "--fail-on-loss",
        action="store_true",
        help="Exit with code 5 if any fields will be lost during conversion",
    )
    p.add_argument("--verbose", "-v", action="count", default=0)

    # shortcuts
    p = sub.add_parser("ombre2claw", help="Ombre → OpenClaw (shortcut)")
    p.add_argument("--source", "-s", type=Path, required=True)
    p.add_argument("--target", "-T", type=Path, required=True)
    p.add_argument("--output-mode", choices=["daily-notes", "structured"], default="daily-notes")
    p.add_argument("--verbose", "-v", action="count", default=0)

    p = sub.add_parser("claw2ombre", help="OpenClaw → Ombre (shortcut)")
    p.add_argument("--source", "-s", type=Path, required=True)
    p.add_argument("--target", "-T", type=Path, required=True)
    p.add_argument("--verbose", "-v", action="count", default=0)

    # validate
    p = sub.add_parser("validate", help="Validate memory files")
    p.add_argument("--level", choices=["schema", "semantic", "roundtrip"], default="schema")
    p.add_argument("--source", "-s", type=Path, required=True, help="Directory or file to validate")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")

    # diff
    p = sub.add_parser("diff", help="Compare two memory directories")
    p.add_argument("--source", "-s", type=Path, nargs=2, required=True, metavar=("DIR1", "DIR2"))
    p.add_argument("--ignore", help="Ignore field groups: timestamps,tags,importance")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")

    # stats
    p = sub.add_parser("stats", help="Show memory statistics")
    p.add_argument("--source", "-s", type=Path, required=True)

    # inspect
    p = sub.add_parser("inspect", help="Inspect a single memory file")
    p.add_argument("file", type=Path, help="File to inspect")
    p.add_argument("--format", "-f", choices=["ombre", "openclaw"], help="Force format detection")

    # formats
    sub.add_parser("formats", help="List installed format plugins")

    # merge
    p = sub.add_parser("merge", help="Merge memories from multiple sources into one target")
    p.add_argument(
        "--sources",
        "-s",
        nargs="+",
        required=True,
        metavar="FORMAT:PATH",
        help="Source(s) as format:path, e.g. ombre:/data/ombre mem0:/data/mem0",
    )
    p.add_argument(
        "--to",
        "-T",
        required=True,
        metavar="FORMAT:PATH",
        help="Target as format:path, e.g. openclaw:/data/output",
    )
    p.add_argument(
        "--on-conflict",
        choices=["newest", "oldest", "first", "last"],
        default="newest",
        help="Conflict resolution when same id exists in multiple sources (default: newest)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", "-v", action="count", default=0)

    # broadcast
    p = sub.add_parser("broadcast", help="Write memories from one source to multiple targets")
    p.add_argument(
        "--from",
        "-f",
        dest="from_spec",
        required=True,
        metavar="FORMAT:PATH",
        help="Source as format:path, e.g. ombre:/data/ombre",
    )
    p.add_argument(
        "--to",
        "-T",
        nargs="+",
        required=True,
        metavar="FORMAT:PATH",
        help="Target(s) as format:path, e.g. mem0:/out openclaw:/out2",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", "-v", action="count", default=0)

    return parser


# ── Dispatch ───────────────────────────────────────────────────────


def _dispatch(args) -> None:
    if args.command == "formats":
        _cmd_formats()
    elif args.command == "merge":
        _cmd_merge(args)
    elif args.command == "broadcast":
        _cmd_broadcast(args)
    elif args.command == "convert":
        _cmd_convert(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "inspect":
        _cmd_inspect(args)
    elif args.command == "diff":
        _cmd_diff(args)
    elif args.command == "stats":
        _cmd_stats(args)
    elif args.command == "ombre2claw":
        args.from_fmt, args.to_fmt, args.dry_run = "ombre", "openclaw", False
        _cmd_convert(args)
    elif args.command == "claw2ombre":
        args.from_fmt, args.to_fmt, args.dry_run = "openclaw", "ombre", False
        _cmd_convert(args)
    else:
        sys.exit(0)


# ── Commands ───────────────────────────────────────────────────────


def _cmd_formats() -> None:
    from .registry import list_formats

    fmts = list_formats()
    if not fmts:
        print("No format plugins installed.")
        return
    print(f"{'Format':<15} {'Reader':<10} {'Writer':<10}")
    print("-" * 35)
    for name, caps in fmts.items():
        print(f"{name:<15} {'yes' if caps['reader'] else 'no':<10} {'yes' if caps['writer'] else 'no':<10}")


def _cmd_convert(args) -> None:
    from .converter import analyze_conversion
    from .registry import get_reader, get_writer

    src_plugin = get_reader(args.from_fmt)
    writer_kwargs = {}
    if args.to_fmt == "openclaw":
        writer_kwargs["output_mode"] = args.output_mode
    dst_plugin = get_writer(args.to_fmt, **writer_kwargs)

    # Read first to compute analysis
    result = src_plugin.read(args.source)
    memories = result.memories
    total = len(memories)
    print(f"Read:     {total} memories from {args.from_fmt}")

    # Analyze before writing
    analysis = analyze_conversion(memories, src_plugin, dst_plugin)
    _print_compatibility(analysis, total, args.verbose)

    if getattr(args, "fail_on_loss", False):
        lost = [i for i in analysis.impacts if i.severity == "lost"]
        if lost:
            labels = ", ".join(i.label for i in lost)
            print(
                f"--fail-on-loss: {len(lost)} field type(s) will be lost: {labels}",
                file=sys.stderr,
            )
            sys.exit(ExitCode.FORMAT_INCOMPATIBLE)

    # Dry run
    if args.dry_run:
        print(f"\nDry run: would convert {total} memories")
        return

    # Write
    start = time.perf_counter()
    write_warnings = dst_plugin.write(memories, args.target)
    elapsed = time.perf_counter() - start

    if write_warnings and args.verbose:
        for w in write_warnings[:10]:
            print(f"  [write] {w}")

    all_warnings = result.warnings + write_warnings
    print(f"Warnings: {len(all_warnings)}" if all_warnings else "Warnings: 0")
    print(f"Time:     {elapsed:.2f}s")


def _print_compatibility(analysis, total: int, verbosity: int) -> None:
    """Print structured Compatibility Report."""
    if not analysis.impacts:
        if verbosity >= 1:
            print("Compatibility: fully supported")
        return

    icons = {"lost": "[!]", "degraded": "[~]", "preserved": "[ok]"}
    titles = {"lost": "Not supported", "degraded": "Degraded", "preserved": "Preserved via metadata"}

    # Group by severity
    by_sev: dict[str, list] = {}
    for imp in analysis.impacts:
        by_sev.setdefault(imp.severity, []).append(imp)

    print("\nCompatibility Report:")

    for sev in ("lost", "preserved", "degraded"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        title = titles.get(sev, sev)
        print(f"  {icons.get(sev, '?')} {title}:")
        for imp in items:
            pct = f" ({imp.count * 100 // total}%)" if verbosity >= 1 else ""
            print(f"    {imp.label}: {imp.count} field values{pct}")
            if verbosity >= 2:
                print(f"      → {imp.reason}")
            if verbosity >= 2 and imp.recoverable:
                print("      → Recoverable via roundtrip")


def _cmd_validate(args) -> None:
    from .validators import validate_roundtrip, validate_schema, validate_semantic

    if args.level == "schema":
        issues = validate_schema(args.source)
    elif args.level == "semantic":
        issues = validate_semantic(args.source)
    elif args.level == "roundtrip":
        issues = validate_roundtrip(args.source)
    else:
        issues = []

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    if args.format == "json":
        import json

        out = {
            "total": len(errors) + len(warnings),
            "errors": [{"code": e.code, "path": e.path, "message": e.message} for e in errors],
            "warnings": [{"code": w.code, "path": w.path, "message": w.message} for w in warnings],
        }
        print(json.dumps(out, indent=2))
    else:
        if errors:
            print(f"Errors: {len(errors)}")
            for e in errors:
                print(f"  {e.code.value if hasattr(e.code, 'value') else e.code} {e.path}: {e.message}")
        if warnings:
            print(f"Warnings: {len(warnings)}")
            for w in warnings[:10]:
                print(f"  {w.code} {w.path}: {w.message}")
        if not errors and not warnings:
            print(f"All files valid ({args.level})")

    sys.exit(ExitCode.VALIDATION_ERROR if errors else ExitCode.SUCCESS)


def _cmd_diff(args) -> None:
    from .converter import CompareOptions, compare_memories
    from .registry import get_reader

    dir1, dir2 = args.source
    ignore_fields = set((args.ignore or "").split(",")) if args.ignore else set()

    r1 = get_reader(_detect_format(dir1))
    r2 = get_reader(_detect_format(dir2))

    m1 = r1.read(dir1).memories
    m2 = r2.read(dir2).memories

    ids1 = {m.id for m in m1}
    ids2 = {m.id for m in m2}

    only_in_1 = sorted(ids1 - ids2)
    only_in_2 = sorted(ids2 - ids1)

    # Field-level diff with --ignore support
    opts = CompareOptions(
        ignore=ignore_fields
        | {"relationships", "updated_at", "source", "checksum", "metadata", "extensions", "schema_version"},
    )
    issues = compare_memories(m1, m2, options=opts)

    if args.format == "json":
        import json

        field_errs = sum(1 for i in issues if i.severity == "error")
        print(
            json.dumps(
                {
                    "only_in_source": len(only_in_1),
                    "only_in_target": len(only_in_2),
                    "field_differs": field_errs,
                    "details": [
                        {"memory_id": i.memory_id, "field": i.field, "message": i.message} for i in issues[:20]
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Only in source: {len(only_in_1)}")
        print(f"Only in target: {len(only_in_2)}")
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        print(f"Field differs: {len(errors)} errors, {len(warnings)} warnings")

        if only_in_1:
            print(f"\n  Added ({len(only_in_1)}):")
            for i in only_in_1[:10]:
                print(f"    + {i}")
        if only_in_2:
            print(f"\n  Removed ({len(only_in_2)}):")
            for i in only_in_2[:10]:
                print(f"    - {i}")
        if errors[:5]:
            print("\n  Content diffs:")
            for e in errors[:5]:
                print(f"    [{e.memory_id}] {e.field}: {e.message[:80]}")

    has_diff = bool(only_in_1 or only_in_2 or [i for i in issues if i.severity == "error"])
    sys.exit(ExitCode.DIFF_FOUND if has_diff else ExitCode.SUCCESS)


def _cmd_stats(args) -> None:
    from .registry import get_reader

    fmt = _detect_format(args.source)
    reader = get_reader(fmt)
    result = reader.read(args.source)
    mems = result.memories

    kinds: dict[str, int] = {}
    domains: dict[str, int] = {}
    total_tags = 0
    total_body = 0
    oldest = None
    newest = None

    for m in mems:
        kinds[m.kind] = kinds.get(m.kind, 0) + 1
        for d in m.domains:
            if d:
                domains[d] = domains.get(d, 0) + 1
        total_tags += len(m.tags)
        body_len = len(m.body or "")
        total_body += body_len
        if m.created_at:
            if not oldest or m.created_at < oldest:
                oldest = m.created_at
            if not newest or m.created_at > newest:
                newest = m.created_at

    n = len(mems)
    print(f"Total:     {n} memories ({fmt})")
    for k, v in sorted(kinds.items()):
        bar = "█" * (v * 20 // n) if n else ""
        print(f"  {k:<12} {v:>4} ({v * 100 // n:>2}%) {bar}")
    print(f"Domains:   {len(domains)} unique")
    if domains:
        top = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]
        for d, c in top:
            print(f"  {d:<20} {c}")
    print(f"Tags:      {total_tags / n:.1f} avg per memory" if n else "Tags: 0")
    print(f"Body:      {total_body // n} chars avg" if n else "Body: 0")
    if oldest:
        print(f"Oldest:    {oldest.date()}")
    if newest:
        print(f"Newest:    {newest.date()}")


def _detect_format(path: Path) -> str:
    """Auto-detect format from directory structure."""
    if (path / "MEMORY.md").exists() or (path / "memory").exists():
        return "openclaw"
    # Check for ombre-buckets structure
    for subdir in ["dynamic", "permanent", "feel"]:
        if (path / subdir).exists():
            return "ombre"
    return "ombre"  # default


def _cmd_inspect(args) -> None:
    from .registry import get_reader, list_formats

    args.file.read_text(encoding="utf-8")
    fmt = args.format

    # Auto-detect format
    if not fmt:
        for name in list_formats():
            try:
                plugin = get_reader(name)
                result = plugin.read(args.file.parent)
                if result.memories:
                    fmt = name
                    break
            except (NotImplementedError, KeyError):
                continue
        if not fmt:
            print("Could not detect format. Use --format to specify.")
            sys.exit(ExitCode.IO_ERROR)

    plugin = get_reader(fmt)
    try:
        result = plugin.read(args.file.parent)
    except NotImplementedError:
        print(f"'{fmt}' plugin does not support reading.")
        sys.exit(ExitCode.IO_ERROR)

    # Match by filename stem or bucket_id
    stem = args.file.stem
    mem = next((m for m in result.memories if stem == m.id or stem in str(m.id)), None)
    if not mem and result.memories:
        mem = result.memories[0]  # fallback: first memory
    if not mem:
        print("No memory parsed from file.")
        sys.exit(ExitCode.SUCCESS)

    print(f"Format:   {fmt}")
    print(f"Source:   {mem.source.uri if mem.source else 'N/A'}")
    print()
    print("Canonical:")
    print(f"  id:              {mem.id}")
    print(f"  name:            {mem.name}")
    print(f"  kind:            {mem.kind}")
    print(f"  status:          {mem.status}")
    print(f"  domains:         {mem.domains}")
    print(f"  tags:            {mem.tags}")
    print(f"  importance:      {mem.importance_score} ({mem.importance_label or 'N/A'})")
    print(f"  valence/arousal: {mem.valence}/{mem.arousal}")
    print(f"  pinned:          {mem.pinned}")
    if mem.body:
        body_preview = mem.body[:200].replace("\n", " ")
        print(f"  body:            {body_preview}{'...' if len(mem.body or '') > 200 else ''}")
    if result.warnings:
        print(f"\nWarnings: {len(result.warnings)}")
        for w in result.warnings[:5]:
            print(f"  - {w}")


def _cmd_merge(args) -> None:
    from .registry import get_reader, get_writer

    # Parse sources
    parsed_sources: list[tuple[str, Path]] = []
    for spec in args.sources:
        parsed_sources.append(_parse_source(spec))

    # Parse target
    target_fmt, target_path = _parse_source(args.to)

    # Read all sources
    all_memories: list = []
    source_stats: list[tuple[str, int]] = []
    for fmt, path in parsed_sources:
        reader = get_reader(fmt)
        try:
            result = reader.read(path)
            n = len(result.memories)
            all_memories.append((fmt, path, result.memories))
            source_stats.append((fmt, n))
            if args.verbose:
                print(f"Source {fmt}: {n} memories from {path}")
        except Exception as e:
            print(f"Error reading {fmt}:{path}: {e}", file=sys.stderr)
            sys.exit(ExitCode.IO_ERROR)

    # Merge with conflict resolution
    merged: dict[str, tuple] = {}  # id -> (memory, source_fmt, source_path)
    duplicates_resolved = 0

    for src_idx, (fmt, path, memories) in enumerate(all_memories):
        for mem in memories:
            if mem.id in merged:
                existing_mem, existing_fmt, existing_path, existing_idx = merged[mem.id]
                keep_existing = _resolve_conflict(existing_mem, mem, args.on_conflict)
                if not keep_existing:
                    merged[mem.id] = (mem, fmt, path, src_idx)
                duplicates_resolved += 1
            else:
                merged[mem.id] = (mem, fmt, path, src_idx)

    unique_memories = [t[0] for t in merged.values()]
    total = sum(n for _, n in source_stats)
    unique = len(unique_memories)
    dupes = total - unique

    print(f"Sources:  {len(parsed_sources)} ({', '.join(f'{f}({n})' for f, n in source_stats)})")
    print(f"Total:    {total} memories")
    print(f"Unique:   {unique}")
    if dupes:
        print(f"Resolved: {dupes} conflicts (strategy: {args.on_conflict})")

    if args.dry_run:
        print(f"\nDry run: would write {unique} memories to {target_fmt}:{target_path}")
        return

    writer = get_writer(target_fmt)
    start = time.perf_counter()
    warnings = writer.write(unique_memories, target_path)
    elapsed = time.perf_counter() - start

    if warnings and args.verbose:
        for w in warnings[:10]:
            print(f"  [write] {w}")
    print(f"Warnings: {len(warnings)}" if warnings else "Warnings: 0")
    print(f"Time:     {elapsed:.2f}s")


def _cmd_broadcast(args) -> None:
    from .registry import get_reader, get_writer

    src_fmt, src_path = _parse_source(args.from_spec)
    reader = get_reader(src_fmt)
    try:
        result = reader.read(src_path)
    except Exception as e:
        print(f"Error reading {src_fmt}:{src_path}: {e}", file=sys.stderr)
        sys.exit(ExitCode.IO_ERROR)

    memories = result.memories
    print(f"Read:     {len(memories)} memories from {src_fmt}")

    if args.dry_run:
        print(f"\nDry run: would broadcast to {len(args.to)} target(s)")
        for spec in args.to:
            fmt, path = _parse_source(spec)
            print(f"  → {fmt}:{path}")
        return

    parsed_targets = [_parse_source(spec) for spec in args.to]
    total_warnings = 0
    start = time.perf_counter()
    for fmt, path in parsed_targets:
        writer = get_writer(fmt)
        warnings = writer.write(memories, path)
        total_warnings += len(warnings)
        status = f"{len(memories)} written"
        if warnings:
            status += f", {len(warnings)} warnings"
        print(f"  → {fmt}:{path}: {status}")
        if args.verbose and warnings:
            for w in warnings[:5]:
                print(f"    [warn] {w}")
    elapsed = time.perf_counter() - start
    print(f"Targets:  {len(parsed_targets)}")
    print(f"Warnings: {total_warnings}" if total_warnings else "Warnings: 0")
    print(f"Time:     {elapsed:.2f}s")


def _resolve_conflict(existing, incoming, strategy: str) -> bool:
    """Return True if existing should be kept, False if incoming should replace."""
    if strategy == "first":
        return True
    if strategy == "last":
        return False

    # Compare by datetime
    def _dt_key(mem) -> int:
        dt = mem.updated_at or mem.created_at
        if dt is None:
            return 0
        return int(dt.timestamp())

    e_key = _dt_key(existing)
    i_key = _dt_key(incoming)

    if strategy == "newest":
        # key=0 means no date → dated incoming replaces undated existing
        return not i_key > e_key
    elif strategy == "oldest":
        # i_key != 0: undated incoming never displaces an existing record
        return not (i_key < e_key and i_key != 0)

    return True  # fallback: keep existing


def _parse_source(s: str) -> tuple[str, Path]:
    """Parse 'format:path' - splits on first colon only (Windows-safe)."""
    idx = s.index(":")
    fmt = s[:idx]
    path = Path(s[idx + 1 :])
    return fmt, path


if __name__ == "__main__":
    main()


# ── Helpers ────────────────────────────────────────────────────────
