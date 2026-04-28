from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .platform.astrbot_event_adapter import (
    dehydrate_group_message,
    extract_onebot_action_client,
)
from .commands.command_auth import (
    COMMAND_PERMISSION_DENIED,
    GROUP_ENABLE_PERMISSION_DENIED,
)
from .commands.command_controller import GROUP_ADMIN_EXEMPT_USAGE
from .platform.platform_actions import PlatformActions
from .runtime.plugin_runtime import build_chat_filter_runtime


COMMAND_PREFIXES = ("/chatfilter", "/cf", ".cf")

__all__ = (
    "COMMAND_PERMISSION_DENIED",
    "GROUP_ADMIN_EXEMPT_USAGE",
    "GROUP_ENABLE_PERMISSION_DENIED",
    "ChatFilterPlugin",
)


class ChatFilterPlugin(Star):
    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
        platform_actions: PlatformActions | None = None,
    ) -> None:
        super().__init__(context)
        runtime = build_chat_filter_runtime(
            context,
            config,
            platform_actions,
            logger,
            platform_actions_provider=self._configured_platform_actions,
        )
        self.settings = runtime.settings
        self.data_root = runtime.data_root
        self.repository = runtime.repository
        self.rule_snapshot = runtime.rule_snapshot
        self.state = runtime.state
        self.command_service = runtime.command_service
        self.matcher = runtime.matcher
        self.platform_actions = runtime.platform_actions
        self.violation_action_executor = runtime.violation_action_executor
        self.violation_recorder = runtime.violation_recorder
        self.message_filter_service = runtime.message_filter_service
        self.report_service = runtime.report_service
        self.file_probe_service = runtime.file_probe_service
        self._platform_action_factory = runtime.platform_action_factory
        self._command_gateway = runtime.command_gateway

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = dehydrate_group_message(event)
        if self._is_own_command(message.text):
            return

        platform_actions = self._platform_action_factory.for_platform(
            message.platform,
            extract_onebot_action_client(event),
        )
        result = await self.message_filter_service.handle_group_message(
            message,
            platform_actions,
        )
        if result.stop_event:
            event.stop_event()
        if result.warn_user:
            yield event.plain_result(result.warning_message)

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
        yield await self._command_gateway.bind(event, listening_group, push_group)

    @cf.command("mute")
    async def cf_mute(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        seconds: str = "",
    ):
        yield await self._command_gateway.mute(event, group_id, seconds)

    @cf.command("mute-stack")
    async def cf_mute_stack(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        multiplier: str = "",
        reset_seconds: str = "",
    ):
        yield await self._command_gateway.mute_stack(
            event,
            group_id,
            multiplier,
            reset_seconds,
        )

    @cf.command("probe")
    async def cf_probe(self, event: AstrMessageEvent):
        yield await self._command_gateway.probe(event)

    @cf.command("forward-probe")
    async def cf_forward_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        yield await self._command_gateway.forward_probe(event, target_group)

    @cf.command("report-dry-run")
    async def cf_report_dry_run(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        days: str = "",
    ):
        yield await self._command_gateway.report_dry_run(
            event,
            listening_group,
            days,
        )

    @cf.command("file-probe")
    async def cf_file_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        yield await self._command_gateway.file_probe(event, target_group)

    @cf.command("help")
    async def cf_help(self, event: AstrMessageEvent):
        yield await self._command_gateway.help(event)

    @cf.command("status")
    async def cf_status(self, event: AstrMessageEvent):
        yield await self._command_gateway.status(event)

    @cf.command("enable")
    async def cf_enable(self, event: AstrMessageEvent):
        yield await self._command_gateway.enable(event)

    @cf.command("disable")
    async def cf_disable(self, event: AstrMessageEvent):
        yield await self._command_gateway.disable(event)

    @cf.group("group")
    def cf_group():
        pass

    @cf_group.command("status")
    async def cf_group_status(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_status(event)

    @cf_group.command("enable")
    async def cf_group_enable(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_enable(event)

    @cf_group.command("disable")
    async def cf_group_disable(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_disable(event)

    @cf_group.command("add")
    async def cf_group_add(self, event: AstrMessageEvent, word: str):
        yield await self._command_gateway.group_add(event, word)

    @cf_group.command("remove")
    async def cf_group_remove(self, event: AstrMessageEvent, word: str):
        yield await self._command_gateway.group_remove(event, word)

    @cf_group.command("list")
    async def cf_group_list(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_list(event)

    @cf_group.command("admin-exempt")
    async def cf_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self._command_gateway.group_admin_exempt(event, action)

    @cf_group.command("exempt")
    async def cf_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self._command_gateway.group_admin_exempt(event, action)

    @chatfilter.command("help")
    async def chatfilter_help(self, event: AstrMessageEvent):
        yield await self._command_gateway.help(event)

    @chatfilter.command("status")
    async def chatfilter_status(self, event: AstrMessageEvent):
        yield await self._command_gateway.status(event)

    @chatfilter.command("enable")
    async def chatfilter_enable(self, event: AstrMessageEvent):
        yield await self._command_gateway.enable(event)

    @chatfilter.command("disable")
    async def chatfilter_disable(self, event: AstrMessageEvent):
        yield await self._command_gateway.disable(event)

    @chatfilter.group("group")
    def chatfilter_group():
        pass

    @chatfilter_group.command("status")
    async def chatfilter_group_status(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_status(event)

    @chatfilter_group.command("enable")
    async def chatfilter_group_enable(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_enable(event)

    @chatfilter_group.command("disable")
    async def chatfilter_group_disable(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_disable(event)

    @chatfilter_group.command("add")
    async def chatfilter_group_add(self, event: AstrMessageEvent, word: str):
        yield await self._command_gateway.group_add(event, word)

    @chatfilter_group.command("remove")
    async def chatfilter_group_remove(self, event: AstrMessageEvent, word: str):
        yield await self._command_gateway.group_remove(event, word)

    @chatfilter_group.command("list")
    async def chatfilter_group_list(self, event: AstrMessageEvent):
        yield await self._command_gateway.group_list(event)

    @chatfilter_group.command("admin-exempt")
    async def chatfilter_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self._command_gateway.group_admin_exempt(event, action)

    @chatfilter_group.command("exempt")
    async def chatfilter_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self._command_gateway.group_admin_exempt(event, action)

    def _configured_platform_actions(self) -> PlatformActions | None:
        return getattr(self, "platform_actions", None)

    @staticmethod
    def _is_own_command(text: str) -> bool:
        stripped = text.lstrip()
        return any(stripped.startswith(prefix) for prefix in COMMAND_PREFIXES)
