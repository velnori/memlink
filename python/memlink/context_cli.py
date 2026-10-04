"""CLI for private pack, explicit selection, handoff, and offline verification."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .context_bundle import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_RECORDS,
    choose,
    handoff,
    handoff_from,
    load_bundle,
    pack,
    verify,
    write_selection,
)
from .context_text import inventory
from .read_support import load_json

SCOPE_HELP = (
    "Approved scope: supplied OpenClaw workspace only; MEMORY.md + recursive memory/**/*.md. "
    "USER.md and DREAMS.md require explicit flags, including with --all. "
    "No home discovery, config, credentials, sessions, skills, or plugins."
)


def _input_flags(parser):
    parser.add_argument("--from", dest="from_fmt", choices=["openclaw"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--include-user", action="store_true", help="Explicitly approve optional USER.md")
    parser.add_argument("--include-dreams", action="store_true", help="Explicitly approve optional DREAMS.md")


def _selectors(parser):
    parser.add_argument(
        "--all", action="store_true", help="Explicitly approve every record in this pack's memory scope"
    )
    for flag, dest, help_text in (
        ("--source", "sources", "Exact source-relative file (Windows separators accepted)"),
        ("--id", "ids", "Inventory record_id or unambiguous native ID"),
        ("--tag", "tags", "Existing structured tag; no inferred labels"),
        ("--project", "projects", "Existing structured project field"),
        ("--scope", "scopes", "Exact scope KEY=VALUE; scope=unknown is explicit"),
        ("--state", "states", "Exact structured state, e.g. active, archived, unresolved"),
    ):
        parser.add_argument(flag, dest=dest, action="append", default=[], help=help_text)


def _selector_options(args):
    return {
        "all_records": args.all,
        **{k: getattr(args, k) for k in ("sources", "ids", "tags", "projects", "scopes", "states")},
    }


def add_commands(sub):
    p = sub.add_parser("pack", description="Create a PRIVATE memory archive. " + SCOPE_HELP)
    _input_flags(p)
    p.add_argument("--out", type=Path, required=True, help="New private pack directory")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")
    p = sub.add_parser(
        "select",
        description="Bind explicit approval to a verified private pack digest. "
        "Across selector types use AND; repeated values within a type use OR, except --scope uses AND.",
    )
    p.add_argument("pack", type=Path)
    _selectors(p)
    p.add_argument("--interactive", action="store_true", help="TTY numbered record picker; optional, not review")
    p.add_argument("--out", type=Path, required=True, help="New private selection JSON file")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")
    p = sub.add_parser("handoff", description="Create controlled context.md from explicit approval. " + SCOPE_HELP)
    p.add_argument("pack", type=Path, nargs="?")
    _input_flags(p)
    _selectors(p)
    p.add_argument("--selection", type=Path, help="Digest-bound private selection JSON")
    p.add_argument("--out", type=Path, required=True, help="New shareable handoff directory")
    p.add_argument(
        "--secrets",
        choices=["warn", "redact", "fail"],
        default="warn",
        help="Deterministic checks, not complete DLP; warn shares detected values without a prompt",
    )
    p.add_argument("--redact-file", type=Path, help="PRIVATE JSON with literals/patterns arrays; requires redact")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="UTF-8 context.md budget, not tokens")
    p.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    p.add_argument(
        "--truncate-at-record-boundary", action="store_true", help="Explicitly keep a complete ordered prefix"
    )
    p.add_argument("--review", action="store_true", help="Optional TTY review of exact final text, then type APPROVE")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")
    p = sub.add_parser(
        "verify",
        description="Verify schemas, exact file set, digests, approval, policy, and budget offline. "
        "Hashes are not signatures; retain manifest SHA256 separately for stronger tamper detection.",
    )
    p.add_argument("bundle", type=Path)
    p.add_argument("--expected-sha256", help="Externally retained manifest.json SHA256")
    p.add_argument("--pack", type=Path, help="Also compare handoff to the original verified private pack")
    p.add_argument("--redact-file", type=Path, help="Original private rules, only with --pack")
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")


def _tty_review(text: bytes) -> bool:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("--review requires a TTY; omit it for deterministic no-review automation")
    print(text.decode("utf-8"), file=sys.stderr, end="")
    print(
        "This is the exact context.md to be shared. Type APPROVE to confirm; anything else declines:", file=sys.stderr
    )
    return input() == "APPROVE"


def _pick(bundle, args):
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("--interactive requires a TTY; use explicit selectors/selection/--all for automation")
    if args.all or any(getattr(args, k) for k in ("sources", "ids", "tags", "projects", "scopes", "states")):
        raise ValueError("Interactive selection cannot be combined with selectors/--all")
    print(inventory(bundle.records).decode("utf-8"), file=sys.stderr)
    for index, r in enumerate(bundle.records, 1):
        print(f"{index}: {r['record_id']}", file=sys.stderr)
    print(
        "Enter comma-separated record numbers (this chooses records; it does not mark human review):", file=sys.stderr
    )
    try:
        selected = {int(x.strip()) for x in input().split(",")}
    except ValueError as exc:
        raise ValueError("Invalid record numbers") from exc
    if not selected or min(selected) < 1 or max(selected) > len(bundle.records):
        raise ValueError("Record number is outside this inventory")
    return choose(bundle, ids=[r["record_id"] for i, r in enumerate(bundle.records, 1) if i in selected])


def run(args):
    if args.command == "pack":
        if args.from_fmt != "openclaw" or args.input is None:
            raise ValueError("pack requires --from openclaw --input WORKSPACE")
        result = pack(args.input, args.out, include_user=args.include_user, include_dreams=args.include_dreams)
    elif args.command == "select":
        bundle = load_bundle(args.pack)
        selection = _pick(bundle, args) if args.interactive else choose(bundle, **_selector_options(args))
        write_selection(bundle, selection, args.out)
        result = {
            "status": "selected",
            "records": len(selection["records"]),
            "human_reviewed": False,
            "pack_sha256": bundle.manifest_sha256,
        }
    elif args.command == "handoff":
        if args.review and (not sys.stdin.isatty() or not sys.stderr.isatty()):
            raise ValueError("--review requires a TTY; no-review automation uses selectors/selection/--all")
        options = {
            "secrets": args.secrets,
            "redaction_rules": load_json(args.redact_file) if args.redact_file else None,
            "max_bytes": args.max_bytes,
            "max_records": args.max_records,
            "truncate": args.truncate_at_record_boundary,
            "review": args.review,
        }
        selector_flags = any(getattr(args, k) for k in ("sources", "ids", "tags", "projects", "scopes", "states"))
        if args.pack is None:
            if args.from_fmt != "openclaw" or args.input is None or not args.all or args.selection or selector_flags:
                raise ValueError(
                    "Direct input requires --from openclaw --input WORKSPACE --all; selective mode uses pack"
                )
            result = handoff_from(
                args.input, args.out, include_user=args.include_user, include_dreams=args.include_dreams, **options
            )
        else:
            if args.input or args.from_fmt or args.include_user or args.include_dreams:
                raise ValueError("Pack input already binds source scope; input/include flags cannot expand it")
            if args.selection and (args.all or selector_flags):
                raise ValueError("Use either --selection or explicit selectors/--all")
            bundle = load_bundle(args.pack)
            selection = load_json(args.selection) if args.selection else choose(bundle, **_selector_options(args))
            result = handoff(bundle, selection, args.out, **options)
    else:
        result = verify(
            args.bundle,
            expected_sha256=args.expected_sha256,
            private_pack=args.pack,
            redaction_rules=load_json(args.redact_file) if args.redact_file else None,
        )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print("Status: " + result["status"])
        print("Records: " + str(len(result["records"]) if isinstance(result["records"], list) else result["records"]))
        print("Human reviewed: " + str(result["human_reviewed"]).lower())
        for warning in result.get("warnings", []):
            print("Warning: " + warning)
        if "manifest_sha256" in result:
            print("Manifest SHA256: " + result["manifest_sha256"])
