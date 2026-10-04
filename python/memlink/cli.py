"""MemLink CLI: offline Full Migration, verified output and scoped workflows."""

from __future__ import annotations

import argparse
import json
import sys
from enum import IntEnum
from pathlib import Path

from ._version import __version__
from .codec import memory_dict, parse_time
from .detection import detect_format as _detect_format
from .registry import PluginNotFoundError, get_reader, get_writer, list_formats
from .transaction import TransactionError


def _resolve_conflict(existing, incoming, strategy):
    """Compatibility entry point for the original CLI helper."""
    from .converter import resolve_conflict

    return resolve_conflict(existing, incoming, strategy)


class ExitCode(IntEnum):
    SUCCESS = 0
    DIFF_FOUND = 1
    VALIDATION_ERROR = 2
    IO_ERROR = 3
    CONCURRENT_MODIFICATION = 4
    FORMAT_INCOMPATIBLE = 5
    USER_ABORT = 130


class _Specs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        previous = getattr(namespace, self.dest, None) or []
        setattr(namespace, self.dest, previous + values)


def _output_args(p):
    p.add_argument("--output-mode", choices=["daily-notes", "structured"], default="daily-notes")
    p.add_argument(
        "--all",
        action="store_true",
        help="Include every record inside the supplied approved input root, including archived",
    )
    p.add_argument("--include-archived", action="store_true")
    p.add_argument("--kind", "-k", nargs="+")
    p.add_argument("--domain", "-d", nargs="+")
    p.add_argument("--status", choices=["active", "archived"])
    p.add_argument("--include-user", action="store_true", help="Read OpenClaw USER.md explicitly")
    p.add_argument("--include-dreams", action="store_true", help="Read legacy OpenClaw DREAMS.md explicitly")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--strict",
        "--fail-on-loss",
        dest="strict",
        action="store_true",
        help="Exit 5 before committing any unallowed archive/semantic change",
    )
    p.add_argument(
        "--allow-change",
        action="append",
        default=[],
        metavar="FIELD",
        help="Explicit strict-mode field exception, recorded in receipt",
    )
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")
    p.add_argument("--verbose", "-v", action="count", default=0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memlink", description="Offline AI Memory Interchange Layer")
    p.add_argument("--version", action="version", version=f"memlink {__version__}")
    sub = p.add_subparsers(dest="command")
    for name in ("convert", "migrate", "ombre2claw", "claw2ombre"):
        q = sub.add_parser(name)
        if name in ("convert", "migrate"):
            q.add_argument("--from", "-f", dest="from_fmt", default="auto")
            q.add_argument("--to", "-t", dest="to_fmt", required=True)
        q.add_argument("--source", "-s", type=Path, required=True)
        q.add_argument("--target", "-T", type=Path, required=True)
        if name == "migrate":
            q.add_argument("--on-conflict", choices=["skip", "replace", "rename"], default="skip")
        _output_args(q)
    q = sub.add_parser("merge")
    q.add_argument("--sources", "-s", action=_Specs, nargs="+", required=True, metavar="FORMAT:PATH")
    q.add_argument("--to", "-T", required=True, metavar="FORMAT:PATH")
    q.add_argument("--on-conflict", choices=["newest", "oldest", "first", "last"], default="newest")
    q.add_argument(
        "--link-by-id", action="store_true", help="Explicitly link otherwise distinct identities by native ID"
    )
    _output_args(q)
    q = sub.add_parser("broadcast")
    q.add_argument("--from", "-f", dest="from_spec", required=True, metavar="FORMAT:PATH")
    q.add_argument("--to", "-T", action=_Specs, nargs="+", required=True, metavar="FORMAT:PATH")
    _output_args(q)
    q = sub.add_parser("validate")
    q.add_argument("--level", choices=["schema", "semantic", "roundtrip"], default="schema")
    q.add_argument("--source", "-s", type=Path, required=True)
    q.add_argument("--from", dest="from_fmt", default="auto")
    q.add_argument("--intermediate", default="openclaw")
    q.add_argument("--output-mode", choices=["daily-notes", "structured"], default="daily-notes")
    q.add_argument("--format", choices=["pretty", "json"], default="pretty")
    q = sub.add_parser("diff")
    q.add_argument("--source", "-s", nargs=2, type=Path, required=True)
    q.add_argument("--from-1", default="auto")
    q.add_argument("--from-2", default="auto")
    q.add_argument("--ignore", default="")
    q.add_argument("--format", choices=["pretty", "json"], default="pretty")
    q = sub.add_parser("stats")
    q.add_argument("--source", "-s", type=Path, required=True)
    q.add_argument("--from", dest="from_fmt", default="auto")
    q = sub.add_parser("inspect")
    q.add_argument("file", type=Path)
    q.add_argument("--format", "-f", default="auto")
    q.add_argument("--id", dest="memory_id")
    sub.add_parser("formats")
    return p


def _parse_source(s: str) -> tuple[str, Path]:
    if ":" not in s:
        raise ValueError("Expected FORMAT:PATH")
    fmt, path = s.split(":", 1)
    if not fmt or not path:
        raise ValueError("Expected nonempty FORMAT:PATH")
    return fmt, Path(path)


def _reader(fmt, path, args=None):
    selection = "auto" if fmt == "auto" else "explicit"
    fmt = _detect_format(path) if fmt == "auto" else fmt
    kwargs = {}
    if fmt == "openclaw" and args:
        kwargs = {
            "include_user": getattr(args, "include_user", False),
            "include_dreams": getattr(args, "include_dreams", False),
        }
    reader = get_reader(fmt, **kwargs)
    reader.selection = selection
    return reader


def _writer(fmt, args):
    return get_writer(fmt, **({"output_mode": args.output_mode} if fmt == "openclaw" else {}))


def _options(args):
    return {
        "all": args.all,
        "include_archived": args.include_archived,
        "kind": args.kind,
        "domain": args.domain,
        "status": args.status,
        "strict": args.strict,
        "dry_run": args.dry_run,
        "allow_changes": set(args.allow_change),
    }


def _display(receipt, args):
    if args.format == "json":
        print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))
        return
    print("Status:   " + receipt["status"])
    print("Records:  " + str(len(receipt.get("records", []))))
    for plan in receipt.get("plan", []):
        print(f"  {plan['action']}: {plan['path']}")
    if args.verbose:
        for source in receipt.get("sources", []):
            print(f"Source:   {source['format']} ({source.get('variant', 'unknown')}) {source.get('stats', {})}")
        for record in receipt.get("records", []):
            print(f"Record:   {record['id']} -> {record['target_id']} ({record['outcome']})")
            if args.verbose > 1:
                for field, impact in record["fields"].items():
                    print(f"    {field}: {impact['status']}")
    for warning in receipt.get("warnings", []):
        print("Warning:  " + warning)
    for error in receipt.get("errors", []):
        print("Error:    " + error, file=sys.stderr)
    if receipt.get("status") != "planned":
        print("Receipt:  .memlink/receipt.json")


