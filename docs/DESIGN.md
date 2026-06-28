# memlink — AI Memory Interchange Layer

> A language-neutral interchange layer for AI memory systems — similar in spirit to how Pandoc enables document interoperability.

## 定位

**memlink** 是 AI Memory 格式桥接层。通过统一的 Canonical Memory 中间格式，任何 AI 记忆系统只需各写一个 Reader + Writer 就能互通。

**设计哲学**：Canonical 是「无损运输层」，不是「标准化裁判」。不替用户改写数据，只管安全送达。

**长期方向**：规范与实现分离。`spec/` 定义 Canonical Schema（语言无关 + JSON Schema），Python 实现只是第一个。未来可以有 Rust、Go、TypeScript 实现同一套 Schema。

v0 目标：Ombre Brain ↔ OpenClaw 双向转换。架构预留扩展到 Mem0、Zep、Claude Memory、OpenMemory 等。

---

## Schema 兼容策略

- **1.x**：向后兼容（只加字段、不删不改）
- **2.0**：允许不兼容变更

Reader/Writer 按 `schema_version` 做适配，不按 package version。

---

## 项目结构

```
memlink/
├── spec/                       # 语言无关规范
│   ├── canonical-v1.md         # Canonical Schema v1 规范
│   ├── canonical-v1.schema.json # JSON Schema（自动校验用）
│   └── source-uri.md           # Source URI 格式规范
├── python/
│   └── memlink/
│       ├── __init__.py
│       ├── models.py           # CanonicalMemory + Source + Relationship
│       ├── plugin.py           # FormatPlugin + Capabilities + ReadResult
│       ├── serialization.py    # 序列化安全（JSON/YAML/TOML）
│       ├── cli.py
│       ├── ombre_reader.py
│       ├── ombre_writer.py
│       ├── openclaw_reader.py
│       ├── openclaw_writer.py
│       ├── converter.py        # Normalize → Mapping → Transform → Validation
│       └── validators.py       # 三级校验 + 结构化 issue
└── tests/
    ├── fixtures/
    └── test_*.py
```

---

## 核心架构：Canonical Model

不绑定具体格式。Reader 负责「格式 A → Canonical」，Writer 负责「Canonical → 格式 B」。复杂度 O(n)。

### Canonical Memory

```python
from typing import Union, Literal
from dataclasses import dataclass, field
from datetime import datetime

JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]

@dataclass
class Source:
    format: str                      # "ombre" / "openclaw" / "mem0"
    path: str                        # "dynamic/user/abc.md"
    uri: str | None = None           # "ombre://dynamic/user/abc"

@dataclass
class Memory:
    schema_version: Literal["1"]

    # 标识
    id: str
    name: str | None = None
    source: Source | None = None     # 替代 source_uri 字符串

    # 内容
    summary: str | None = None
    body: str | None = None

    # 分类（kind 为开放 str，规范推荐值见下方）
    kind: str = "dynamic"
    status: Literal["active", "archived"] = "active"

    # 标签与领域
    tags: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    # 时间（UTC RFC 3339）
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 情感
    valence: float | None = None
    arousal: float | None = None

    # 重要性（不归一化）
    importance_score: float | None = None
    importance_label: str | None = None

    pinned: bool = False

    # 内容校验（可选，用于 diff/merge/去重）
    checksum: str | None = None      # SHA256(body)

    # 元数据分层
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)  # memlink 不解析，推荐 namespace

@dataclass
class Relationship:
    target_id: str
    type: str                        # 推荐：relates_to | parent | child | derived_from
    weight: float | None = None
```

### Kind 推荐值（非限制）

| 推荐值 | 语义 | Reader 映射示例 |
|--------|------|----------------|
| `dynamic` | 日常浮沉 | dynamic、conversation、reflection、todo |
| `permanent` | 永久保留 | permanent、fact、document、bookmark、skill |
| `emotion` | 情感/感受 | emotion、feel、mood |

Writer 对不认识的 kind 回退 `dynamic` + warning。

