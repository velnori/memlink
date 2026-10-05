# Architecture: two workflows, one interchange layer

MemLink remains an AI Memory Interchange Layer. A Reader parses an approved source into language-neutral Canonical records; a Writer serializes those records to an exact target file variant. Package 2.0.0 does not replace or renumber canonical-v1.

```text
Source files → Reader → Canonical → Writer → native files + archive + receipt
                          │
                          └→ private pack → all / select → controlled context + receipt
```

**Full Migration** automatically converts the approved set. New-directory export and safe migrate into existing built-in targets share staging, real native readback, accounting, source/target competition checks and per-file commits. Best effort is the default; strict is an explicit policy. There is no mandatory manual classification.

**Context Handoff** uses the OpenClaw Reader with a narrower, explicit memory scope. The private pack retains full sources and canonical values. All-record handoff skips human selection/review; selective handoff projects only approved records into reference text. Both validate scope, policy, budget and integrity. Neither writes hidden client Saved Memory.

Canonical identity includes source namespace, scope and native ID. Equal IDs from different users or approved roots remain distinct. An archive carries the originating identity and exact values for transport; native readback never relies on archive recovery to assert native preservation. Capabilities are preflight hints. Field results in the receipt come from actual serialization and target readback.

The [manifest](compatibility.md) binds support claims to exact variants and independently maintained synthetic goldens. Conformance is shipped in the package; release readiness verifies the package outside the checkout. Multilanguage implementations and new adapter expansion remain deferred pending real needs, while the Canonical/Reader/Writer architecture remains intact.

See [DESIGN](../DESIGN.md), [Canonical specification](https://github.com/velnori/memlink/blob/main/spec/canonical-v1.md), [Plugin API](../api/plugin.md), and [2.0 upgrade](migration-2.0.md).
