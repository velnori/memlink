# memlink 执行计划 v2

## 总体策略

- **测试先行**：每个模块先写 fixtures 和测试，再写实现
- **单一运行时依赖**：PyYAML（处理 frontmatter），其余全部标准库
- **Never Raise**：Reader 解析失败 → warning → skip → 继续，不崩溃
- **增量交付**：每个 Phase 产出一个可验证的结果

---

## 关键决策（评审后确定）

### YAML 解析：用 PyYAML，不自己写

两个评审都反对自研 YAML parser。实际 frontmatter 会遇到的边缘情况（`|`/`>` 多行字符串、引号内冒号、`#` 注释、`~` null、缩进列表变体、嵌套对象）远超 40 行能覆盖的范围。

**采纳方案**：`pyyaml>=6.0` 作为唯一运行时依赖。`pip install memlink` 自动安装。PyYAML 是 Python 生态最普遍的依赖之一（pytest、docker-compose、AWS CLI 都依赖它），不会有额外负担。

### 并发检测：mtime+size，不用 SHA256

SHA256 对 MEMORY.md 来说过重。`os.stat()` 的 `st_mtime` + `st_size` 组合足够检测并发修改，且 O(1) 不随文件大小增长。

### Reader 职责收窄

Reader 只负责读原始字符串、存入 Canonical。**不解析 datetime、不做归一化、不猜字段**。Converter 统一做类型转换。这样不同 Reader 的行为一致，Canonical 不会因为 Reader 实现差异而不一致。

---

## Phase 0.5 — 核心数据层 + 验证器 + 测试底板

**目标**：数据模型、接口、验证器就绪。20+ 边界测试通过。

**当前状态**：
- [x] `models.py` — Memory, Source, Relationship, JSONValue
- [x] `plugin.py` — FormatPlugin, Capabilities, ReadResult, ValidationIssue
- [x] `serialization.py` — sanitize()
- [x] `converter.py` — check_compatibility(), convert()

### 0.5.0 真实格式验证（Day 1 先做）

**不要基于假设开发**。先拿真实 Ombre 和 OpenClaw 文件确认：

```
需要确认的 Ombre 格式问题：
  - content 在 frontmatter 里（多行字符串）还是在 frontmatter 外面的 body？
  - domain 是逗号分隔字符串 "user, preferences" 还是 YAML list [user, preferences]？
  - tags 同理
  - type 的实际值：dynamic / permanent / feel？有没有别的？
  - created 的时间格式：ISO 8601？带时区？

需要确认的 OpenClaw 格式问题：
  - MEMORY.md 索引行格式：纯列表 / 带描述 / 分组？
  - metadata 字段的实际命名：metadata.type / metadata.domain / metadata.tags？
  - description 是否总是存在？
  - feels/ 目录是否单独索引？
```

验证完成后更新 DESIGN.md 的字段映射表（如有差异）。

### 0.5.1 validators.py + 错误码表

```
错误码分层：
  Schema 错误 (ML001-ML099)
    ML001 InvalidDatetime
    ML002 MissingID
    ML003 DuplicateID
    ML004 InvalidSchema
    ML005 MissingRequiredField
    ML010 InvalidSourceURI

  Semantic 错误 (ML100-ML199)
    ML100 BodyEmpty          (warning，不强制)
    ML101 ValueOutOfRange    (valence/arousal)
    ML102 UnsupportedKind
    ML103 UnknownDomain

  I/O 错误 (ML200-ML299)
    ML200 FileNotFound
    ML201 PermissionDenied
    ML202 CorruptFile

  转换错误 (ML300-ML399)
    ML300 ConcurrentModification
    ML301 FormatIncompatible
    ML302 IDConflict

  Roundtrip 错误 (ML400-ML499)
    ML400 RoundtripIDMismatch
    ML401 RoundtripContentMismatch
```

```python
# validators.py
class ErrorCode(str, Enum):
    INVALID_DATETIME = "ML001"
    MISSING_ID = "ML002"
    DUPLICATE_ID = "ML003"
    # ... 完整定义

@dataclass
class ValidationIssue:
    code: ErrorCode
    severity: Severity          # error / warning / info
    path: str | None            # 文件路径
    memory_id: str | None       # 记忆 ID
    field: str | None           # 问题字段
    message: str
    suggestion: str | None = None
```

### 0.5.2 ID 合法化（percent-encoding 方案）

不用 `-` 替换非法字符——`a/b` 和 `a-b` 会撞。用 percent-encoding，可逆：

```python
# models.py

import re
from pathlib import Path

FILENAME_RESERVED_CHARS = r'[<>:"/\\|?*\x00-\x1f]'

def sanitize_id(raw: str) -> str:
    """将任意字符串转为合法文件名。

    规则：
    1. 非法字符 → percent-encode（%2F、%3A 等），可逆恢复
    2. Unicode（中文/emoji）保留
    3. 长度 ≤ 255 字节（UTF-8）
    4. Windows 保留名（CON/PRN/AUX...）前加 _
    5. 空值回退为 "unnamed"
    """
    def replace_char(m: re.Match) -> str:
        return f"%{ord(m.group(0)):02X}"

    sanitized = re.sub(FILENAME_RESERVED_CHARS, replace_char, raw)
    sanitized = sanitized.strip('. ')

    reserved = {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    if sanitized.upper() in reserved:
        sanitized = f'_{sanitized}'

    while len(sanitized.encode('utf-8')) > 255:
        sanitized = sanitized[:-1]

    return sanitized or "unnamed"
```

### 0.5.3 Golden Tests

每个 fixture 配套一个 `expected.json`，存 Canonical 的标准输出：

```
tests/fixtures/ombre_samples/
  dynamic/user/sample.md
  dynamic/user/sample.expected.json   ← Golden: Reader 输出必须匹配

tests/fixtures/openclaw_samples/
  memory/test-memory.md
  memory/test-memory.expected.json
```

测试：
```python
def test_golden_ombre():
    reader = OmbreReader()
    result = reader.read(FIXTURES / "ombre_samples")
    actual = [asdict(m) for m in result.memories]
    expected = json.loads(FIXTURES / "ombre_samples/dynamic/user/sample.expected.json")
    assert actual == expected
```