### 字段分层

```
core fields   → id, name, body, kind, status, tags, domains, source, checksum ...
                 ↑ Reader/Writers 必须处理
metadata      → Canonical Schema 定义的扩展（memlink namespace），已知语义
                 ↑ 规范的一部分
extensions    → memlink 完全不理解，仅负责运输
                 ↑ 第三方自由扩展，推荐 namespace 防撞名（extensions.mem0.xxx）
metadata.memlink.original → 源格式原始字段快照
                 ↑ lossless roundtrip 的关键
```

---

## FormatPlugin 接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationIssue:
    code: str                        # "ML001" 错误码
    severity: Severity
    file: str | None
    field: str | None
    message: str
    suggestion: str | None = None

@dataclass
class ReadResult:
    memories: list[Memory]
    warnings: list[str]
    stats: dict[str, int]            # {"parsed": 245, "skipped": 3, "invalid": 0}

@dataclass
class Capabilities:
    version: Literal["1"] = "1"

    # 功能支持
    relationships: bool = False
    attachments: bool = False
    summary: bool = True
    emotion: bool = False
    importance_label: bool = False
    ttl: bool = False
    embedding: bool = False

    # 约束
    max_body_size: int | None = None          # 字节数
    supported_kinds: set[str] | None = None   # None=所有

    # 扩展能力
    preserve_unknown_fields: bool = True       # 是否能保留 extensions

class FormatPlugin(ABC):
    name: str
    version_supported: str             # semver range, e.g. ">=1,<3"
    capabilities: Capabilities

    @abstractmethod
    def read(self, path: Path) -> ReadResult: ...

    @abstractmethod
    def write(self, memories: Iterable[Memory], path: Path) -> list[str]: ...

    @abstractmethod
    def validate(self, path: Path) -> list[ValidationIssue]: ...
```

### 能力兼容检查 + Feature Loss Report

转换前检查，转换后统计：

```
memlink convert --from ombre --to openclaw -s ... -t ...

  WARNING: Target does not support relationships → 8 will be dropped
  WARNING: Target cannot preserve unknown extensions → 5 will be dropped

  Converted: 128

  ── Feature Loss ──
  relationships      8 dropped
  emotion           14 dropped
  extensions          5 dropped
  ─────────────────
  Total loss         27 fields across 19 memories
```

---

## 错误码体系

| Code | 含义 |
|------|------|
| ML001 | InvalidDatetime — 时间戳格式错误 |
| ML002 | MissingID — 缺少必需 id |
| ML003 | DuplicateID — 重复 id |
| ML004 | InvalidSchema — schema_version 不兼容 |
| ML005 | CircularReference — metadata 循环引用 |
| ML006 | NestingTooDeep — metadata 嵌套过深 |
| ML007 | UnsupportedKind — kind 不被目标格式支持 |
| ML008 | BodyTooLarge — 超过目标格式大小限制 |
| ML009 | ConcurrentModification — MEMORY.md 并发修改 |
| ML010 | InvalidSourceURI — source URI 格式非法 |

---

## Exit Code

| Code | 含义 |
|------|------|
| 0 | Success |
| 1 | Diff found（diff 命令发现差异） |
| 2 | Validation error（校验失败） |
| 3 | I/O error（文件读写错误） |
| 4 | Concurrent modification（并发冲突） |
| 5 | Format incompatible（能力不兼容） |
| 130 | User interrupted（Ctrl+C） |

---

## 转换映射表

### Ombre → Canonical

| Ombre 字段 | Canonical 字段 | 规则 |
|-----------|---------------|------|
| bucket_id | id | 直接复制 |
| — | source.format | `"ombre"` |
| — | source.path | `{type}/{domain}/{name}.md` |
| — | source.uri | `ombre://{type}/{domain}/{bucket_id}` |
| name | name | 直接复制 |
| content (body) | body | 直接复制 |
| — | summary | 留空 |
| type | kind | `dynamic→dynamic / permanent→permanent / feel→emotion` |
| — | status | 默认 active |
| domain | domains | 多值保留为 list |
| tags | tags | 直接复制 |
| importance (1-10) | importance_score | 原值保留 |
| valence | valence | 直接复制 |
| arousal | arousal | 直接复制 |
| created | created_at | 原始时区→metadata.memlink.original.created_tz |
| pinned | pinned | 直接复制 |
| — | checksum | SHA256(body) |
| — | metadata.memlink | 原始字段快照 |

