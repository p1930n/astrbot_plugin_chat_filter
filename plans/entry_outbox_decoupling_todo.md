# 入口与 Outbox 入队解耦 TODO

## 背景

`README.md` 的压测诊断显示，群消息入口平均耗时过高，主要风险是命中后入口仍等待 SQLite outbox 入队完成，导致 `stop_event` 不能快速返回。

本 TODO 只覆盖 `astrbot_plugin_chat_filter` 的入口返回与违规任务入队解耦，不改变命令体系、规则匹配语义、SQLite outbox 表结构或平台动作执行链路。

## 目标

- 群消息入口命中后能基于匹配结果立即返回 `stop_event` 决策。
- SQLite outbox 写入从入口同步等待路径移到后台 writer。
- 继续复用现有持久化 outbox worker 处理审计记录、禁言、撤回、转发和 warning 文本发送。
- 在队列满、插件关闭、SQLite 背压和热重载 shutdown 时有明确失败语义、metrics 和脱敏日志。

## 非目标

- 不改 AstrBot 装饰器和命令注册方式。
- 不把 AstrBot `event` 对象传入 runtime 服务。
- 不在 `main.py` 中发送违规 warning，也不为违规消息入口 `yield event.plain_result(...)`。
- 不新增数据库 schema，不替换现有 SQLite outbox。
- 不用每条消息 `asyncio.create_task()` 直接写库，避免无界任务堆积。

## TODO

### 入口边界

- [x] 保持 `main.py` 的 AstrBot 边界职责不变：事件脱水、跳过自身 `.cf` 和 `/cf` 命令、提取 OneBot action client、选择 `PlatformActions`。
- [x] 保持 `MessageFilterService` 只接收原生 `ChatMessage` 和 `PlatformActions`，不接收 AstrBot `event`。
- [x] 命中后仍由入口层根据 `MessageFilterResult.stop_event` 调用 `event.stop_event()`。
- [x] 确认违规 warning 仍由后台违规处理链通过 `PlatformActions.send_text_log()` 发送，不接回入口响应装配。

### 内存入队层

- [x] 在 `ViolationIngressWriter` 中新增有界内存 ingress queue，容量使用现有 outbox pending 配置，不使用无界队列。
- [x] 调整入口入队：注册 `platform_actions`、构造 `ViolationOutboxEntry`、执行内存队列 `put_nowait` 后立即返回。
- [x] 增加内存层 idempotency set，避免同一 `message_id` 在 writer 落库前重复进入内存队列。
- [x] `enqueue()` 在内存队列满时返回 `False`，记录 `backpressure`，reason 使用 `memory_queue_full`。
- [x] `enqueue()` 在 `_closed=True` 时返回 `False`，记录 `backpressure`，reason 使用 `closed`。

### 后台 Writer

- [x] 在 `ViolationIngressWriter.start()` 中启动单后台 writer，用于把内存 ingress queue 写入 SQLite outbox。
- [x] writer 调用现有 `repository.enqueue_violation_outbox()`，保留数据库层 active count、去重和恢复语义。
- [x] writer 写入成功时继续记录 `violation_job.enqueued.total`。
- [x] writer 命中数据库重复时记录 `violation_job.duplicate.total`。
- [x] writer 命中 SQLite active outbox 满时记录 `backpressure`，reason 使用 `max_pending`。
- [x] writer 写入异常时只记录错误类型，不输出 SQL、路径、token、平台上下文或完整消息内容。
- [x] writer 异常重试采用有限退避，长期失败依靠有界内存队列形成背压。

### Shutdown 与恢复

- [x] `shutdown()` 先停止接收新任务，再尝试 flush 内存 ingress queue 到 SQLite outbox。
- [x] flush 设置短超时，超时后记录剩余未落库数量和脱敏日志。
- [x] 取消 writer 与现有 outbox workers 时保持可等待，避免热重载后残留后台任务。
- [x] 保留现有 processing job recovery，不改变 SQLite outbox 已持久化任务的恢复流程。

### Metrics

- [x] 增加入口缓冲或 writer 相关 metrics 常量，用于区分内存接受、写库成功、写库等待和背压。
- [x] 保留现有 `message.handle_group_message.ms`，用于验证入口耗时不再包含 SQLite 写入等待。
- [ ] 评估补充 `violation_job.enqueue.ms` 和 `violation_job.enqueue_lock_wait.ms`，对应 README 中的压测诊断需求。
- [ ] 后续压测时补充 outbox pending、processing、oldest pending age 指标，避免只看完成总数误判吞吐。

### 测试