以后任何修改 → Golden Test 告警，Roundtrip 非常稳定。

### 0.5.4 测试清单

```
test_models.py           # 构造 Memory、序列化、ID sanitize、casefold 碰撞检测
test_serialization.py    # sanitize: 循环引用、深度、datetime→ISO、set→sorted
test_validators.py       # 用 fixtures 测三级校验 + 错误码
test_plugin.py           # Capabilities 默认值、ReadResult stats
```

### Phase 0.5 完成标准

```
$ pytest tests/ -v
  test_models.py ............ ~30 passed
  test_serialization.py ..... ~15 passed
  test_validators.py ........ ~10 passed
  test_plugin.py ............  ~5 passed
```

---

## Phase 1 — 单向转换 Ombre → OpenClaw

### 1.1 ombre_reader.py

核心原则：**Never Raise**。解析失败 → warning → skip → 继续。

```
OmbreReader.read(path: Path) → ReadResult

流程：
  1. path.rglob("*.md")
  2. 每个文件 → yaml.safe_load(frontmatter_text)
  3. 字段映射（保留原始字符串，不做类型转换）：

     frontmatter["bucket_id"]  → id（str() 强制）
     frontmatter["name"]       → name
     frontmatter 外的 body     → body
     frontmatter["content"]    → body（若 body 在 frontmatter 内）
     frontmatter["type"]       → kind 映射
     frontmatter["domain"]     → domains（字符串拆 list 或直接取 list）
     frontmatter["tags"]       → tags
     frontmatter["importance"] → importance_score（原始 int）
     frontmatter["valence"]    → valence
     frontmatter["arousal"]    → arousal
     frontmatter["created"]    → 原始字符串 → metadata.memlink.original.created_raw
     frontmatter["pinned"]     → pinned

  4. Converter 统一将 created_raw → created_at（datetime）
  5. 构造 Source、checksum
  6. 保存 metadata.memlink.original 完整快照

  7. stats = {"parsed": N, "skipped": N, "invalid": N}
     解析失败的 → stats["skipped"]++、warnings++，不中断
```

### 1.2 openclaw_writer.py

关键改动：MEMORY.md 并发检测用 mtime+size，SHA256 替换。

```
OpenClawWriter.write(memories, path: Path) → list[str]

路由（同前）：
  kind=emotion → memory/feels/<id>.md
  status=archived → 跳过
  其他 → memory/<id>.md

MEMORY.md 索引更新：
  1. 读取 MEMORY.md → stat(): st_mtime + st_size
  2. 解析现有条目
  3. 合并新条目（按 id 去重）
  4. 重新 stat() → 比较 st_mtime+st_size
  5. 不一致 → ML300 ConcurrentModification
  6. 所有条目按 id 排序 → 写入
```

### 1.3 测试

```
test_ombre_reader.py    # Golden Tests + 正常/边界用例
test_openclaw_writer.py # 路由 + MEMORY.md 增量 + 并发检测
test_converter.py       # 端到端 + Feature Loss Report（含 Reason 字段）
```

---

## Phase 2 — 反向转换 + Roundtrip

**目标**：OpenClaw → Ombre 完整可用。Roundtrip 测试通过。

### 2.0 需要讨论确认的关键问题

**问题 A：OpenClaw 的 description → Ombre 存哪里？**

OpenClaw 有 `description`（摘要），Ombre 没有对应字段。三个方案：

| 方案 | 做法 | 影响 |
|------|------|------|
| A | 丢弃 | 反向转换丢失 description |
| B | 存到 metadata.memlink.original | roundtrip 可恢复，但 Ombre 里看不到 |
| C | 拼入 body 前面 | Ombre 能看到，但会改变原文内容 |

**建议**：方案 B——存 metadata.memlink.original，不污染 body。roundtrip 回来会恢复。

---

**问题 B：Ombre 的 bucket_id 用什么？**

Phase 1 已将 `bucket_id` → Canonical `id` → OpenClaw 文件名。反向时：

| 情况 | bucket_id 来源 |
|------|---------------|
| metadata.memlink.original 存在 | 恢复 original.bucket_id |
| 无 memlink（纯 OpenClaw 数据） | 用文件名（去掉 .md）当 bucket_id |

文件名用 percent-encoding 存了 `/` 等特殊字符，反向需 decode 恢复。

---

**问题 C：domain 推断，Ombre 需要主 domain**

Ombre 的 `domain` 是一个字符串（如 `"user, preferences"`）。Canonical 的 `domains` 是 list。

反向映射规则：
1. metadata.memlink.original.domains 存在 → 恢复原始分隔字符串
2. Canonical.domains 有值 → 取 `domains[0]` 作 Ombre domain
3. 都无 → `--unknown-domain-action` 控制行为

---

**问题 D：type 映射回来怎么处理**

Ombre `type` 值域是 `dynamic/permanent/feel`。Canonical `kind` 是开放 string。

反向映射：
| Canonical kind | Ombre type |
|---------------|-----------|
| dynamic | dynamic |
| permanent | permanent |
| emotion | feel |
| 其他值 | 回退 dynamic + warning |

---

**问题 E：importance 反向怎么存**

Phase 1 将 Ombre `importance: 8`（int）存到 Canonical `importance_score: 8.0`（float）。反向写回 Ombre 时：

- importance_label 为 "high"/"critical" 等 → 写 importance_label
- importance_score 为 float → `int(score)` 写回
- 都无 → 默认 5

---

### 2.1 openclaw_reader.py（~80行）

Reader 不写成一个 `read()` 大函数，拆成 6 步 Pipeline：

```
discover_files() → parse_frontmatter() → map_to_canonical() → recover_original() → validate() → collect_warnings() → ReadResult
```

#### 2.1.1 文件发现（容错优先）

```
策略：
  1. MEMORY.md 存在且解析成功 → 按索引行读取
  2. MEMORY.md 损坏或不存在 → warning + fallback 递归扫描 memory/**/*.md
  3. 两种情况都要覆盖 memory/feels/ 目录

MEMORY.md 支持多种格式变体：
  # 变体 A：纯列表
  - memory/test.md

  # 变体 B：带描述
  - memory/test.md - Project kickoff meeting

  # 变体 C：分组
  ## Work
  - memory/project-alpha.md
  ## Personal
  - memory/birthday.md

解析规则：
  - 以 "- memory/" 开头的行 → 条目
  - " - " 分隔路径和描述
  - 跳过 # 标题行、空行、非列表行
  - 分组信息保留但 v0 不导出
```

