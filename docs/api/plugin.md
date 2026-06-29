# Plugin API

Add a new memory format by implementing one class.

## FormatPlugin

```python
from memlink.plugin import FormatPlugin, ReadResult, Capabilities

class MyFormatReader(FormatPlugin):
    name = "myformat"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=False,
        summary=True,
    )

    def read(self, path: Path) -> ReadResult:
        """Read format → Canonical. Never raise."""
        ...

    def write(self, memories, path) -> list[str]:
        """Canonical → format. Return warnings."""
        ...

    def validate(self, path) -> list[ValidationIssue]:
        """Check format integrity."""
        ...
```

## Capabilities

| Field | Default | Description |
|-------|---------|-------------|
| `emotion` | `False` | Supports valence/arousal |
| `summary` | `True` | Has summary/description field |
| `relationships` | `False` | Supports memory relationships |
| `importance_label` | `False` | Accepts non-numeric importance |
| `preserve_unknown_fields` | `True` | Can store unrecognized fields |
| `supported_kinds` | `None` | Set of accepted `kind` values |
| `max_body_size` | `None` | Body size limit in bytes |

## Spec Compliance Checklist

Third-party plugins should map these Canonical Schema core fields:

| # | Canonical Field | Required | Type | Notes |
|---|----------------|----------|------|-------|
| 1 | `id` | ✅ | `str` | Stable unique identifier |
| 2 | `name` | ✅ | `str` | Short label (derive from body if native name missing) |
| 3 | `body` | ✅ | `str` | Main content |
| 4 | `kind` | ✅ | `str` | Open vocabulary; map to `"dynamic"` if unknown |
| 5 | `tags` | — | `list[str]` | Sorted, deterministic |
| 6 | `created_at` | ✅ | `datetime` | ISO 8601, UTC |
| 7 | `updated_at` | — | `datetime` | ISO 8601, UTC |
| 8 | `valence` | — | `float` | -1.0 to 1.0 |
| 9 | `arousal` | — | `float` | 0.0 to 1.0 |
| 10 | `importance_score` | — | `float` | Format-native scale |
| 11 | `pinned` | — | `bool` | Default `False` |
| 12 | `status` | — | `"active"` or `"archived"` | Default `"active"` |

Reader must never raise (warn + skip on error). Writer must return `list[str]` warnings, never raise on single-record failure.

## Registration

```python
# registry.py
from .myformat_reader import MyFormatReader
register_reader(MyFormatReader)
```

Or via `pyproject.toml` entry_points for external packages.
