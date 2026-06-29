# Quick Start

## Install

```bash
pip install memlink-bridge
```

## Convert Generic Markdown → OpenClaw

```bash
mkdir -p /tmp/memlink-demo
cat > /tmp/memlink-demo/hello.md << 'EOF'
---
title: Hello MemLink
tags: [demo]
---
This is a memory.
EOF

memlink convert --from generic --to openclaw \
  -s /tmp/memlink-demo \
  -T /tmp/memlink-output
```

## Convert Mem0 Export → OpenClaw

```bash
memlink convert --from mem0 --to openclaw \
  -s ./mem0-export \
  -T ./openclaw-memories
```

## Convert Ombre → OpenClaw

```bash
memlink convert --from ombre --to openclaw \
  -s ~/.claude/ombre-buckets \
  -T ./memories
```

## Inspect & Validate

```bash
memlink inspect memory-file.md
memlink validate --level schema -s memories/
memlink formats
```
