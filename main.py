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
from .matcher import ChatFilterMatcher
from .platform_actions import (
    OneBotV11PlatformActions,
    PlatformActions,
    QQPlatformActions,
    format_platform_probe,
)
from .repository import ChatFilterRepository, default_data_root
from .settings import ChatFilterSettings
from .violation_actions import ViolationActionExecutor
from .violation_records import ViolationRecorder


COMMAND_PREFIXES = ("/chatfilter", "/cf", ".cf")


class ChatFilterPlugin(Star):
    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
        platform_actions: PlatformActions | None = None,
    ) -> None:
        super().__init__(context)
        self.settings = ChatFilterSettings.from_config(config)
        self.repository = ChatFilterRepository(
            default_data_root(),
            max_word_count=self.settings.max_word_count,
            max_word_length=self.settings.max_word_length,
        )
        self.matcher = ChatFilterMatcher()
        self.platform_actions = platform_actions
        self.violation_action_executor = ViolationActionExecutor(
            self.repository,
            logger=logger,
            default_mute_duration_seconds=self.settings.mute_duration_seconds,
        )
        self.violation_recorder = ViolationRecorder(self.repository, logger)
        self.state = load_runtime_state(self.repository, logger)
        self.command_service = ChatFilterCommandService(
            self.repository,
            self.state,
            self.settings,
            logger,
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

        result = self.matcher.detect(message, self.settings, self.state)
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @cf.command("bind")
    async def cf_bind(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        push_group: str = "",
    ):
        snapshot = dehydrate_event_snapshot(event)
        if listening_group == "list" and not push_group:
            yield event.plain_result(
                await self.command_service.format_push_bindings(snapshot.platform)
            )
            return

        yield event.plain_result(
            await self.command_service.add_push_binding(
                snapshot,
                listening_group_id=listening_group,
                push_group_id=push_group,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @cf.command("mute")
    async def cf_mute(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        seconds: str = "",
    ):
        snapshot = dehydrate_event_snapshot(event)
        if group_id == "list" and not seconds:
            yield event.plain_result(
                await self.command_service.format_group_mute_policies(
                    snapshot.platform
                )
            )
            return

        yield event.plain_result(
            await self.command_service.set_group_mute_duration(
                snapshot,
                group_id=group_id,
                seconds=seconds,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @cf.command("probe")
    async def cf_probe(self, event: AstrMessageEvent):
        snapshot = dehydrate_event_snapshot(event)
        capabilities = self._platform_actions_for_event(event).probe_capabilities(
            snapshot.platform
        )
        yield event.plain_result(format_platform_probe(snapshot, capabilities))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("status")
    async def chatfilter_status(self, event: AstrMessageEvent):
        yield event.plain_result(self.command_service.format_status())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("enable")
    async def chatfilter_enable(self, event: AstrMessageEvent):
        yield event.plain_result(await self.command_service.set_global_enabled(True))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("disable")
    async def chatfilter_disable(self, event: AstrMessageEvent):
        yield event.plain_result(await self.command_service.set_global_enabled(False))

    @chatfilter.group("group")
    def chatfilter_group():
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("status")
    async def chatfilter_group_status(self, event: AstrMessageEvent):
        yield event.plain_result(
            self.command_service.format_group_status(
                current_group_key_from_event(event)
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("enable")
    async def chatfilter_group_enable(self, event: AstrMessageEvent):
        yield event.plain_result(
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                True,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("disable")
    async def chatfilter_group_disable(self, event: AstrMessageEvent):
        yield event.plain_result(
            await self.command_service.set_group_enabled(
                current_group_key_from_event(event),
                False,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("add")
    async def chatfilter_group_add(self, event: AstrMessageEvent, word: str):
        yield event.plain_result(
            await self.command_service.add_group_word(
                current_group_key_from_event(event),
                word,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("remove")
    async def chatfilter_group_remove(self, event: AstrMessageEvent, word: str):
        yield event.plain_result(
            await self.command_service.remove_group_word(
                current_group_key_from_event(event),
                word,
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("list")
    async def chatfilter_group_list(self, event: AstrMessageEvent):
        yield event.plain_result(
            self.command_service.format_group_words(
                current_group_key_from_event(event)
            )
        )

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
