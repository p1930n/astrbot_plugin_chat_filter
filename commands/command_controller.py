from __future__ import annotations

from .command_auth import CommandAuthorizer
from .action_policy_command_service import ACTION_POLICY_USAGE
from .command_service import ChatFilterCommandService
from .command_validation import (
    build_group_key,
    is_action_toggle_value,
    resolve_target_group_id,
    resolve_target_group_key,
)
from ..services.file_probe_service import FileProbeService
from ..domain.models import PlatformEventSnapshot
from ..platform.platform_actions import PlatformActions, format_platform_probe
from ..services.report_service import ViolationReportService
from ..runtime.metrics import ChatFilterMetrics


GROUP_ADMIN_EXEMPT_USAGE = (
    "Usage: .cf group admin-exempt status|enable|disable (alias: exempt)"
)
GROUP_ENABLE_USAGE = "Usage: .cf enable [group id]"
GROUP_DISABLE_USAGE = "Usage: .cf disable [group id]"
GROUP_ADD_TO_USAGE = "Usage: .cf group add-to <group id> <word>[,<word>...]"
GROUP_REMOVE_USAGE = "Usage: .cf group remove <word>[,<word>...]"
GROUP_REMOVE_TO_USAGE = "Usage: .cf group remove-to <group id> <word>[,<word>...]"
GROUP_BYPASS_ADD_USAGE = "Usage: .cf group bypass-add <group id> <word>[,<word>...]"
GROUP_BYPASS_REMOVE_USAGE = (
    "Usage: .cf group bypass-remove [group id] <word>[,<word>...]"
)
TARGET_GROUP_PERMISSION_DENIED = (
    "Chat Filter target group permission denied: "
    "requires AstrBot admin permission."
)
GLOBAL_DIAGNOSTICS_PERMISSION_DENIED = (
    "Chat Filter diagnostics permission denied: "
    "requires AstrBot admin permission."
)


