# Phase 02 SQLite Bindings 开发日志

## 阶段目标

本阶段围绕违规命中后的审计入库能力打底，目标是为后续推送、禁言、撤回、合并转发和周期文件生成提供可追踪的数据基础。

- 扩展 SQLite 结构，支持违规命中记录、监听群与多个推送群的绑定关系。
- 预留 WebUI 后续参数，包括禁言时长边界、周期报告默认值与群级覆盖能力。
- 违规命中后仅执行本地入库，不在本阶段调用平台禁言、撤回、合并转发或文件推送能力。
- 明确后续 AstrBot 实机确认点，避免基于未验证字段或平台能力继续扩大实现范围。

## 改动范围

本阶段代码改动范围应限定在以下能力面：

- SQLite 表结构与迁移：绑定关系、违规记录、后续周期批次或群级策略所需字段。
- Repository 层：绑定读写、命中记录入库、后续按群和时间窗口查询所需的基础接口。
- Model 层：绑定、命中记录、动作状态和 WebUI 参数对应的数据结构。
- 设置与配置：为后续 WebUI 暴露参数提供默认值和边界表达。
- 入口层：只接入命中后入库路径，不接入平台动作。

本阶段不实现：

- 禁言。
- 撤回。
- 合并转发。
- 单独日志消息推送。
- 周期文件生成与发送。
- 平台 API 重试、限流、队列或后台调度。

## 与 plans/violation_push_logic.md 的对应关系

本阶段对应计划中的“实现边界与阶段状态”和“多推送群与群级周期补充”部分，落实其中关于 Phase 2 的基础能力边界：

- 对应“阶段 2 只实现绑定关系、表结构、配置参数和命中记录入库”：本阶段仅保存命中记录和绑定基础，不执行平台处置动作。
- 对应“先入库，后执行平台动作”的处理顺序建议：当前阶段只完成“先入库”，后续动作保留为后续阶段。
- 对应“一个监听群绑定多个推送群”的补充设计：SQLite 绑定关系应按一行一个绑定建模，避免把多个推送群压入单个字符串字段。
- 对应 WebUI 参数建议：禁言时长、周期报告默认值、群级覆盖策略在本阶段作为配置和数据结构基础预留。
- 对应平台能力待确认点：禁言、撤回、合并转发、发文件、message_id、群/用户字段和权限上下文均不得在本阶段假定可用。

## 验证项

本阶段验收应覆盖以下项目：

- SQLite 初始化后可创建或迁移所需表结构，重复初始化不破坏已有数据。
- 监听群到多个推送群的绑定可以持久化，重载后仍可读取。
- 同一平台、同一监听群、同一推送群的重复绑定按设计保持幂等或被明确拒绝。
- 命中违规词后能写入违规记录，至少包含平台、群、用户、命中规则、命中片段、时间和后续动作状态占位。
- 未绑定推送群时，命中记录仍能入库，不触发推送相关动作。
- 日志不输出完整用户隐私、完整命中文本、token、cookie、SQL 或异常堆栈。
- 缺少必要事件字段时应跳过本次处理并输出脱敏日志，不能构造伪造 ID。
- 配置默认值可被加载，WebUI 后续参数没有真实密钥或敏感默认值。

需要 AstrBot 实机确认的验证项：

- `.cf` 命令前缀是否与当前 AstrBot 目标版本、命令装饰器和已有命令路由兼容。
- 事件对象中 `message_id` 的获取方式、稳定性和空值行为。
- QQ 用户名称、群名称或展示名字段是否可用，以及是否应作为快照字段入库。

## Subagent 审查指出的风险

- `.cf` 前缀需要 AstrBot 实机确认，不能只凭本地代码判断命令是否可触发。
- `message_id` 字段需要 AstrBot 与目标 QQ 适配器实机确认；缺失时不能构造伪 ID。
- QQ 名称、群名称等展示字段需要实机确认；展示名不稳定，后续应保留 ID 作为审计主键，名称只作为快照。
- 高频命中直接写库可能造成事件路径阻塞或 SQLite 锁竞争，后续需要队列、背压、限流和失败降级设计。
- 平台动作本阶段不实现；禁言、撤回、合并转发、发文件都必须等官方 API 和目标平台能力确认后再接入。

## 下一阶段建议

- 先完成 AstrBot 实机验证，确认 `.cf` 命令、事件字段、权限上下文和标准响应装配方式。
- 命中写库路径进入高频场景前，按 async-runtime workflow 设计队列、并发限制、超时、背压和热重载释放。
- 平台动作接入前，按 astrbot-integration workflow 确认禁言、撤回、合并转发和发文件 API。
- 如继续扩展表结构、查询形态或数据生命周期，先按 persistence workflow 复核迁移、索引和保留策略。
- 周期文件与群级周期策略应独立为调度边界，不应继续堆入入口层。

## Commit / Push 记录

- Commit: `0f13183 Phase 02 SQLite bindings and violation records`.
- Push: originally pushed to `origin/main`; follow-up development now targets `origin/working`.

## Acceptance Amendment: Mute Duration Policy

- WebUI should expose only `mute_duration_seconds` as the global default mute duration in seconds.
- WebUI should not expose mute minimum or maximum bounds.
- Internal validation uses 10 seconds as the lower bound because QQ backend mute duration can be shorter than the frontend display boundary.
- Group-specific mute duration is stored in SQLite and managed separately from WebUI global defaults.
- Added group-level mute policy groundwork for later platform-action execution.
