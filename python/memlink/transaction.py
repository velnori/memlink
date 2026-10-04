"""Verified file export/apply, with per-file commits and owned rollback.

No network, global atomicity claim, automatic deletion, or workspace configuration edits.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from ._version import __version__
from .codec import content_checksum, identity, memory_dict, parse_time, scope_of, stable_json
from .models import Memory, sanitize_id
from .read_support import load_json
from .safety import check_overlap, checked_root, digest, file_key, safe_child, snapshot


class TransactionError(RuntimeError):
    def __init__(self, message: str, receipt: dict, exit_code: int = 3):
        super().__init__(message)
        base = {
            "schema": "memlink-receipt",
            "version": "1",
            "tool_version": __version__,
            "transaction_id": uuid.uuid4().hex,
            "operation": "export",
            "sources": [],
            "target": {},
            "filters": {},
            "excluded": [],
            "records": [],
            "plan": [],
            "outputs": [],
            "readback": {"status": "not-run"},
            "backup": None,
            "warnings": [],
            "errors": [message],
            "status": "failed",
        }
        self.receipt = {**base, **receipt}
        self.exit_code = exit_code


class ConcurrentModificationError(TransactionError):
    pass


# These are public adapter mappings, not capability claims. Equality is still
# measured using the actual native reader. Comment/sidecar recovery is excluded.
NATIVE_FIELDS = {
    "generic": set(Memory.__dataclass_fields__),
    "ombre": {
        "id",
        "name",
        "body",
        "kind",
        "tags",
        "domains",
        "created_at",
        "valence",
        "arousal",
        "importance_score",
        "pinned",
    },
    "mem0": {"id", "body", "tags", "created_at", "updated_at"},
    "zep": {"id", "body", "created_at", "updated_at"},
    "openclaw": {"body", "name"},
}


def _target_memories(memories: list[Memory], fmt: str, reserved_ids: set[str] | None = None) -> list[Memory]:
    result = copy.deepcopy(memories)
    occupied: set[str] = {file_key(sanitize_id(mid)) for mid in reserved_ids or set()}
    counts: dict[str, int] = {}
    for memory in result:
        memory.created_at = parse_time(memory.created_at)
        memory.updated_at = parse_time(memory.updated_at)
        key = stable_json(identity(memory))
        occurrence = counts.get(key, 0)
        counts[key] = occurrence + 1
        seed = hashlib.sha256(f"{key}:{occurrence}".encode()).hexdigest()
        if fmt == "ombre" and memory.source and memory.source.format != "ombre":
            import re

            if not re.fullmatch(r"[0-9a-f]{12}", memory.id):
                memory.id = seed[:12]
        canonical_key = file_key(sanitize_id(memory.id))
        if canonical_key in occupied:
            memory.id = memory.id[:80] + "~" + seed[:20]
            canonical_key = file_key(sanitize_id(memory.id))
        if canonical_key in occupied:
            raise ValueError("Unresolvable target ID collision")
        occupied.add(canonical_key)
        memory.checksum = content_checksum(memory.body)
    return result


def planned_paths(memory: Memory, writer) -> str:
    fmt = writer.name
    if fmt == "generic":
        return f"notes/{sanitize_id(memory.id)}.md"
    if fmt == "mem0":
        return "memories.json"
    if fmt == "zep":
        return "facts.json"
    if fmt == "ombre":
        kind = {"emotion": "feel", "dynamic": "dynamic", "permanent": "permanent"}.get(memory.kind, "dynamic")
        domain = next((d for d in memory.domains if d != "_unknown"), "")
        parts = [kind] + ([sanitize_id(domain)] if domain else []) + [sanitize_id(memory.id) + ".md"]
        return "/".join(parts)
    if fmt == "openclaw":
        if getattr(writer, "output_mode", "daily-notes") == "structured":
            sub = "feels/" if memory.kind == "emotion" else ""
            return f"memory/{sub}{sanitize_id(memory.id)}.md"
        if memory.kind == "permanent":
            return "MEMORY.md"
        day = memory.created_at.date().isoformat() if memory.created_at else "undated"
        return f"memory/{day}.md"
    return "unknown"


def _rename_path(relative: str, sha: str, target: Path, reserved: set[str]) -> str:
    path = Path(relative)
    if relative == "MEMORY.md":
        candidate = f"memory/imported-long-term-{sha[:16]}.md"
    else:
        candidate = (path.parent / f"{path.stem[:80]}-memlink-{sha[:16]}{path.suffix}").as_posix()
    for n in range(1000):
        name = candidate if n == 0 else str(Path(candidate).with_stem(Path(candidate).stem + f"-{n}"))
        if file_key(name) not in reserved and not safe_child(target, name).exists():
            return name.replace("\\", "/")
    raise ValueError("Cannot allocate deterministic rename")


def _make_plan(candidate: dict, before: dict, target: Path, mode: str, conflict: str) -> list[dict]:
    plan = []
    reserved = {file_key(x) for x in before} | {file_key(x) for x in candidate}
    target_keys = {file_key(p): p for p in before}
    for relative, info in sorted(candidate.items()):
        old_path = target_keys.get(file_key(relative))
        old = before.get(old_path) if old_path else None
        action = "create"
        destination = relative
        if old is not None:
            destination = old_path
            if old["sha256"] == info["sha256"]:
                action = "unchanged"
            elif mode != "migrate":
                raise ValueError("Export target is not empty; use migrate with an explicit conflict policy")
            elif conflict == "skip":
                action = "skip"
            elif conflict == "replace":
                action = "update"
            else:
                destination = _rename_path(relative, info["sha256"], target, reserved)
                reserved.add(file_key(destination))
        # A directory at a proposed file path is also a conflict, never a file overwrite.
        if safe_child(target, destination).is_dir():
            raise ValueError(f"Output path is a directory: {destination}")
        plan.append(
            {
                "path": destination,
                "candidate": relative,
                "action": action,
                "conflict": old is not None and action != "unchanged",
                "strategy": conflict,
                "before_sha256": old["sha256"] if old and destination == old_path else None,
                "conflict_sha256": old["sha256"] if old else None,
                "sha256": info["sha256"],
            }
        )
    return plan


class OutputTransaction:
    """One target transaction; managed sources require matching read contexts."""

    def __init__(
        self,
        writer,
        target: Path,
        *,
        sources: list[Path] | None = None,
        mode: str = "export",
        conflict: str = "skip",
        strict: bool = False,
        dry_run: bool = False,
        allow_changes: set[str] | None = None,
    ):
        if mode not in {"export", "migrate"} or conflict not in {"skip", "replace", "rename"}:
            raise ValueError("Unknown transaction mode/conflict policy")
        self.writer = writer
        self.target = checked_root(target)
        self.sources = [checked_root(p) for p in sources or []]
        check_overlap(self.sources, self.target)
        self.mode, self.conflict = mode, conflict
        self.strict, self.dry_run = strict, dry_run
        self.allow_changes = allow_changes or set()
        if self.allow_changes - set(Memory.__dataclass_fields__):
            raise ValueError("allow_changes accepts only published canonical field names")
        self.created_dirs: list[Path] = []
        self.committed: list[dict] = []
        self.backup: Path | None = None
        self.before: dict = {}
        self.root_existed = self.target.exists()
        self.lock: Path | None = None
        self.lock_token = uuid.uuid4().hex.encode("ascii")

    def before_commit(self) -> None:
        """Optional local test hook, called before the competition check."""

    def after_file_commit(self, relative: str) -> None:
        """Optional local test hook for injected commit failure."""

    def _mkdir(self, directory: Path) -> None:
        missing = []
        while not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for path in reversed(missing):
            checked_root(path)
            path.mkdir()
            self.created_dirs.append(path)

    def _check_current(self) -> None:
        if self.target.exists() != self.root_existed or snapshot(self.target) != self.before:
            raise RuntimeError("Target changed after planning; rerun migration")

    def _put(self, source: Path, relative: str, before_sha: str | None) -> None:
        dest = safe_child(self.target, relative)
        if before_sha is None:
            if dest.exists():
                raise RuntimeError(f"Concurrent file creation: {relative}")
        elif not dest.is_file() or digest(dest) != before_sha:
            raise RuntimeError(f"Concurrent file modification: {relative}")
        self._mkdir(dest.parent)
        # An owned temp file is created on the destination filesystem, then replaced.
        fd, temp = tempfile.mkstemp(prefix=".memlink-write-", dir=dest.parent)
        temp_path = Path(temp)
        try:
            with os.fdopen(fd, "wb") as stream, source.open("rb") as incoming:
                shutil.copyfileobj(incoming, stream)
                stream.flush()
                os.fsync(stream.fileno())
            checked_root(dest)
            if before_sha is None:
                # Exclusive destination creation prevents a last-moment create race.
                with dest.open("xb") as stream:
                    try:
                        with temp_path.open("rb") as incoming:
                            shutil.copyfileobj(incoming, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    except Exception:
                        # Record the exclusively created partial file for owned rollback.
                        stream.close()
                        self.committed.append({"path": relative, "sha256": digest(dest), "before_sha256": None})
                        raise
            else:
                if digest(dest) != before_sha:
                    raise RuntimeError(f"Concurrent file modification: {relative}")
                os.replace(temp_path, dest)
            self.committed.append({"path": relative, "sha256": digest(dest), "before_sha256": before_sha})
            self.after_file_commit(relative)
        finally:
            temp_path.unlink(missing_ok=True)

    def _rollback(self) -> list[str]:
        problems = []
        for entry in reversed(self.committed):
            file = safe_child(self.target, entry["path"])
            if not file.exists() or digest(file) != entry["sha256"]:
                problems.append(f"Kept concurrently modified file: {entry['path']}")
                continue
            try:
                if entry["before_sha256"] is not None and self.backup:
                    shutil.copy2(safe_child(self.backup, entry["path"]), file)
                else:
                    file.unlink()
            except OSError as exc:
                problems.append(f"Restore failed: {entry['path']}: {exc}")
        for directory in reversed(self.created_dirs):
            with suppress(OSError):
                # Only owned, now-empty directories are removed.
                directory.rmdir()
        return problems

    def execute(
        self,
        memories: list[Memory],
        *,
        source_contexts: list[dict] | None = None,
        filters: dict | None = None,
        exclusions: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        from .registry import get_reader
        from .validators import _get_schema, validate_instance, validate_memory

        receipt: dict[str, Any] = {
            "schema": "memlink-receipt",
            "version": "1",
            "tool_version": __version__,
            "transaction_id": uuid.uuid4().hex,
            "operation": self.mode,
            "sources": source_contexts or [],
            "filters": filters or {},
            "excluded": exclusions or [],
            "target": {
                "format": self.writer.name,
                "root": self.target.name,
                "mode": getattr(self.writer, "output_mode", "files"),
                "conflict_policy": self.conflict,
            },
            "records": [],
            "plan": [],
            "outputs": [],
            "readback": {"status": "not-run"},
            "backup": None,
            "warnings": [],
            "errors": [],
            "status": "failed",
        }
        receipt["workflow"] = details or {}
        receipt["policy"] = {"strict": self.strict, "allow_changes": sorted(self.allow_changes)}
        if len(self.sources) != len(source_contexts or []):
            message = "Managed sources require one source_context per source from read_source()"
            receipt["errors"].append(message)
            raise TransactionError(message, receipt, 2)
        for context in source_contexts or []:
            receipt["warnings"].extend(context.get("warnings", []))
        try:
            _get_schema()  # Missing schema fails even for an explicit legal empty set.
        except Exception as exc:
            receipt["errors"].append(str(exc))
            raise TransactionError("Canonical schema unavailable: " + str(exc), receipt, 2) from exc
        self.before = snapshot(self.target)
        if self.target.exists() and not self.target.is_dir():
            raise TransactionError("Target root must be a directory", receipt, 2)
        if self.mode == "export" and self.before:
            raise TransactionError(
                "Export target is nonempty; use migrate --on-conflict skip|replace|rename", receipt, 2
            )
        if self.mode == "migrate" and self.writer.name not in NATIVE_FIELDS:
            raise TransactionError("This plugin is export-only; safe apply is not verified", receipt, 5)
        originals = copy.deepcopy(memories)
        for memory in originals:
            issues = validate_memory(memory)
            if issues:
                receipt["errors"].extend(i.message for i in issues)
        if receipt["errors"]:
            raise TransactionError("Invalid canonical input", receipt, 2)
        for memory in originals:
            actual_checksum = content_checksum(memory.body)
            if memory.checksum and memory.checksum != actual_checksum:
                receipt["warnings"].append(f"{memory.id}: external checksum replaced by actual content checksum")
            memory.checksum = actual_checksum
        reserved_ids: set[str] = set()
        if self.mode == "migrate" and self.conflict == "rename" and self.target.exists():
            prior_reader = get_reader(self.writer.name)
            prior_reader.native_only = True
            prior = prior_reader.read(self.target)
            if prior.errors:
                raise TransactionError(
                    "Cannot inspect existing target for rename: " + "; ".join(prior.errors), receipt, 2
                )
            reserved_ids = {m.id for m in prior.memories}
        targets = _target_memories(originals, self.writer.name, reserved_ids)
        if self.dry_run:
            predicted = {planned_paths(m, self.writer): {"sha256": "unknown"} for m in targets}
            receipt["plan"] = _make_plan(predicted, self.before, self.target, self.mode, self.conflict)
            receipt["status"] = "planned"
            receipt["records"] = [
                {
                    "identity": identity(o),
                    "id": o.id,
                    "target_id": t.id,
                    "outcome": "planned",
                    "path": planned_paths(t, self.writer),
                    "fields": {
                        f: {"status": "unknown", "reason": "Dry-run estimate; serialization/readback not run"}
                        for f in Memory.__dataclass_fields__
                    },
                }
                for o, t in zip(originals, targets, strict=True)
            ]
            return receipt
        parent = self.target.parent
        while not parent.exists():
            parent = parent.parent
        try:
            # Cooperative writers serialize on this explicit root, including a new root.
            # External applications still require the subsequent snapshot/byte checks.
            lock_name = hashlib.sha256(str(self.target).casefold().encode()).hexdigest()[:24]
            lock_path = checked_root(parent / f".memlink-lock-{lock_name}")
            try:
                with lock_path.open("xb") as lock_stream:
                    lock_stream.write(self.lock_token)
                self.lock = lock_path
            except FileExistsError as exc:
                raise ConcurrentModificationError("Target is locked by another transaction", receipt, 4) from exc
            with tempfile.TemporaryDirectory(prefix=".memlink-stage-", dir=parent) as temp:
                staging = Path(temp) / "candidate"
                staging.mkdir()
                warnings = self.writer._serialize(targets, staging)
                if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
                    raise ValueError("Plugin write() did not return list[str]")
                receipt["warnings"].extend(warnings)
                native_reader = get_reader(self.writer.name)
                native_reader.native_only = True
                native = native_reader.read(staging)
                if native.errors or native.stats.get("invalid", 0):
                    raise ValueError("Target reader rejected staging: " + "; ".join(native.errors + native.warnings))
                by_id = {m.id: m for m in native.memories}
                if len(by_id) != len(native.memories) or len(native.memories) != len(targets):
                    raise ValueError("Target record count/ID readback mismatch")
                candidate = snapshot(staging)
                if not candidate:
                    raise ValueError("Writer produced no output")
                receipt["plan"] = _make_plan(candidate, self.before, self.target, self.mode, self.conflict)
                plan_by_path = {p["candidate"]: p for p in receipt["plan"]}
                archive_records = []
                for original, target in zip(originals, targets, strict=True):
                    if target.id not in by_id:
                        raise ValueError(f"Target record {target.id} is not readable")
                    actual = by_id[target.id]
                    relative = getattr(
                        actual, "_native_path", actual.source.path.split("#")[0] if actual.source else ""
                    )
                    if relative not in plan_by_path:
                        raise ValueError("Reader did not locate the serialized record")
                    plan = plan_by_path[relative]
                    fields = {}
                    original_data, actual_data = memory_dict(original), memory_dict(actual)
                    previous_archive = self.target / ".memlink/archive.json"
                    if self.mode == "migrate" and plan["action"] == "unchanged" and previous_archive.exists():
                        previous_data = load_json(previous_archive)
                        prior_entries = [
                            e
                            for e in previous_data["records"]
                            if e["path"] == plan["path"] and e["target_id"] == target.id
                        ]
                        if any(stable_json(e["memory"]) != stable_json(original_data) for e in prior_entries):
                            plan["action"] = "skip" if self.conflict == "skip" else "update"
                            plan["conflict"] = True
                            plan["reason"] = "Canonical archive differs despite identical native file bytes"
                    native_fields = NATIVE_FIELDS.get(self.writer.name, set())
                    if self.writer.name == "openclaw" and getattr(self.writer, "output_mode", None) == "structured":
                        native_fields = {"body", "name", "summary"}  # metadata remains transport data
                    for field, value in original_data.items():
                        target_value = actual_data[field]
                        if field in native_fields and stable_json(value) == stable_json(target_value):
                            status, reason = "native-preserved", "Measured equal using target adapter readback"
                        elif field in native_fields:
                            status, reason = "transformed", "Deterministic target mapping; original retained in archive"
                        else:
                            status, reason = (
                                "archive-only",
                                "Target native contract does not express this field; exact value in archive",
                            )
                        fields[field] = {
                            "status": status,
                            "reason": reason,
                            "original": value,
                            "target": target_value,
                            "archive": ".memlink/archive.json" if status != "native-preserved" else None,
                        }
                    outcome = "conflict" if plan["action"] == "skip" else "output"
                    record = {
                        "identity": identity(original),
                        "id": original.id,
                        "target_id": target.id,
                        "path": plan["path"],
                        "outcome": outcome,
                        "fields": fields,
                    }
                    if outcome == "conflict":
                        record["fields"] = {
                            f: {
                                "status": "dropped",
                                "reason": "Conflict skipped; candidate was not committed",
                                "archive": None,
                            }
                            for f in original_data
                        }
                        receipt["warnings"].append(f"{original.id}: conflict skipped at {plan['path']}")
                    else:
                        archive_records.append(
                            {
                                "target_id": target.id,
                                "path": plan["path"],
                                "sha256": plan["sha256"],
                                "native_body": actual.body,
                                "native_scope": scope_of(actual),
                                "memory": original_data,
                            }
                        )
                    receipt["records"].append(record)
                changes = [
                    (f, f"{r['id']}.{f}: {impact['status']}")
                    for r in receipt["records"]
                    for f, impact in r["fields"].items()
                    if impact["status"] != "native-preserved" and _meaningful(f, impact.get("original"))
                ]
                blocked_changes = [description for field, description in changes if field not in self.allow_changes]
                if changes:
                    receipt["warnings"].append(f"{len(changes)} field values require archive or transformation")
                receipt["readback"] = {
                    "status": "verified",
                    "parsed": len(native.memories),
                    "compared_fields": len(Memory.__dataclass_fields__),
                }
                if self.strict and (blocked_changes or any(r["outcome"] == "conflict" for r in receipt["records"])):
                    raise TransactionError("Strict conversion blocked: " + "; ".join(blocked_changes[:8]), receipt, 5)
                # Retain only current, hash-verified prior archives for untouched target files.
                old_archive = self.target / ".memlink/archive.json"
                if self.mode == "migrate" and old_archive.exists():
                    data = load_json(old_archive)
                    if data.get("schema") != "memlink-archive" or data.get("version") != "1":
                        raise ValueError("Unknown existing archive schema/version")
                    touched = {p["path"] for p in receipt["plan"] if p["action"] in {"create", "update"}}
                    archived_targets = {(e["path"], e["target_id"]) for e in archive_records}
                    for entry in data["records"]:
                        if (
                            entry["path"] not in touched
                            and (entry["path"], entry["target_id"]) not in archived_targets
                            and entry["path"] in self.before
                            and self.before[entry["path"]]["sha256"] == entry["sha256"]
                        ):
                            archive_records.append(entry)
                admin = staging / ".memlink"
                admin.mkdir()
                archive = {"schema": "memlink-archive", "version": "1", "records": archive_records}
                archive_file = admin / "archive.json"
                archive_file.write_text(
                    json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline=""
                )
                # Read the bytes again and verify every archived canonical record.
                if stable_json(load_json(archive_file)) != stable_json(archive):
                    raise ValueError("Archive verification failed")
                final_hashes = {p: info["sha256"] for p, info in self.before.items()}
                final_hashes.update({p["path"]: p["sha256"] for p in receipt["plan"] if p["action"] != "skip"})
                for entry in archive_records:
                    if final_hashes.get(entry["path"]) != entry["sha256"]:
                        raise ValueError("Archive path/hash mismatch")
                admin_plans = [
                    {
                        "path": ".memlink/archive.json",
                        "candidate": ".memlink/archive.json",
                        "action": "update" if old_archive.exists() else "create",
                        "before_sha256": self.before.get(".memlink/archive.json", {}).get("sha256"),
                        "sha256": digest(archive_file),
                    }
                ]
                self.before_commit()
                for source, context in zip(self.sources, source_contexts or [], strict=True):
                    from .safety import files_in

                    current_paths = {
                        p.name if source.is_file() else p.relative_to(source).as_posix() for p in files_in(source)
                    }
                    expected_paths = {f["path"] for f in context.get("files", []) if f.get("role") != "transport"}
                    if current_paths != expected_paths:
                        raise RuntimeError("Source changed after reading; input file set differs")
                    for input_file in context.get("files", []):
                        file = source if source.is_file() else safe_child(source, input_file["path"])
                        if not file.is_file() or digest(file) != input_file["sha256"]:
                            raise RuntimeError("Source changed after reading; rerun conversion")
                self._check_current()
                self._mkdir(self.target)
                backup_files = [p for p in receipt["plan"] + admin_plans if p["action"] == "update"]
                # The last receipt is also owned output, and gets backed up before replacement.
                if ".memlink/receipt.json" in self.before:
                    backup_files.append({"path": ".memlink/receipt.json"})
                if self.mode == "migrate":
                    self.backup = self.target / ".memlink/backups" / receipt["transaction_id"]
                    self._mkdir(self.backup)
                    for plan in backup_files:
                        original_file = safe_child(self.target, plan["path"])
                        backed = safe_child(self.backup, plan["path"])
                        self._mkdir(backed.parent)
                        shutil.copy2(original_file, backed)
                        if digest(backed) != self.before[plan["path"]]["sha256"]:
                            raise RuntimeError("Backup differs from planning snapshot")
                    receipt["backup"] = {
                        "path": self.backup.relative_to(self.target).as_posix(),
                        "files": [p["path"] for p in backup_files],
                        "retention": "Manual; no automatic cleanup",
                    }
                    backup_manifest = {
                        "schema": "memlink-restore",
                        "version": "1",
                        "files": backup_files,
                        "created": [p["path"] for p in receipt["plan"] + admin_plans if p["action"] == "create"]
                        + ([".memlink/receipt.json"] if ".memlink/receipt.json" not in self.before else []),
                    }
                    (self.backup / "restore.json").write_text(
                        json.dumps(backup_manifest, indent=2), encoding="utf-8", newline=""
                    )
                for plan in receipt["plan"] + admin_plans:
                    if plan["action"] in {"create", "update"}:
                        self._put(safe_child(staging, plan["candidate"]), plan["path"], plan["before_sha256"])
                # Verify committed bytes and record counts before producing a successful receipt.
                for plan in receipt["plan"] + admin_plans:
                    if plan["action"] != "skip" and digest(safe_child(self.target, plan["path"])) != plan["sha256"]:
                        raise RuntimeError("Post-commit digest mismatch")
                committed_read = native_reader.read(self.target)
                if committed_read.errors:
                    raise RuntimeError("Post-commit native read failed")
                committed_ids = {m.id for m in committed_read.memories}
                if any(r["target_id"] not in committed_ids for r in receipt["records"] if r["outcome"] == "output"):
                    raise RuntimeError("Post-commit records are not readable")
                receipt["readback"]["post_commit"] = "verified"
                receipt["accounting"] = {
                    "input_records": sum(c["stats"].get("records_total", 0) for c in receipt["sources"]),
                    "parsed": sum(c["stats"].get("parsed", 0) for c in receipt["sources"]),
                    "invalid": sum(c["stats"].get("invalid", 0) for c in receipt["sources"]),
                    "unsupported": sum(c["stats"].get("unsupported", 0) for c in receipt["sources"]),
                    "selected": len(originals),
                    "excluded": len(receipt["excluded"]),
                    "output": sum(r["outcome"] == "output" for r in receipt["records"]),
                    "conflict_skipped": sum(r["outcome"] == "conflict" for r in receipt["records"]),
                }
                receipt["outputs"] = [
                    {"path": p["path"], "sha256": p["sha256"]}
                    for p in receipt["plan"] + admin_plans
                    if p["action"] != "skip"
                ]
                receipt["status"] = "partial" if receipt["warnings"] else "success"
                from importlib.resources import files

                receipt_schema = json.loads(
                    files("memlink").joinpath("resources/memlink-receipt-v1.schema.json").read_text(encoding="utf-8")
                )
                receipt_issues = validate_instance(receipt, receipt_schema)
                if receipt_issues:
                    raise ValueError("Invalid receipt: " + "; ".join(receipt_issues))
                receipt_file = admin / "receipt.json"
                receipt_file.write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline=""
                )
                self._put(
                    receipt_file, ".memlink/receipt.json", self.before.get(".memlink/receipt.json", {}).get("sha256")
                )
                return receipt
        except Exception as exc:
            problems = self._rollback()
            receipt["errors"].append(str(exc))
            receipt["errors"].extend(problems)
            receipt["status"] = "partial" if problems else "failed"
            receipt["rollback"] = "incomplete" if problems else "restored-owned-changes"
            if isinstance(exc, TransactionError):
                raise TransactionError(str(exc), receipt, exc.exit_code) from exc
            if "Concurrent" in str(exc) or "changed after planning" in str(exc) or "Source changed" in str(exc):
                raise ConcurrentModificationError(str(exc), receipt, 4) from exc
            raise TransactionError(str(exc), receipt, 2 if isinstance(exc, ValueError) else 3) from exc
        finally:
            if self.lock and self.lock.exists() and self.lock.read_bytes() == self.lock_token:
                self.lock.unlink()


def execute_output(memories: list[Memory], writer, target: Path, **kwargs) -> dict:
    context = {k: kwargs.pop(k) for k in ("source_contexts", "filters", "exclusions", "details") if k in kwargs}
    return OutputTransaction(writer, target, **kwargs).execute(memories, **context)


def _meaningful(field: str, value) -> bool:
    if value is None or value == [] or value == {}:
        return False
    return not (field == "pinned" and value is False)