- [x] 更新 `test_message_filter_service.py`：命中后仍调用入队接口，但测试不再假设入口等待 SQLite 写入完成。
- [x] 保留 `MessageFilterService` 测试：队列拒绝时仍返回 `MessageFilterResult(stop_event=True)`。
- [x] 新增 `test_violation_ingress_writer.py`：`enqueue()` 在 repository 写入阻塞时仍快速返回。
- [x] 补内存队列满测试：返回 `False`，记录 `violation_job.backpressure.total`，日志 reason 为 `memory_queue_full`。
- [x] 保留同一 `message_id` 在 writer flush 前重复入队只保留一次的测试。
- [x] 保留 writer 写入成功后现有 worker 继续处理任务的测试。
- [ ] 补 SQLite 写入异常后的有限重试或背压测试。
- [ ] 补 shutdown flush 超时测试：已缓冲 entry 尽量落到 SQLite，超时路径记录剩余数量。
- [x] 保留 `test_main_group_message_filter.py` 对违规入口无 `plain_result`、自身命令先跳过、`stop_event` 只在入口执行的语义检查。

## 验收清单

- [x] 高频群消息命中后，`message.handle_group_message.ms` 不再包含 SQLite outbox 写入等待。
- [x] 命中消息仍按配置阻断后续 AstrBot handler。
- [x] `warn_user=False` 时后台违规处理链不发送 warning 文本。
- [ ] 内存队列满、插件关闭、SQLite active outbox 满、SQLite 异常均有 metrics 和脱敏日志。
- [x] 插件热重载或卸载后 writer / worker task 可等待取消。
- [x] 不新增依赖，不需要同步 `requirements.txt`。
- [x] 不新增配置项，无需同步 `_conf_schema.json`、`ChatFilterSettings` 和 README 配置表。

## 后续 PR TODO

### PR 2：清理入口返回模型

建议 commit 标识：`refactor(result)`，后续可按实际改动细化为 `refactor(message-filter)` 或 `test(main-entry)`。

- [ ] 将 `MessageFilterResult` 收敛为只包含 `stop_event`。
- [ ] 移除测试中对 `warn_user` / `warning_message` 的旧字段构造。
- [ ] 保持 `warn_user` / `warning_message` 只存在于 `ChatFilterSettings` 和后台违规处理链。
- [ ] 补充或保留测试：违规 warning 不通过 `plain_result` 或入口响应装配发送。

### PR 3：正则匹配超时与 ReDoS 边界

建议 commit 标识：`fix(regex)`；若引入依赖，拆出 `build(deps)` 或 `chore(deps)`。

- [ ] 决定是否引入第三方 `regex` 包，并同步 `pyproject.toml` / 依赖声明。
- [ ] 若引入 `regex`，在每次 `search()` 时使用 per-search timeout。
- [ ] 在 `ChatFilterSettings` 中增加受控超时配置，例如 `regex_match_timeout_seconds`，并同步 `_conf_schema.json`、README 配置表和测试。
- [ ] 捕获 timeout 异常，记录脱敏 metrics / diagnostics，然后继续处理下一条规则。
- [ ] 若暂不引依赖，进一步收紧 regex 数量、pattern 长度、match target 长度和静态 denylist，并在 README 标明不是完整 ReDoS 防护。
- [ ] 补 `test_matcher_rules.py` / `test_rule_snapshot.py`，覆盖 regex timeout、跳过诊断和现有 compile/high-risk 行为。

### PR 4：质量工具链与 CI

建议 commit 标识：`chore(quality)`；按 CI 文件和工具配置可细化为 `ci(test)`、`chore(ruff)`、`chore(coverage)`。

- [ ] 在 `pyproject.toml` 增加 Ruff 基础配置。
- [ ] 在 CI 中加入 `ruff check .`。
- [ ] 在 CI 中加入 `ruff format --check .`，不同时维护 Black。
- [ ] 加入 coverage 命令：`python -m coverage run -m unittest discover -s . -p "test_*.py"` 和 `python -m coverage report`。
- [ ] coverage 先不设硬阈值，等基线稳定后再决定。
- [ ] mypy / pyright 暂不强制进 CI；如需引入，先只做本地或允许失败的基线评估。
- [ ] README 的开发验证命令同步更新。

### PR 1 后续补强项

建议 commit 标识：`test(runtime)` 或 `fix(runtime)`，按实际是否改生产代码决定。

- [ ] 补 SQLite 写入异常后的 writer 有限重试测试。
- [ ] 补 shutdown flush 超时测试。
- [ ] 评估 writer 异常后是否需要立即自动重启；当前行为是记录错误，下一次 `start()` 可重新创建 writer。
- [ ] 补压测指标：outbox pending、processing、oldest pending age。

## 当前状态

- 状态：PR 1 主体已实现，PR 2 / PR 3 / PR 4 未实现。
- 授权边界：当前 TODO 用于跟踪后续小 PR；未经明确授权不提交、不推送。
- 后续实现若触及入口、运行时、正则、依赖或 CI，继续按对应 workflow 执行。
