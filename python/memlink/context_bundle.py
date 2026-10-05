"""Private archives, digest-bound selection, and verified context bundles.

No network or model dependency. Full Migration retains its existing contracts.
All bundles use the existing transaction's exclusive writes and owned rollback.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files as resource_files
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from ._version import __version__
from .codec import identity, memory_from_dict, stable_json
from .context_scope import (
    approved_path,
    assert_source,
    capture,
    object_sha,
    parse_view,
    scope_rules,
    sha,
    source_ref,
    source_snapshot,
)
from .context_text import HEADER, inventory, project, render, secret_spans, section, transform
from .read_support import load_json, loads_json
from .safety import (
    MAX_FILE_BYTES,
    MAX_RECORDS,
    check_overlap,
    checked_root,
    digest,
    file_key,
    files_in,
    safe_child,
    snapshot,
)
from .transaction import OutputTransaction, TransactionError
from .validators import validate_instance, validate_memory

DEFAULT_MAX_BYTES = 1024 * 1024
DEFAULT_MAX_RECORDS = 1000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _schema(value, filename: str) -> None:
    schema = json.loads(resource_files("memlink").joinpath("resources/" + filename).read_text(encoding="utf-8"))
    issues = validate_instance(value, schema)

    def closed(data, spec, path=""):
        if isinstance(data, dict):
            props = spec.get("properties", {})
            for key in data:
                sub = props.get(key, spec.get("additionalProperties", True))
                if sub is False:
                    issues.append(path + "." + key + ": unexpected field")
                elif isinstance(sub, dict):
                    closed(data[key], sub, path + "." + key)
        if isinstance(data, (list, str)):
            for name, sign in (("min", -1), ("max", 1)):
                limit = spec.get(name + ("Items" if isinstance(data, list) else "Length"))
                if limit is not None and sign * len(data) > sign * limit:
                    issues.append(path + ": resource/length bound exceeded")
        if isinstance(data, list):
            if spec.get("uniqueItems") and len({stable_json(x) for x in data}) != len(data):
                issues.append(path + ": duplicate items")
            for item in data:
                closed(item, spec.get("items", {}), path + "[]")

    closed(value, schema)
    if issues:
        # Diagnostics report schema locations, never sensitive input values.
        raise ValueError("Invalid context schema: " + "; ".join(issues[:8]))


def _proofs(records: list[dict]) -> list[dict]:
    return [{"record_id": r["record_id"], "sha256": r["sha256"]} for r in records]


def _exact(value: dict, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Unexpected/missing " + label + " fields")


def _files(content: dict[str, bytes]) -> list[dict]:
    return [{"path": path, "sha256": sha(raw), "bytes": len(raw)} for path, raw in sorted(content.items())]


def _report(manifest: dict, outputs: list[dict]) -> dict:
    pack = manifest["kind"] == "private-pack"
    records = manifest["records"]
    policy = manifest["policy"]
    warnings = []
    if not pack and policy["secrets"] == "warn" and manifest["safety"]["detected"]:
        warnings.append(f"{manifest['safety']['detected']} suspected credential occurrence(s); warn policy shares them")
    if not pack and manifest["budget"]["truncated"]:
        warnings.append("Explicit record-boundary truncation excluded approved records")
    if pack:
        warnings.append("Private archive: contains complete approved sources; do not share/upload by default")
        if manifest["reader"]["suspected_credentials"]:
            warnings.append(
                f"Private sources contain {manifest['reader']['suspected_credentials']} suspected credentials"
            )
    warnings.append("Deterministic secret checks are advisory, not complete DLP; hashes are not signatures")
    return {
        "schema": "memlink-receipt",
        "version": "1",
        "tool_version": manifest["tool_version"],
        "transaction_id": manifest["bundle_id"],
        "operation": "export",
        "bundle_kind": manifest["kind"],
        "sources": [
            {
                "format": "openclaw",
                "namespace": manifest["scope"]["namespace"],
                "approved_rules": manifest["scope"]["rules"],
                "snapshot_sha256": manifest["snapshot_sha256"],
            }
        ],
        "target": {"format": "context-bundle", "kind": manifest["kind"]},
        "filters": {"mode": "private-archive" if pack else manifest["approval"]["mode"]},
        "excluded": [] if pack else manifest["approval"]["excluded"],
        "records": [
            {
                "identity": r["identity"],
                "id": r["record_id"],
                "target_id": r["record_id"],
                "outcome": "output",
                "fields": {
                    "content": {"status": "canonical-private" if pack else "deterministic-text"},
                    "unknown_fields": {"status": "private-only"},
                },
            }
            for r in records
        ],
        "plan": [{"path": f["path"], "action": "create"} for f in outputs],
        "outputs": outputs,
        "readback": {"status": "verified", "method": "offline-bundle"},
        "backup": None,
        "warnings": warnings,
        "errors": [],
        "status": "success",
        "human_reviewed": False if pack else manifest["human_reviewed"],
        "review": None if pack else manifest["review"],
        "policy": policy,
        "accounting": {
            "approved": len(records) if pack else len(manifest["approval"]["requested"]),
            "output": len(records),
            "excluded": 0 if pack else len(manifest["approval"]["excluded"]),
        },
        **({} if pack else {"safety": manifest["safety"], "budget": manifest["budget"]}),
    }


def _seal(manifest: dict, content: dict[str, bytes]) -> dict[str, bytes]:
    report = _report(manifest, _files(content))
    content["report.json"] = json_bytes(report)
    manifest["files"] = _files(content)
    content["manifest.json"] = json_bytes(manifest)
    if any(len(raw) > MAX_FILE_BYTES for raw in content.values()):
        raise ValueError("Bundle artifact exceeds the per-file byte limit")
    return content


class BundleTransaction(OutputTransaction):
    """New-directory bundle export, with a final manifest and real stage readback."""

    def __init__(self, target: Path, sources: list[Path]):
        super().__init__(SimpleNamespace(name="context-bundle"), target, sources=sources)
        if self.target.exists():
            raise ValueError("Bundle output must be a new directory")

    def publish(self, content: dict[str, bytes], guard: Callable[[], None]) -> dict:
        try:
            self._mkdir(self.target.parent)
            self.lock = self.target.parent / (".memlink-lock-" + sha(str(self.target).encode())[:24])
            with self.lock.open("xb") as stream:
                stream.write(self.lock_token)
        except FileExistsError as exc:
            self.lock = None
            raise TransactionError("Another bundle operation owns this target", {}, 4) from exc
        try:
            with tempfile.TemporaryDirectory(prefix=".memlink-stage-", dir=self.target.parent) as temp:
                stage = Path(temp)
                for path, raw in content.items():
                    out = safe_child(stage, path)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(raw)
                load_bundle(stage)
                self.before_commit()
                guard()
                self._check_current()
                for path in sorted(set(content) - {"manifest.json"}):
                    self._put(safe_child(stage, path), path, None)
                guard()
                self._put(stage / "manifest.json", "manifest.json", None)
                result = load_bundle(self.target)
                guard()
                return result.report
        except BaseException as exc:
            problems = self._rollback()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            code = exc.exit_code if isinstance(exc, TransactionError) else 4 if isinstance(exc, RuntimeError) else 3
            raise TransactionError(
                "Bundle export failed; owned output rolled back",
                {
                    "errors": ["Bundle export failed"],
                    "warnings": problems,
                },
                code,
            ) from exc
        finally:
            if self.lock and self.lock.exists() and self.lock.read_bytes() == self.lock_token:
                self.lock.unlink()


@dataclass
class Bundle:
    root: Path
    manifest: dict
    report: dict
    records: list[dict]
    manifest_sha256: str
    disk_snapshot: dict
    disk_directories: set[str]

    def unchanged(self) -> None:
        if snapshot(self.root) != self.disk_snapshot or _disk_files(self.root)[1] != self.disk_directories:
            raise TransactionError("Bundle changed during operation; retry", {}, 4)


def pack(root: Path, target: Path, *, include_user: bool = False, include_dreams: bool = False) -> dict:
    root = checked_root(root)
    transaction = BundleTransaction(target, [root])
    rules = scope_rules(include_user, include_dreams)
    records, context, before, sources = capture(root, rules)
    for record in records:
        record["sha256"] = object_sha(record)
    namespace = records[0]["identity"]["namespace"]
    source_entries = [
        {"ref": source_ref(path), "path": path, "sha256": sha(raw), "bytes": len(raw)}
        for path, raw in sorted(sources.items())
    ]
    manifest = {
        "schema": "memlink-context-bundle",
        "version": "1",
        "kind": "private-pack",
        "tool_version": __version__,
        "bundle_id": uuid.uuid4().hex,
        "created_at": now(),
        "scope": {"format": "openclaw", "namespace": namespace, "rules": rules, "approved_root": str(root)},
        "snapshot_sha256": object_sha(source_entries),
        "sources": source_entries,
        "records": [
            {**p, "identity": r["identity"], "source_ref": r["source_ref"]}
            for p, r in zip(_proofs(records), records, strict=True)
        ],
        "reader": {
            "variant": context["variant"],
            "stats": context["stats"],
            "warnings": context["warnings"],
            "suspected_credentials": sum(len(secret_spans(raw.decode("utf-8"))) for raw in sources.values()),
        },
        "policy": {"secrets": "private", "literal_rules": 0, "pattern_rules": 0},
    }
    content = {"sources/" + path: raw for path, raw in sources.items()}
    content["records.jsonl"] = "".join(stable_json(r) + "\n" for r in records).encode("utf-8")
    content["inventory.md"] = inventory(records)
    return transaction.publish(_seal(manifest, content), lambda: assert_source(root, rules, before))


def _disk_files(root: Path) -> tuple[dict, set[str]]:
    import os

    paths = {f.relative_to(root).as_posix(): f for f in files_in(root, include_control=True)}
    directories = {
        Path(base, name).relative_to(root).as_posix()
        for base, dirs, _ in os.walk(root, followlinks=False)
        for name in dirs
    }
    return paths, directories


def load_bundle(root: Path, *, expected_sha256: str | None = None) -> Bundle:
    try:
        return _load_bundle(root, expected_sha256=expected_sha256)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed context bundle structure") from exc


def _load_bundle(root: Path, *, expected_sha256: str | None = None) -> Bundle:
    root = checked_root(root)
    if not root.is_dir():
        raise ValueError("verify requires a bundle directory")
    before = snapshot(root)
    manifest_raw = safe_child(root, "manifest.json").read_bytes()
    manifest_sha = sha(manifest_raw)
    if expected_sha256 is not None and manifest_sha != expected_sha256:
        raise ValueError("Manifest differs from the externally retained SHA256")
    manifest = loads_json(manifest_raw.decode("utf-8"))
    _schema(manifest, "memlink-context-bundle-v1.schema.json")
    common = {
        "schema",
        "version",
        "kind",
        "tool_version",
        "bundle_id",
        "created_at",
        "scope",
        "snapshot_sha256",
        "sources",
        "records",
        "policy",
        "files",
    }
    pack_kind = manifest["kind"] == "private-pack"
    _exact(
        manifest,
        common | ({"reader"} if pack_kind else {"approval", "budget", "safety", "human_reviewed", "review"}),
        "manifest",
    )
    _exact(manifest["scope"], {"format", "namespace", "rules"} | ({"approved_root"} if pack_kind else set()), "scope")
    rules = manifest["scope"]["rules"]
    if rules != scope_rules("USER.md" in rules, "DREAMS.md" in rules):
        raise ValueError("Unknown/expanded approved memory scope")
    if pack_kind and manifest["scope"]["namespace"] != (
        "openclaw:" + sha(manifest["scope"]["approved_root"].encode("utf-8"))[:20]
    ):
        raise ValueError("Source namespace/root mismatch")
    actual, directories = _disk_files(root)
    expected = {f["path"]: f for f in manifest["files"]}
    if len(expected) != len(manifest["files"]) or len({file_key(p) for p in expected}) != len(expected):
        raise ValueError("Duplicate bundle file paths")
    if "manifest.json" in expected or set(actual) != {*expected, "manifest.json"}:
        raise ValueError("Missing/extra bundle files")
    expected_dirs = {
        str(parent).replace("\\", "/") for p in expected for parent in Path(p).parents if str(parent) != "."
    }
    if directories != expected_dirs:
        raise ValueError("Missing/extra bundle directories")
    for path, entry in expected.items():
        file = safe_child(root, path)
        if digest(file) != entry["sha256"] or file.stat().st_size != entry["bytes"]:
            raise ValueError("Artifact digest/size mismatch")
    report = load_json(safe_child(root, "report.json"))
    _schema(report, "memlink-context-report-v1.schema.json")
    _schema(report, "memlink-receipt-v1.schema.json")
    records = _verify_pack(root, manifest, expected) if pack_kind else _verify_handoff(root, manifest, expected)
    outputs = [f for f in manifest["files"] if f["path"] != "report.json"]
    if report != _report(manifest, outputs):
        raise ValueError("Receipt disagrees with bundle/policy/review/budget")
    if snapshot(root) != before:
        raise TransactionError("Bundle changed during verification", {}, 4)
    return Bundle(root, manifest, report, records, manifest_sha, before, directories)


def _verify_pack(root: Path, manifest: dict, expected: dict) -> list[dict]:
    sources = manifest["sources"]
    if object_sha(sources) != manifest["snapshot_sha256"]:
        raise ValueError("Private source snapshot mismatch")
    if manifest["policy"] != {"secrets": "private", "literal_rules": 0, "pattern_rules": 0}:
        raise ValueError("Private archive cannot claim sharing/redaction")
    expected_names = {"records.jsonl", "inventory.md", "report.json"}
    for source in sources:
        _exact(source, {"ref", "path", "sha256", "bytes"}, "private source")
        if not approved_path(source["path"], manifest["scope"]["rules"]) or source["ref"] != source_ref(source["path"]):
            raise ValueError("Private source outside approved scope")
        file = expected.get("sources/" + source["path"])
        if not file or file["sha256"] != source["sha256"] or file["bytes"] != source["bytes"]:
            raise ValueError("Private source reference mismatch")
        expected_names.add("sources/" + source["path"])
    if set(expected) != expected_names or len({s["ref"] for s in sources}) != len(sources):
        raise ValueError("Private source file set mismatch")
    records = []
    for line in safe_child(root, "records.jsonl").read_text(encoding="utf-8").splitlines():
        record = loads_json(line)
        _exact(record, {"record_id", "identity", "occurrence", "source_ref", "labels", "memory", "sha256"}, "record")
        data = {k: v for k, v in record.items() if k != "sha256"}
        if record["sha256"] != object_sha(data):
            raise ValueError("Private record digest mismatch")
        if validate_instance(record["memory"]):
            raise ValueError("Invalid canonical data in private pack")
        memory = memory_from_dict(record["memory"])
        if validate_memory(memory) or identity(memory) != record["identity"]:
            raise ValueError("Invalid canonical record/identity")
        records.append(record)
        if len(records) > MAX_RECORDS:
            raise ValueError("Record resource limit exceeded")
    reparsed, context = parse_view(root / "sources", manifest["scope"]["namespace"], manifest["scope"]["rules"])
    if manifest["reader"] != {
        "variant": context["variant"],
        "stats": context["stats"],
        "warnings": context["warnings"],
        "suspected_credentials": sum(
            len(secret_spans((root / "sources" / s["path"]).read_text(encoding="utf-8"))) for s in sources
        ),
    }:
        raise ValueError("Private reader diagnostics/accounting mismatch")
    for record in reparsed:
        record["sha256"] = object_sha(record)
    if records != reparsed:
        raise ValueError("Private canonical data differs from actual source readback")
    descriptors = [
        {**p, "identity": r["identity"], "source_ref": r["source_ref"]}
        for p, r in zip(_proofs(records), records, strict=True)
    ]
    if descriptors != manifest["records"] or len({r["record_id"] for r in records}) != len(records):
        raise ValueError("Private record manifest mismatch")
    if inventory(records) != safe_child(root, "inventory.md").read_bytes():
        raise ValueError("Private inventory differs from actual records")
    return records


def _verify_handoff(root: Path, manifest: dict, expected: dict) -> list[dict]:
    if set(expected) != {"context.md", "report.json"}:
        raise ValueError("Handoff cannot contain private sources or extra files")
    if manifest["policy"]["secrets"] not in {"warn", "redact", "fail"}:
        raise ValueError("Invalid handoff secrets policy")
    records = manifest["records"]
    for record in records:
        _schema(record, "memlink-context-record-v1.schema.json")
    ids = [r["record_id"] for r in records]
    approval = manifest["approval"]
    if approval["mode"] == "all" and (
        len(approval["requested"]) != approval["pack_record_count"]
        or object_sha(approval["requested"]) != approval["pack_records_sha256"]
    ):
        raise ValueError("--all approval differs from the complete pack inventory commitment")
    requested = {p["record_id"]: p["sha256"] for p in approval["requested"]}
    excluded = {p["record_id"]: p["sha256"] for p in approval["excluded"]}
    if (
        len(requested) != len(approval["requested"])
        or len(excluded) != len(approval["excluded"])
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Duplicate approval/record IDs")
    if set(ids) & set(excluded) or set(requested) != set(ids) | set(excluded):
        raise ValueError("Handoff selection differs from approved records")
    if [p["record_id"] for p in approval["requested"]] != ids + list(excluded):
        raise ValueError("Budget selection must retain a complete ordered prefix")
    for record in records:
        if record["original_sha256"] != requested[record["record_id"]]:
            raise ValueError("Handoff record is not bound to its approval")
        if record["identity"]["namespace"] != manifest["scope"]["namespace"]:
            raise ValueError("Handoff record belongs to another source scope")
    if any(requested[rid] != checksum for rid, checksum in excluded.items()):
        raise ValueError("Excluded record approval mismatch")
    sources = {s["ref"]: s for s in manifest["sources"]}
    if len(sources) != len(manifest["sources"]):
        raise ValueError("Duplicate handoff source refs")
    for source in sources.values():
        _exact(source, {"ref", "path", "format"}, "handoff source")
        if not approved_path(source["path"], manifest["scope"]["rules"]):
            raise ValueError("Handoff source outside approved scope")
    if set(sources) != {r["source"]["ref"] for r in records} or any(
        r["source"] != sources[r["source"]["ref"]] for r in records
    ):
        raise ValueError("Unresolved/unused handoff source refs")
    # Known paths/controls and credentials must match the declared output policy.
    clean, counts = transform(records, "warn")
    if clean != records or counts["path_scrubbed"] or counts["text_escaped"]:
        raise ValueError("Handoff contains unsanitized paths/control characters")
    if manifest["policy"]["secrets"] == "warn" and counts["detected"] != manifest["safety"]["detected"]:
        raise ValueError("Secret warning/report mismatch")
    if manifest["policy"]["secrets"] in {"redact", "fail"} and counts["detected"]:
        raise ValueError("Secret remains under redact/fail policy")
    if manifest["policy"]["secrets"] != "redact" and manifest["safety"]["redacted"]:
        raise ValueError("Redaction contradicts policy")
    if manifest["policy"]["secrets"] == "fail" and manifest["safety"]["detected"]:
        raise ValueError("Fail policy cannot claim successful secret findings")
    if manifest["safety"]["redacted"] > stable_json(records).count("[REDACTED]"):
        raise ValueError("Redaction report has no corresponding output markers")
    text = render(records)
    if safe_child(root, "context.md").read_bytes() != text:
        raise ValueError("Context differs from the actual approved text projection")
    budget = manifest["budget"]
    if budget["actual_bytes"] != len(text) or budget["actual_records"] != len(records):
        raise ValueError("Budget accounting mismatch")
    if len(text) > budget["max_bytes"] or len(records) > budget["max_records"]:
        raise ValueError("Handoff exceeds declared budget")
    if bool(excluded) != budget["truncated"] or bool(excluded) and not budget["truncate_at_record_boundary"]:
        raise ValueError("Undeclared budget exclusions")
    if manifest["human_reviewed"]:
        if manifest["review"] != {"method": "tty-confirmation", "context_sha256": sha(text), "decision": "approved"}:
            raise ValueError("Human review evidence is absent/stale")
    elif manifest["review"] is not None:
        raise ValueError("No-review output cannot claim human confirmation")
    return records


def choose(
    bundle: Bundle, *, all_records: bool = False, sources=(), ids=(), tags=(), projects=(), scopes=(), states=()
) -> dict:
    if bundle.manifest["kind"] != "private-pack":
        raise ValueError("select requires a verified private pack")
    groups = [sources, ids, tags, projects, scopes, states]
    if all_records and any(groups):
        raise ValueError("--all cannot be combined with selectors")
    if not all_records and not any(groups):
        raise ValueError("Explicit --all or selectors are required; nothing is silently selected")
    source_map = {s["ref"]: s["path"] for s in bundle.manifest["sources"]}
    normalized = [str(s).replace("\\", "/") for s in sources]
    scope_pairs = []
    for rule in scopes:
        key, sep, value = rule.partition("=")
        if not sep or key not in {"user_id", "agent_id", "session_id", "run_id", "scope"} or not value:
            raise ValueError("Scope selectors use user_id|agent_id|session_id|run_id|scope=VALUE")
        scope_pairs.append((key, value))
    candidates = []
    for r in bundle.records:
        labels = r["labels"]
        if sources and source_map[r["source_ref"]] not in normalized:
            continue
        if ids and r["record_id"] not in ids and r["memory"]["id"] not in ids:
            continue
        if tags and not set(tags).intersection(labels["tags"]):
            continue
        if projects and labels["project"] not in projects:
            continue
        if states and labels["state"] not in states:
            continue
        if scope_pairs and not all(str(r["identity"]["scope"].get(k)) == v for k, v in scope_pairs):
            continue
        candidates.append(r)
    if not candidates:
        raise ValueError("Selectors matched no records")
    if ids:
        for requested in ids:
            matching = [r for r in candidates if requested in {r["record_id"], r["memory"]["id"]}]
            if not matching:
                raise ValueError("Requested record ID was not selected")
            if len(matching) > 1:
                raise ValueError("Native ID is ambiguous; use inventory record_id or scope selector")
    return {
        "schema": "memlink-context-selection",
        "version": "1",
        "pack_sha256": bundle.manifest_sha256,
        "mode": "all" if all_records else "selection",
        "created_at": now(),
        "records": _proofs(candidates),
    }


def validate_selection(bundle: Bundle, selection: dict) -> list[dict]:
    _schema(selection, "memlink-context-selection-v1.schema.json")
    if bundle.manifest["kind"] != "private-pack" or selection["pack_sha256"] != bundle.manifest_sha256:
        raise ValueError("Selection is stale or bound to another private pack")
    approved = {r["record_id"]: r for r in bundle.records}
    selected_ids = [p["record_id"] for p in selection["records"]]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Duplicate selection record IDs")
    if not selected_ids:
        raise ValueError("Selection must approve at least one record")
    for proof in selection["records"]:
        if proof["record_id"] not in approved or approved[proof["record_id"]]["sha256"] != proof["sha256"]:
            raise ValueError("Selection record version/scope does not match private pack")
    selected = [r for r in bundle.records if r["record_id"] in selected_ids]
    if _proofs(selected) != selection["records"]:
        raise ValueError("Selection must follow the private inventory order")
    if selection["mode"] == "all" and _proofs(bundle.records) != selection["records"]:
        raise ValueError("--all approval omits approved records")
    return selected


def write_selection(bundle: Bundle, selection: dict, output: Path) -> None:
    validate_selection(bundle, selection)
    output = checked_root(output)
    check_overlap([bundle.root], output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Selection output must be a new file in an existing directory")
    raw = json_bytes(selection)
    bundle.unchanged()
    try:
        with output.open("xb") as stream:
            stream.write(raw)
        bundle.unchanged()
    except BaseException:
        if output.exists() and digest(output) == sha(raw):
            output.unlink()
        raise


def prepare_handoff(
    bundle: Bundle,
    selection: dict,
    *,
    secrets: str = "warn",
    redaction_rules: dict | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_records: int = DEFAULT_MAX_RECORDS,
    truncate: bool = False,
) -> tuple[dict, dict[str, bytes]]:
    selected = validate_selection(bundle, selection)
    if type(max_bytes) is not int or type(max_records) is not int or min(max_bytes, max_records) < 1:
        raise ValueError("Budgets must be positive UTF-8 bytes/record counts")
    if max_bytes > MAX_FILE_BYTES or max_records > MAX_RECORDS:
        raise ValueError("Budget exceeds bundle resource limits")
    source_map = {s["ref"]: s for s in bundle.manifest["sources"]}
    projections: list[dict] = []
    safety = {"detected": 0, "redacted": 0, "path_scrubbed": 0, "text_escaped": 0}
    bytes_used = len(HEADER.encode("utf-8"))
    excluded: list[dict] = []
    for r in selected:
        projected, counts = transform(project(r, source_map), secrets, redaction_rules)
        projected = cast(dict, projected)
        addition = len(section(projected).encode("utf-8"))
        if excluded or len(projections) >= max_records or bytes_used + addition > max_bytes:
            if not truncate:
                raise ValueError("Budget exceeded; reselect or explicitly --truncate-at-record-boundary")
            excluded.append({"record_id": r["record_id"], "sha256": r["sha256"], "reason": "budget"})
            continue
        projections.append(projected)
        bytes_used += addition
        for key, value in counts.items():
            safety[key] += value
    if not projections:
        raise ValueError("Budget cannot fit one complete record; no handoff was created")
    rules = redaction_rules or {"literals": [], "patterns": []}
    public_sources = {r["source"]["ref"]: r["source"] for r in projections}
    manifest = {
        "schema": "memlink-context-bundle",
        "version": "1",
        "kind": "handoff",
        "tool_version": __version__,
        "bundle_id": uuid.uuid4().hex,
        "created_at": now(),
        "scope": {k: v for k, v in bundle.manifest["scope"].items() if k != "approved_root"},
        "snapshot_sha256": bundle.manifest["snapshot_sha256"],
        "sources": list(public_sources.values()),
        "records": projections,
        "approval": {
            "mode": selection["mode"],
            "pack_sha256": bundle.manifest_sha256,
            "pack_record_count": len(bundle.records),
            "pack_records_sha256": object_sha(_proofs(bundle.records)),
            "requested": selection["records"],
            "excluded": excluded,
        },
        "policy": {
            "secrets": secrets,
            "literal_rules": len(rules["literals"]),
            "pattern_rules": len(rules["patterns"]),
        },
        "safety": safety,
        "human_reviewed": False,
        "review": None,
        "budget": {
            "max_bytes": max_bytes,
            "max_records": max_records,
            "actual_bytes": bytes_used,
            "actual_records": len(projections),
            "truncate_at_record_boundary": truncate,
            "truncated": bool(excluded),
        },
    }
    return manifest, {"context.md": render(projections)}


def handoff(
    bundle: Bundle,
    selection: dict,
    target: Path,
    *,
    review: bool = False,
    _source_guard: Callable[[], None] | None = None,
    _source_root: Path | None = None,
    **options,
) -> dict:
    transaction = BundleTransaction(target, [bundle.root, *([_source_root] if _source_root else [])])
    manifest, content = prepare_handoff(bundle, selection, **options)
    if type(review) is not bool:
        raise ValueError("Review must request an explicit TTY confirmation")
    if review:
        from .context_cli import _tty_review

        if not _tty_review(content["context.md"]):
            raise TransactionError("Human review declined; no output was created", {}, 130)
        manifest["human_reviewed"] = True
        manifest["review"] = {
            "method": "tty-confirmation",
            "context_sha256": sha(content["context.md"]),
            "decision": "approved",
        }
    bundle.unchanged()

    def guard():
        bundle.unchanged()
        if _source_guard:
            _source_guard()

    return transaction.publish(_seal(manifest, content), guard)


def handoff_from(
    root: Path, target: Path, *, include_user: bool = False, include_dreams: bool = False, **options
) -> dict:
    """Explicit --all path: no selection CLI, no human review by default."""
    root = checked_root(root)
    check_overlap([root], target)
    rules = scope_rules(include_user, include_dreams)
    before, _ = source_snapshot(root, rules)
    with tempfile.TemporaryDirectory(prefix="memlink-private-handoff-") as temp:
        private_root = Path(temp).resolve(strict=True) / "private-pack"
        pack(root, private_root, include_user=include_user, include_dreams=include_dreams)
        assert_source(root, rules, before)
        private = load_bundle(private_root)
        selection = choose(private, all_records=True)
        return handoff(
            private,
            selection,
            target,
            _source_guard=lambda: assert_source(root, rules, before),
            _source_root=root,
            **options,
        )


def verify(
    root: Path,
    *,
    expected_sha256: str | None = None,
    private_pack: Path | None = None,
    redaction_rules: dict | None = None,
) -> dict:
    bundle = load_bundle(root, expected_sha256=expected_sha256)
    provenance = "not-checked"
    if private_pack is not None:
        if bundle.manifest["kind"] != "handoff":
            raise ValueError("--pack is only for verifying handoff against its private approval")
        private = load_bundle(private_pack)
        approval = bundle.manifest["approval"]
        selection = {
            "schema": "memlink-context-selection",
            "version": "1",
            "created_at": now(),
            "pack_sha256": approval["pack_sha256"],
            "mode": approval["mode"],
            "records": approval["requested"],
        }
        policy = bundle.manifest["policy"]
        rules = redaction_rules or {"literals": [], "patterns": []}
        if len(rules["literals"]) != policy["literal_rules"] or len(rules["patterns"]) != policy["pattern_rules"]:
            raise ValueError("Use the original private redaction rules to verify the projection against --pack")
        budget = bundle.manifest["budget"]
        planned, _ = prepare_handoff(
            private,
            selection,
            secrets=policy["secrets"],
            redaction_rules=rules,
            max_bytes=budget["max_bytes"],
            max_records=budget["max_records"],
            truncate=budget["truncate_at_record_boundary"],
        )
        for key in ("scope", "snapshot_sha256", "sources", "records", "approval", "policy", "budget", "safety"):
            if bundle.manifest[key] != planned[key]:
                raise ValueError("Handoff projection/approval differs from actual private source records")
        private.unchanged()
        provenance = "verified-against-pack"
    elif redaction_rules is not None:
        raise ValueError("--redact-file verification requires --pack")
    bundle.unchanged()
    return {
        "status": "verified",
        "kind": bundle.manifest["kind"],
        "manifest_sha256": bundle.manifest_sha256,
        "records": len(bundle.records),
        "human_reviewed": bundle.report["human_reviewed"],
        "provenance": provenance,
        "warnings": bundle.report["warnings"],
    }
