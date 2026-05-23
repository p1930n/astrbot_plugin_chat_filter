# Changelog

本文件记录 `astrbot_plugin_chat_filter` 的重要变更。

## [Unreleased]
### 变更
- **群级启用**：`.cf enable` 和 `/chatfilter enable` 改为启用当前群的聊天过滤；AstrBot 管理员可追加群号启用指定群。
- **群级关闭**：`.cf disable` 和 `/chatfilter disable` 改为关闭当前群的聊天过滤；追加群号关闭指定群时仅允许 AstrBot 管理员操作。
- **WebUI 配置边界**：从 `_conf_schema.json` 移除插件内部的全局聊天过滤 `enabled` 配置；插件级启停只交给 AstrBot WebUI，过滤生效范围由群策略控制。
- **默认群策略**：移除 WebUI 中的 `default_group_enabled` 配置；未单独配置的群固定为默认关闭，只能通过 `.cf enable` 或 `.cf enable [群号]` 显式启用。
- **命中提示装配**：违规命中提示改为插件侧纯文本群消息发送，不再通过 AstrBot `plain_result` 回装，避免触发平台自动 @ 用户；命令响应仍交给 AstrBot 平台设置处理。
- **状态输出**：`.cf status` 移除冗余的 `global=enabled|disabled` 和默认群策略字段，仅保留全局规则数量和已配置群数量。
- **违规处理链路**：命中消息后先进入持久化 outbox，再由后台 worker 依次执行写记录、禁言、撤回、转发和日志推送，避免把所有管理动作阻塞在群消息入口。
- **管理动作幂等**：outbox 重试时会读取已有动作状态，已成功的禁言、撤回、转发和日志推送不再重复执行。
- **运行时治理**：新增 outbox 最大待处理数、worker 数、最大重试次数和动作速率限制配置，并补齐背压、重试退避、热重载关闭和处理中任务恢复逻辑。

### 新增
- **Overview 指令**：新增 `.cf overview` 摘要输出和 `.cf overview csv` 明细输出，用于查看当前平台已启用过滤的群、监听群以及对应推送群关系。
- **Overview 回归覆盖**：补充 `.cf overview` 空参数命令入口和 `.cf overview csv` 跳过滤器的回归测试，确保指令继续由 AstrBot 命令路由处理。
- **回归覆盖**：新增测试，确保旧持久化状态中的 `global_enabled=false` 不再阻断已启用群的过滤行为。
- **Metrics 指令**：新增 `.cf metrics` 指令，输出匹配、队列、动作和记录耗时等运行指标，便于压测和线上诊断。
- **持久化 Outbox**：新增 `violation_outbox` schema v5、Repository 边界和后台队列测试，覆盖入队、去重、背压、重试、恢复和关闭路径。
- **群级词管理**：新增 `.cf group remove-to` 指定群移除自定义词，支持逗号批量输入。
- **群级全局词绕过**：新增 `.cf group bypass-add`、`.cf group bypass-remove`、`.cf group bypass-list` 和 `.cf group bypass-add-to`，允许 AstrBot 管理员按群绕过指定全局普通词。
