from __future__ import annotations

from .command_runtime import (
    CommandLogger,
    CommandRuntimeService,
    load_runtime_state,
)
from .command_validation import (
    BIND_LIST_LIMIT as _BIND_LIST_LIMIT,
    MAX_QQ_GROUP_ID_LENGTH as _MAX_QQ_GROUP_ID_LENGTH,
    is_valid_qq_group_id,
    parse_mute_duration,
    parse_mute_escalation_multiplier,
    parse_mute_escalation_reset_seconds,
)
from ..services.forward_probe_service import (
    FORWARD_PROBE_TEXT as _FORWARD_PROBE_TEXT,
    ForwardProbeService,
)
from .global_command_service import GlobalCommandService
from .group_policy_command_service import GroupPolicyCommandService
from .action_policy_command_service import ActionPolicyCommandService
from .overview_command_service import OverviewCommandService
from ..domain.models import (
    GroupPolicy,
    PlatformEventSnapshot,
    PushBinding,
    RuntimeState,
)
from .mute_policy_command_service import MutePolicyCommandService
from ..platform.platform_actions import PlatformActions
from .push_binding_command_service import (
    PushBindingCommandService,
    group_push_bindings,
)
from ..persistence.repository import ChatFilterRepository
from ..domain.rule_snapshot import RuleSnapshot
from ..domain.settings import ChatFilterSettings


BIND_LIST_LIMIT = _BIND_LIST_LIMIT
MAX_QQ_GROUP_ID_LENGTH = _MAX_QQ_GROUP_ID_LENGTH
FORWARD_PROBE_TEXT = _FORWARD_PROBE_TEXT


class ChatFilterCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        state: RuntimeState,
        settings: ChatFilterSettings,
        rule_snapshot: RuleSnapshot,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._state = state
        self._settings = settings
        self._rule_snapshot = rule_snapshot
        self._logger = logger

        self._runtime = CommandRuntimeService(repository, state, logger)
        self._global_commands = GlobalCommandService(
            state,
            rule_snapshot,
        )
        self._group_policy_commands = GroupPolicyCommandService(
            state,
            settings,
            self._runtime,
        )
        self._action_policy_commands = ActionPolicyCommandService(
            repository,
            state,
            logger,
        )
        self._push_binding_commands = PushBindingCommandService(repository, logger)
        self._overview_commands = OverviewCommandService(repository, state, logger)
        self._mute_policy_commands = MutePolicyCommandService(
            repository,
            settings,
            logger,
        )
        self._forward_probe_service = ForwardProbeService()

    def format_status(self) -> str:
        return self._global_commands.format_status()

    def format_help(self) -> str:
        return self._global_commands.format_help()

    def format_regex_skips(self, limit: str = "") -> str:
        return self._global_commands.format_regex_skips(limit)

    def format_group_status(self, group_key: str | None) -> str:
        return self._group_policy_commands.format_group_status(group_key)

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        return await self._group_policy_commands.set_group_enabled(
            group_key,
            enabled,
        )

    async def set_group_admin_exempt_enabled(
        self,
        group_key: str | None,
        enabled: bool,
    ) -> str:
        return await self._group_policy_commands.set_group_admin_exempt_enabled(
            group_key,
            enabled,
        )

    def format_group_admin_exempt_status(self, group_key: str | None) -> str:
        return self._group_policy_commands.format_group_admin_exempt_status(group_key)

    async def add_group_word(self, group_key: str | None, word: str) -> str:
        return await self._group_policy_commands.add_group_word(group_key, word)

    async def remove_group_word(self, group_key: str | None, word: str) -> str:
        return await self._group_policy_commands.remove_group_word(group_key, word)

    def format_group_words(self, group_key: str | None) -> str:
        return self._group_policy_commands.format_group_words(group_key)

    async def add_push_binding(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        listening_group_id: str,
        push_group_id: str,
    ) -> str:
        return await self._push_binding_commands.add_push_binding(
            snapshot,
            listening_group_id=listening_group_id,
            push_group_id=push_group_id,
        )

    async def format_push_bindings(self, platform: str) -> str:
        return await self._push_binding_commands.format_push_bindings(platform)

    async def format_overview(self, platform: str, output_format: str = "") -> str:
        return await self._overview_commands.format_overview(platform, output_format)

    async def format_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> str:
        return await self._action_policy_commands.format_group_action_policy(
            platform=platform,
            group_id=group_id,
        )

    async def set_group_action_toggle(
        self,
        *,
        platform: str,
        group_id: str,
        action: str,
        enabled: str,
        updated_by: str,
    ) -> str:
        return await self._action_policy_commands.set_group_action_toggle(
            platform=platform,
            group_id=group_id,
            action=action,
            enabled=enabled,
            updated_by=updated_by,
        )

    async def set_group_action_mode(
        self,
        *,
        platform: str,
        group_id: str,
        mode: str,
        updated_by: str,
    ) -> str:
        return await self._action_policy_commands.set_group_action_mode(
            platform=platform,
            group_id=group_id,
            mode=mode,
            updated_by=updated_by,
        )

    async def format_action_policy_overview(
        self,
        platform: str,
        output_format: str = "",
    ) -> str:
        return await self._action_policy_commands.format_action_policy_overview(
            platform,
            output_format,
        )

    async def set_group_mute_duration(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        group_id: str,
        seconds: str,
    ) -> str:
        return await self._mute_policy_commands.set_group_mute_duration(
            snapshot,
            group_id=group_id,
            seconds=seconds,
        )

    async def format_group_mute_policies(self, platform: str) -> str:
        return await self._mute_policy_commands.format_group_mute_policies(platform)

    async def set_group_mute_escalation(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        group_id: str,
        multiplier: str,
        reset_seconds: str,
    ) -> str:
        return await self._mute_policy_commands.set_group_mute_escalation(
            snapshot,
            group_id=group_id,
            multiplier=multiplier,
            reset_seconds=reset_seconds,
        )

    async def format_group_mute_escalation_policies(self, platform: str) -> str:
        return await self._mute_policy_commands.format_group_mute_escalation_policies(
            platform
        )

    async def run_forward_probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
        target_group_id: str,
    ) -> str:
        return await self._forward_probe_service.run_forward_probe(
            snapshot,
            platform_actions,
            target_group_id,
        )

    async def _try_save_state(self) -> bool:
        return await self._runtime.try_save_state()

    def _mutable_group_policy(self, group_key: str) -> GroupPolicy:
        return self._runtime.mutable_group_policy(group_key)


def _is_valid_qq_group_id(value: str) -> bool:
    return is_valid_qq_group_id(value)


def _group_push_bindings(bindings: list[PushBinding]) -> dict[str, list[str]]:
    return group_push_bindings(bindings)


def _parse_mute_duration(value: str) -> int | None:
    return parse_mute_duration(value)


def _parse_mute_escalation_multiplier(value: str) -> int | None:
    return parse_mute_escalation_multiplier(value)


def _parse_mute_escalation_reset_seconds(value: str) -> int | None:
    return parse_mute_escalation_reset_seconds(value)


__all__ = [
    "ChatFilterCommandService",
    "CommandLogger",
    "load_runtime_state",
]
