from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .astrbot_event_adapter import (
    dehydrate_group_message,
    extract_onebot_action_client,
    field_state,
    has_required_message_scope,
)
from .command_auth import (
    COMMAND_PERMISSION_DENIED,
    GROUP_ENABLE_PERMISSION_DENIED,
    CommandAuthorizer,
)
from .command_controller import GROUP_ADMIN_EXEMPT_USAGE, CommandController
from .command_gateway import CommandGateway
from .command_service import ChatFilterCommandService, load_runtime_state
from .file_probe_service import FileProbeService
from .matcher import ChatFilterMatcher
from .platform_action_factory import PlatformActionFactory
from .platform_actions import PlatformActions
from .report_service import ViolationReportService
from .repository import ChatFilterRepository, default_data_root
from .rule_snapshot import RuleSnapshot
from .settings import ChatFilterSettings
from .violation_actions import ViolationActionExecutor
from .violation_records import ViolationRecorder


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
        self._command_authorizer = CommandAuthorizer(self._get_config)
        self._command_controller = CommandController(
            self.command_service,
            self.report_service,
            self.file_probe_service,
            self.command_authorizer,
        )
        self._platform_action_factory = PlatformActionFactory(
            self._configured_platform_actions
        )
        self._command_gateway = CommandGateway(
            self.command_controller,
            self.platform_action_factory,
        )

    @property
    def command_authorizer(self) -> CommandAuthorizer:
        authorizer = getattr(self, "_command_authorizer", None)
        if authorizer is None:
            authorizer = CommandAuthorizer(self._get_config)
            self._command_authorizer = authorizer
        return authorizer

    @property
    def command_controller(self) -> CommandController:
        controller = getattr(self, "_command_controller", None)
        if controller is None:
            controller = CommandController(
                self.command_service,
                getattr(self, "report_service", None),
                getattr(self, "file_probe_service", None),
                self.command_authorizer,
            )
            self._command_controller = controller
        return controller

    @property
    def platform_action_factory(self) -> PlatformActionFactory:
        factory = getattr(self, "_platform_action_factory", None)
        if factory is None:
            factory = PlatformActionFactory(self._configured_platform_actions)
            self._platform_action_factory = factory
        return factory

    @property
    def command_gateway(self) -> CommandGateway:
        gateway = getattr(self, "_command_gateway", None)
        if gateway is None:
            gateway = CommandGateway(
                self.command_controller,
                self.platform_action_factory,
            )
            self._command_gateway = gateway
        return gateway

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

        platform_actions = self.platform_action_factory.for_platform(
            message.platform,
            extract_onebot_action_client(event),
        )
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
        yield await self.command_gateway.bind(event, listening_group, push_group)

    @cf.command("mute")
    async def cf_mute(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        seconds: str = "",
    ):
        yield await self.command_gateway.mute(event, group_id, seconds)

    @cf.command("mute-stack")
    async def cf_mute_stack(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        multiplier: str = "",
        reset_seconds: str = "",
    ):
        yield await self.command_gateway.mute_stack(
            event,
            group_id,
            multiplier,
            reset_seconds,
        )

    @cf.command("probe")
    async def cf_probe(self, event: AstrMessageEvent):
        yield await self.command_gateway.probe(event)

    @cf.command("forward-probe")
    async def cf_forward_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        yield await self.command_gateway.forward_probe(event, target_group)

    @cf.command("report-dry-run")
    async def cf_report_dry_run(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        days: str = "",
    ):
        yield await self.command_gateway.report_dry_run(
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
        yield await self.command_gateway.file_probe(event, target_group)

    @cf.command("help")
    async def cf_help(self, event: AstrMessageEvent):
        yield await self.command_gateway.help(event)

    @cf.command("status")
    async def cf_status(self, event: AstrMessageEvent):
        yield await self.command_gateway.status(event)

    @cf.command("enable")
    async def cf_enable(self, event: AstrMessageEvent):
        yield await self.command_gateway.enable(event)

    @cf.command("disable")
    async def cf_disable(self, event: AstrMessageEvent):
        yield await self.command_gateway.disable(event)

    @cf.group("group")
    def cf_group():
        pass

    @cf_group.command("status")
    async def cf_group_status(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_status(event)

    @cf_group.command("enable")
    async def cf_group_enable(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_enable(event)

    @cf_group.command("disable")
    async def cf_group_disable(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_disable(event)

    @cf_group.command("add")
    async def cf_group_add(self, event: AstrMessageEvent, word: str):
        yield await self.command_gateway.group_add(event, word)

    @cf_group.command("remove")
    async def cf_group_remove(self, event: AstrMessageEvent, word: str):
        yield await self.command_gateway.group_remove(event, word)

    @cf_group.command("list")
    async def cf_group_list(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_list(event)

    @cf_group.command("admin-exempt")
    async def cf_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self.command_gateway.group_admin_exempt(event, action)

    @cf_group.command("exempt")
    async def cf_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self.command_gateway.group_admin_exempt(event, action)

    @chatfilter.command("help")
    async def chatfilter_help(self, event: AstrMessageEvent):
        yield await self.command_gateway.help(event)

    @chatfilter.command("status")
    async def chatfilter_status(self, event: AstrMessageEvent):
        yield await self.command_gateway.status(event)

    @chatfilter.command("enable")
    async def chatfilter_enable(self, event: AstrMessageEvent):
        yield await self.command_gateway.enable(event)

    @chatfilter.command("disable")
    async def chatfilter_disable(self, event: AstrMessageEvent):
        yield await self.command_gateway.disable(event)

    @chatfilter.group("group")
    def chatfilter_group():
        pass

    @chatfilter_group.command("status")
    async def chatfilter_group_status(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_status(event)

    @chatfilter_group.command("enable")
    async def chatfilter_group_enable(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_enable(event)

    @chatfilter_group.command("disable")
    async def chatfilter_group_disable(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_disable(event)

    @chatfilter_group.command("add")
    async def chatfilter_group_add(self, event: AstrMessageEvent, word: str):
        yield await self.command_gateway.group_add(event, word)

    @chatfilter_group.command("remove")
    async def chatfilter_group_remove(self, event: AstrMessageEvent, word: str):
        yield await self.command_gateway.group_remove(event, word)

    @chatfilter_group.command("list")
    async def chatfilter_group_list(self, event: AstrMessageEvent):
        yield await self.command_gateway.group_list(event)

    @chatfilter_group.command("admin-exempt")
    async def chatfilter_group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self.command_gateway.group_admin_exempt(event, action)

    @chatfilter_group.command("exempt")
    async def chatfilter_group_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        yield await self.command_gateway.group_admin_exempt(event, action)

    def _command_result(self, event: AstrMessageEvent, text: str):
        return self.command_gateway.command_result(event, text)

    async def _group_admin_exempt_command_response(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        return await self.command_gateway.group_admin_exempt_response_text(
            event,
            action,
        )

    async def _group_admin_exempt_command_text(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        return await self.command_gateway.group_admin_exempt_text(event, action)

    def _command_denial(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> str | None:
        return self.command_gateway.command_denial(
            event,
            allow_group_manager=allow_group_manager,
        )

    def _can_use_command(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> bool:
        return self.command_gateway.can_use_command(
            event,
            allow_group_manager=allow_group_manager,
        )

    def _check_global_permission(self, event: AstrMessageEvent) -> bool:
        return self.command_gateway.check_global_permission(event)

    def _platform_actions_for_event(self, event: AstrMessageEvent) -> PlatformActions:
        return self.command_gateway.platform_actions_for_event(event)

    def _configured_platform_actions(self) -> PlatformActions | None:
        return getattr(self, "platform_actions", None)

    def _get_config(self) -> object:
        return self.context.get_config()

    @staticmethod
    def _is_own_command(text: str) -> bool:
        stripped = text.lstrip()
        return any(stripped.startswith(prefix) for prefix in COMMAND_PREFIXES)
