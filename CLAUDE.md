# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

memlink — AI Memory Interchange Layer。语言无关的 AI 记忆格式桥接层。v0：Ombre Brain ↔ OpenClaw 双向转换 CLI。架构预留 Mem0、Zep 等。MIT 协议，发布到 PyPI。

## 项目结构

```
memlink/
├── spec/                        # 语言无关规范（先于实现）
│   ├── canonical-v1.md          # Canonical Schema v1 规范
│   ├── canonical-v1.schema.json # JSON Schema
│   └── source-uri.md            # Source URI 格式规范
├── python/memlink/              # Python 实现
├── docs/                        # 设计文档 + 评审记录
├── tests/                       # 测试
├── pyproject.toml               # 项目元数据 + 依赖 + ruff/mypy/pytest 配置
├── README.md
├── LICENSE (MIT)
└── .gitignore
```

## 技术栈

Python ≥3.10。运行时依赖：`pyyaml>=6.0`（唯一外部依赖，处理 YAML frontmatter）。开发依赖：pytest、pytest-cov、mypy、ruff、hypothesis。

## 架构

```
格式 A → AReader → CanonicalMemory → BWriter → 格式 B
```

`FormatPlugin` 统一接口（read / write / validate + Capabilities）。O(n) 复杂度。

### Python 模块（11 文件，~600 行）

```
memlink/
  __init__.py          # version string
  models.py            # CanonicalMemory + Source + Relationship + JSONValue
  plugin.py            # FormatPlugin ABC + ReadResult + Capabilities + ValidationIssue
  serialization.py     # 序列化安全 + 深度限制 + 循环引用检测
  cli.py               # argparse CLI
  ombre_reader.py      # Ombre → Canonical
  ombre_writer.py      # Canonical → Ombre
  openclaw_reader.py   # MEMORY.md + memory/*.md → Canonical
  openclaw_writer.py   # Canonical → MEMORY.md + memory/*.md
  converter.py         # Normalize → Mapping → Transform → Validation
  validators.py        # 三级校验 + MLxxx 错误码
```

## 关键约束

- 全程 pathlib.Path
- `body` 可为 `None`
- `kind`、`Relationship.type` 为开放 `str`，规范推荐值不限制
- importance 不归一化，score+label 保留原值
- archived 是 status 不是 kind
- 文件名用 id，percent-encoding 处理非法字符（可逆），casefold 检测 Windows 冲突
- `metadata` = Canonical 定义扩展，`extensions` = 透传（推荐 namespace 防撞名）
- metadata 值限定 JSON 兼容类型（`serialization.py` 深度限制+循环检测）
- 不做 NLP domain 推断，`--unknown-domain-action skip|default:<name>`（默认 skip）
- MEMORY.md 是 Writer 实现细节，Canonical 不关心索引
- Writer 写入前 mtime+size 检测并发修改
- Reader：Never Raise（解析失败→warning→skip→继续），不解析日期（留字符串给 Converter）
- Reader.read() → `ReadResult`（memories + warnings + stats）
- Converter 统一做 datetime 类型转换，保证 Reader 行为一致
- 所有输出确定性排序（tags/domains sorted()、MEMORY.md 按 id）
- 转换前 Capabilities 兼容检查 + Feature Loss Report（含 Reason）
- Golden Tests：每个 fixture 配 expected.json
- Fuzz Testing：hypothesis 100 随机 case
- Roundtrip 语义一致非字节一致，v0 豁免 relationships
- 规范 (`spec/`) 与实现分离
- 错误码统一 MLxxx 格式（ML001-ML499 四层）
- CLI verbose 三级：-v/-vv/-vvv
- 兼容性承诺：Schema Stable / Plugin+CLI+Python API Experimental

## 开发命令

```bash
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/test_converter.py -v
ruff check memlink/ && ruff format memlink/
mypy memlink/
python -m memlink.cli --help
```

## 设计文档

- [DESIGN.md](docs/DESIGN.md) — 完整技术方案（570行，终版冻结）
- [建议1.md](docs/建议1.md) / [建议2.md](docs/建议2.md) — 四轮外部评审记录
- [spec/canonical-v1.md](spec/canonical-v1.md) — Canonical Schema 规范
- [spec/canonical-v1.schema.json](spec/canonical-v1.schema.json) — JSON Schema
