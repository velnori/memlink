"""Format recognition requires positive evidence; no first-success adapter guessing."""

from __future__ import annotations

from pathlib import Path

from ._frontmatter import parse_frontmatter
from .read_support import load_json
from .safety import files_in


def detect_format(path: Path) -> str:
    files = files_in(path)
    candidates = set()
    if path.is_file() and path.name == "MEMORY.md":
        candidates.add("openclaw")
    if path.is_dir() and ((path / "MEMORY.md").is_file() or (path / "memory").is_dir()):
        candidates.add("openclaw")
    if path.is_dir() and any((path / n).is_dir() for n in ("dynamic", "permanent", "feel")):
        candidates.add("ombre")
    if candidates == {"openclaw"} and path.is_dir():
        return "openclaw"  # Other workspace files are outside this adapter's memory scope.
    json_files = [f for f in files if f.suffix.lower() == ".json" and (path.is_file() or f.parent == path.absolute())]
    preferred = [f for f in json_files if f.name in {"memories.json", "facts.json", "conversations.json"}]
    selected_json = set(preferred or json_files)
    for file in files:
        if file.suffix.lower() == ".json":
            if file not in selected_json:
                continue
            data = load_json(file)
            if isinstance(data, dict):
                if "facts" in data or ("messages" in data and "summary" in data):
                    candidates.add("zep")
                elif "results" in data:
                    records = data["results"]
                    if isinstance(records, list) and records:
                        if isinstance(records[0], dict) and "memory" in records[0]:
                            candidates.add("mem0")
                        elif isinstance(records[0], dict) and ("fact" in records[0] or "content" in records[0]):
                            candidates.add("zep")
                    elif file.name == "memories.json" and records == []:
                        candidates.add("mem0")
            elif isinstance(data, list) and data:
                for record in data:
                    if not isinstance(record, dict):
                        continue
                    if "mapping" in record:
                        candidates.add("chatgpt")
                    elif "chat_messages" in record:
                        candidates.add("claude_export")
                    elif "memory" in record:
                        candidates.add("mem0")
                    elif "fact" in record:
                        candidates.add("zep")
        elif file.suffix.lower() == ".md":
            if "openclaw" in candidates and (
                file.name in {"MEMORY.md", "DREAMS.md", "USER.md"} or "memory" in file.relative_to(path).parts
            ):
                continue
            try:
                fm, _ = parse_frontmatter(file.read_bytes().decode("utf-8"))
            except ValueError:
                continue
            if "bucket_id" in fm:
                candidates.add("ombre")
            elif fm.get("schema") == "memlink-stream-summary-v1":
                candidates.add("stream-summary")
            elif fm.get("schema_version") == "1" and "id" in fm:
                candidates.add("generic")
            elif path.is_file() and "metadata" in fm and "name" in fm:
                candidates.add("openclaw")
            elif "ombre" not in candidates:
                candidates.add("generic")
    if len(candidates) != 1:
        raise ValueError("Ambiguous or unknown format; specify --from / --format explicitly")
    return next(iter(candidates))