#### 2.1.2 字段映射（Never Raise）

```
每个 .md 文件：

解析 YAML frontmatter（PyYAML）

字段映射：
  name                                    → name（必需——缺失→skip+warn）
  description                             → summary
  body（frontmatter 外的文本）             → body
  metadata.type                           → domains[0]
  metadata.domain                         → domains[0]（type 优先）
  metadata.tags                           → tags
  metadata.importance                     → 数值→importance_score，非数值→importance_label
  metadata.valence                        → valence
  metadata.arousal                        → arousal
  metadata.created_at                     → created_at（ISO 字符串→UTC datetime，非法→None+warn）
  metadata.pinned                         → pinned
  metadata.checksum                       → checksum
  metadata.source_uri                     → source.uri

文件名（去 .md、decode percent-encoding）  → id（优先 metadata.memlink.original.id）
"feels" 在路径中                           → kind="emotion"（其次 metadata.memlink.original.kind）
metadata.priority == "high"               → kind="permanent"
都无                                      → kind="dynamic"
```

#### 2.1.3 Original Recovery（白名单）

```
若 metadata.memlink.original 存在，恢复以下字段：
  ✅ 恢复：id, kind, domains, importance, created_tz
  ❌ 不恢复：body, summary（用户可能在 OpenClaw 中手动编辑了这些）
  
原因：避免把用户后来修改的内容覆盖掉。
```

#### 2.1.4 测试（~20 tests）

```
test_openclaw_reader.py

  test_read_basic                     # 正常 dynamic 文件
  test_read_with_description          # description → summary
  test_read_emotion_kind              # feels/ 目录 → kind=emotion
  test_read_importance_label          # "high" → importance_label
  test_domain_from_metadata_type      # metadata.type → domains[0]
  test_missing_name_field             # 缺 name → skip+warn
  test_unindexed_files_warning        # 不在 MEMORY.md 中 → warning
  test_restore_from_memlink_metadata  # original 字段恢复
  test_unknown_domain_fallback        # 无 domain → ["_unknown"]
  test_validate_missing_memory_dir    # 缺 memory/ 目录 → error
  test_validate_missing_memory_md     # 缺 MEMORY.md → warning
  test_chinese_and_emoji              # 中文+emoji 正确处理
  test_empty_body                     # 空 body → None
  test_malformed_yaml                 # 损坏 YAML → skip+invalid
  test_memory_index_grouped_format    # 分组 MEMORY.md 正确解析
  test_priority_high_to_permanent     # priority:high → kind=permanent
  test_extensions_preserved           # extensions 原样保留
```

### 2.2 ombre_writer.py（~80行）

#### 2.2.1 目录策略

```
一步确定目标路径：
  kind=dynamic    → path/dynamic/
  kind=permanent  → path/permanent/
  kind=emotion    → path/feel/
  未知 kind       → warning + path/dynamic/

Domain 规则：
  domains=[] 或 domains=["_unknown"] → "general" + warning
  domains 多值                        → 取 domains[0] 作目录名 + warning（其余 domain 保留在字段值中）
  正常单值                            → domains[0] 作目录名
```

#### 2.2.2 字段映射（固定顺序、YAML 直接拼接）

不使用 `yaml.dump()`，手动拼接 YAML 行以保证字段顺序和 Ombre 风格（逗号分隔 tags、无引号纯字符串等）。

```
固定字段顺序：
  bucket_id → name → type → domain → tags → importance → valence → arousal → created → pinned

映射规则：
  id（优先 metadata.memlink.original.id）  → bucket_id
  name                                     → name
  body                                     → body（Ombre body 在 frontmatter 外）
  kind                                     → type：emotion→feel，未知→dynamic+warn
  tags                                     → tags（逗号分隔字符串，Ombre 风格）
  domains[0]                               → domain（字符串）
  importance                               → 优先级：
                                              1. original.importance 有 → 恢复原始值
                                              2. importance_score 有 → int(score)，钳位 1-10
                                              3. importance_label 有 → 查表：critical=10, high=8, medium=5, low=3, minimal=1
                                              4. 都无 → 默认 5
  valence                                  → valence（有则写）
  arousal                                  → arousal（有则写）
  created_at                               → 若有 original.created_tz → 恢复原始时区字符串
                                             若无 → created_at.isoformat()
  pinned                                   → pinned（仅 True 时写入）

特值处理：
  name 含 ":" / "#" → 加双引号
  空 body → 写空行（frontmatter 后 "\n\n"）
  archived status → warning（Ombre 无此概念）
```

#### 2.2.3 测试（~20 tests）

```
test_ombre_writer.py

  test_write_basic                    # 基本写入，检查字段存在
  test_write_emotion_to_feel          # emotion → feel/ 目录 + type=feel
  test_write_permanent_kind           # permanent → permanent/ 目录
  test_restore_original_id            # metadata.memlink.original.id → bucket_id
  test_restore_original_importance    # 恢复原始 importance 值（不是归一化的）
  test_importance_label_to_score      # "high" → 8
  test_unknown_domain_fallback        # _unknown → "general" + warning
  test_unknown_kind_fallback          # 未知 kind → dynamic + warning
  test_archived_status_warning        # archived → warning
  test_restore_original_timezone      # 原始时区恢复
  test_multi_domain_list              # 多 domain：第一个作目录，全部写字段值
  test_tags_comma_separated           # tags → 逗号分隔
  test_pinned_field                   # pinned=true
  test_sanitize_illegal_id            # ID 非法字符 → sanitize_id
  test_chinese_domain_and_id          # 中文 domain+ID
  test_empty_body                     # 空 body
  test_yaml_special_chars_quoted      # 含冒号的 name → 加引号
  test_batch_write                    # 批量 10 个
  test_frontmatter_field_order        # 字段顺序固定
```

### 2.3 Roundtrip 验证

