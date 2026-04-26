from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .astrbot_event_adapter import (
    current_group_key_from_event,
    dehydrate_event_snapshot,
    dehydrate_group_message,
    extract_onebot_action_client,
    field_state,
    has_required_message_scope,
)
from .command_service import ChatFilterCommandService, load_runtime_state
from .file_probe_service import FileProbeService
from .matcher import ChatFilterMatcher
from .platform_actions import (
    OneBotV11PlatformActions,
    PlatformActions,
    QQPlatformActions,
    format_platform_probe,
)
from .report_service import ViolationReportService
from .repository import ChatFilterRepository, default_data_root
from .rule_snapshot import RuleSnapshot
from .settings import ChatFilterSettings
from .violation_actions import ViolationActionExecutor
from .violation_records import ViolationRecorder


COMMAND_PREFIXES = ("/chatfilter", "/cf", ".cf")
COMMAND_PERMISSION_DENIED = (
    "Chat Filter command permission denied: "
    "requires AstrBot admin or QQ group owner/admin permission."
)
GROUP_ENABLE_PERMISSION_DENIED = (
    "Chat Filter group enable permission denied: "
    "requires AstrBot admin permission."
)
GROUP_ADMIN_EXEMPT_USAGE = (
    "Usage: .cf group admin-exempt status|enable|disable "
    "or /chatfilter group admin-exempt status|enable|disable "
    "(alias: exempt)"
)