def _cmd_convert(args):
    from .converter import convert

    if args.command == "ombre2claw":
        args.from_fmt, args.to_fmt = "ombre", "openclaw"
    elif args.command == "claw2ombre":
        args.from_fmt, args.to_fmt = "openclaw", "ombre"
    result = convert(
        _reader(args.from_fmt, args.source, args),
        _writer(args.to_fmt, args),
        args.source,
        args.target,
        mode="migrate" if args.command == "migrate" else "export",
        conflict=getattr(args, "on_conflict", "skip"),
        **_options(args),
    )
    _display(result["receipt"], args)


def _cmd_merge(args):
    from .converter import merge

    sources = [(_reader(f, p, args), p) for f, p in map(_parse_source, args.sources)]
    fmt, path = _parse_source(args.to)
    result = merge(
        sources, _writer(fmt, args), path, on_conflict=args.on_conflict, link_by_id=args.link_by_id, **_options(args)
    )
    _display(result["receipt"], args)


def _cmd_broadcast(args):
    from .converter import _execute_selection, read_source

    fmt, path = _parse_source(args.from_spec)
    reader = _reader(fmt, path, args)
    memories, context, excluded, _ = read_source(reader, path, **_options(args))
    results = []
    for spec in args.to:
        try:
            target_fmt, target_path = _parse_source(spec)
            receipt = _execute_selection(
                memories, context, excluded, _writer(target_fmt, args), path, target_path, _options(args)
            )
            results.append({"target": spec, "exit_code": 0, "receipt": receipt})
        except TransactionError as exc:
            results.append({"target": spec, "exit_code": exc.exit_code, "receipt": exc.receipt})
        except Exception as exc:
            results.append(
                {
                    "target": spec,
                    "exit_code": 5 if isinstance(exc, PluginNotFoundError) else 3,
                    "receipt": {"status": "failed", "errors": [str(exc)], "warnings": []},
                }
            )
    status = (
        "failed"
        if any(r["exit_code"] for r in results)
        else "planned"
        if args.dry_run
        else "partial"
        if any(r["receipt"]["status"] == "partial" for r in results)
        else "success"
    )
    if args.format == "json":
        print(json.dumps({"status": status, "targets": results}, ensure_ascii=False, indent=2))
    else:
        print("Status:   " + status)
        for r in results:
            print(f"  {r['target']}: {r['receipt']['status']} (exit {r['exit_code']})")
            for message in r["receipt"].get("errors", []) + r["receipt"].get("warnings", []):
                print("    " + message)
    if any(r["exit_code"] for r in results):
        raise SystemExit(3)


