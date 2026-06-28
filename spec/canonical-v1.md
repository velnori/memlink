# Canonical Memory Schema v1

**Version**: 1.0
**Status**: Stable
**Compatibility**: 1.x backward-compatible, 2.0 may break

## Overview

Canonical Memory is the language-neutral intermediate representation used by memlink to bridge AI memory systems. Any format-specific Reader converts source data into this schema; any Writer converts from this schema into the target format.

## Design Principles

- **Lossless transport** — Canonical is a shipping layer, not a judge. It preserves original values rather than normalizing them.
- **Open-ended** — `kind`, `Relationship.type`, and `extensions` are open strings with recommended values, not closed enumerations. Unknown values degrade gracefully, not fatally.
- **Layered** — Core fields (every Reader/Writer must handle), metadata (Canonical-defined extensions with known semantics), extensions (opaque pass-through).

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `"1"` | Canonical schema version |
| `id` | `string` | Stable identifier, unique within a dataset |

## Optional Fields

### Identity

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `string \| null` | `null` | Display title |
| `source` | `Source \| null` | `null` | Origin format + path + URI |

### Content

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `summary` | `string \| null` | `null` | Short description (OpenClaw description, Mem0 summary, etc.) |
| `body` | `string \| null` | `null` | Full content. May be null for metadata-only memories. |

### Classification

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `kind` | `string` | `"dynamic"` | Recommended: `dynamic`, `permanent`, `emotion`. Unknown → fallback `dynamic`. |
| `status` | `"active" \| "archived"` | `"active"` | Lifecycle status, orthogonal to kind. |

### Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tags` | `list[string]` | `[]` | Free-form labels |
| `domains` | `list[string]` | `[]` | Hierarchical categories (e.g., `["user", "preferences"]`) |
| `created_at` | `datetime \| null` | `null` | UTC RFC 3339 |
| `updated_at` | `datetime \| null` | `null` | UTC RFC 3339 |

### Emotion

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `valence` | `float \| null` | `null` | 0.0–1.0, Russell's circumplex model |
| `arousal` | `float \| null` | `null` | 0.0–1.0, Russell's circumplex model |

### Importance

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `importance_score` | `float \| null` | `null` | Numeric value, format-native range (not normalized) |
| `importance_label` | `string \| null` | `null` | Label-based (e.g., `"high"`, `"critical"`) |

### Other

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pinned` | `bool` | `false` | Prevent archival/decay |
| `checksum` | `string \| null` | `null` | SHA256(body), for diff/merge/dedup |

### Extension Layers

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `metadata` | `dict[string, JSONValue]` | `{}` | Canonical-defined extensions with known semantics |
| `extensions` | `dict[string, any]` | `{}` | Opaque pass-through, recommended `{format_name: {...}}` namespace |

### Relationships (v0 reserved)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `relationships` | `list[Relationship]` | `[]` | Stored in `metadata.memlink.relationships`. v0 writers skip. |

## Source

```yaml
source:
  format: ombre            # Format name
  path: dynamic/user/abc.md # Relative path within the format's storage
  uri: ombre://dynamic/user/abc  # Machine-readable URI (RFC 3986, URL-encoded)
```

## Relationship

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_id` | `string` | Yes | ID of the related memory |
| `type` | `string` | Yes | Recommended: `relates_to`, `parent`, `child`, `derived_from` |
| `weight` | `float \| null` | No | Relationship strength |

## Kind Recommended Values

| Value | Semantics | Examples of source values that map here |
|-------|-----------|----------------------------------------|
| `dynamic` | Floating/transient memories | dynamic, conversation, reflection, todo |
| `permanent` | Long-term retention | permanent, fact, document, bookmark, skill |
| `emotion` | Emotional/feeling records | emotion, feel, mood |

## metadata.memlink (Roundtrip Preservation)

```yaml
metadata:
  memlink:
    source:
      format: ombre
      version: "1.0"        # Source format version
    schema_version: "1"
    converted_at: "2026-06-28T10:00:00Z"
    original:               # Full original field snapshot
      id: "bucket_id_here"
      kind: dynamic
      domains: [user, preferences, work]
      importance: 8
      created_tz: "2024-06-28T10:00:00+08:00"
```

## JSON Value Constraint

All values in `metadata` must be JSON-compatible:
- `null`, `bool`, `int`, `float`, `str`
- `list[JSONValue]`
- `dict[str, JSONValue]`

Non-JSON types (datetime, set, custom objects) are serialized to JSON-safe equivalents by the implementation.

## Versioning Policy

- **1.x**: Additive only — new optional fields, no removal, no type changes.
- **2.0**: Breaking changes allowed — field removal, type changes, semantic shifts.

Writers declare `version_supported` (semver range, e.g. `">=1,<3"`). Readers and Writers map to/from the schema version they support.