#### 2.3.1 Canonical Comparator

不用 `assert a == b`。写一个专门的比较函数，返回结构化 Difference：

```python
def compare_memory(a: Memory, b: Memory) -> list[Difference]:
    """
    比较两个 Memory，返回字段级差异列表。
    - tags/domains 排序后比较
    - None == None
    - 时间转 ISO 字符串比较
    - v0 豁免：relationships
    """
    ...

@dataclass
class Difference:
    field: str          # 差异字段
    expected: Any       # 期望值
    actual: Any         # 实际值
    severity: str       # "error" | "warning" | "info"
```

以后 Diff、Validate、Roundtrip 全部复用这个 Comparator。

#### 2.3.2 两个方向的 Roundtrip

```
方向 A：Ombre → OpenClaw → Ombre
  检查：
    ✓ id/bucket_id 恢复一致
    ✓ name 恢复一致
    ✓ kind/type 映射往返：dynamic↔dynamic, permanent↔permanent, emotion↔feel↔emotion
    ✓ importance 原值恢复：8 → 8（不是 0.8）
    ✓ domain 恢复（字符串 → list → 字符串）
    ✓ tags 恢复（排序后比较）
    ✓ created_at 时区保留（"2024-01-01T18:00:00+08:00" → UTC → 恢复 "+08:00"）
    ✓ body 内容一致
    ✓ pinned 恢复
    ✓ v0 豁免：relationships、description

方向 B：OpenClaw → Ombre → OpenClaw
  同上 + description 从 metadata.memlink.original 恢复一致

退出标准（工程化指标，不是 test count）：
  Fixture roundtrip success rate:      100%
  Real Ombre dataset roundtrip rate:   >95%
  Real OpenClaw dataset roundtrip rate: >95%
```

#### 2.3.3 测试（~15 tests）

```
test_roundtrip.py

  test_ombre_to_openclaw_to_ombre              # A 方向完整流程
  test_openclaw_to_ombre_to_openclaw           # B 方向完整流程
  test_roundtrip_preserves_id                  # ID 精确恢复
  test_roundtrip_preserves_importance_score    # importance 8 → 8，不是 0.8
  test_roundtrip_preserves_timezone            # 时区 "+08:00" 恢复
  test_roundtrip_preserves_multi_domains       # 多 domain 完整保留
  test_roundtrip_chinese_and_emoji             # 中文 + 🚀😊
  test_roundtrip_empty_body                    # 空 body
  test_roundtrip_all_emotion_fields            # emotion feel/ 目录完整恢复
  test_roundtrip_pinned_field                  # pinned 保留
  test_roundtrip_batch                         # 批量 3+ 条
```

### 2.4 Domain 推断测试（~8 tests）

```
test_domain_inference.py

  test_infer_from_metadata_domain      # metadata.domain 存在 → 直接取
  test_infer_from_metadata_type         # metadata.type → 取 type
  test_infer_fallback_unknown           # 都无 → ["_unknown"]
  test_restore_from_memlink_original    # 有 original → 完整恢复
  test_cli_unknown_domain_action_skip   # CLI --unknown-domain-action skip
  test_cli_unknown_domain_action_default # CLI --unknown-domain-action default:general
```

### 2.5 Phase 2 完成标准

```bash
$ pytest tests/test_openclaw_reader.py -v    # 20 passed
$ pytest tests/test_ombre_writer.py -v       # 20 passed
$ pytest tests/test_roundtrip.py -v          # 15 passed
$ pytest tests/test_domain_inference.py -v   # 8 passed

# Roundtrip 量化验证
$ python -m memlink.integration_test
  Roundtrip: 117/117 (100%)
  Loss: summary=2, relationships=8
  Time: 0.33s
```

---

---

## Phase 3 — CLI 全实现 + 模糊测试 + 边缘用例

**目标**：`memlink` 命令完整可用，help 文档清晰，exit code 正确，JSON 输出模式。

### 3.0 需要讨论确认的设计决策

**问题 F：convert vs ombre2claw 到底要不要快捷命令？**

Phase 1 的 CLI 设计有两个版本：

```bash
# 通用版：格式名通过 --from/--to 指定
memlink convert --from ombre --to openclaw -s ... -t ...

# 快捷版：固定命令名
memlink ombre2claw -s ... -t ...
```

| 方案 | 优点 | 缺点 |
|------|------|------|
| 两种都要 | 通用版可扩展，快捷版好记 | CLI 更复杂 |
| 只要 convert | 简单统一 | 命令长 |
| convert + 自动检测格式 | 最友好 | 检测可能出错 |

**建议**：v0 两种都要。`convert` 是通用接口（文档推荐），`ombre2claw`/`claw2ombre` 是快捷别名（内部调 convert）。以后第三方格式只有 `convert`。

---

**问题 G：--format json 输出哪些命令需要？**

| 命令 | pretty | json | 理由 |
|------|--------|------|------|
| validate | ✅ | ✅ | CI 消费用 json |
| diff | ✅ | ✅ | CI gate 用 json |
| stats | ✅ | ✅ | 自动化统计 |
| inspect | ✅ | ❌ | 调试命令，人看 |
| convert | ✅ | ❌ | 转换过程人看 |

**建议**：validate/diff/stats 三种支持 --format json。inspect/convert 只 pretty。

---

**问题 H：inspect 命令输出什么内容？**

单文件调试神器。输入一个 .md 文件，memlink 自动检测格式（或手动指定），输出 Canonical 表示 + warnings + extensions。

```
$ memlink inspect dynamic/user/sample.md

  Format:   Ombre
  Schema:   valid
  Source:   ombre://dynamic/user/abcd1234-user-prefs

  ── Canonical ──
  id:              abcd1234-user-prefs
  name:            用户偏好设置
  kind:            dynamic
  status:          active
  domains:         [user, preferences]
  tags:            [dark-mode, notifications, 中文标签]
  importance:      7.0
  valence:         0.8
  body:            145 chars
  checksum:        sha256:e65bfe66...

  ── Warnings ──
  (none)

  ── Extensions ──
  (none)
```

---

**问题 I：--verbose 三级各打什么？**