def _cmd_validate(args):
    from .validators import validate_roundtrip, validate_schema, validate_semantic

    fmt = None if args.from_fmt == "auto" else args.from_fmt
    if args.level == "roundtrip":
        issues = validate_roundtrip(args.source, fmt, args.intermediate, args.output_mode)
    else:
        issues = (validate_schema if args.level == "schema" else validate_semantic)(args.source, fmt)
    errors = [i for i in issues if i.severity == "error"]
    if args.format == "json":
        from dataclasses import asdict

        print(
            json.dumps(
                {"errors": [asdict(i) for i in errors], "issues": [asdict(i) for i in issues]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in issues:
            print(f"{issue.code}: {issue.message}")
        if not errors:
            print("Validated " + args.level + " using the source adapter")
    if errors:
        raise SystemExit(2)


def _cmd_inspect(args):
    if not args.file.is_file():
        raise ValueError("Inspect requires an existing single file")
    reader = _reader(args.format, args.file)
    result = reader.read(args.file)
    matches = [m for m in result.memories if args.memory_id is None or m.id == args.memory_id]
    if not matches:
        raise ValueError("Requested ID/file has no parsed memory; no fallback record")
    if args.memory_id and len(matches) != 1:
        raise ValueError("Requested ID is ambiguous")
    print(
        json.dumps(
            {"format": reader.name, "memories": [memory_dict(m) for m in matches], "warnings": result.warnings},
            ensure_ascii=False,
            indent=2,
        )
    )


def _cmd_stats(args):
    from .converter import read_source

    memories, context, _, warnings = read_source(_reader(args.from_fmt, args.source), args.source, all=True)
    dates = [parse_time(m.created_at) for m in memories if m.created_at is not None]
    print(f"Total: {len(memories)} memories")
    print("Accounting: " + json.dumps(context["stats"]))
    if dates:
        print(f"Oldest: {min(dates).isoformat()}\nNewest: {max(dates).isoformat()}")
    for warning in warnings:
        print("Warning: " + warning)


def _cmd_diff(args):
    from .converter import CompareOptions, compare_memories, read_source

    a, b = args.source
    first, _, _, _ = read_source(_reader(args.from_1, a), a, all=True)
    second, _, _, _ = read_source(_reader(args.from_2, b), b, all=True)
    ignored = set(args.ignore.split(",")) if args.ignore else set()
    for group, fields in {
        "timestamps": {"created_at", "updated_at"},
        "importance": {"importance_label", "importance_score"},
    }.items():
        if group in ignored:
            ignored.update(fields)
            ignored.remove(group)
    issues = compare_memories(first, second, CompareOptions(ignore=ignored))
    from dataclasses import asdict

    print(
        json.dumps({"issues": [asdict(i) for i in issues]}, ensure_ascii=False, indent=2)
    ) if args.format == "json" else print(f"Differences: {len(issues)}")
    if issues:
        raise SystemExit(1)


def _cmd_formats():
    for fmt, caps in list_formats().items():
        print(f"{fmt:<15} reader={'yes' if caps['reader'] else 'no'} writer={'yes' if caps['writer'] else 'no'}")


def _dispatch(args):
    commands = {
        "convert": _cmd_convert,
        "migrate": _cmd_convert,
        "ombre2claw": _cmd_convert,
        "claw2ombre": _cmd_convert,
        "merge": _cmd_merge,
        "broadcast": _cmd_broadcast,
        "validate": _cmd_validate,
        "inspect": _cmd_inspect,
        "stats": _cmd_stats,
        "diff": _cmd_diff,
    }
    if args.command == "formats":
        _cmd_formats()
    elif args.command in commands:
        commands[args.command](args)


def main():
    # The CLI owns its text streams: redirected JSON and diagnostics are UTF-8
    # regardless of the locale or Python UTF-8 mode. Keep embedded text sinks usable.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    try:
        _dispatch(args)
    except TransactionError as exc:
        if getattr(args, "format", None) == "json":
            print(json.dumps(exc.receipt, ensure_ascii=False, indent=2))
        else:
            print("Error: " + str(exc), file=sys.stderr)
            for warning in exc.receipt.get("warnings", []):
                print("Warning: " + warning, file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except PluginNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(5) from exc
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(3) from exc


if __name__ == "__main__":
    main()