class CommandController:
    def __init__(
        self,
        command_service: ChatFilterCommandService,
        report_service: ViolationReportService | None,
        file_probe_service: FileProbeService | None,
        authorizer: CommandAuthorizer,
        metrics: ChatFilterMetrics | None = None,
    ) -> None:
        self._command_service = command_service
        self._report_service = report_service
        self._file_probe_service = file_probe_service
        self._authorizer = authorizer
        self._metrics = metrics

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

    async def regex_skips(
        self,
        snapshot: PlatformEventSnapshot,
        limit: str = "",
    ) -> str:
        if not self.check_global_permission(snapshot):
            return GLOBAL_DIAGNOSTICS_PERMISSION_DENIED
        return self._command_service.format_regex_skips(limit)

    async def metrics(self, snapshot: PlatformEventSnapshot) -> str:
        if not self.check_global_permission(snapshot):
            return GLOBAL_DIAGNOSTICS_PERMISSION_DENIED
        if self._metrics is None:
            return "Chat Filter metrics:\nunavailable"
        return self._metrics.format_snapshot()

    async def action_status(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = resolve_target_group_id(snapshot, group_id)
        if target_group_id is None:
            return ACTION_POLICY_USAGE

        denial = self._action_policy_denial(snapshot, target_group_id)
        if denial:
            return denial

        return await self._command_service.format_group_action_policy(
            platform=snapshot.platform,
            group_id=target_group_id,
        )

    async def action_toggle(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
        group_id: str = "",
        enabled: str = "",
    ) -> str:
        if not enabled and is_action_toggle_value(group_id):
            enabled = group_id
            group_id = ""
        target_group_id = resolve_target_group_id(snapshot, group_id)
        if target_group_id is None or not enabled:
            return ACTION_POLICY_USAGE

        denial = self._action_policy_denial(snapshot, target_group_id)
        if denial:
            return denial

        return await self._command_service.set_group_action_toggle(
            platform=snapshot.platform,
            group_id=target_group_id,
            action=action,
            enabled=enabled,
            updated_by=snapshot.sender_id,
        )

    async def action_mode(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        mode: str = "",
    ) -> str:
        if not mode and group_id.strip().casefold() in ("strict", "audit"):
            mode = group_id
            group_id = ""
        target_group_id = resolve_target_group_id(snapshot, group_id)
        if target_group_id is None or not mode:
            return ACTION_POLICY_USAGE

        denial = self._action_policy_denial(snapshot, target_group_id)
        if denial:
            return denial

        return await self._command_service.set_group_action_mode(
            platform=snapshot.platform,
            group_id=target_group_id,
            mode=mode,
            updated_by=snapshot.sender_id,
        )

    async def action_overview(
        self,
        snapshot: PlatformEventSnapshot,
        output_format: str = "",
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.format_action_policy_overview(
            snapshot.platform,
            output_format,
        )

    async def enable(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = group_id.strip()
        denial = self._target_group_permission_denial(snapshot, target_group_id)
        if denial:
            return denial

        group_key = resolve_target_group_key(snapshot, target_group_id)
        if group_key is None:
            return GROUP_ENABLE_USAGE
        return await self._command_service.set_group_enabled(group_key, True)

    async def disable(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = group_id.strip()
        denial = self._target_group_permission_denial(snapshot, target_group_id)
        if denial:
            return denial

        group_key = resolve_target_group_key(snapshot, target_group_id)
        if group_key is None:
            return GROUP_DISABLE_USAGE
        return await self._command_service.set_group_enabled(group_key, False)

    async def group_status(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_group_status(build_group_key(snapshot))

    async def group_enable(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.set_group_enabled(
            build_group_key(snapshot),
            True,
        )

    async def group_disable(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return await self._command_service.set_group_enabled(
            build_group_key(snapshot),
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

        return await self._command_service.add_group_word(build_group_key(snapshot), word)

    async def group_add_to(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        if not self.check_global_permission(snapshot):
            return TARGET_GROUP_PERMISSION_DENIED

        group_key = resolve_target_group_key(snapshot, group_id)
        words = _split_group_words(word)
        if group_key is None or not words:
            return GROUP_ADD_TO_USAGE
        if len(words) == 1:
            return await self._command_service.add_group_word(group_key, words[0])
        return await self._add_group_words(group_key, words, bypass=False)

    async def _add_group_words(
        self,
        group_key: str,
        words: tuple[str, ...],
        *,
        bypass: bool,
    ) -> str:
        counts = {
            "added": 0,
            "exists": 0,
            "invalid": 0,
            "limit": 0,
            "failed": 0,
        }
        for word in words:
            if bypass:
                result = await self._command_service.add_group_bypass_word(
                    group_key,
                    word,
                )
                added_text = "Group bypass word added."
                exists_text = "Group bypass word already exists."
                limit_text = "Group bypass word limit reached."
            else:
                result = await self._command_service.add_group_word(group_key, word)
                added_text = "Group word added."
                exists_text = "Group word already exists."
                limit_text = "Group word limit reached."

            if result == added_text:
                counts["added"] += 1
            elif result == exists_text:
                counts["exists"] += 1
            elif result == "Invalid word length.":
                counts["invalid"] += 1
            elif result == limit_text:
                counts["limit"] += 1
            else:
                counts["failed"] += 1
        noun = "bypass words" if bypass else "words"
        return (
            f"Group {noun} added: "
            f"added={counts['added']}, "
            f"exists={counts['exists']}, "
            f"invalid={counts['invalid']}, "
            f"limit={counts['limit']}, "
            f"failed={counts['failed']}."
        )

    async def group_remove(
        self,
        snapshot: PlatformEventSnapshot,
        word: str,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        group_key = build_group_key(snapshot)
        words = _split_group_words(word)
        if group_key is None:
            return "This command must be used in a group chat."
        if not words:
            return GROUP_REMOVE_USAGE
        if len(words) == 1:
            return await self._command_service.remove_group_word(group_key, words[0])
        return await self._remove_group_words(group_key, words, bypass=False)

    async def group_remove_to(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        if not self.check_global_permission(snapshot):
            return TARGET_GROUP_PERMISSION_DENIED

        group_key = resolve_target_group_key(snapshot, group_id)
        words = _split_group_words(word)
        if group_key is None or not words:
            return GROUP_REMOVE_TO_USAGE
        if len(words) == 1:
            return await self._command_service.remove_group_word(group_key, words[0])
        return await self._remove_group_words(group_key, words, bypass=False)

    async def group_bypass_add(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        return await self._add_group_bypass_words_to_target(
            snapshot,
            group_id,
            word,
        )

    async def _add_group_bypass_words_to_target(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str,
        word: str,
    ) -> str:
        target_group_id = group_id.strip()
        denial = self._target_group_permission_denial(snapshot, target_group_id)
        if denial:
            return denial

        group_key = resolve_target_group_key(snapshot, target_group_id)
        words = _split_group_words(word)
        if not target_group_id or group_key is None or not words:
            return GROUP_BYPASS_ADD_USAGE
        if len(words) == 1:
            return await self._command_service.add_group_bypass_word(
                group_key,
                words[0],
            )
        return await self._add_group_words(group_key, words, bypass=True)

    async def group_bypass_remove(
        self,
        snapshot: PlatformEventSnapshot,
        group_id_or_word: str = "",
        word: str = "",
    ) -> str:
        target_group_id, words_text = _optional_target_group_and_words(
            group_id_or_word,
            word,
        )
        denial = self._target_group_permission_denial(snapshot, target_group_id)
        if denial:
            return denial

        group_key = resolve_target_group_key(snapshot, target_group_id)
        words = _split_group_words(words_text)
        if not words:
            return GROUP_BYPASS_REMOVE_USAGE
        if group_key is None:
            return "This command must be used in a group chat."
        if len(words) == 1:
            return await self._command_service.remove_group_bypass_word(
                group_key,
                words[0],
            )
        return await self._remove_group_words(group_key, words, bypass=True)

    async def group_bypass_list(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = group_id.strip()
        denial = self._target_group_permission_denial(snapshot, target_group_id)
        if denial:
            return denial
        group_key = resolve_target_group_key(snapshot, target_group_id)
        return self._command_service.format_group_bypass_words(group_key)

    async def _remove_group_words(
        self,
        group_key: str,
        words: tuple[str, ...],
        *,
        bypass: bool,
    ) -> str:
        counts = {"removed": 0, "not_found": 0, "failed": 0}
        for word in words:
            if bypass:
                result = await self._command_service.remove_group_bypass_word(
                    group_key,
                    word,
                )
                removed_text = "Group bypass word removed."
                not_found_text = "Group bypass word not found."
            else:
                result = await self._command_service.remove_group_word(
                    group_key,
                    word,
                )
                removed_text = "Group word removed."
                not_found_text = "Group word not found."

            if result == removed_text:
                counts["removed"] += 1
            elif result == not_found_text:
                counts["not_found"] += 1
            else:
                counts["failed"] += 1
        noun = "bypass words" if bypass else "words"
        return (
            f"Group {noun} removed: "
            f"removed={counts['removed']}, "
            f"not_found={counts['not_found']}, "
            f"failed={counts['failed']}."
        )

    async def group_list(self, snapshot: PlatformEventSnapshot) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial

        return self._command_service.format_group_words(build_group_key(snapshot))

    async def group_admin_exempt_response(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
    ) -> str:
        denial = self.command_denial(snapshot)
        if denial:
            return denial
        return await self.group_admin_exempt_text(snapshot, action)

    def _action_policy_denial(
        self,
        snapshot: PlatformEventSnapshot,
        target_group_id: str,
    ) -> str | None:
        if target_group_id != snapshot.group_id:
            if not self.check_global_permission(snapshot):
                return TARGET_GROUP_PERMISSION_DENIED
            return None
        return self.command_denial(snapshot)

    def _target_group_permission_denial(
        self,
        snapshot: PlatformEventSnapshot,
        target_group_id: str,
    ) -> str | None:
        if target_group_id and target_group_id != snapshot.group_id:
            if not self.check_global_permission(snapshot):
                return TARGET_GROUP_PERMISSION_DENIED
            return None
        return self.command_denial(snapshot)

    async def group_admin_exempt_text(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
    ) -> str:
        group_key = build_group_key(snapshot)
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


def _split_group_words(words: str) -> tuple[str, ...]:
    return tuple(
        item
        for item in (
            part.strip()
            for part in words.replace("\uff0c", ",").split(",")
        )
        if item
    )


def _optional_target_group_and_words(
    group_id_or_word: str,
    word: str,
) -> tuple[str, str]:
    if word:
        return group_id_or_word.strip(), word
    return "", group_id_or_word
