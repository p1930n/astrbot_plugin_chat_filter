# Changelog

本文件记录 `astrbot_plugin_chat_filter` 的重要变更。

## [Unreleased]
### 变更
- **群级启用**：`.cf enable` 和 `/chatfilter enable` 改为启用当前群的聊天过滤；AstrBot 管理员可追加群号启用指定群。
- **群级关闭**：`.cf disable` 和 `/chatfilter disable` 改为关闭当前群的聊天过滤；追加群号关闭指定群时仅允许 AstrBot 管理员操作。
- **WebUI 配置边界**：从 `_conf_schema.json` 移除插件内部的全局聊天过滤 `enabled` 配置；插件级启停只交给 AstrBot WebUI，过滤生效范围由群策略控制。
- **状态输出**：`.cf status` 移除冗余的 `global=enabled|disabled` 字段，仅保留默认群策略、全局规则数量和已配置群数量。

### 新增
- **回归覆盖**：新增测试，确保旧持久化状态中的 `global_enabled=false` 不再阻断已启用群的过滤行为。
