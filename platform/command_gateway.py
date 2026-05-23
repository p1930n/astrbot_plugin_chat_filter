from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .astrbot_event_adapter import (
    dehydrate_event_snapshot,
    extract_onebot_action_client,
)
from ..commands.command_controller import CommandController
from ..domain.models import PlatformEventSnapshot
from .group_member_role_resolver import GroupMemberRoleResolver
from .platform_actions import PlatformActions
from .platform_action_factory import PlatformActionFactory


class CommandGateway:
    def __init__(
        self,
        controller: CommandController,
        platform_action_factory: PlatformActionFactory,
        group_member_role_resolver: GroupMemberRoleResolver | None = None,
    ) -> None:
        self._controller = controller
        self._platform_action_factory = platform_action_factory
        self._group_member_role_resolver = (
            group_member_role_resolver or GroupMemberRoleResolver()
        )

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
            await self._snapshot_for_event(event),
            action,
        )

    async def group_admin_exempt_text(
        self,
        event: AstrMessageEvent,
        action: str,
    ) -> str:
        return await self._controller.group_admin_exempt_text(
            await self._snapshot_for_event(event),
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
                await self._snapshot_for_event(event),
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
                await self._snapshot_for_event(event),
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
                await self._snapshot_for_event(event),
                group_id,
                multiplier,
                reset_seconds,
            ),
        )

    async def probe(self, event: AstrMessageEvent):
        snapshot = await self._snapshot_for_event(event)
        platform_actions = self._platform_actions_for_snapshot(snapshot, event)
        return self.command_result(
            event,
            await self._controller.probe(
                snapshot,
                platform_actions,
            ),
        )

    async def forward_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        snapshot = await self._snapshot_for_event(event)
        platform_actions = self._platform_actions_for_snapshot(snapshot, event)
        return self.command_result(
            event,
            await self._controller.forward_probe(
                snapshot,
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
                await self._snapshot_for_event(event),
                listening_group,
                days,
            ),
        )

    async def file_probe(
        self,
        event: AstrMessageEvent,
        target_group: str = "",
    ):
        snapshot = await self._snapshot_for_event(event)
        platform_actions = self._platform_actions_for_snapshot(snapshot, event)
        return self.command_result(
            event,
            await self._controller.file_probe(
                snapshot,
                platform_actions,
                target_group,
            ),
        )

    async def help(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.help(await self._snapshot_for_event(event)),
        )

    async def status(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.status(await self._snapshot_for_event(event)),
        )

    async def overview(self, event: AstrMessageEvent, output_format: str = ""):
        return self.command_result(
            event,
            await self._controller.overview(
                await self._snapshot_for_event(event),
                output_format,
            ),
        )

    async def regex_skips(self, event: AstrMessageEvent, limit: str = ""):
        return self.command_result(
            event,
            await self._controller.regex_skips(
                await self._snapshot_for_event(event),
                limit,
            ),
        )

    async def metrics(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.metrics(await self._snapshot_for_event(event)),
        )

    async def action_status(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.action_status(
                await self._snapshot_for_event(event),
                group_id,
            ),
        )

    async def action_toggle(
        self,
        event: AstrMessageEvent,
        action: str,
        group_id: str = "",
        enabled: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.action_toggle(
                await self._snapshot_for_event(event),
                action,
                group_id,
                enabled,
            ),
        )

    async def action_mode(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        mode: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.action_mode(
                await self._snapshot_for_event(event),
                group_id,
                mode,
            ),
        )

    async def action_overview(
        self,
        event: AstrMessageEvent,
        output_format: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.action_overview(
                await self._snapshot_for_event(event),
                output_format,
            ),
        )

    async def enable(self, event: AstrMessageEvent, group_id: str = ""):
        return self.command_result(
            event,
            await self._controller.enable(
                await self._snapshot_for_event(event),
                group_id,
            ),
        )

    async def disable(self, event: AstrMessageEvent, group_id: str = ""):
        return self.command_result(
            event,
            await self._controller.disable(
                await self._snapshot_for_event(event),
                group_id,
            ),
        )

    async def group_status(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_status(await self._snapshot_for_event(event)),
        )

    async def group_enable(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_enable(await self._snapshot_for_event(event)),
        )

    async def group_disable(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_disable(await self._snapshot_for_event(event)),
        )

    async def group_add(self, event: AstrMessageEvent, word: str):
        return self.command_result(
            event,
            await self._controller.group_add(
                await self._snapshot_for_event(event),
                word,
            ),
        )

    async def group_add_to(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        word: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.group_add_to(
                await self._snapshot_for_event(event),
                group_id,
                word,
            ),
        )

    async def group_remove(self, event: AstrMessageEvent, word: str):
        return self.command_result(
            event,
            await self._controller.group_remove(
                await self._snapshot_for_event(event),
                word,
            ),
        )

    async def group_remove_to(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        word: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.group_remove_to(
                await self._snapshot_for_event(event),
                group_id,
                word,
            ),
        )

    async def group_list(self, event: AstrMessageEvent):
        return self.command_result(
            event,
            await self._controller.group_list(await self._snapshot_for_event(event)),
        )

    async def group_bypass_add(
        self,
        event: AstrMessageEvent,
        group_id: str = "",
        word: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.group_bypass_add(
                await self._snapshot_for_event(event),
                group_id,
                word,
            ),
        )

    async def group_bypass_remove(
        self,
        event: AstrMessageEvent,
        group_id_or_word: str = "",
        word: str = "",
    ):
        return self.command_result(
            event,
            await self._controller.group_bypass_remove(
                await self._snapshot_for_event(event),
                group_id_or_word,
                word,
            ),
        )

    async def group_bypass_list(self, event: AstrMessageEvent, group_id: str = ""):
        return self.command_result(
            event,
            await self._controller.group_bypass_list(
                await self._snapshot_for_event(event),
                group_id,
            ),
        )

    async def group_admin_exempt(
        self,
        event: AstrMessageEvent,
        action: str = "status",
    ):
        return self.command_result(
            event,
            await self._controller.group_admin_exempt_response(
                await self._snapshot_for_event(event),
                action,
            ),
        )

    async def _snapshot_for_event(
        self,
        event: AstrMessageEvent,
    ) -> PlatformEventSnapshot:
        return await self._group_member_role_resolver.resolve_snapshot(
            dehydrate_event_snapshot(event),
            extract_onebot_action_client(event),
        )

    def _platform_actions_for_snapshot(
        self,
        snapshot: PlatformEventSnapshot,
        event: AstrMessageEvent,
    ) -> PlatformActions:
        return self._platform_action_factory.for_platform(
            snapshot.platform,
            extract_onebot_action_client(event),
        )
