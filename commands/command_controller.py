from __future__ import annotations

from .command_auth import CommandAuthorizer
from .command_service import ChatFilterCommandService
from .command_validation import is_valid_qq_group_id
from ..services.file_probe_service import FileProbeService
from ..domain.models import PlatformEventSnapshot
from ..platform.platform_actions import PlatformActions, format_platform_probe
from ..services.report_service import ViolationReportService


GROUP_ADMIN_EXEMPT_USAGE = (
    "Usage: .cf group admin-exempt status|enable|disable (alias: exempt)"
)
GROUP_ENABLE_USAGE = "Usage: .cf enable [group id]"
GROUP_DISABLE_USAGE = "Usage: .cf disable [group id]"
TARGET_GROUP_PERMISSION_DENIED = (
    "Chat Filter target group permission denied: "
    "requires AstrBot admin permission."
)


class CommandController:
    def __init__(
        self,
        command_service: ChatFilterCommandService,
        report_service: ViolationReportService | None,
        file_probe_service: FileProbeService | None,
        authorizer: CommandAuthorizer,
    ) -> None:
        self._command_service = command_service
        self._report_service = report_service
        self._file_probe_service = file_probe_service
        self._authorizer = authorizer

    def command_denial(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        allow_group_manager: bool = True,
    ) -> str | None:
        return self._authorizer.command_denial(
            snapshot,
            allow_group_manager=allow_group_manager,
        )

    def can_use_command(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        allow_group_manager: bool = True,
    ) -> bool:
        return self._authorizer.can_use_command(
            snapshot,
            allow_group_manager=allow_group_manager,
        )

    def check_global_permission(self, snapshot: PlatformEventSnapshot) -> bool:
        return self._authorizer.check_global_permission(snapshot)

    async def bind(
        self,
        snapshot: PlatformEventSnapshot,
        listening_group: str = "",
        push_group: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        if listening_group == "list" and not push_group:
            return await self._command_service.format_push_bindings(snapshot.platform)

        return await self._command_service.add_push_binding(
            snapshot,
            listening_group_id=listening_group,
            push_group_id=push_group,
        )

    async def mute(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        seconds: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        if group_id == "list" and not seconds:
            return await self._command_service.format_group_mute_policies(
                snapshot.platform
            )

        return await self._command_service.set_group_mute_duration(
            snapshot,
            group_id=group_id,
            seconds=seconds,
        )

    async def mute_stack(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        multiplier: str = "",
        reset_seconds: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        if group_id == "list" and not multiplier and not reset_seconds:
            return await self._command_service.format_group_mute_escalation_policies(
                snapshot.platform
            )

        return await self._command_service.set_group_mute_escalation(
            snapshot,
            group_id=group_id,
            multiplier=multiplier,
            reset_seconds=reset_seconds,
        )

    async def probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        capabilities = platform_actions.probe_capabilities(snapshot.platform)
        return format_platform_probe(snapshot, capabilities)

    async def forward_probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
        target_group: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.run_forward_probe(
            snapshot,
            platform_actions,
            target_group,
        )

    async def report_dry_run(
        self,
        snapshot: PlatformEventSnapshot,
        listening_group: str = "",
        days: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._report_service.generate_dry_run(
            snapshot,
            listening_group_id=listening_group,
            days=days,
        )

    async def file_probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
        target_group: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._file_probe_service.run_file_probe(
            snapshot,
            platform_actions,
            target_group,
        )

    async def help(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_help()

    async def status(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_status()

    async def overview(
        self,
        snapshot: PlatformEventSnapshot,
        output_format: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.format_overview(
            snapshot.platform,
            output_format,
        )

    async def enable(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        denial = self.command_denial(snapshot, allow_group_manager=False)
        if denial:
            return denial

        group_key = _target_group_key(snapshot, group_id)
        if group_key is None:
            return GROUP_ENABLE_USAGE
        return await self._command_service.set_group_enabled(group_key, True)

    async def disable(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = group_id.strip()
        if target_group_id:
            if not self.check_global_permission(snapshot):
                return TARGET_GROUP_PERMISSION_DENIED
        else:
            denial = self.command_denial(snapshot)
            if denial:
                return denial

        group_key = _target_group_key(snapshot, target_group_id)
        if group_key is None:
            return GROUP_DISABLE_USAGE
        return await self._command_service.set_group_enabled(group_key, False)

    async def group_status(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_group_status(_group_key(snapshot))

    async def group_enable(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot, allow_group_manager=False)
        if denial:
            return denial

        return await self._command_service.set_group_enabled(
            _group_key(snapshot),
            True,
        )

    async def group_disable(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.set_group_enabled(
            _group_key(snapshot),
            False,
        )

    async def group_add(
        self,
        snapshot: PlatformEventSnapshot,
        word: str,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.add_group_word(_group_key(snapshot), word)

    async def group_remove(
        self,
        snapshot: PlatformEventSnapshot,
        word: str,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.remove_group_word(
            _group_key(snapshot),
            word,
        )

    async def group_list(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_group_words(_group_key(snapshot))

    async def group_admin_exempt_response(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial
        return await self.group_admin_exempt_text(snapshot, action)

    async def group_admin_exempt_text(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
    ) -> str:
        group_key = _group_key(snapshot)
        normalized_action = action.strip().casefold()
        if normalized_action in ("", "status"):
            return self._command_service.format_group_admin_exempt_status(group_key)
        if normalized_action in ("enable", "enabled", "on", "true", "1"):
            return await self._command_service.set_group_admin_exempt_enabled(
                group_key,
                True,
            )
        if normalized_action in ("disable", "disabled", "off", "false", "0"):
            return await self._command_service.set_group_admin_exempt_enabled(
                group_key,
                False,
            )
        return GROUP_ADMIN_EXEMPT_USAGE


def _group_key(snapshot: PlatformEventSnapshot) -> str | None:
    if not snapshot.platform or not snapshot.group_id:
        return None
    return f"{snapshot.platform}:{snapshot.group_id}"


def _target_group_key(
    snapshot: PlatformEventSnapshot,
    group_id: str = "",
) -> str | None:
    target_group_id = group_id.strip()
    if not target_group_id:
        return _group_key(snapshot)
    if not snapshot.platform or not is_valid_qq_group_id(target_group_id):
        return None
    return f"{snapshot.platform}:{target_group_id}"
