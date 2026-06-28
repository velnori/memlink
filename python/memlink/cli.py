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
    parser.add_argument("--version", action="version", version="memlink 0.1.0")
    sub = parser.add_subparsers(dest="command")

    # convert
    p = sub.add_parser("convert", help="Convert between memory formats")
    p.add_argument("--from", "-f", dest="from_fmt", required=True, help="Source format (ombre, openclaw)")
    p.add_argument("--to", "-t", dest="to_fmt", required=True, help="Target format (ombre, openclaw)")
    p.add_argument("--source", "-s", type=Path, required=True, help="Source directory")
    p.add_argument("--target", "-T", type=Path, required=True, help="Target directory")
    p.add_argument("--output-mode", choices=["daily-notes", "structured"], default="daily-notes",
                   help="OpenClaw output mode (default: daily-notes)")
    p.add_argument("--kind", "-k", nargs="+", help="Only convert specific kind(s)")
    p.add_argument("--dry-run", action="store_true", help="Parse only, don't write")
    p.add_argument("--include-archived", action="store_true")
    p.add_argument("--verbose", "-v", action="count", default=0)

    # validate
    p = sub.add_parser("validate", help="Validate memory files")
    p.add_argument("--level", choices=["schema", "semantic", "roundtrip"], default="schema")
    p.add_argument("--source", "-s", type=Path, required=True, help="Directory or file to validate")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")

    # inspect
    p = sub.add_parser("inspect", help="Inspect a single memory file")
    p.add_argument("file", type=Path, help="File to inspect")
    p.add_argument("--format", "-f", choices=["ombre", "openclaw"], help="Force format detection")

    # formats
    sub.add_parser("formats", help="List installed format plugins")

    return parser


# ── Dispatch ───────────────────────────────────────────────────────

def _dispatch(args) -> None:
    if args.command == "formats":
        _cmd_formats()
    elif args.command == "convert":
        _cmd_convert(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "inspect":
        _cmd_inspect(args)
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
    from .registry import get_reader, get_writer
    from .converter import convert, check_compatibility

    src_plugin = get_reader(args.from_fmt)
    dst_plugin = get_writer(args.to_fmt)

    compat = check_compatibility(src_plugin, dst_plugin)
    if compat and args.verbose:
        for w in compat:
            print(f"[compat] {w}")

    start = time.perf_counter()

    result = convert(src_plugin, dst_plugin, args.source, args.target)

    elapsed = time.perf_counter() - start

    n = len(result["memories"])
    warnings = result["warnings"]
    loss = result["feature_loss"]

    print(f"Converted: {n} memories")
    if warnings:
        print(f"Warnings:  {len(warnings)}")
        if args.verbose:
            for w in warnings[:10]:
                print(f"  - {w}")
    if loss:
        print("Feature Loss:")
        for k, v in loss.items():
            reason = _loss_reason(src_plugin, dst_plugin, k)
            print(f"  {k}: {v} dropped  ({reason})")
    print(f"Time:     {elapsed:.2f}s")


def _cmd_validate(args) -> None:
    from .validators import validate_schema, validate_semantic

    if args.level == "schema":
        issues = validate_schema(args.source)
    elif args.level == "semantic":
        issues = validate_semantic(args.source)
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


def _cmd_inspect(args) -> None:
    from .registry import get_reader, list_formats
    from .models import Memory

    text = args.file.read_text(encoding="utf-8")
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
        body_preview = mem.body[:200].replace('\n', ' ')
        print(f"  body:            {body_preview}{'...' if len(mem.body or '') > 200 else ''}")
    if result.warnings:
        print(f"\nWarnings: {len(result.warnings)}")
        for w in result.warnings[:5]:
            print(f"  - {w}")


# ── Helpers ────────────────────────────────────────────────────────

def _is_read_only(plugin) -> bool:
    try:
        plugin.read(Path("."))
        return False
    except NotImplementedError:
        return True
    except Exception:
        return False


def _is_write_only(plugin) -> bool:
    try:
        plugin.write([], Path("."))
        return False
    except NotImplementedError:
        return True
    except Exception:
        return False


def _loss_reason(src, dst, field: str) -> str:
    sc = src.capabilities
    tc = dst.capabilities
    reasons = {
        "relationships": "Target plugin capability=false",
        "emotion": "Target plugin capability=false",
    }
    if not tc.preserve_unknown_fields:
        return "Target cannot preserve unknown extensions"
    return reasons.get(field, "Format limitation")
