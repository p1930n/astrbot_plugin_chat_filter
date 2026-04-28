# Chat Filter

AstrBot 群聊过滤插件。插件会在群消息中检测违禁词和正则规则，命中后可提示、阻断后续处理、禁言、撤回，并把命中消息转发到指定推送群。

## 功能

- 群消息过滤：支持全局规则和每群自定义词。
- 普通词抗绕过：默认允许词内插入少量字符仍命中，例如通过 `obfuscated_word_max_gap` 控制间隔。
- SQLite 规则存储：违禁词和正则规则以 `global_rules` 为准，不从 JSON 配置读取词库。
- 正则规则：支持 `{{GAP}}` 占位符，由 `regex_gap_max` 控制展开后的最大间隔。
- 每群启停：可单独开启或关闭某个群的过滤。
- 群主/管理员豁免：每个群独立开关，默认开启；关闭后群主和管理员也会被检测。
- 违规处置：命中后可警告用户、阻断事件、禁言、撤回消息。
- 命中转发：可把监听群命中消息转发到一个或多个推送群。
- 禁言策略：支持每群设置基础禁言时长，并按连续命中叠加禁言。
- 审计报表：命中记录写入 SQLite，可手动生成 TSV dry-run 报表。
- 平台探针：提供转发消息和文件发送探针，便于调试平台适配能力。

## 指令

以下示例使用 `.cf`。全局和群策略命令也提供 `/chatfilter` 入口，例如 `/chatfilter status`、`/chatfilter group status`。

| 指令 | 说明 |
| --- | --- |
| `.cf help` | 查看插件命令摘要。 |
| `.cf status` | 查看全局词数量和已记录群数量。 |
| `.cf overview` | 查看当前平台已启用过滤群、监听群和推送绑定数量摘要。 |
| `.cf overview csv` | 以 CSV 格式列出当前平台启用过滤的群，以及监听群绑定的推送群。 |
| `.cf enable [群号]` | 启用当前群或指定群过滤；不再作为全局开关。此命令只允许 AstrBot 管理员使用。 |
| `.cf disable [群号]` | 关闭当前群或指定群过滤；不再作为全局开关。传入群号时只允许 AstrBot 管理员使用。 |
| `.cf group status` | 查看当前群过滤状态、继承状态、管理员豁免状态和群自定义词数量。 |
| `.cf group enable` | 启用当前群过滤。此命令只允许 AstrBot 管理员使用。 |
| `.cf group disable` | 关闭当前群过滤。 |
| `.cf group add <词>` | 给当前群添加自定义过滤词。 |
| `.cf group remove <词>` | 从当前群移除自定义过滤词。 |
| `.cf group list` | 查看当前群自定义词数量。 |
| `.cf group admin-exempt status` | 查看当前群群主/管理员豁免开关。 |
| `.cf group admin-exempt enable` | 开启当前群群主/管理员豁免。 |
| `.cf group admin-exempt disable` | 关闭当前群群主/管理员豁免。 |
| `.cf group exempt status|enable|disable` | `admin-exempt` 的短别名。 |
| `.cf bind <监听群> <推送群>` | 为监听群添加命中消息推送群。 |
| `.cf bind list` | 查看当前平台的推送绑定列表。 |
| `.cf mute <群号> <秒数>` | 设置指定群命中后的基础禁言时长。 |
| `.cf mute list` | 查看当前平台的群禁言策略。 |
| `.cf mute-stack <群号> <倍率> <重置秒数>` | 设置连续命中禁言叠加策略。 |
| `.cf mute-stack list` | 查看当前平台的禁言叠加策略。 |
| `.cf probe` | 查看当前平台动作能力探针。 |
| `.cf forward-probe [群号]` | 向指定群或当前群发送合并转发探针。 |
| `.cf file-probe [群号]` | 向指定群或当前群发送文件探针。 |
| `.cf report-dry-run [群号] [天数]` | 生成指定群命中历史 TSV 报表；未传群号时使用当前群。 |

管理员豁免动作也支持 `/chatfilter group admin-exempt status|enable|disable` 和 `/chatfilter group exempt status|enable|disable`。

## 权限

- 默认情况下，命令允许 AstrBot 管理员、QQ群主或 QQ 群管理员使用。
- `.cf enable`、`.cf group enable`、`/chatfilter enable` 和 `/chatfilter group enable` 更严格，只允许 AstrBot 管理员使用。
- `.cf disable [群号]` 和 `/chatfilter disable [群号]` 指定群号时只允许 AstrBot 管理员使用；不指定群号时仍允许当前群的群主或管理员使用。
- 权限判断依赖 AstrBot 配置中的管理员 ID 和平台事件中的群角色信息，不信任消息文本中的自称身份。

## 配置

插件配置来自 AstrBot 的 `_conf_schema.json`：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `case_sensitive` | `false` | 是否区分大小写。 |
| `obfuscated_word_matching_enabled` | `true` | 是否启用普通词抗绕过匹配。 |
| `obfuscated_word_max_gap` | `4` | 普通词相邻字符最大间隔。 |
| `regex_gap_max` | `8` | 正则规则 `{{GAP}}` 占位符展开后的最大间隔。 |
| `stop_event` | `true` | 命中后是否阻断后续事件处理。 |
| `warn_user` | `true` | 命中后是否发送纯文本提示；插件不会主动 @ 用户。 |
| `warning_message` | `消息触发聊天过滤策略，请调整后重试。` | 命中后的纯文本提示文案。 |
| `max_word_count` | `500` | 每个词库最多词条数。 |
| `max_word_length` | `64` | 单个词条最大长度。 |
| `violation_records_enabled` | `true` | 是否写入 SQLite 命中审计记录。 |
| `mute_duration_seconds` | `600` | 默认基础禁言时长。 |
| `mute_escalation_multiplier` | `2` | 默认连续命中禁言叠加倍率。 |
| `mute_escalation_reset_seconds` | `3600` | 连续命中状态重置时间。 |
| `default_report_days` | `7` | 报表默认统计天数。 |

## 数据存储

- 主数据库：`data/astrbot_plugin_chat_filter/chat_filter.db`
- 全局规则表：`global_rules`
- 群策略、推送绑定、禁言策略和命中记录也存储在 SQLite。
- 运行时 JSON 配置只保存功能开关和安全参数，不保存违禁词或正则规则。
- 手动报表输出到插件数据目录下的 `reports/`。
- 文件探针输出到插件数据目录下的 `probes/`。

## 适配说明

- `aiocqhttp` 平台会优先使用 OneBot V11 action client 执行禁言、撤回、转发和文件发送。
- 非 OneBot 或能力不可用的平台会返回 unsupported/failed 状态，过滤检测本身仍可运行。
- 命中消息转发依赖 `.cf bind` 配置的推送群；没有绑定时只记录未调度状态。

## 开发验证

```powershell
py -3.13 -B -m unittest discover -s . -p "test_*.py"
git diff --check
```
