# Source URI Format

## Structure

```
<format>://<authority>/<path>[?query][#fragment]
```

| Component | Required | Description |
|-----------|----------|-------------|
| `format` | Yes | Format name: `ombre`, `openclaw`, `mem0`, `zep`, etc. |
| `authority` | No | Empty for local files, hostname for remote (v1). Triple-slash for local: `ombre:///path`. |
| `path` | Yes | Absolute path within the format's storage hierarchy. |
| `query` | No | Reserved for v1 (version, branch). |
| `fragment` | No | Reserved for v1 (anchor within a memory). |

## Encoding

- Path segments: URL-encoded per RFC 3986
  - `动态/项目` → `%E5%8A%A8%E6%80%81/%E9%A1%B9%E7%9B%AE`
- Reserved characters (`/`, `?`, `#`, `:`) must be percent-encoded when part of a segment value
- Null bytes (`\0`) and newlines are forbidden in all components

## Examples

```
ombre:///dynamic/user/preferences       # Ombre local, dynamic type, user domain
ombre:///permanent/docs/manual          # Ombre local, permanent type, docs domain
ombre:///feel/2024/sunset               # Ombre local, emotion type

openclaw:///memory/project-alpha        # OpenClaw local, memory directory
openclaw:///memory/feels/nostalgia      # OpenClaw local, feels directory

# Future (v1)
ombre://remote.host/dynamic/user/abc    # Remote Ombre instance
mem0://api.mem0.io/v1/users/abc         # Mem0 cloud API
```

## Validation (Python)

```python
from urllib.parse import urlparse

def validate_source_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return (
        parsed.scheme in SUPPORTED_FORMATS
        and parsed.path.startswith("/")
        and all(c not in parsed.path for c in ['\0', '\n'])
    )
```