### Ombre → OpenClaw（写入时）

| Canonical 字段 | OpenClaw 字段 | 规则 |
|---------------|-------------|------|
| id | 文件名 | 用 id，不用 name |
| name | frontmatter name | 直接复制 |
| summary | description | 有则写入，无则取 body 首段 120 字 |
| body | body | 直接复制 |
| source.uri | metadata.source_uri | 直接复制 |
| domains | metadata.domain | 逗号拼接 |
| tags | metadata.tags | YAML list |
| importance_score / importance_label | metadata.importance | 优先 label |
| valence | metadata.valence | 直接复制 |
| arousal | metadata.arousal | 直接复制 |
| created_at | metadata.created_at | UTC ISO |
| pinned | metadata.pinned | true/false |
| checksum | metadata.checksum | 直接复制 |
| kind + status | 路由 | 见路由表 |
| metadata.memlink | metadata.memlink | 原样保留 |
| extensions | metadata.extensions | YAML 序列化（若 preserve_unknown_fields=True） |

### Kind + Status 路由

MEMORY.md 索引是 OpenClaw Writer 的实现细节，Canonical 不关心索引。

| Canonical | OpenClaw 目标 |
|-----------|--------------|
| kind=dynamic, status=active | `memory/<id>.md` + MEMORY.md 索引 |
| kind=permanent, status=active | `memory/<id>.md` + `priority: high` |
| kind=emotion, status=active | `memory/feels/<id>.md` |
| status=archived | 跳过（`--include-archived` 强制转换） |
| kind 为其他值 | 回退 `dynamic` + warning |

### OpenClaw → Canonical

| OpenClaw 字段 | Canonical 字段 | 规则 |
|-------------|---------------|------|
| 文件名（去掉 .md） | id | 若 metadata.memlink.original.id 存在则恢复 |
| — | source.format | `"openclaw"` |
| — | source.path | `memory/<filename>.md` |
| — | source.uri | `openclaw://memory/<filename>` |
| name | name | 直接复制 |
| description | summary | 直接复制 |
| body | body | 直接复制 |
| metadata.type | domains[0] | 最高优先级 |
| metadata.tags | tags | 直接复制 |
| metadata.importance | importance_score / importance_label | 数值→score，非数值→label |
| metadata.valence | valence | 直接复制，无则 None |
| metadata.arousal | arousal | 直接复制，无则 None |
| metadata.created_at | created_at | ISO→UTC |
| metadata.pinned | pinned | 无则 false |
| metadata.checksum | checksum | 直接复制 |
| metadata.memlink.original | — | 反向转换恢复原始字段 |

### Domain 推断（OpenClaw → Ombre）

不做 NLP。严格优先级：
1. `metadata.memlink.original.domains`
2. `metadata.domain` / `metadata.type`
3. 无匹配 → `--unknown-domain-action skip|default:<name>`（默认 skip）

### 术语映射

| 概念 | Ombre | Canonical | OpenClaw |
|------|-------|-----------|----------|
| 情感 | feel | emotion | feels/ |
| 归档 | — | status=archived | — |
| 永久 | permanent | kind=permanent | priority: high |
| 动态 | dynamic | kind=dynamic | MEMORY.md 索引 |

---

## Lossless Roundtrip：metadata.memlink

```yaml
metadata:
  memlink:
    source:
      format: ombre
      version: "1.0"              # 源格式版本
    schema_version: "1"
    converted_at: "2026-06-28T10:00:00Z"
    original:
      id: "bucket_id_here"
      kind: dynamic
      domains: [user, preferences, work]
      importance: 8
      created_tz: "2024-06-28T10:00:00+08:00"
```

