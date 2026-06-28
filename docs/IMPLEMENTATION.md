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

### 改动点

- `openclaw_reader.py`：同 Never Raise 原则
- `ombre_writer.py`：按 kind 路由到 dynamic/permanent/feel 目录
- Converter 统一处理 datetime 的双向转换
- Feature Loss Report 增加 Reason 字段：

```
  ── Feature Loss ──
  relationships      8 dropped  (Target plugin capability=false)
  emotion           14 dropped  (Target plugin capability=false)
```

### Roundtrip 测试

```
test_roundtrip.py       # Golden Tests: Ombre→OpenClaw→Ombre
test_domain_inference.py
```

---

## Phase 3 — CLI + 模糊测试 + 边缘用例

### 3.1 CLI

子命令同前。新增：
- `-v` warning、`-vv` 每个文件、`-vvv` 每个字段映射
- `--format json` 输出（validate、diff）
- Exit code：按之前定义的 0-5+130

### 3.2 模糊测试（Fuzz Test）

用 `hypothesis` 库（dev 依赖）生成随机输入：

```python
# tests/test_fuzz.py
from hypothesis import given, strategies as st

@given(
    body=st.text(max_size=10000),
    tags=st.lists(st.text(min_size=1, max_size=50), max_size=20),
    has_emoji=st.booleans(),
)
def test_memory_roundtrip_never_crashes(body, tags, has_emoji):
    """构造任意 Memory → 转换 → 不能崩"""
    ...
```

100 个随机 case，覆盖 emoji、null、中文、空格、超长字符串。

### 3.3 确定性排序规则

所有输出固定排序，确保 Git Diff 干净：
- `tags`：`sorted()` 后写入
- `domains`：`sorted()` 后写入
- MEMORY.md 索引：按 id 排序
- 文件遍历：`sorted(path.rglob("*.md"))`

### 3.4 ID 冲突检测：casefold

```
Windows: ABC.md == abc.md
Linux:   ABC.md != abc.md

统一用 casefold() 检测：
  sanitize_id("ABC").casefold() == sanitize_id("abc").casefold()
  → 冲突
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
| `cli.py` | 3 | 150 | 🚧 |
| **合计** | | **~830** | |

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
| `test_openclaw_reader.py` | 2 | 10 |
| `test_ombre_writer.py` | 2 | 10 |
| `test_roundtrip.py`（含 Golden） | 2 | 15 |
| `test_domain_inference.py` | 2 | 5 |
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