| 级别 | 输出内容 |
|------|---------|
| 默认 | 只输出 summary（converted N、warnings count、feature loss） |
| -v | 每条 warning 详情 + 跳过/失败文件名 |
| -vv | 每个文件转换过程（"parsing a.md → kind=dynamic ✓"） |
| -vvv | 每个字段映射明细（"bucket_id→id: abcd1234"） |

---

### 3.1 CLI 架构

**拆分子包，不塞一个 200 行文件：**

```
memlink/
  cli/
    __init__.py     # main() + parser + dispatch
    convert.py      # convert / ombre2claw / claw2ombre
    validate.py     # validate
    diff.py         # diff
    inspect.py      # inspect
    stats.py        # stats
    formats.py      # formats
```

### 3.2 CLI 子命令实现详情

#### `memlink formats`

```
→ importlib.metadata.entry_points() 动态发现已安装插件
→ 表格输出：

  Format      Reader    Writer
  ombre       ✅        ✅
  openclaw    ✅        ✅
```

#### `memlink convert`

```
memlink convert --from <FMT> --to <FMT> -s <PATH> -t <PATH> [options]

流程：
  1. 解析 --from / --to → entry_points 查找对应 Reader/Writer 类
  2. 实例化 reader、writer
  3. 调用 convert(reader, writer, source_path, target_path, **filters)
  4. 输出结果摘要 + Feature Loss Report + 耗时

参数：
  --from, -f         源格式名（必填）
  --to, -t           目标格式名（必填）
  -s, --source       源目录（必填）
  -t, --target       目标目录（必填）
  --domain, -d       只转换特定 domain
  --kind, -k         只转换特定 kind
  --status           active|archived（默认 active）
  --dry-run          只解析，显示会转换的列表，不写入
  --overwrite        覆盖已存在的目标文件（默认不覆盖）
  --id-conflict      rename|skip|merge（默认 rename）
  --merge-strategy   append|replace|reject
  --filename         id|name（默认 id）
  --rebuild-index    完全重建 MEMORY.md 索引
  --include-archived 转换时包含已归档记忆
  --unknown-domain-action  skip|default:<name>（默认 skip）
  -v, -vv, -vvv      详细程度

输出示例（默认）：
  Converted: 117 memories (87 dynamic, 8 permanent, 17 emotion, 5 skipped)
  Warnings: 2
  Target: /path/to/output/
  Time: 0.23s

  ── Feature Loss ──
  emotion (valence/arousal): 117 dropped  (Target plugin capability=false)
  extensions: 1 dropped  (Target cannot preserve unknown extensions)
```

#### `memlink ombre2claw` / `memlink claw2ombre`

快捷命令——内部转调 `convert`：

```python
def ombre2claw(args):
    args.from_format = "ombre"
    args.to_format = "openclaw"
    return convert_command(args)
```

#### `memlink import`

```
memlink import --from <FMT> -s <PATH>

同 convert，但：
  - 目标格式自动检测当前目录
  - --id-conflict 默认 skip（不覆盖已有记忆）
  - 用于"把外部记忆导入当前系统"的语义
```

#### `memlink inspect`

```
memlink inspect <FILE> [--format ombre|openclaw]

单文件调试：
  1. 自动检测格式（或手动指定）
  2. 调用对应 Reader 的单文件读取
  3. 输出 Canonical 表示 + source + warnings + extensions
```

#### `memlink validate`

```
memlink validate --level schema|semantic|roundtrip -s <PATH> [--format json]

--level schema:   YAML 语法 + 必需字段
--level semantic: 字段类型、值范围、重复 id
--level roundtrip: A→B→A 一致性（Phase 2 后）

--format pretty (默认):
  ✓ 120 files valid
  ✗ 3 errors:
    ML002: Missing ID — broken/no-id.md
    ML002: Missing ID — broken/invalid-yaml.md
    ML004: Invalid YAML — broken/invalid-yaml.md

--format json:
  {
    "total": 120,
    "errors": [...],
    "warnings": [...]
  }
```

#### `memlink stats`

```
memlink stats -s <PATH>

统计：
  Total:     120 memories
  ├─ dynamic:     85 (70.8%) ████████████████████████
  ├─ permanent:   30 (25.0%) ████████
  └─ emotion:      5 ( 4.2%) █

  Domain Distribution:
    user:          45 ████████████████████
    work:          30 █████████████
    project:       25 ███████████
    personal:      20 █████████
```

#### `memlink diff`

```
memlink diff -s <PATH1> <PATH2> [--format json]

比较两个目录的 Canonical 表示：
  1. 两侧各读一遍
  2. 按 id 匹配
  3. 输出差异摘要 + 详情

--format pretty:
  Only in source:      12
  Only in target:       5
  Common:              83
    Content differs:    7
    Metadata differs:  15

  [Content Diff] project-alpha
    importance_score: 8 → 6 (-2)
    tags: +['urgent'] -['low-priority']

Exit code: 0=一致, 1=有差异, 2=错误
```

### 3.3 Convert 命令详细流程

```
convert 执行流程（每一步打日志）：
  1. 解析 --from / --to → Plugin 发现（首次 entry_points() 后缓存为 dict）
  2. Capability Check → 如有不兼容，提前 warning
  3. Reader → 读源目录
  4. Filter → --domain / --kind / --status 过滤
  5. Dry-run? → 是则打印列表退出
  6. Converter → 统一类型转换（datetime 等）
  7. Writer → 写目标目录
  8. Feature Loss Report → 统计丢失字段
  9. Summary → 固定格式输出
  10. Exit Code → 0 成功

固定输出格式（Summary）：
  Read:     120
  Converted: 118
  Skipped:     2
  Warnings:    4
  Duration:  0.38s

  ── Feature Loss ──
  emotion:       0 lost  (Preserved in metadata.memlink)
  summary:       2 lost  (Ombre has no summary slot)
  relationships: 8 lost  (v0 writer skip)
```

### 3.4 inspect 命令详细输出