反向转换时若 `metadata.memlink` 存在，优先恢复 `original` 中的字段。

### Extensions 命名空间约定

三方扩展推荐用格式名作 namespace，避免撞名：

```yaml
extensions:
  mem0:
    user_id: "abc"
  zep:
    session_id: "xyz"
```

---

## CLI 设计

```bash
pip install memlink

# 列出已安装格式
memlink formats

# 转换
memlink convert --from ombre --to openclaw   -s ~/.claude/ombre-buckets -t ./memories/
memlink convert --from openclaw --to ombre   -s ./memory/ -t ~/.claude/ombre-buckets/

# 快捷
memlink ombre2claw -s ~/.claude/ombre-buckets -t ./memories/
memlink claw2ombre -s ./memory/ -t ~/.claude/ombre-buckets/

# 导入（默认 --id-conflict=skip）
memlink import --from ombre -s ~/.claude/ombre-buckets
memlink import --from openclaw -s ./memory/

# 调试：单文件解析检查
memlink inspect sample.md                 # 自动检测格式
memlink inspect --format ombre sample.md  # 指定格式

# 选项
--source, -s          源目录
--target, -t          目标目录
--domain, -d          只转换特定 domain
--kind, -k            只转换特定 kind
--status              active|archived
--dry-run             只解析不写入
--overwrite           覆盖已存在文件
--id-conflict         rename|skip|merge（默认 rename）
--merge-strategy      append|replace|reject
--filename            id|name（默认 id）
--rebuild-index       完全重建 MEMORY.md 索引
--include-archived    包含已归档记忆
--unknown-domain-action  skip|default:<name>（默认 skip）
--verbose, -v

# 校验
memlink validate --level schema|semantic|roundtrip -s <path>
memlink validate --level schema --format json -s <path>

# 辅助
memlink stats -s ombre-buckets/ openclaw-memories/
memlink diff -s ombre-buckets/ openclaw-memories/
memlink diff -s ombre/ openclaw/ --format json
```

---

## inspect 命令输出

```
$ memlink inspect dynamic/user/sample.md

  Format:   Ombre
  Schema:   valid
  Source:   ombre://dynamic/user/7f32c91e

  ── Canonical ──
  id:        7f32c91e
  name:      "User Preferences"
  kind:      dynamic
  domains:   [user, preferences]
  tags:      [dark-mode, notifications]
  body:      234 chars

  ── Warnings ──
  (none)

  ── Extensions ──
  mem0.user_id: abc
```

---

## 实现路线图

| 阶段 | 内容 | 产出 |
|------|------|------|
| Phase 0.5 | spec/ + models.py + plugin.py + validators.py + serialization.py + 20 边界测试 | 规范 + 接口 + 验证器 |
| Phase 1 | 单向 Ombre → OpenClaw：reader + writer + converter + 能力检查 | 可用 MVP |
| Phase 2 | 反向转换 + metadata.memlink roundtrip + Feature Loss Report | roundtrip 测试 |
| Phase 3 | CLI 全子命令 + diff + exit code + inspect | 可发布 CLI |
| Phase 4 | PyPI + README + GitHub Actions (Linux/macOS/Windows, 3.10-3.12) | pip install |
| Phase 5 | 真实数据验证 + 文档 + Compatibility Matrix | 发版 |

### 测试覆盖率目标

| 模块 | 目标 |
|------|------|
| models.py | 100% |
| serialization.py | 100% |
| validators.py | 95%+ |
| *_reader.py | 90%+ |
| *_writer.py | 90%+ |
| converter.py | 90%+ |
| 项目整体 | ≥85% |

---

## 兼容性矩阵（Compatibility Matrix）

README 中展示：

