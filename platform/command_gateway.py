from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .astrbot_event_adapter import (
    dehydrate_event_snapshot,
    extract_onebot_action_client,
)
from ..commands.command_controller import CommandController
from .platform_actions import PlatformActions
from .platform_action_factory import PlatformActionFactory


class CommandGateway:
    def __init__(
        self,
        controller: CommandController,
        platform_action_factory: PlatformActionFactory,
    ) -> None:
        self._controller = controller
        self._platform_action_factory = platform_action_factory

    def command_result(self, event: AstrMessageEvent, text: str):
        event.stop_event()
        return event.plain_result(text)

    def command_denial(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> str | None:
        return self._controller.command_denial(
            dehydrate_event_snapshot(event),
            allow_group_manager=allow_group_manager,
        )

    def can_use_command(
        self,
        event: AstrMessageEvent,
        *,
        allow_group_manager: bool = True,
    ) -> bool:
        return self._controller.can_use_command(
            dehydrate_event_snapshot(event),
            allow_group_manager=allow_group_manager,
        )

    def check_global_permission(self, event: AstrMessageEvent) -> bool:
        return self._controller.check_global_permission(dehydrate_event_snapshot(event))

    def platform_actions_for_event(self, event: AstrMessageEvent) -> PlatformActions:
        snapshot = dehydrate_event_snapshot(event)
        return self._platform_action_factory.for_platform(
            snapshot.platform,
            extract_onebot_action_client(event),
        )

    async def group_admin_exempt_response_text(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        return await self._controller.group_admin_exempt_response(
            dehydrate_event_snapshot(event),
            action,
        )

    async def group_admin_exempt_text(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        return await self._controller.group_admin_exempt_text(
            dehydrate_event_snapshot(event),
            action,
        )

    async def bind(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        push_group: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.bind(
                dehydrate_event_snapshot(event),
                listening_group,
                push_group,
            ),
        )

    async def mute(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        seconds: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.mute(
                dehydrate_event_snapshot(event),
                group_id,
                seconds,
            ),
        )

    async def mute_stack(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        multiplier: str = "",
        reset_seconds: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.mute_stack(
                dehydrate_event_snapshot(event),
                group_id,
                multiplier,
                reset_seconds,
            ),
        )

    async def probe(self, event: AstrMessageEvent):
        platform_actions = self.platform_actions_for_event(event)
        return self.command_result(
            event,
            await self._controller.probe(
                dehydrate_event_snapshot(event),
                platform_actions,
            ),
        )

    async def forward_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        platform_actions = self.platform_actions_for_event(event)
        return self.command_result(
            event,
            await self._controller.forward_probe(
                dehydrate_event_snapshot(event),
                platform_actions,
                target_group,
            ),
        )

    async def report_dry_run(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        days: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.report_dry_run(
                dehydrate_event_snapshot(event),
                listening_group,
                days,
            ),
        )

    async def file_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        platform_actions = self.platform_actions_for_event(event)
        return self.command_result(
            event,
            await self._controller.file_probe(
                dehydrate_event_snapshot(event),
                platform_actions,
                target_group,
            ),
        )

    async def help(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.help(dehydrate_event_snapshot(event)),
        )

    async def status(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.status(dehydrate_event_snapshot(event)),
        )

    async def overview(self, event: AstrMessageEvent, output_format: str = ""):
        return self.command_result(
            event,
            await self._controller.overview(
                dehydrate_event_snapshot(event),
                output_format,
            ),
        )

    async def enable(self, event: AstrMessageEvent, group_id: str = ""):
        return self.command_result(
            event,
            await self._controller.enable(dehydrate_event_snapshot(event), group_id),
        )

    async def disable(self, event: AstrMessageEvent, group_id: str = ""):
        return self.command_result(
            event,
            await self._controller.disable(dehydrate_event_snapshot(event), group_id),
        )

    async def group_status(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_status(dehydrate_event_snapshot(event)),
        )

    async def group_enable(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_enable(dehydrate_event_snapshot(event)),
        )

    async def group_disable(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_disable(dehydrate_event_snapshot(event)),
        )

    async def group_add(self, event: AstrMessageEvent, word: str):
        return self.command_result(
            event,
            await self._controller.group_add(dehydrate_event_snapshot(event), word),
        )

    async def group_remove(self, event: AstrMessageEvent, word: str):
        return self.command_result(
            event,
            await self._controller.group_remove(dehydrate_event_snapshot(event), word),
        )

    async def group_list(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_list(dehydrate_event_snapshot(event)),
        )

    async def group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        return self.command_result(
            event,
            await self._controller.group_admin_exempt_response(
                dehydrate_event_snapshot(event),
                action,
            ),
        )
