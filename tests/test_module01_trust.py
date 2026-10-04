"""Module 1 acceptance: real native files, archive fidelity and owned transactions."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from memlink.codec import content_checksum, memory_dict
from memlink.converter import compare_memories, convert, merge, resolve_conflict, run_roundtrip
from memlink.models import Memory, Relationship, Source, sanitize_id
from memlink.plugin import Capabilities, FormatPlugin, ReadResult
from memlink.registry import get_reader, get_writer, register_reader, register_writer
from memlink.safety import BoundaryError, digest, snapshot
from memlink.serialization import sanitize
from memlink.transaction import OutputTransaction, TransactionError, execute_output
from memlink.validators import validate_instance, validate_memory, validate_schema

FIXTURES = Path(__file__).parent / "fixtures"
FULL = FIXTURES / "module01/full-workspace"


def rich_memory():
    return Memory(
        id="a/b",
        name='A "quoted"\nname',
        body="## heading\r\n---\n<!-- ordinary -->\r\nTail  \n",
        summary="Summary",
        kind="emotion",
        status="archived",
        domains=["work", "personal"],
        valence=0.0,
        arousal=0.0,
        relationships=[Relationship("other", "relates_to", 0.0)],
        created_at=datetime.fromisoformat("2026-10-02T00:30:00+08:00"),
        extensions={"id": "cannot-hijack", "unknown": [0, {"nested": True}]},
        source=Source("generic", "input.md"),
    )


@pytest.mark.parametrize("fmt", ["generic", "mem0", "zep", "openclaw", "ombre"])
def test_actual_native_and_archive_field_receipt(tmp_path, fmt):
    original = rich_memory()
    writer = get_writer(fmt)
    target = tmp_path / fmt
    writer.write([original], target)
    receipt = json.loads((target / ".memlink/receipt.json").read_text(encoding="utf-8"))
    assert receipt == writer.last_receipt
    assert receipt["status"] == ("success" if fmt == "generic" else "partial")
    assert receipt["readback"]["post_commit"] == "verified"
    native_reader = get_reader(fmt)
    native_reader.native_only = True
    native = native_reader.read(target)
    assert not native.errors and len(native.memories) == 1
    data = memory_dict(native.memories[0])
    impacts = receipt["records"][0]["fields"]
    for field, impact in impacts.items():
        if impact["status"] == "native-preserved":
            assert impact["original"] == data[field]
        if impact["status"] in {"archive-only", "transformed"}:
            assert impact["archive"] == ".memlink/archive.json"
    archive = json.loads((target / ".memlink/archive.json").read_text(encoding="utf-8"))
    expected = copy.deepcopy(original)
    expected.checksum = content_checksum(expected.body)
    assert archive["records"][0]["memory"] == memory_dict(expected)
    assert archive["records"][0]["sha256"] == digest(target / archive["records"][0]["path"])
    recovered = get_reader(fmt).read(target)
    assert not recovered.errors and recovered.stats["archive_recovered"] == 1
    assert memory_dict(recovered.memories[0]) == memory_dict(expected)
    if fmt in {"mem0", "zep"}:
        record = json.loads((target / ("memories.json" if fmt == "mem0" else "facts.json")).read_text(encoding="utf-8"))
        assert (
            record["results" if fmt == "mem0" else "facts"][0]["memory" if fmt == "mem0" else "fact"] == original.body
        )
        assert impacts["valence"]["status"] == "archive-only"
        assert impacts["relationships"]["status"] == "archive-only"
    if fmt == "generic":
        file = next((target / "notes").glob("*.md"))
        fm = yaml.safe_load(file.read_text(encoding="utf-8").split("---", 2)[1])
        assert fm["id"] == "a/b" and fm["valence"] == 0.0
        assert fm["relationships"][0]["weight"] == 0.0


def test_archive_edit_never_conceals_native_body_change(tmp_path):
    writer = get_writer("generic")
    writer.write([Memory(id="one", body="original")], tmp_path / "out")
    file = tmp_path / "out/notes/one.md"
    file.write_bytes(file.read_bytes().replace(b"original", b"modified"))
    result = get_reader("generic").read(tmp_path / "out")
    assert not result.errors
    assert result.memories[0].body == "modified"
    assert any("stale" in w for w in result.warnings)


@pytest.mark.parametrize("corruption", ["top-level", "missing-field", "wrong-type", "future-version"])
@pytest.mark.parametrize("fmt", ["generic", "mem0"])
def test_malformed_archive_is_invalid_input_not_recovery_success(tmp_path, corruption, fmt):
    target = tmp_path / "out"
    get_writer(fmt).write([Memory(id="one", body="native")], target)
    archive_path = target / ".memlink/archive.json"
    data = json.loads(archive_path.read_text(encoding="utf-8"))
    if corruption == "top-level":
        data = []
    elif corruption == "missing-field":
        del data["records"][0]["target_id"]
    elif corruption == "wrong-type":
        data["records"][0]["memory"] = "invalid"
    else:
        data["version"] = "future"
    archive_path.write_text(json.dumps(data), encoding="utf-8")
    result = get_reader(fmt).read(target)
    assert result.errors and not result.memories
    assert result.stats["invalid"] and result.stats["records_total"]
    assert validate_schema(target, fmt)


@pytest.mark.parametrize("mode", ["daily-notes", "structured"])
def test_daily_three_records_zero_values_and_literal_body(tmp_path, mode):
    memories = [rich_memory() for _ in range(3)]
    for i, memory in enumerate(memories):
        memory.id = f"item-{i}"
        memory.created_at = datetime(2026, 10, 2, 10, tzinfo=timezone.utc)
    get_writer("openclaw", output_mode=mode).write(memories, tmp_path / "out")
    native = get_reader("openclaw")
    native.native_only = True
    result = native.read(tmp_path / "out")
    assert not result.errors and len(result.memories) == 3
    assert {m.id for m in result.memories} == {m.id for m in memories}
    assert all(m.body == memories[0].body for m in result.memories)
    assert all(m.valence == 0.0 and m.arousal == 0.0 for m in result.memories)


@pytest.mark.parametrize(
    "invalid",
    ["non-object", "duplicate-key", "null-flag-type", "memory-type", "null-flag-with-body", "oversized-prefix"],
)
def test_openclaw_frame_json_is_bounded_and_typed(tmp_path, invalid):
    from memlink.openclaw_records import MARKER, render_records

    text = render_records([Memory(id="frame", body="literal body")])
    marker = MARKER.search(text)
    assert marker
    frame = json.loads(base64.urlsafe_b64decode(marker[1]))
    if invalid == "non-object":
        payload = "[]"
    elif invalid == "duplicate-key":
        payload = '{"version":"future","version":"1"}'
    else:
        if invalid == "null-flag-with-body":
            frame["body_is_null"] = True
        elif invalid == "oversized-prefix":
            frame["prefix_length"] = frame["payload_length"]
        else:
            frame["body_is_null" if invalid == "null-flag-type" else "memory"] = "wrong type"
        payload = json.dumps(frame)
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    text = text[: marker.start()] + f"<!-- memlink-record-v1:{encoded} -->\n" + text[marker.end() :]
    source = tmp_path / "MEMORY.md"
    source.write_text(text, encoding="utf-8", newline="")
    result = get_reader("openclaw").read(source)
    assert result.errors and not result.memories and result.stats["invalid"]
    assert validate_schema(source, "openclaw")


def test_official_plain_files_and_explicit_workspace_scope(tmp_path):
    root = tmp_path / "openclaw"
    (root / "memory").mkdir(parents=True)
    (root / "MEMORY.md").write_text("# Preferences\nOffline first.", encoding="utf-8")
    (root / "memory/2026-10-02-slug.md").write_text("A plain daily note", encoding="utf-8")
    (root / "USER.md").write_text("User model", encoding="utf-8")
    (root / "TOOLS.md").write_text("tool configuration", encoding="utf-8")
    result = get_reader("openclaw").read(root)
    assert {m.id for m in result.memories} == {"MEMORY.md", "memory/2026-10-02-slug.md"}
    assert all(f["outcome"] == "excluded" for f in result.files if f["path"] in {"USER.md", "TOOLS.md"})
    explicit = get_reader("openclaw", include_user=True).read(root)
    assert any(m.id == "USER.md" for m in explicit.memories)
    assert next(m for m in result.memories if m.id.endswith("slug.md")).created_at == datetime(
        2026, 10, 2, tzinfo=timezone.utc
    )


def test_missing_memory_directory_and_dangling_index(tmp_path):
    (tmp_path / "MEMORY.md").write_text("# Memory Index\n- memory/missing.md\n", encoding="utf-8")
    result = get_reader("openclaw").read(tmp_path)
    assert not result.errors and not result.memories
    assert any("Dangling" in w for w in result.warnings)
    assert any(i.severity == "error" for i in validate_schema(tmp_path, "openclaw"))


@pytest.mark.parametrize("policy", ["skip", "replace", "rename"])
@pytest.mark.parametrize("fmt", ["generic", "openclaw", "mem0", "zep", "ombre"])
def test_existing_target_conflict_policies_keep_non_memory_files(tmp_path, policy, fmt):
    root = tmp_path / "out"
    writer = get_writer(fmt)
    old = Memory(id="one", body="OLD", created_at=datetime(2026, 10, 2, tzinfo=timezone.utc))
    new = Memory(id="one", body="NEW", created_at=old.created_at)
    writer.write([old], root)
    (root / "TOOLS.cfg").write_bytes(b"untouched-config")
    previous = snapshot(root)
    receipt = execute_output([new], writer, root, mode="migrate", conflict=policy)
    assert (root / "TOOLS.cfg").read_bytes() == b"untouched-config"
    read = get_reader(fmt).read(root)
    assert not read.errors
    bodies = [m.body for m in read.memories]
    if policy == "skip":
        assert bodies == ["OLD"]
        assert receipt["records"][0]["outcome"] == "conflict"
        assert all(v["status"] == "dropped" for v in receipt["records"][0]["fields"].values())
    elif policy == "replace":
        assert bodies == ["NEW"]
        assert any(p["action"] == "update" for p in receipt["plan"])
        assert receipt["backup"]["files"]
    else:
        assert sorted(bodies) == ["NEW", "OLD"]
        assert receipt["records"][0]["target_id"] != "one"
    backup = root / receipt["backup"]["path"]
    for name in receipt["backup"]["files"]:
        assert digest(backup / name) == previous[name]["sha256"]
    assert (backup / "restore.json").exists()


def test_legacy_dream_and_note_shared_id_preserve_both_occurrences(tmp_path):
    source = tmp_path / "source"
    (source / "memory").mkdir(parents=True)
    (source / "memory/abcdef123456.md").write_text("---\nname: Primary\n---\nPrimary note", encoding="utf-8")
    review = "## abcdef123456\n\nDifferent review\nvalence: 0.0 / arousal: 0.0\n"
    (source / "DREAMS.md").write_text(review, encoding="utf-8", newline="")
    reader = get_reader("openclaw", include_dreams=True)
    parsed = reader.read(source)
    assert len(parsed.memories) == parsed.stats["parsed"] == parsed.stats["records_total"] == 2
    assert parsed.stats["files_parsed"] == 2
    assert [m.id for m in parsed.memories] == ["abcdef123456", "abcdef123456"]
    assert "Primary note" in parsed.memories[0].body
    assert parsed.memories[1].body == "Different review"
    assert parsed.memories[1].extensions["openclaw_dreams_source"] == review
    result = convert(reader, get_writer("generic"), source, tmp_path / "out", all=True)
    assert result["receipt"]["accounting"]["output"] == 2
    restored = get_reader("generic").read(tmp_path / "out")
    assert len(restored.memories) == 2 and not restored.errors
    assert compare_memories(parsed.memories, restored.memories) == []


def test_skip_detects_changed_archive_with_identical_native_json(tmp_path):
    root = tmp_path / "out"
    writer = get_writer("mem0")
    writer.write([Memory(id="one", body="same", valence=0.0)], root)
    receipt = execute_output(
        [Memory(id="one", body="same", valence=1.0)], writer, root, mode="migrate", conflict="skip"
    )
    assert receipt["records"][0]["outcome"] == "conflict"
    assert get_reader("mem0").read(root).memories[0].valence == 0.0


def test_export_refuses_nonempty_root_and_overlap(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    (root / "config.cfg").write_bytes(b"original")
    with pytest.raises(TransactionError) as failure:
        get_writer("mem0").write([Memory(id="one", body="NEW")], root)
    assert failure.value.exit_code == 2
    assert (root / "config.cfg").read_bytes() == b"original"
    with pytest.raises(BoundaryError):
        convert(get_reader("generic"), get_writer("generic"), FULL, FULL / "nested")


def test_dry_run_and_strict_do_not_create_target(tmp_path):
    target = tmp_path / "deep/out"
    before = snapshot(tmp_path)
    dry = convert(get_reader("generic"), get_writer("mem0"), FULL, target, all=True, dry_run=True)["receipt"]
    assert dry["status"] == "planned" and dry["readback"]["status"] == "not-run"
    assert snapshot(tmp_path) == before
    assert all(v["status"] == "unknown" for r in dry["records"] for v in r["fields"].values())
    with pytest.raises(TransactionError) as failure:
        convert(get_reader("generic"), get_writer("mem0"), FULL, target, all=True, strict=True)
    assert failure.value.exit_code == 5
    assert not target.exists() and snapshot(tmp_path) == before


def test_commit_failure_restores_only_owned_changes(tmp_path, monkeypatch):
    root = tmp_path / "out"
    writer = get_writer("generic")
    writer.write([Memory(id="a", body="OLD")], root)
    (root / "config.cfg").write_bytes(b"original-config")
    before = snapshot(root)

    def fail(self, relative):
        if relative == "notes/a.md":
            raise OSError("injected commit interruption")

    monkeypatch.setattr(OutputTransaction, "after_file_commit", fail)
    with pytest.raises(TransactionError) as failure:
        execute_output(
            [Memory(id="a", body="NEW"), Memory(id="b", body="added")], writer, root, mode="migrate", conflict="replace"
        )
    assert failure.value.exit_code == 3
    assert failure.value.receipt["rollback"] == "restored-owned-changes"
    for name, info in before.items():
        assert digest(root / name) == info["sha256"]
    assert not (root / "notes/b.md").exists()
    assert not list(tmp_path.glob(".memlink-stage-*"))
    assert not list(tmp_path.glob(".memlink-lock-*"))


def test_competing_writer_is_not_overwritten(tmp_path, monkeypatch):
    root = tmp_path / "out"
    get_writer("generic").write([Memory(id="a", body="OLD")], root)

    def change(self):
        (root / "notes/a.md").write_bytes(b"external change")

    monkeypatch.setattr(OutputTransaction, "before_commit", change)
    with pytest.raises(TransactionError) as failure:
        execute_output([Memory(id="a", body="NEW")], get_writer("generic"), root, mode="migrate", conflict="replace")
    assert failure.value.exit_code == 4
    assert (root / "notes/a.md").read_bytes() == b"external change"


def test_post_commit_external_change_remains_and_reports_incomplete_rollback(tmp_path, monkeypatch):
    root = tmp_path / "out"

    def change_and_fail(self, relative):
        if relative == "notes/a.md":
            (root / relative).write_bytes(b"external change")
            raise OSError("injected after outside edit")

    monkeypatch.setattr(OutputTransaction, "after_file_commit", change_and_fail)
    with pytest.raises(TransactionError) as failure:
        get_writer("generic").write([Memory(id="a", body="NEW")], root)
    assert failure.value.exit_code == 3
    assert failure.value.receipt["rollback"] == "incomplete"
    assert failure.value.receipt["status"] == "partial"
    assert (root / "notes/a.md").read_bytes() == b"external change"


def test_source_file_addition_detected_before_commit(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.md").write_text("first", encoding="utf-8")

    def change(self):
        (source / "b.md").write_text("added later", encoding="utf-8")

    monkeypatch.setattr(OutputTransaction, "before_commit", change)
    with pytest.raises(TransactionError) as failure:
        convert(get_reader("generic"), get_writer("generic"), source, tmp_path / "out", all=True)
    assert failure.value.exit_code == 4
    assert not (tmp_path / "out").exists()


def test_root_lock_excludes_competing_transaction(tmp_path):
    target = (tmp_path / "out").absolute()
    lock = tmp_path / (".memlink-lock-" + hashlib.sha256(str(target).casefold().encode()).hexdigest()[:24])
    lock.write_bytes(b"other owner")
    with pytest.raises(TransactionError) as failure:
        get_writer("mem0").write([Memory(id="a", body="NEW")], target)
    assert failure.value.exit_code == 4
    assert lock.read_bytes() == b"other owner"
    assert not target.exists()


def test_traversal_percent_unicode_case_and_long_filename_mapping(tmp_path):
    ids = ["a/b", "a%2Fb", "x", "x.", "CON", "_CON", "é", "e\u0301", "Case", "case", "中" * 200]
    writer = get_writer("ombre")
    writer.write([Memory(id=mid, body=mid, domains=["../../escape"]) for mid in ids], tmp_path / "out")
    result = get_reader("ombre").read(tmp_path / "out")
    assert sorted(m.id for m in result.memories) == sorted(ids)
    assert len(list((tmp_path / "out").rglob("*.md"))) == len(ids)
    assert not (tmp_path / "escape").exists()
    assert sanitize_id("a/b") != sanitize_id("a%2Fb")
    assert all(len(p.name.encode("utf-8")) <= 200 for p in (tmp_path / "out").rglob("*.md"))


def test_hardlink_and_symlink_are_rejected(tmp_path):
    original = tmp_path / "original.md"
    original.write_bytes(b"memory")
    linked = tmp_path / "linked.md"
    os.link(original, linked)
    assert get_reader("generic").read(original).errors
    linked.unlink()
    alias = tmp_path / "alias.md"
    try:
        os.symlink(original, alias)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable; junction tested separately")
    assert get_reader("generic").read(alias).errors
    alias.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_is_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.md").write_bytes(b"do not touch")
    junction = tmp_path / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(real)], capture_output=True)
    if result.returncode:
        pytest.skip("Junction creation unavailable")
    try:
        assert get_reader("generic").read(junction).errors
        with pytest.raises(BoundaryError):
            get_writer("generic").write([Memory(id="a")], junction)
        assert (real / "a.md").read_bytes() == b"do not touch"
    finally:
        os.rmdir(junction)


@pytest.mark.parametrize(
    "text",
    [
        "---\nid: a\nid: b\n---\nbody",
        "---\nx: &a [*a]\n---\nbody",
        "---\nx: .nan\n---\nbody",
        "---\nx: [broken\n---\nbody",
    ],
)
def test_unsafe_yaml_is_reported_invalid(tmp_path, text):
    (tmp_path / "a.md").write_text(text, encoding="utf-8")
    result = get_reader("generic").read(tmp_path)
    assert not result.memories and result.stats["invalid"] > 0
    assert any(i.severity == "error" for i in validate_schema(tmp_path, "generic"))


@pytest.mark.parametrize(
    "text", ['{"results":[],"results":[]}', '{"results":[{"id":"x","memory":"x","score":NaN}]}', "{}", '{"results":{}}']
)
def test_invalid_json_shapes_and_values_are_not_green(tmp_path, text):
    (tmp_path / "memories.json").write_text(text, encoding="utf-8")
    assert any(i.severity == "error" for i in validate_schema(tmp_path, "mem0"))


def test_resource_limits_and_nonfinite_values(tmp_path, monkeypatch):
    import memlink.safety as safety

    monkeypatch.setattr(safety, "MAX_FILE_BYTES", 20)
    (tmp_path / "big.md").write_bytes(b"a" * 21)
    assert get_reader("generic").read(tmp_path / "big.md").errors
    for value in (float("nan"), float("inf"), float("-inf")):
        assert validate_memory(Memory(id="a", importance_score=value))
        with pytest.raises(ValueError):
            sanitize(value)
    with pytest.raises(ValueError):
        sanitize([0] * 100001)
    assert sanitize({0, "x", None}) == [None, 0, "x"]


@pytest.mark.parametrize(
    "fmt,fixture",
    [
        ("generic", "module01/full-workspace"),
        ("ombre", "ombre_samples/dynamic"),
        ("openclaw", "openclaw_samples"),
        ("mem0", "mem0_samples"),
        ("zep", "zep_samples"),
    ],
)
def test_corresponding_format_roundtrip_nonzero(tmp_path, fmt, fixture):
    report = run_roundtrip(FIXTURES / fixture, fmt, keep_temp=tmp_path / "roundtrip")
    assert report.total > 0 and report.failed == 0, report.to_dict()
    assert report.matched == report.total
    if fmt == "generic":
        assert (tmp_path / "roundtrip/intermediate/memory/2026-10-02.md").exists()


def test_empty_or_invalid_roundtrip_is_not_green(tmp_path):
    for fmt in ("generic", "mem0", "openclaw", "ombre", "zep"):
        report = run_roundtrip(tmp_path, fmt)
        assert report.failed > 0 and report.issues


def test_scoped_identity_merge_duplicate_compare_and_epoch(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "memories.json").write_text(
        json.dumps(
            {
                "results": [
                    {"id": "same", "memory": "A", "user_id": "alice", "created_at": 0},
                    {"id": "same", "memory": "B", "user_id": "bob"},
                ]
            }
        ),
        encoding="utf-8",
    )
    result = merge([(get_reader("mem0"), source)], get_writer("generic"), tmp_path / "default", all=True)
    assert len(result["memories"]) == 2
    assert len(get_reader("generic").read(tmp_path / "default").memories) == 2
    linked = merge(
        [(get_reader("mem0"), source)], get_writer("generic"), tmp_path / "linked", all=True, link_by_id=True
    )
    assert len(linked["memories"]) == 1
    assert linked["receipt"]["workflow"]["merge"]["link_by_id"] is True
    epoch = next(m for m in result["memories"] if m.body == "A")
    assert epoch.created_at == datetime(1970, 1, 1, tzinfo=timezone.utc)
    naive = Memory(id="one", created_at=datetime(2026, 10, 2))
    aware = Memory(id="one", created_at=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert not resolve_conflict(naive, aware, "newest")
    assert resolve_conflict(naive, aware, "oldest")
    first, second = Memory(id="one", body="FIRST", checksum="same"), Memory(id="one", body="SECOND", checksum="same")
    assert any(i.field == "body" for i in compare_memories([first], [second]))
    assert compare_memories([first, second], [first])


def test_packaged_schema_rejects_instances_and_version():
    assert validate_instance({"schema_version": "1", "id": "x"}) == []
    assert validate_instance({"schema_version": "99", "id": "x"})
    assert validate_instance({"schema_version": "1", "id": "x", "valence": 2.0})
    resource = Path(__file__).parents[1] / "python/memlink/resources/canonical-v1.schema.json"
    assert json.loads(resource.read_text(encoding="utf-8")) == json.loads(
        (Path(__file__).parents[1] / "spec/canonical-v1.schema.json").read_text(encoding="utf-8")
    )


def test_plugin_contract_failures_and_role_registration(monkeypatch):
    import memlink.registry as registry

    monkeypatch.setattr(registry, "_readers", {})
    monkeypatch.setattr(registry, "_writers", {})

    class Legacy(FormatPlugin):
        name = "legacy"
        capabilities = Capabilities()

        def read(self, path):
            return ReadResult([])

        def write(self, memories, path):
            return []

        def validate(self, path):
            return []

    register_reader(Legacy)
    assert "legacy" in registry._readers and "legacy" not in registry._writers
    register_writer(Legacy)
    assert "legacy" in registry._writers

    class Duplicate(Legacy):
        pass

    with pytest.raises(ValueError, match="Duplicate"):
        register_reader(Duplicate)

    class Missing(Legacy):
        name = "missing"
        capabilities = None

    with pytest.raises(ValueError):
        register_reader(Missing)

    class Future(Legacy):
        name = "future"
        version_supported = ">=99"

    with pytest.raises(ValueError):
        register_reader(Future)

    class Invalid(Legacy):
        name = "invalid"
        capabilities = Capabilities(emotion="yes")

    with pytest.raises(ValueError):
        register_reader(Invalid)


def test_chatgpt_branch_selected_raw_graph_and_claude_mixed_blocks(tmp_path):
    source = tmp_path / "chatgpt"
    source.mkdir()
    graph = {
        "id": "conversation",
        "current_node": "chosen",
        "mapping": {
            "root": {
                "parent": None,
                "message": {"author": {"role": "user"}, "content": {"content_type": "text", "parts": ["question"]}},
            },
            "abandoned": {
                "parent": "root",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["ABANDONED"]},
                },
            },
            "chosen": {
                "parent": "root",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["CHOSEN", {"asset_pointer": "attachment"}]},
                },
            },
        },
    }
    (source / "conversations.json").write_text(json.dumps([graph]), encoding="utf-8")
    receipt = convert(get_reader("chatgpt"), get_writer("mem0"), source, tmp_path / "chat-out", all=True)["receipt"]
    assert receipt["status"] == "partial" and receipt["warnings"]
    memory = get_reader("mem0").read(tmp_path / "chat-out").memories[0]
    assert "CHOSEN" in memory.body and "ABANDONED" not in memory.body
    assert memory.extensions["chatgpt_transcript"] == graph
    claude = tmp_path / "claude"
    claude.mkdir()
    record = {
        "uuid": "conversation",
        "chat_messages": [
            {
                "sender": "human",
                "text": "alternate",
                "content": [{"type": "text", "text": "selected text"}, {"type": "tool_use", "payload": {"unknown": 0}}],
                "attachments": [{"name": "data.bin", "opaque": True}],
            }
        ],
    }
    (claude / "conversations.json").write_text(json.dumps([record]), encoding="utf-8")
    result = convert(get_reader("claude_export"), get_writer("generic"), claude, tmp_path / "claude-out", all=True)
    recovered = get_reader("generic").read(tmp_path / "claude-out").memories[0]
    assert recovered.body == "human: selected text"
    assert recovered.extensions["claude_transcript"] == record
    assert any("attachments" in w for w in result["warnings"])


@pytest.mark.parametrize("variant", ["cycle", "missing-parent", "missing-active", "malformed-author"])
def test_chatgpt_invalid_graph_has_deterministic_record_failure(tmp_path, variant):
    graph = {
        "id": "bad",
        "current_node": "a",
        "mapping": {
            "a": {
                "parent": None,
                "message": {"author": {"role": "user"}, "content": {"parts": ["text"], "content_type": "text"}},
            }
        },
    }
    if variant == "cycle":
        graph["mapping"]["a"]["parent"] = "a"
    elif variant == "missing-parent":
        graph["mapping"]["a"]["parent"] = "missing"
    elif variant == "missing-active":
        graph.pop("current_node")
        graph["mapping"]["b"] = {"parent": None}
    else:
        graph["mapping"]["a"]["message"]["author"] = "invalid"
    (tmp_path / "conversations.json").write_text(json.dumps([graph]), encoding="utf-8")
    result = get_reader("chatgpt").read(tmp_path)
    assert not result.memories
    assert result.stats["invalid"] == 1
    assert result.records[0]["outcome"] == "invalid"


def test_stream_time_zero_status_and_raw_collection_fields(tmp_path):
    source = tmp_path / "summary.md"
    source.write_text(
        "---\nschema: memlink-stream-summary-v1\ntitle: summary\ndate: 1970-01-01\n"
        "timezone: UTC\nstatus: archived\npeak_hour: 0\ntotal_events: 0\ncollection_git: partial\n---\nbody",
        encoding="utf-8",
    )
    result = get_reader("stream-summary").read(source)
    assert not result.errors and len(result.memories) == 1
    memory = result.memories[0]
    assert memory.created_at == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert memory.status == "archived" and memory.summary == "0 events, peak at 0:00"
    assert memory.extensions["stream_frontmatter"]["collection_git"] == "partial"


def test_unknown_schema_missing_schema_and_legacy_writer_wrapper_fail_closed(tmp_path, monkeypatch):
    import memlink.validators as validators

    assert validate_memory(Memory(id="x", schema_version="future"))

    def unavailable():
        raise OSError("schema resource missing")

    monkeypatch.setattr(validators, "_load_canonical_schema", unavailable)
    monkeypatch.setattr(validators, "_SCHEMA_CACHE", None)
    assert any(i.severity == "error" for i in validate_schema(FULL, "generic"))
    assert not run_roundtrip(FULL, "generic").matched


def test_legacy_writer_wrapper_receives_only_staging_and_fails_before_commit(tmp_path):
    # The legacy serializer really runs, receives staging and cannot commit invalid output.
    called = []

    class Legacy(FormatPlugin):
        name = "generic"
        capabilities = Capabilities()

        def read(self, path):
            return ReadResult([])

        def write(self, memories, path):
            called.append(path)
            (path / "malformed.md").write_text("---\nx: [broken\n---\nbody", encoding="utf-8")
            return []

        def validate(self, path):
            return []

    with pytest.raises(TransactionError):
        Legacy().write([Memory(id="a")], tmp_path / "legacy-out")
    assert not (tmp_path / "legacy-out").exists()
    assert called and all(p != tmp_path / "legacy-out" for p in called)


def test_unverified_identity_claim_cannot_merge_independent_sources(tmp_path):
    sources = []
    for index in (1, 2):
        root = tmp_path / f"source-{index}"
        root.mkdir()
        fm = {
            "id": "same",
            "schema_version": "1",
            "metadata": {
                "_memlink_identity": {"namespace": "forged", "scope": {"scope": "unknown"}, "native_id": "same"}
            },
            "_memlink_body_length": 4,
        }
        (root / "a.md").write_text("---\n" + yaml.safe_dump(fm) + "---\n\nbody", encoding="utf-8", newline="")
        sources.append((get_reader("generic"), root))
    result = merge(sources, get_writer("generic"), tmp_path / "out", all=True)
    assert len(result["memories"]) == 2
    assert all(m.metadata["_memlink_identity"]["namespace"] != "forged" for m in result["memories"])
    assert all(m.metadata["_claimed_identity"]["namespace"] == "forged" for m in result["memories"])


def test_mem0_top_level_unknowns_and_zep_top_level_session_scope(tmp_path):
    mem0 = tmp_path / "mem0.json"
    mem0.write_text(
        json.dumps({"results": [{"id": "same", "memory": "one"}], "relations": [{"unknown_relation": "raw"}]}),
        encoding="utf-8",
    )
    result = get_reader("mem0").read(mem0)
    assert result.memories[0].extensions["mem0_export_fields"]["relations"] == [{"unknown_relation": "raw"}]
    zep = tmp_path / "zep.json"
    zep.write_text(
        json.dumps({"session_id": "session-A", "facts": [{"uuid": "same", "fact": "one"}]}), encoding="utf-8"
    )
    memory = get_reader("zep").read(zep).memories[0]
    assert memory.metadata["_memlink_identity"]["scope"] == {"session_id": "session-A"}


def test_versioned_receipt_archive_and_compatibility_resources(tmp_path):
    from importlib.resources import files

    from memlink.registry import list_formats

    receipt_schema = json.loads(
        files("memlink").joinpath("resources/memlink-receipt-v1.schema.json").read_text(encoding="utf-8")
    )
    archive_schema = json.loads(
        files("memlink").joinpath("resources/memlink-archive-v1.schema.json").read_text(encoding="utf-8")
    )
    contract = json.loads(files("memlink").joinpath("resources/compatibility-v1.json").read_text(encoding="utf-8"))
    assert {
        name: {"reader": row["reader"], "writer": row["writer"]} for name, row in contract["formats"].items()
    } == list_formats()
    for fmt in ("generic", "mem0", "zep", "openclaw", "ombre"):
        target = tmp_path / fmt
        get_writer(fmt).write([rich_memory()], target)
        receipt = json.loads((target / ".memlink/receipt.json").read_text(encoding="utf-8"))
        archive = json.loads((target / ".memlink/archive.json").read_text(encoding="utf-8"))
        assert validate_instance(receipt, receipt_schema) == []
        assert validate_instance(archive, archive_schema) == []
        receipt["version"] = "future"
        assert validate_instance(receipt, receipt_schema)


def test_source_changes_during_parser_read_are_detected(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_bytes(b"ORIGINAL")
    original_read = Path.read_bytes
    changed = []

    def read_and_change(file):
        content = original_read(file)
        if file == source and not changed:
            changed.append(True)
            source.write_bytes(b"CHANGED")
        return content

    monkeypatch.setattr(Path, "read_bytes", read_and_change)
    with pytest.raises(TransactionError) as error:
        convert(get_reader("generic"), get_writer("generic"), source, tmp_path / "out", all=True)
    assert error.value.exit_code == 4
    assert not (tmp_path / "out").exists()


def test_broadcast_reuses_one_input_snapshot(tmp_path, monkeypatch):
    from memlink.converter import broadcast

    source = tmp_path / "source"
    source.mkdir()
    file = source / "a.md"
    file.write_bytes(b"original")

    def change_after_first(self, relative):
        if self.target.name == "first" and relative == ".memlink/receipt.json":
            file.write_bytes(b"changed")

    monkeypatch.setattr(OutputTransaction, "after_file_commit", change_after_first)
    result = broadcast(
        get_reader("generic"),
        source,
        [(get_writer("generic"), tmp_path / "first"), (get_writer("generic"), tmp_path / "second")],
        all=True,
    )
    assert result["status"] == "failed"
    assert result["targets"][0]["exit_code"] == 0
    assert result["targets"][1]["exit_code"] == 4
    assert not (tmp_path / "second").exists()


def test_unknown_capability_version_is_rejected(monkeypatch):
    import memlink.registry as registry

    monkeypatch.setattr(registry, "_readers", {})

    class FutureCaps(FormatPlugin):
        name = "future-caps"
        capabilities = Capabilities(version="future")

        def read(self, path):
            return ReadResult([])

        def write(self, memories, path):
            return []

        def validate(self, path):
            return []

    with pytest.raises(ValueError, match="version"):
        register_reader(FutureCaps)


def test_opaque_library_value_cannot_be_claimed_native_preserved(tmp_path):
    class Opaque:
        def __str__(self):
            return "unproven text"

    memory = Memory(id="opaque", body="text", extensions={"opaque": Opaque()})
    assert validate_memory(memory)
    with pytest.raises(TransactionError) as error:
        get_writer("generic").write([memory], tmp_path / "out")
    assert error.value.exit_code == 2
    assert not (tmp_path / "out").exists()