```
不只是 Canonical。输出 5 个区域：

  ── Raw Frontmatter ──
  bucket_id: abcd1234
  name: 用户偏好设置
  type: dynamic
  ...

  ── Canonical ──
  id:              abcd1234
  name:            用户偏好设置
  kind:            dynamic
  status:          active
  ...

  ── Warnings ──
  (none)

  ── Extensions ──
  mem0.user_id: abc

  ── Capabilities ──
  Reader supports: emotion, summary
  Writer supports: summary
```

### 3.5 diff 命令增加 --ignore

```
memlink diff -s old/ new/
  比较 Canonical 表示，不是比较原始 Markdown

memlink diff -s old/ new/ --ignore timestamps
  忽略 created_at / updated_at 差异

memlink diff -s old/ new/ --ignore tags
  忽略 tags 差异

memlink diff -s old/ new/ --ignore importance
  忽略 importance_score / importance_label 差异

用途：用户只想看"实质内容"变了没，不关心时间戳/标签调整
```

### 3.6 stats 命令扩展

```
memlink stats -s memories/

  Total:           120 memories
  ├─ dynamic:       85 (70.8%)
  ├─ permanent:     30 (25.0%)
  └─ emotion:        5 ( 4.2%)

  Domains:          12 unique
  Average tags:      3.2 per memory
  Average body:     245 chars
  Oldest memory:    2024-01-15 (permanent/docs/manual)
  Newest memory:    2024-07-15 (feel/sample)

  Domain Distribution:
    user:            45 ████████████████████
    work:            30 █████████████
    project:         25 ███████████
    personal:        20 █████████
```

### 3.7 Ctrl+C 清理

```
捕获 KeyboardInterrupt →
  1. 记录"正在清理..."
  2. 检查目标目录中已写入的文件
  3. 报告："Partially written: 2 files in /target/memory/"
  4. 不移除已写入文件（用户决定是否清理）
  5. exit 130
```

### 3.8 统一 Exit Code（所有命令）

```
0   Success                     # 一切正常
1   Validation/Diff Failed       # validate 有 error，或 diff 有差异
2   CLI Usage Error              # 参数错误、缺必填项
3   Plugin Error                 # 格式不支持、插件加载失败
4   I/O Error                    # 文件找不到、权限不够
5   Unexpected Exception         # 未预期错误
130 User Interrupted             # Ctrl+C
```

### 3.9 Plugin 发现缓存

```
首次 entry_points() 扫描 → 缓存为 dict {"ombre": (Reader, Writer), ...}
后续命令复用缓存，不重复扫描

def get_reader(fmt: str) -> type[FormatPlugin]:
    _ensure_plugins_loaded()
    if fmt not in _reader_cache:
        raise PluginError(f"Unknown format: {fmt}")
    return _reader_cache[fmt]()
```

### 3.4 Fuzz Testing

dev 依赖加 `hypothesis`，生成随机 Memory 确保 reader/writer 不崩。

```python
# tests/test_fuzz.py
from hypothesis import given, strategies as st

@given(
    body=st.text(max_size=10000),
    tags=st.lists(st.text(min_size=1, max_size=50), max_size=20),
    domains=st.lists(st.text(min_size=1, max_size=30), max_size=10),
    kind=st.sampled_from(["dynamic", "permanent", "emotion", "unknown-kind"]),
    importance=st.one_of(st.none(), st.floats(min_value=0, max_value=100)),
    has_emoji=st.booleans(),
)
def test_roundtrip_fuzz(body, tags, domains, kind, importance, has_emoji):
    """随机构造 Memory → write → read → 语义一致"""
    ...

# 100 random cases, ~5s
```

---

## Phase 2.5 — 集成测试 + 兼容性报告

**目标**：在写 CLI 之前，先用真实数据跑完整 A→B→A 流程，生成量化报告。这是发布前最有价值的一步。

### 2.5.1 集成测试

```
用 117 条真实 Ombre 数据：

  1. Ombre → Canonical → OpenClaw
  2. OpenClaw → Canonical → Ombre
  3. 逐条 compare_memory(original, restored)
  4. 生成报告

用真实的 OpenClaw 数据（如果能拿到）：
  1. OpenClaw → Canonical → Ombre
  2. Ombre → Canonical → OpenClaw
  3. 同上比较
```

### 2.5.2 Compatibility Report 格式

```
$ python -m memlink.integration_test

  ═══ Roundtrip Compatibility Report ═══
  Dataset: 117 real Ombre memories (87 dynamic, 8 permanent, 17 emotion, 5 archived)

  ── Roundtrip Success ──
  Full match:      114/117 (97.4%)
  Partial match:     3/117 (2.6%)  — description restored from metadata
  Failed:            0/117 (0%)

  ── Field-Level Loss ──
  summary:       2 lost  (Ombre has no summary slot — preserved in metadata)
  emotion:       0 lost  (full roundtrip preserved)
  relationships: 8 lost  (v0 writer skip — stored in metadata.memlink.relationships)

  ── Performance ──
  Ombre→Canonical:      0.12s
  Canonical→OpenClaw:   0.08s
  OpenClaw→Canonical:   0.06s
  Canonical→Ombre:      0.07s
  Total roundtrip:      0.33s

  ═══ Verdict: READY for Phase 3 ═══
```

### 2.5.3 Plugin Contract Tests

提供公共测试模块 `memlink.testing`，任何新插件必须通过：

```python
# memlink/testing.py — 插件契约测试

def test_plugin_contract(reader_cls, writer_cls):
    """
    任何新格式插件必须通过以下测试：
    1. 能读取最小合法样例
    2. 能处理未知字段而不中断
    3. 对非法输入返回结构化 warning，不抛异常
    4. Canonical 一次往返语义一致（在声明的 Capabilities 范围内）
    """
    # ... 标准测试套件
```

后续 Mem0、Zep、OpenMemory 等插件接入时，只需调用 `test_plugin_contract(Mem0Reader, Mem0Writer)`。

---

### 3.10 测试

```
test_cli.py            # 每个子命令端到端 + exit code 验证
test_fuzz.py           # hypothesis 100 random cases
test_merge_strategy.py # append/replace/reject 完整测试
test_edge_cases.py     # 空目录、全空 body、纯中文、emoji、超长 body、100+ 文件
```

### 3.11 Phase 3 完成标准

