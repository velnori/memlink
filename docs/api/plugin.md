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

## Registration

```python
# registry.py
from .myformat_reader import MyFormatReader
register_reader(MyFormatReader)
```

Or via `pyproject.toml` entry_points for external packages.
