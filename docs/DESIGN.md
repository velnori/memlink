# MemLink 设计合同（2.0）

本文件描述当前代码。历史 v0/v1 执行计划保存在 `IMPLEMENTATION.md`；其中未实现的 CLI 设想和 Reader 不解析时间的旧决定已被本合同取代。当前范围是本地文件的 Trusted Conversion / Full Migration，不包含同步或在线 API 导入。

## 保留的架构与 schema

仍使用 **Reader → Canonical Memory → Writer**。每个格式只实现自己的适配器，事务层负责所有格式共有的边界、验证、收据和提交。

`spec/canonical-v1.schema.json` 与规范字段语义保持不变。必需项仍是 `schema_version="1"` 和 `id`；name/body/time 可以为空，kind 保持开放词汇，valence/arousal 的范围仍为 0–1，importance 保留原生尺度。不得为了迁移方便修改 v1 的 required/type/默认值。运行资源原样打入 wheel/sdist，验证器缺资源或遇到未知版本时失败。

包版本、canonical 版本和 transport 版本分别管理：`_version.py` 是包/CLI 版本唯一来源；canonical 固定 v1；receipt/archive/compatibility 使用独立 v1 JSON 资源。

## 输入与身份

只读用户给出的目录或文件。没有 home 自动发现。文件和 JSON/YAML 读取有大小、数量、深度、节点上限；拒绝链接、重复键、循环 alias、NaN/Inf。JSON 目录优先选择明确的标准文件名，否则只接受唯一候选，多个任意 JSON 不取第一个。自动识别需要正面结构证据，不能确定就要求明确格式。

`ReadResult` 保留原有 memories/warnings/stats，并增加 files/records/errors/variant/valid_empty。每个输入文件有 parsed/excluded/invalid/unsupported 和 SHA256；每个记录有结果/原因。filter exclusion 与解析失败分别计数。合法空数组是显式空集；空目录、全部失败不算验证通过。

默认身份为 `批准源根派生 namespace + scope + native id`。namespace 使用格式名及批准根的哈希，不在收据泄露绝对 home 路径。Mem0 scope 包含 user_id/agent_id/run_id，Zep 包含 session_id；无法确定时标记 unknown，不写成默认用户。未经验证的 `_memlink_identity` 不覆盖源派生身份，原声明留在 `_claimed_identity`。与原生文件哈希、读回正文一致的 archive 可以携带原始身份，使转换后的源仍可认出共同来源。

目标 ID/路径映射确定性生成。`sanitize_id` 先转义 `%`，再编码非法字符、边缘点/空格和 Windows 保留名。长名称截断带 SHA256 后缀；receipt/archive 明确映射，不能只靠截断猜原 ID。NFC/casefold 冲突添加稳定后缀。Ombre 外来非 hex ID 使用 identity 派生的 12 位 hex；原 canonical ID 留在归档。

## Export 与 migrate

`convert`/公共 `writer.write` 只接受新或无文件的目标。`migrate` 支持已有目标，默认为 skip，replace/rename 必须显式选择。migrate 不删除未知目标文件，不写 OpenClaw TOOLS/SOUL/AGENTS/配置/认证状态。

步骤：

1. 解析批准源、过滤、验证 canonical，取得输入 ledger/快照。
2. 取得目标文件快照（hash、size、mtime_ns），分配稳定目标 ID 和冲突策略。已有目标上的 rename 同时避开已存在的记录 ID。
3. 在最近存在的目标父目录取得 root 协作锁。staging 与目标在同一文件系统；没有副作用的 dry-run 不取锁、不建立目录。
4. 原有 serializer 写入 staging。目标的实际 native reader 读取所有目标记录，验证数量/ID及逐字段值。Capabilities 不参与最终 preserved 判断。
5. 构造有定位路径、native hash/body/scope 的完整 canonical archive，再读实际归档字节验证。skip 的输入记录不偷偷进入 archive。相同 native bytes 但不同旧 archive 也视为语义冲突。
6. 再检查源文件集合/每个摘要及目标快照。改动则退出 4。建立目标和 `.memlink/backups/<transaction-id>`，备份将更新的文件及旧 receipt，写 restore manifest。
7. 逐文件提交：新增独占创建，更新先验证旧摘要再替换。核对已提交摘要、实际 native 读回和记录，再写 receipt。
8. 失败时倒序恢复本次提交的文件、删除本次新建文件和空目录。对提交后被别人改变的文件不恢复覆盖，保留并返回非零/incomplete rollback。保留备份，不自动清理用户目标。

这不是多文件全局原子事务。协作锁协调 MemLink；外部应用不遵守该锁，hash 检查也无法消除检查到操作之间的所有 OS 竞争窗口。崩溃/断电不是异常 rollback，需使用保留备份。广播目标各自提交，成功目标不会因另一目标失败被撤销。

冲突以目标文档为单位：daily 同日记录、MEMORY 长期文件、Mem0/Zep 单个 JSON 都可能包含多条。skip 会跳过对应整份文档，replace 替换整份文档，rename 保留旧文档另建可定位的新文档。Mem0/Zep rename 生成额外离线 JSON segment；bridge 根据 archive 的明确文件清单读各 segment 的实际 JSON。在线服务如何导入多个文件不属于本实现。

## 实际字段收据

最终状态来自 serializer 字节与真实 native reader：

| 状态 | 实际含义 |
|---|---|
| native-preserved | 公开 native 字段映射且实际值相等 |
| archive-only | native 不表达，该值已在可定位、验证过的本次归档 |
| transformed | 公开确定性映射导致值不同；receipt 有原值/目标值，archive 有完整原值 |
| dropped | skip 冲突等导致本次输入未进入输出；不能算作已经归档 |
| unsupported/unknown | 无法解释的输入/未运行验证；不得当 preserved |

