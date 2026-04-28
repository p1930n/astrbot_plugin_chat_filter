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

### 新增
- **回归覆盖**：新增测试，确保旧持久化状态中的 `global_enabled=false` 不再阻断已启用群的过滤行为。
