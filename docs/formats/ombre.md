# Ombre bucket Markdown

Format `ombre` reads YAML bucket notes under `dynamic/`, `permanent/`, and `feel/`. Native kind/domain routing is mapped to canonical values; original frontmatter and timezone/raw created value remain in `metadata.memlink.original`. `created` enters canonical `created_at` in UTC, including epoch 0 and explicit offsets. Stats and merge use that actual time.

The writer uses deterministic identity-based 12-hex target IDs for foreign non-Ombre IDs. Filename/domain mapping percent-encodes reserved characters and avoids device names, case/Unicode collisions and root escape. The receipt/archive maps canonical IDs to target IDs, so those mappings are not random or silently lost.

YAML values are serialized with safe quoting. Only fields verified through native Ombre readback count as native-preserved. Native importance conversion and one-domain constraints can transform values; summaries, relationships, status, multiple domains and opaque source data may require canonical archive transport. Keep that archive for canonical roundtrip. Invalid bucket notes are counted/reported rather than disappearing.