receipt 包含工具/transport 版本、source variant/识别依据、scope/identity、输入文件与记录统计、filters/excluded、目标模式、逐字段影响、输出摘要、readback、conflict、backup、warnings/errors/status。`.memlink/receipt.json` 不包含自身递归摘要；archive 是版本化独立输出。合法输出仍可能 partial，exit 0 只表示 best-effort 工作流完成。I/O、竞争、严格策略失败均非零。

默认归档所有选中的 canonical 字段，不能归档被过滤的记录。Reader 只有在 native 文件摘要、record body、path/scope/ID 和 archive canonical schema 都正确时恢复原值。native 被修改后，保留当前 native 数据并明确 archive stale。archive 哈希不是数字签名，不表示第三方输入可信。

严格模式在 staging/归档验证后、真实目标任何修改前阻断有值的 archive/transformed 字段或 skip 冲突；invalid/unsupported 源记录也阻断。`--allow-change` 仅接受公开 canonical 字段名，逐项记录；警告和字段真实状态仍保留。None/空集合及默认 pinned=False 不算有值的变化。dry-run 是 planned，字段 unknown，不能声称验证成功。

## 格式行为

- **OpenClaw**：根据当前官方 [memory](https://docs.openclaw.ai/concepts/memory) 与 [workspace](https://docs.openclaw.ai/concepts/agent-workspace) 语义读取 plain MEMORY、daily/slug/recursive imported notes。USER 是 user model，DREAMS 是 dreaming 人工 review；默认排除，显式参数批准才读。普通 DREAMS 作为 review 文档，历史 MemLink emotion entries 是单独兼容变体。default writer 把 permanent 写 MEMORY，其余写 UTC daily/undated，不把 emotion 自动写 DREAMS。MEMORY 的 plain 与历史 index 不能混淆，dangling index 明确告警。
- **OpenClaw transport**：daily 使用版本化、长度定义的 comment/header/payload 边界。同日三条保持三条，正文的标题、横线、普通 comment 和 CRLF 原样保留。comment 中 canonical 数据是运输信息，不冒充 OpenClaw native emotion/关系/身份。structured 独立可选、独立 roundtrip 测试。
- **Ombre**：Reader 解析 created 到 UTC created_at，raw/timezone 留 original；writer 沿用 native type/domain 路由、安全 YAML、importance 原生尺度规则，实际差异进入 receipt。没有日期不能写成字符串 None。
- **Generic**：plain/optional frontmatter；输出 notes/*.md 的 v1 frontmatter 能直接表达完整 canonical 字段；扩展保存在 extensions，额外顶层兼容键不能覆盖 id/核心字段。不同应用的 block reference、数据库、附件行为不在承诺内。
- **Mem0/Zep**：离线 JSON 读写，原生字段及 scope 按公开映射；emotion/relationships 等无 native 表达则 archive-only。未知 record/top-level 字段与原始 scope 保留。metadata-only 记录仍输出，不默默消失。
- **ChatGPT/Claude**：transcript reader，不是 Saved Memory。ChatGPT 遵守 current_node/parent，缺 active 时只允许唯一链；环、孤点/缺 parent 等明确失败。其他分支完整 graph 留 transport。Claude 选择文本 blocks/fallback text；不同 alternate text、tool、attachment 数据留完整原 transcript 并告警，不做 OCR/二进制获取。无支持正文的 conversation 在 source ledger 明确 unsupported，不假装已迁移。
- **Stream summary**：date/timezone→created_at；status/零事件/peak hour=0 保留；采集状态等 unknown raw fields 可恢复。系统没有 IANA tz database 时明确 UTC assumption 告警，保留原 timezone；不会安装额外数据库。

## Merge、compare、validate

同 identity 才默认 merge；显式 link-by-id 入 receipt。newest/oldest 优先 updated_at 再 created_at；有日期优先无日期，tie 保留已有记录；naive 按 UTC，epoch 0 有效。first/last 不比较日期。

compare 按完整 identity 分组保留 duplicate 数量，不先转 dict 丢记录。默认比较全部 canonical 字段，包括 source/metadata/extensions/relationships/status/time/body；实际正文参与比较，外部 checksum 不能短路。明确 `CompareOptions.ignore`/CLI ignore 才允许字段差异。

validate 使用对应真实 reader 和实例 schema/semantic 校验；roundtrip 必须明确或可靠识别源，走对应 reader/writer，默认测试 daily-notes，不强制 structured。零记录及 invalid/unsupported 源不能绿色通过。reader-only transcript/stream 没有反向 writer，roundtrip 明确失败而不是换用 Ombre。

## 插件与边界

保留 FormatPlugin read/write/validate 签名，ReadResult 原字段保持。`__init_subclass__` 给公共 write 包事务 wrapper，raw serializer 只拿 staging；read 包统一 guard。registry 检查 capability 类型/版本、numeric version range、role、重复名称。reader-only/writer-only 各自注册；缺少匹配 reader 的 writer 无法完成验证导出，不能造成功收据。未知第三方格式的 safe apply 未验证，migrate 退出 5；其配对 reader 能验证的 export 可使用 archive，但没有内置 native 字段映射时不宣称 native-preserved。

第三方插件仍是可信 Python 执行代码，wrapper 不是任意恶意 Python 的进程沙箱。代码不依赖网络、AI API、token、上传或遥测。

2.0 采用更严格写入/校验/比较行为，因此保留历史 1.x 稳定承诺作为兼容性背景，明确破坏性行为、理由和迁移示例见 [升级说明](guide/migration-2.0.md)。使用方式、退出码、收据和事务限制见 [CLI 合同](guide/cli.md)；维护者检查命令见仓库 README 和 CONTRIBUTING。