```bash
$ memlink --help
  (完整帮助信息，每个子命令有独立 help)

$ memlink formats
  ombre      reader+writer
  openclaw   reader+writer

$ memlink convert --from ombre --to openclaw \
    -s ~/.claude/ombre-buckets -t ./memories/
  Converted: 117 memories
  ...

$ memlink diff -s old/ new/ --format json
  {"only_in_source": 3, "only_in_target": 1, ...}
  (exit code 1)

$ memlink validate --level sematic -s memories/ --format json
  {"errors": [...]}
  (exit code 0 if clean)
```

---

## Phase 4 — 发布

- [ ] Golden Tests 全部通过
- [ ] CI 绿灯（Linux + macOS + Windows, 3.10/3.11/3.12）
- [ ] 真实 Ombre + OpenClaw 数据测试通过
- [ ] 兼容性承诺文档（Compatibility Promise）：

```
Canonical Schema v1    Stable（冻结，1.x 向后兼容）
Plugin API             Experimental（v0.x 可能变）
CLI                    Experimental（v0.x 可能变）
Python API             Experimental（v0.x 可能变）
```

- [ ] README 补充 "What memlink is NOT" 节：

```
× Synchronization Engine
× Memory Database
× Embedding Store
× Vector Search
× Knowledge Graph
```

- [ ] `git tag v0.1.0` + `pip install memlink`

---

## 文件清单 + 预估行数

| 文件 | Phase | 行数 | 状态 |
|------|-------|------|------|
| `models.py` | 0.5 | 100 | ✅ 已有，待加 sanitize_id |
| `plugin.py` | 0.5 | 70 | ✅ |
| `serialization.py` | 0.5 | 50 | ✅ |
| `converter.py` | 0.5 | 100 | 🚧 待补过滤+统计+datetime 转换 |
| `validators.py` | 0.5 | 80 | 🚧 骨架，待加错误码枚举 |
| `ombre_reader.py` | 1 | 70 | 🚧 |
| `openclaw_writer.py` | 1 | 90 | 🚧 |
| `openclaw_reader.py` | 2 | 60 | 🚧 |
| `ombre_writer.py` | 2 | 60 | 🚧 |
| `cli/__init__.py` | 3 | 40 | 🚧 |
| `cli/convert.py` | 3 | 60 | 🚧 |
| `cli/validate.py` | 3 | 40 | 🚧 |
| `cli/diff.py` | 3 | 40 | 🚧 |
| `cli/inspect.py` | 3 | 30 | 🚧 |
| `cli/stats.py` | 3 | 40 | 🚧 |
| `testing.py` | 2.5 | 50 | 🚧 Plugin Contract Tests |
| **合计** | | **~950** | |

测试：

| 文件 | Phase | tests |
|------|-------|-------|
| `test_models.py` | 0.5 | 30 |
| `test_serialization.py` | 0.5 | 15 |
| `test_validators.py` | 0.5 | 10 |
| `test_plugin.py` | 0.5 | 5 |
| `test_ombre_reader.py` | 1 | 15 |
| `test_openclaw_writer.py` | 1 | 15 |
| `test_converter.py` | 1 | 10 |
| `test_openclaw_reader.py` | 2 | 20 |
| `test_ombre_writer.py` | 2 | 20 |
| `test_roundtrip.py`（含 Golden） | 2 | 15 |
| `test_domain_inference.py` | 2 | 8 |
| `test_integration.py` | 2.5 | 10 |
| `test_cli.py` | 3 | 20 |
| `test_fuzz.py` | 3 | 10 |
| `test_edge_cases.py` | 3 | 15 |
| **合计** | | **~185** |

---

## 关键约束汇总

1. **单一依赖**：`pyyaml>=6.0`，其余标准库
2. **Never Raise**：Reader 解析失败不崩溃
3. **Reader 不解析值**：原始字符串存入，Converter 统一做类型转换
4. **确定性排序**：tags/domains sorted()、MEMORY.md 按 id 排序
5. **percent-encoding 文件名**：可逆、不撞名
6. **casefold ID 冲突检测**：跨平台一致
7. **mtime+size 并发检测**：O(1)，不用 SHA256
8. **Golden Tests**：每个 fixture 配 expected.json
9. **Fuzz Testing**：hypothesis 100 随机 case
10. **Feature Loss Report + Reason**：说清楚为什么丢字段
11. **Verbose 三级**：-v/-vv/-vvv
12. **兼容性承诺**：Schema Stable / Plugin+CLI Experimental

---

## 本轮评审采纳（Phase 2/3 细节补充）

以下来自 Phase 2/3 执行方案的两轮外部评审，已确认采纳。

### Phase 2 采纳

| # | 建议 | 来源 |
|---|------|------|
| 1 | **Reader 拆成 Pipeline**：discover → parse → map → recover → validate → ReadResult | 建议2 |
| 2 | **文件发现容错**：优先读 MEMORY.md 索引；索引损坏 → warning + fallback 递归扫描 | 建议2 |
| 3 | **Original Recovery 白名单**：恢复 id/kind/domains/importance/created_tz，**不恢复** body/summary（避免覆盖用户手动修改） | 建议2 |
| 4 | **importance label→score 映射**：critical=10, high=8, medium=5, low=3, minimal=1 | 建议1 |
| 5 | **Ombre Writer 固定字段顺序**：bucket_id→name→type→domain→tags→importance→created→... | 建议2 |
| 6 | **Ombre Writer 目录策略**：domains[0] 作目录名，多值时 warning；_unknown→"general" | 建议2 |
| 7 | **Roundtrip 用 Comparator**：`compare_memory(a,b)` 返回结构化 Difference，不只 assert | 建议2 |
| 8 | **Roundtrip 退出标准**：Fixtures 100% + 真实数据 >95%，不只看 test count | 建议2 |

### Phase 3 采纳

