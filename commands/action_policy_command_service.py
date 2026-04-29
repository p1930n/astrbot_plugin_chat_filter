from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass

from .command_runtime import CommandLogger
from .command_validation import BIND_LIST_LIMIT, is_valid_qq_group_id
from ..domain.models import GroupActionPolicy, RuntimeState
from ..persistence.repository import ChatFilterRepository
from ..persistence.repository_action_policy import (
    ACTION_POLICY_MODE_AUDIT,
    ACTION_POLICY_MODE_STRICT,
)


ACTION_POLICY_USAGE = (
    "Usage: .cf action status [group]; "
    ".cf action mute|recall|forward [group] on|off; "
    ".cf action mode [group] strict|audit; "
    ".cf action overview [csv]"
)
ACTION_POLICY_CSV_FORMATS = frozenset(("csv", "table"))
ACTION_POLICY_TOGGLES = frozenset(("mute", "recall", "forward"))
ACTION_POLICY_MODES = frozenset((ACTION_POLICY_MODE_STRICT, ACTION_POLICY_MODE_AUDIT))
DEFAULT_ACTION_POLICY = GroupActionPolicy(platform="", group_id="")


class ActionPolicyCommandService:
    def __init__(
        self,
        repository: ChatFilterRepository,
        state: RuntimeState,
        logger: CommandLogger,
    ) -> None:
        self._repository = repository
        self._state = state
        self._logger = logger

    async def format_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> str:
        if not platform:
            return "Chat Filter action policy status failed: platform is unavailable."
        if not is_valid_qq_group_id(group_id):
            return ACTION_POLICY_USAGE

        policy = await self._get_group_action_policy(platform, group_id)
        if policy is None:
            return "Chat Filter action policy status failed."
        return _format_policy_status(policy)

    async def set_group_action_toggle(
        self,
        *,
        platform: str,
        group_id: str,
        action: str,
        enabled: str,
        updated_by: str,
    ) -> str:
        if not platform:
            return "Chat Filter action policy update failed: platform is unavailable."
        if not is_valid_qq_group_id(group_id):
            return ACTION_POLICY_USAGE

        normalized_action = action.strip().casefold()
        if normalized_action not in ACTION_POLICY_TOGGLES:
            return ACTION_POLICY_USAGE
        parsed_enabled = _parse_toggle(enabled)
        if parsed_enabled is None:
            return ACTION_POLICY_USAGE

        try:
            policy = await asyncio.to_thread(
                self._repository.set_group_action_toggle,
                platform=platform,
                group_id=group_id,
                action=normalized_action,
                enabled=parsed_enabled,
                updated_by=updated_by,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter action policy update failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter action policy update failed."

        return (
            "Chat Filter action policy updated: "
            f"{policy.group_id} {normalized_action}="
            f"{_format_enabled(parsed_enabled)}."
        )

    async def set_group_action_mode(
        self,
        *,
        platform: str,
        group_id: str,
        mode: str,
        updated_by: str,
    ) -> str:
        if not platform:
            return "Chat Filter action policy update failed: platform is unavailable."
        if not is_valid_qq_group_id(group_id):
            return ACTION_POLICY_USAGE

        normalized_mode = mode.strip().casefold()
        if normalized_mode not in ACTION_POLICY_MODES:
            return ACTION_POLICY_USAGE

        try:
            policy = await asyncio.to_thread(
                self._repository.set_group_action_mode,
                platform=platform,
                group_id=group_id,
                mode=normalized_mode,
                updated_by=updated_by,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter action policy mode update failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter action policy update failed."

        return (
            "Chat Filter action policy updated: "
            f"{policy.group_id} mode={policy.mode}."
        )

    async def format_action_policy_overview(
        self,
        platform: str,
        output_format: str = "",
    ) -> str:
        if not platform:
            return "Chat Filter action policy overview failed: platform is unavailable."

        explicit_policies = await self._list_group_action_policies(platform)
        if explicit_policies is None:
            return "Chat Filter action policy overview failed."

        rows = _overview_rows(self._state, platform, explicit_policies)
        if output_format.strip().casefold() in ACTION_POLICY_CSV_FORMATS:
            return _format_overview_csv(rows)
        return _format_overview_summary(rows)

    async def _get_group_action_policy(
        self,
        platform: str,
        group_id: str,
    ) -> GroupActionPolicy | None:
        try:
            policy = await asyncio.to_thread(
                self._repository.get_group_action_policy,
                platform=platform,
                group_id=group_id,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter action policy lookup failed: error_type=%s",
                type(exc).__name__,
            )
            return None
        if policy is None:
            return GroupActionPolicy(platform=platform, group_id=group_id)
        return policy

    async def _list_group_action_policies(
        self,
        platform: str,
    ) -> list[GroupActionPolicy] | None:
        try:
            return await asyncio.to_thread(
                self._repository.list_group_action_policies,
                platform=platform,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter action policy overview failed: error_type=%s",
                type(exc).__name__,
            )
            return None


@dataclass(frozen=True, slots=True)
class ActionPolicyOverviewRow:
    group_id: str
    policy: GroupActionPolicy
    explicit: bool


def _overview_rows(
    state: RuntimeState,
    platform: str,
    explicit_policies: list[GroupActionPolicy],
) -> tuple[ActionPolicyOverviewRow, ...]:
    explicit_by_group = {policy.group_id: policy for policy in explicit_policies}
    known_group_ids = _known_group_ids(state, platform) | set(explicit_by_group)
    return tuple(
        ActionPolicyOverviewRow(
            group_id=group_id,
            policy=explicit_by_group.get(
                group_id,
                GroupActionPolicy(platform=platform, group_id=group_id),
            ),
            explicit=group_id in explicit_by_group,
        )
        for group_id in sorted(known_group_ids)
    )


def _known_group_ids(state: RuntimeState, platform: str) -> set[str]:
    prefix = f"{platform}:"
    return {
        group_key.removeprefix(prefix)
        for group_key in state.groups
        if group_key.startswith(prefix)
    }


def _format_policy_status(policy: GroupActionPolicy) -> str:
    return (
        "Chat Filter action policy: "
        f"group={policy.group_id}, "
        f"mode={policy.mode}, "
        f"mute={_format_enabled(policy.mute_enabled)}, "
        f"recall={_format_enabled(policy.recall_enabled)}, "
        f"forward={_format_enabled(policy.forward_enabled)}."
    )


def _format_overview_summary(rows: tuple[ActionPolicyOverviewRow, ...]) -> str:
    if not rows:
        return (
            "Chat Filter action policy overview is empty; "
            "defaults are mode=strict, mute=on, recall=on, forward=on."
        )
    visible_rows = rows[:BIND_LIST_LIMIT]
    lines = [
        "Chat Filter action policy overview:",
        *(_format_overview_row(row) for row in visible_rows),
    ]
    if len(rows) > BIND_LIST_LIMIT:
        lines.append(f"... and {len(rows) - BIND_LIST_LIMIT} more group(s).")
    lines.append("Use .cf action overview csv for details.")
    return "\n".join(lines)


def _format_overview_csv(rows: tuple[ActionPolicyOverviewRow, ...]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("group_id", "mode", "mute", "recall", "forward", "explicit"))
    for row in rows:
        writer.writerow(
            (
                row.group_id,
                row.policy.mode,
                _format_enabled(row.policy.mute_enabled),
                _format_enabled(row.policy.recall_enabled),
                _format_enabled(row.policy.forward_enabled),
                "true" if row.explicit else "false",
            )
        )
    return output.getvalue().rstrip("\n")


def _format_overview_row(row: ActionPolicyOverviewRow) -> str:
    explicit = "explicit" if row.explicit else "default"
    return (
        f"{row.group_id}: mode={row.policy.mode}, "
        f"mute={_format_enabled(row.policy.mute_enabled)}, "
        f"recall={_format_enabled(row.policy.recall_enabled)}, "
        f"forward={_format_enabled(row.policy.forward_enabled)} "
        f"({explicit})"
    )


def _parse_toggle(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in ("on", "enable", "enabled", "true", "1"):
        return True
    if normalized in ("off", "disable", "disabled", "false", "0"):
        return False
    return None


def _format_enabled(value: bool) -> str:
    return "on" if value else "off"