class ChatFilterPlugin(Star):
    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
        platform_actions: PlatformActions | None = None,
    ) -> None:
        super().__init__(context)
        self.settings = ChatFilterSettings.from_config(config)
        self.data_root = default_data_root()
        self.repository = ChatFilterRepository(
            self.data_root,
            max_word_count=self.settings.max_word_count,
            max_word_length=self.settings.max_word_length,
        )
        self.rule_snapshot = RuleSnapshot.from_repository(
            self.repository,
            settings=self.settings,
        )
        self.state = load_runtime_state(self.repository, logger)
        self.command_service = ChatFilterCommandService(
            self.repository,
            self.state,
            self.settings,
            self.rule_snapshot,
            logger,
        )
        self.matcher = ChatFilterMatcher()
        self.platform_actions = platform_actions
        self.violation_action_executor = ViolationActionExecutor(
            self.repository,
            logger=logger,
            default_mute_duration_seconds=self.settings.mute_duration_seconds,
            default_mute_escalation_multiplier=(
                self.settings.mute_escalation_multiplier
            ),
            default_mute_escalation_reset_seconds=(
                self.settings.mute_escalation_reset_seconds
            ),
        )
        self.violation_recorder = ViolationRecorder(self.repository, logger)
        self.report_service = ViolationReportService(
            self.repository,
            data_root=self.data_root,
            default_report_days=self.settings.default_report_days,
            logger=logger,
        )
        self.file_probe_service = FileProbeService(
            data_root=self.data_root,
            logger=logger,
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = dehydrate_group_message(event)
        if self._is_own_command(message.text):
            return
        if not has_required_message_scope(message):
            logger.warning(
                "Chat Filter skipped message with incomplete event scope: "
                "platform=%s group_id=%s sender_id=%s",
                field_state(message.platform),
                field_state(message.group_id),
                field_state(message.user_id),
            )
            return

        result = self.matcher.detect(
            message,
            self.settings,
            self.state,
            self.rule_snapshot,
        )
        if not result.matched:
            return

        platform_actions = self._platform_actions_for_event(event)
        violation_id: int | None = None
        if self.settings.violation_records_enabled:
            violation_id = await self.violation_recorder.record(
                message,
                result.matched_word,
                platform_actions,
            )

        if self.settings.stop_event:
            event.stop_event()
        if violation_id is not None:
            await self.violation_action_executor.execute(
                violation_id=violation_id,
                message=message,
                platform_actions=platform_actions,
            )
        if self.settings.warn_user:
            yield event.plain_result(self.settings.warning_message)

    @filter.command_group("chatfilter")
    def chatfilter():
        pass

    @filter.command_group("cf")
    def cf():
        pass

    @cf.command("bind")
    async def cf_bind(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        push_group: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        if listening_group == "list" and not push_group:
            yield self._command_result(
                event,
                await self.command_service.format_push_bindings(snapshot.platform)
            )
            return

        yield self._command_result(
            event,
            await self.command_service.add_push_binding(
                snapshot,
                listening_group_id=listening_group,
                push_group_id=push_group,
            ),
        )

    @cf.command("mute")
    async def cf_mute(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        seconds: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        if group_id == "list" and not seconds:
            yield self._command_result(
                event,
                await self.command_service.format_group_mute_policies(
                    snapshot.platform
                ),
            )
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_mute_duration(
                snapshot,
                group_id=group_id,
                seconds=seconds,
            ),
        )

    @cf.command("mute-stack")
    async def cf_mute_stack(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        multiplier: str = "",
        reset_seconds: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        if group_id == "list" and not multiplier and not reset_seconds:
            yield self._command_result(
                event,
                await self.command_service.format_group_mute_escalation_policies(
                    snapshot.platform
                ),
            )
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_mute_escalation(
                snapshot,
                group_id=group_id,
                multiplier=multiplier,
                reset_seconds=reset_seconds,
            ),
        )

    @cf.command("probe")
    async def cf_probe(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        capabilities = self._platform_actions_for_event(event).probe_capabilities(
            snapshot.platform
        )
        yield self._command_result(
            event,
            format_platform_probe(snapshot, capabilities),
        )

    @cf.command("forward-probe")
    async def cf_forward_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        yield self._command_result(
            event,
            await self.command_service.run_forward_probe(
                snapshot,
                self._platform_actions_for_event(event),
                target_group,
            ),
        )

    @cf.command("report-dry-run")
    async def cf_report_dry_run(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        days: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        yield self._command_result(
            event,
            await self.report_service.generate_dry_run(
                snapshot,
                listening_group_id=listening_group,
                days=days,
            ),
        )

    @cf.command("file-probe")
    async def cf_file_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        snapshot = dehydrate_event_snapshot(event)
        yield self._command_result(
            event,
            await self.file_probe_service.run_file_probe(
                snapshot,
                self._platform_actions_for_event(event),
                target_group,
            ),
        )

    @cf.command("help")
    async def cf_help(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(event, self.command_service.format_help())

    @cf.command("status")
    async def cf_status(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(event, self.command_service.format_status())

    @cf.command("enable")
    async def cf_enable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_global_enabled(True),
        )

    @cf.command("disable")
    async def cf_disable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_global_enabled(False),
        )

    @cf.group("group")
    def cf_group():
        pass

    @cf_group.command("status")
    async def cf_group_status(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            self.command_service.format_group_status(
                current_group_key_from_event(event)
            ),
        )

    @cf_group.command("enable")
    async def cf_group_enable(self, event: AstrMessageEvent):
        denial = self._command_denial(event, allow_group_manager=False)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                True,
            ),
        )

    @cf_group.command("disable")
    async def cf_group_disable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                False,
            ),
        )

    @cf_group.command("add")
    async def cf_group_add(self, event: AstrMessageEvent, word: str):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.add_group_word(
                current_group_key_from_event(event),
                word,
            ),
        )

    @cf_group.command("remove")
    async def cf_group_remove(self, event: AstrMessageEvent, word: str):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.remove_group_word(
                current_group_key_from_event(event),
                word,
            ),
        )

    @cf_group.command("list")
    async def cf_group_list(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            self.command_service.format_group_words(
                current_group_key_from_event(event)
            ),
        )

    @cf_group.command("admin-exempt")
    async def cf_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield self._command_result(
            event,
            await self._group_admin_exempt_command_response(event, action),
        )

    @cf_group.command("exempt")
    async def cf_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield self._command_result(
            event,
            await self._group_admin_exempt_command_response(event, action),
        )

    @chatfilter.command("help")
    async def chatfilter_help(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(event, self.command_service.format_help())

    @chatfilter.command("status")
    async def chatfilter_status(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(event, self.command_service.format_status())

    @chatfilter.command("enable")
    async def chatfilter_enable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_global_enabled(True),
        )

    @chatfilter.command("disable")
    async def chatfilter_disable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_global_enabled(False),
        )

    @chatfilter.group("group")
    def chatfilter_group():
        pass

    @chatfilter_group.command("status")
    async def chatfilter_group_status(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            self.command_service.format_group_status(
                current_group_key_from_event(event)
            ),
        )

    @chatfilter_group.command("enable")
    async def chatfilter_group_enable(self, event: AstrMessageEvent):
        denial = self._command_denial(event, allow_group_manager=False)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                True,
            ),
        )

    @chatfilter_group.command("disable")
    async def chatfilter_group_disable(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                False,
            ),
        )

    @chatfilter_group.command("add")
    async def chatfilter_group_add(self, event: AstrMessageEvent, word: str):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.add_group_word(
                current_group_key_from_event(event),
                word,
            ),
        )

    @chatfilter_group.command("remove")
    async def chatfilter_group_remove(self, event: AstrMessageEvent, word: str):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            await self.command_service.remove_group_word(
                current_group_key_from_event(event),
                word,
            ),
        )

    @chatfilter_group.command("list")
    async def chatfilter_group_list(self, event: AstrMessageEvent):
        denial = self._command_denial(event)
        if denial:
            yield self._command_result(event, denial)
            return

        yield self._command_result(
            event,
            self.command_service.format_group_words(
                current_group_key_from_event(event)
            ),
        )

    @chatfilter_group.command("admin-exempt")
    async def chatfilter_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield self._command_result(
            event,
            await self._group_admin_exempt_command_response(event, action),
        )

    @chatfilter_group.command("exempt")
    async def chatfilter_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield self._command_result(
            event,
            await self._group_admin_exempt_command_response(event, action),
        )

    @staticmethod
    def _command_result(event: AstrMessageEvent, text: str):
        event.stop_event()
        return event.plain_result(text)

    async def _group_admin_exempt_command_response(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        denial = self._command_denial(event)
        if denial:
            return denial
        return await self._group_admin_exempt_command_text(event, action)

    async def _group_admin_exempt_command_text(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        group_key = current_group_key_from_event(event)
        normalized_action = action.strip().casefold()
        if normalized_action in ("", "status"):
            return self.command_service.format_group_admin_exempt_status(group_key)
        if normalized_action in ("enable", "enabled", "on", "true", "1"):
            return await self.command_service.set_group_admin_exempt_enabled(
                group_key,
                True,
            )
        if normalized_action in ("disable", "disabled", "off", "false", "0"):
            return await self.command_service.set_group_admin_exempt_enabled(
                group_key,
                False,
            )
        return GROUP_ADMIN_EXEMPT_USAGE

    def _command_denial(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> str | None:
        if self._can_use_command(event, allow_group_manager=allow_group_manager):
            return None
        if not allow_group_manager:
            return GROUP_ENABLE_PERMISSION_DENIED
        return COMMAND_PERMISSION_DENIED

    def _can_use_command(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> bool:
        if self._check_global_permission(event):
            return True
        return (
            allow_group_manager
            and dehydrate_event_snapshot(event).sender_is_group_manager
        )

    def _check_global_permission(self, event: AstrMessageEvent) -> bool:
        snapshot = dehydrate_event_snapshot(event)
        if not snapshot.sender_id:
            return False
        try:
            config = self.context.get_config()
        except Exception:
            return False

        admins = _config_value(config, "admins_id")
        if admins is None:
            admins = _config_value(config, "admin_ids")
        return snapshot.sender_id in _normalized_id_set(admins)

    def _platform_actions_for_event(self, event: AstrMessageEvent) -> PlatformActions:
        if self.platform_actions is not None:
            return self.platform_actions

        snapshot = dehydrate_event_snapshot(event)
        if snapshot.platform != "aiocqhttp":
            return QQPlatformActions()
        return OneBotV11PlatformActions(extract_onebot_action_client(event))

    @staticmethod
    def _is_own_command(text: str) -> bool:
        stripped = text.lstrip()
        return any(stripped.startswith(prefix) for prefix in COMMAND_PREFIXES)


def _config_value(config: object, key: str) -> object:
    if hasattr(config, "get"):
        try:
            value = config.get(key)
        except Exception:
            value = None
        if value is not None:
            return value
    try:
        return getattr(config, key, None)
    except Exception:
        return None


def _normalized_id_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {
            item
            for item in (part.strip() for part in value.replace(",", " ").split())
            if item
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return {item for item in (str(raw).strip() for raw in value) if item}
    normalized = str(value).strip()
    if not normalized:
        return set()
    return {normalized}