| Format | Read | Write | Roundtrip | Lossless |
|--------|------|-------|-----------|----------|
| Ombre Brain | ✅ | ✅ | ✅ | ✅ |
| OpenClaw | ✅ | ✅ | ✅ | ⚠️ summary |
| Mem0 | 🚧 | 🚧 | — | — |
| Zep | 🚧 | 🚧 | — | — |

---

## 关键约束

- 全程 pathlib.Path
- 时间统一 UTC RFC 3339，原始时区保留到 metadata.memlink.original.created_tz
- `body` 可为 `None`
- `kind` 和 `Relationship.type` 为开放 `str`，规范推荐值但不限制
- Reader.read() 返回 `ReadResult`（memories + warnings + stats）
- Writer.write() 返回 `list[str]`（warnings）
- 文件名默认用 id
- `metadata` 是 Canonical 定义的扩展，`extensions` 推荐 namespace 防撞名
- metadata 值限定 JSON 兼容类型（`serialization.py` 含深度限制 + 循环检测）
- MEMORY.md 是 Writer 实现细节，Canonical 不关心索引
- MEMORY.md 写入前 SHA256 检测并发修改
- 不做 NLP domain 推断
- v0 支持 export/import，不支持 bidirectional sync
- Roundtrip 检查语义一致非字节一致，v0 豁免 relationships
- Plugin 声明 `version_supported` 语义化版本范围
- 错误码统一 `MLxxx` 格式

---

## 风险点

| 风险 | 概率 | 应对 |
|------|------|------|
| Ombre 中文 domain vs OpenClaw ASCII | 高 | 文件名支持中文 |
| YAML id 类型推断 | 中 | safe_load 后强制 str() |
| Win/Mac/Linux 路径分隔符 | 中 | 全程 pathlib |
| metadata 循环引用 | 中 | serialization.py 循环检测 |
| MEMORY.md 并发写入 | 中 | SHA256 检测（v0），filelock（v0.2） |
| 未来 kind 值爆炸 | 已解决 | 开放 str + 推荐值 + 未知回退 |
| importance 值域不统一 | 已解决 | score+label 保留原值 |
| roundtrip 元数据流失 | 已解决 | metadata.memlink + 时区保留 + format_version |
| ID 冲突 | 已解决 | --id-conflict rename\|skip\|merge |
| 文件名随 title 变 | 已解决 | 默认用 id |
| Domain 推断出错 | 已解决 | --unknown-domain-action skip\|default |
| Schema 演进不兼容 | 已解决 | schema_version + 兼容策略声明 |
| 能力不匹配静默丢弃 | 已解决 | Capabilities + Feature Loss Report |
| Extensions 字段撞名 | 已解决 | namespace 约定 |

---

## 实现决策（执行计划评审后确定）

以下决策来自 [IMPLEMENTATION.md](IMPLEMENTATION.md) v2，经两轮评审确认：

| 决策 | 选择 | 理由 |
|------|------|------|
| YAML 解析 | **PyYAML**（唯一运行时依赖） | 自研 parser 维护成本远超收益 |
| 并发检测 | **mtime+size** | O(1)，够用；SHA256 过重 |
| Reader 异常处理 | **Never Raise** | 解析失败→warning→skip→继续 |
| 字段值解析 | **Reader 存原始字符串，Converter 统一转类型** | 保证不同 Reader 行为一致 |
| 文件名非法字符 | **percent-encoding**（`/`→`%2F`） | 可逆，`a/b` 和 `a-b` 不会撞 |
| ID 冲突检测 | **casefold()** | Windows 大小写不敏感 |
| 输出排序 | **确定性排序**（tags/domains sorted()、MEMORY.md 按 id） | Git Diff 干净 |
| 测试策略 | **Golden Tests**（fixture + expected.json） | 任何修改后立即发现差异 |
| Fuzz 测试 | **hypothesis**（dev 依赖，100 随机 case） | 边缘情况自动发现 |
| Verbose | **三级**（-v/-vv/-vvv） | 调试 Reader 神器 |
| Feature Loss Report | **含 Reason 字段** | Debug 明确知道为什么丢 |
