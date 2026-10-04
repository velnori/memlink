"""Approved source reads and validated optional archive recovery."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files as resource_files
from pathlib import Path

from .codec import attach_identity, content_checksum, memory_from_dict, scope_of, stable_json
from .models import Memory
from .plugin import ReadResult
from .read_support import load_json, relative
from .safety import MAX_RECORDS, checked_root, digest, files_in, safe_child, snapshot


def _load_archive(path: Path) -> dict:
    from .validators import validate_instance

    data = load_json(path)
    schema = json.loads(
        resource_files("memlink").joinpath("resources/memlink-archive-v1.schema.json").read_text(encoding="utf-8")
    )
    issues = validate_instance(data, schema)
    if issues:
        raise ValueError("Invalid archive: " + "; ".join(issues))
    if len(data["records"]) > MAX_RECORDS:
        raise ValueError("Archive record resource limit exceeded")
    return data


def guarded_read(plugin, parse, path: Path, *, native_only: bool = False) -> ReadResult:
    try:
        root = checked_root(path)
        files = files_in(root)
        before_read = snapshot(root, include_control=False)
        archive_path = safe_child(root, ".memlink/archive.json") if root.is_dir() else None
        archive_before = digest(archive_path) if archive_path and archive_path.exists() else None
        result = parse(plugin, root)
        if not isinstance(result, ReadResult):
            raise ValueError("Plugin read() did not return ReadResult")
        if not isinstance(result.memories, list) or any(not isinstance(m, Memory) for m in result.memories):
            raise ValueError("Plugin memories must be list[Memory]")
        if any(
            not isinstance(items, list) or any(not isinstance(x, str) for x in items)
            for items in (result.warnings, result.errors)
        ):
            raise ValueError("Plugin warnings/errors must be list[str]")
        if not isinstance(result.stats, dict) or any(
            not isinstance(k, str) or type(v) is not int or v < 0 for k, v in result.stats.items()
        ):
            raise ValueError("Plugin stats must be nonnegative integer accounting")
        if (
            any(
                not isinstance(items, list) or any(not isinstance(x, dict) for x in items)
                for items in (result.files, result.records)
            )
            or type(result.valid_empty) is not bool
        ):
            raise ValueError("Plugin ledger/empty marker has invalid types")
        # Renamed offline JSON segments are explicitly routed by our transport manifest.
        # Their fields still come from actual native JSON, never from archived canonical values.
        if plugin.name in {"mem0", "zep"} and root.is_dir() and (root / ".memlink/archive.json").exists():
            transport = _load_archive(safe_child(root, ".memlink/archive.json"))
            already = {m.source.path for m in result.memories if m.source}
            extra_paths = sorted({e["path"] for e in transport["records"] if e["path"] not in already})
            for rel in extra_paths:
                file = safe_child(root, rel)
                if file.suffix.lower() != ".json" or not file.is_file():
                    continue
                segment = parse(plugin, file)
                for m in segment.memories:
                    if m.source:
                        m.source.path = rel
                result.memories.extend(segment.memories)
                result.records.extend(segment.records)
                result.warnings.extend(segment.warnings)
                result.errors.extend(segment.errors)
                result.files = [f for f in result.files if f["path"] != rel]
                result.files.append({"path": rel, "outcome": "parsed"})
            if extra_paths:
                result.variant += "+manifest-segments"
        if len(result.memories) > MAX_RECORDS:
            raise ValueError("Record resource limit exceeded")
        from .validators import validate_memory

        valid = []
        parsed_records = [r for r in result.records if r.get("outcome") == "parsed"]
        for index, memory in enumerate(result.memories):
            issues = validate_memory(memory)
            if issues:
                reason = "; ".join(i.message for i in issues)
                result.warnings.append(f"{memory.id}: invalid canonical record: {reason}")
                result.stats["invalid"] = result.stats.get("invalid", 0) + 1
                if index < len(parsed_records):
                    parsed_records[index].update(outcome="invalid", reason=reason)
            else:
                valid.append(memory)
        result.memories = valid
        namespace = plugin.name + ":" + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:20]
        parsed_paths = {
            getattr(m, "_native_path", m.source.path.replace("\\", "/").split("#")[0])
            for m in result.memories
            if m.source
        }
        specified = {f["path"]: f for f in result.files}
        result.files = []
        for file in files:
            rel = relative(file, root)
            status = specified.get(rel, {}).get("outcome")
            if status is None:
                status = "parsed" if rel in parsed_paths else "excluded"
                if rel not in parsed_paths and file.suffix.lower() in {".md", ".json"}:
                    status = "invalid" if result.errors or result.stats.get("invalid", 0) else "unsupported"
            result.files.append({"path": rel, "outcome": status, "sha256": digest(file), "bytes": file.stat().st_size})
        for mem in result.memories:
            if mem.source:
                mem.source.path = mem.source.path.replace("\\", "/")
            if not native_only:
                attach_identity(mem, namespace)
            actual = content_checksum(mem.body)
            if mem.checksum and mem.checksum != actual:
                result.warnings.append(f"{mem.id}: input checksum disagrees with actual body; recomputed")
                mem.metadata["_input_checksum"] = mem.checksum
            mem.checksum = actual
        result.stats["parsed"] = len(result.memories)
        result.stats["files_total"] = len(result.files)
        for state in ("parsed", "excluded", "invalid", "unsupported"):
            result.stats[f"files_{state}"] = sum(f["outcome"] == state for f in result.files)
        if not result.records:
            result.records = [{"id": m.id, "outcome": "parsed"} for m in result.memories]
            for i in range(result.stats.get("skipped", 0) + result.stats.get("invalid", 0)):
                result.records.append({"index": i, "outcome": "invalid"})
        # Derive record totals from the ledger, including records rejected by adapters.
        result.stats["invalid"] = sum(r["outcome"] == "invalid" for r in result.records)
        result.stats["unsupported"] = sum(r["outcome"] == "unsupported" for r in result.records)
        result.stats["records_total"] = len(result.records)
        if not native_only and root.is_dir() and (root / ".memlink" / "archive.json").exists():
            recover_archive(root, result)
            file = safe_child(root, ".memlink/archive.json")
            result.files.append(
                {
                    "path": ".memlink/archive.json",
                    "role": "transport",
                    "outcome": "parsed",
                    "sha256": digest(file),
                    "bytes": file.stat().st_size,
                }
            )
            result.stats["files_total"] += 1
            result.stats["files_parsed"] += 1
        if snapshot(root, include_control=False) != before_read:
            raise ValueError("Source changed during read")
        archive_after = digest(archive_path) if archive_path and archive_path.exists() else None
        if archive_after != archive_before:
            raise ValueError("Source archive changed during read")
        return result
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        locals_snapshot = locals().get("before_read", {})
        ledger = (
            [
                {"path": relative(f, root), "outcome": "invalid", **locals_snapshot.get(relative(f, root), {})}
                for f in files
            ]
            if "files" in locals()
            else []
        )
        return ReadResult(
            [],
            warnings=[str(exc)],
            errors=[str(exc)],
            files=ledger,
            records=[{"outcome": "invalid", "reason": str(exc)}],
            stats={
                "parsed": 0,
                "invalid": 1,
                "records_total": 1,
                "files_total": len(ledger),
                "files_invalid": len(ledger),
            },
        )


def recover_archive(root: Path, result: ReadResult) -> None:
    archive_path = safe_child(root, ".memlink/archive.json")
    data = _load_archive(archive_path)

    def key(memory):
        return (
            getattr(memory, "_native_path", memory.source.path.split("#")[0] if memory.source else ""),
            memory.id,
            stable_json(scope_of(memory)),
        )

    native: dict[tuple, list[Memory]] = {}
    for m in result.memories:
        native.setdefault(key(m), []).append(m)
    recovered: dict[tuple, Memory] = {}
    for entry in data["records"]:
        target_id = entry["target_id"]
        target_key = (entry["path"], target_id, stable_json(entry.get("native_scope", {"scope": "unknown"})))
        if target_key in recovered:
            raise ValueError("Duplicate archive target ID")
        file = safe_child(root, entry["path"])
        if not file.exists() or digest(file) != entry["sha256"]:
            result.warnings.append(f"{target_id}: archive is stale; reading current native data")
            continue
        if target_key not in native or len(native[target_key]) != 1:
            raise ValueError(f"Archive record {target_id} cannot be read back from target")
        original = memory_from_dict(entry["memory"])
        from .validators import validate_memory

        if validate_memory(original):
            raise ValueError("Archive contains invalid canonical data")
        # The archive must never conceal a different body in a readable native record.
        if stable_json(native[target_key][0].body) != stable_json(entry["native_body"]):
            raise ValueError(f"{target_id}: native body differs from archived readback")
        recovered[target_key] = original
    result.memories = [recovered.get(key(m), m) for m in result.memories]
    result.stats["archive_recovered"] = len(recovered)