| # | 建议 | 来源 |
|---|------|------|
| 1 | **CLI 拆分子包**：`commands/convert.py validate.py diff.py inspect.py stats.py` | 建议2 |
| 2 | **Convert 固定输出格式**：Read N / Converted M / Skipped K / Warnings W / Duration | 建议2 |
| 3 | **inspect 输出扩展**：Raw Frontmatter + Canonical + Warnings + Extensions + Capabilities | 建议2 |
| 4 | **validate JSON 含 summary**：`{"summary": {"errors": N, "warnings": M}, "issues": [...]}` | 建议2 |
| 5 | **diff 加 --ignore**：`--ignore tags` / `--ignore timestamps` / `--ignore importance` | 建议2 |
| 6 | **stats 扩展**：增加 average tags、average body length、oldest/newest memory | 建议2 |
| 7 | **Plugin 发现缓存**：首次 `entry_points()` 后缓存为 dict，避免重复扫描 | 建议2 |
| 8 | **统一退出码**：0=Success, 1=Diff/Validate Failed, 2=CLI Error, 3=Plugin, 4=IO, 5=Unexpected | 建议2（替代原来只对 diff 的 0/1/2） |
| 9 | **Ctrl+C 清理**：捕获后清理已写入的部分文件，exit 130 | 建议2 |
| 10 | **Plugin Contract Tests**：公共测试模块，任何新插件必须通过（最小样例/未知字段/结构化 warning/一次往返一致） | 建议2 |

### 新增 Phase 2.5 — 集成测试 + 兼容性报告

在 CLI 前增加一个集成验证阶段，用真实数据跑完整 A→B→A 流程，生成量化报告：

```
$ python -m memlink.integration_test

  ── Roundtrip Report ──
  Total memories:    117
  Roundtrip success: 117/117 (100%)
  
  ── Field-Level Loss ──
  summary (description):   2 lost (Ombre has no summary slot)
  emotion (valence/arousal): 0 lost (roundtrip preserved)
  relationships:            8 lost (v0 writer skip)
  
  ── Performance ──
  Read (Ombre):     0.12s
  Write (OpenClaw): 0.08s
  Read (OpenClaw):  0.06s
  Write (Ombre):    0.07s
  Total roundtrip:  0.33s

$ memlink validate --level roundtrip -s real-data/
  ✓ 117/117 memories pass roundtrip
```

| # | 建议 | 来源 |
|---|------|------|
| 1 | 在 CLI 前先跑真实数据集成测试 | 建议2 |
| 2 | 生成量化 Compatibility Report（Roundtrip Rate + Loss + Performance） | 建议2 |
| 3 | 所有新插件必须通过 Plugin Contract Tests | 建议2 |

---

## 终轮评审采纳（Phase 2/3 最终版）

### 设计变更

| # | 变更 | 说明 |
|---|------|------|
| 1 | **Converter 不做类型转换** | Reader 负责 raw→Canonical，Writer 负责 Canonical→raw。Converter 只管 filter/merge/feature-loss/compatibility，不碰 datetime |
| 2 | **Atomic Write** | 所有 Writer 先写 `.tmp` → `fsync()` → `rename()`。README 写明 "All writes are atomic on the same filesystem" |
| 3 | **Feature Loss 提前算** | 写入前做 Capability Check，提前告诉用户"将损失 X 个字段"，未来可加 `--interactive` 确认 |
| 4 | **Spec Compliance 清单** | 每个插件声明 Canonical 支持度：✅ Core / ✅ Summary / ⚠ Relationships (metadata only) 等 |

### 数据安全

| # | 建议 | 来源 |
|---|------|------|
| 1 | **空 domains 处理**：`domains=[]` 和 `domains=["_unknown"]` 都回退到 "general" + warning | 建议1 |
| 2 | **importance NaN/Inf 处理**：`math.isnan()` / `math.isinf()` → 默认 5 + warning | 建议1 |
| 3 | **URL decode 文件名**：`urllib.parse.unquote()` 还原 percent-encoded 字符 | 建议1 |
| 4 | **Reader 区分 Fatal vs Recoverable**：YAML 错/缺字段 → skip+warn；目录不存在/权限不足 → Fatal | 建议2 |
| 5 | **Checksum 写算法名**：`{algorithm: "sha256", value: "xxx"}` 而非裸字符串 | 建议2 |
| 6 | **MEMORY.md 保留用户注释**：Writer 只更新 `- memory/` 条目，不动其他文本 | 建议2 |
| 7 | **Reader Discovery 去重**：resolved path → `set()`，避免同一文件读两遍 | 建议2 |

### CLI 增强

| # | 建议 | 来源 |
|---|------|------|
| 1 | **统一 JSON Schema**：`validate_result.json` / `diff_result.json` / `stats_result.json` 结构固定 | 建议1 |
| 2 | **`validate --strict`**：warning 也 exit 1（CI 友好） | 建议2 |
| 3 | **`inspect` 支持 stdin**：`cat xxx.md \| memlink inspect -` | 建议2 |
| 4 | **`diff --id-only`**：只输出新增/删除 ID，速度快 | 建议2 |
| 5 | **`stats --format csv`**：id,kind,domain,tags_count,body_length（Excel 分析） | 建议2 |
| 6 | **Plugin 错误详细报告**：`memlink formats` 显示每个格式的加载状态（OK/Error） | 建议1 |

### 测试 + 质量

| # | 建议 | 来源 |
|---|------|------|
| 1 | **Fuzz 用随机 text()**：`kind=st.text()` 而非 `sampled_from`，疯狂一点 | 建议2 |
| 2 | **Plugin Contract +1**：Reader 必须 deterministic（同一输入两次 read() 结果完全一致） | 建议2 |
| 3 | **Difference 加 path**：JSON Pointer 风格字段路径 `/metadata/tags/0` | 建议2 |
| 4 | **P0 优先级**：空 domains > importance NaN > URL decode > JSON Schema > Plugin 错误 | 建议1 |

### 重要度排序（终版）

| 优先级 | 数量 | 内容 |
|--------|------|------|
| **P0** | 4 | 空 domains、importance 边界、URL decode、Atomic Write |
| **P1** | 5 | 统一 JSON Schema、Feature Loss 提前、Plugin Contract deterministic、Fatal/Recoverable、Spec Compliance |
| **P1** | 5 | validate --strict、inspect stdin、diff --id-only、checksum 算法名、MEMORY.md 保留注释 |
| **P2** | 6 | 颜色高亮(rich)、进度条(tqdm)、stats csv、diff --ignore、MEMORY.md 分组、benchmark |
