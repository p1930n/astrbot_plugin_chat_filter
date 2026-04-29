from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.commands.action_policy_command_service import (  # noqa: E402
    ACTION_POLICY_USAGE,
    ActionPolicyCommandService,
)
from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    GroupActionPolicy,
    GroupPolicy,
    RuntimeState,
)


class ActionPolicyCommandServiceTests(unittest.TestCase):
    def test_status_uses_default_policy_when_group_has_no_explicit_row(self) -> None:
        service = _service(repository=_Repository())

        result = asyncio.run(
            service.format_group_action_policy(platform="qq", group_id="100")
        )

        self.assertEqual(
            result,
            "Chat Filter action policy: group=100, mode=strict, "
            "mute=on, recall=on, forward=on.",
        )

    def test_toggle_update_validates_group_and_updates_repository(self) -> None:
        repository = _Repository()
        service = _service(repository=repository)

        result = asyncio.run(
            service.set_group_action_toggle(
                platform="qq",
                group_id="100",
                action="mute",
                enabled="off",
                updated_by="200",
            )
        )

        self.assertEqual(result, "Chat Filter action policy updated: 100 mute=off.")
        self.assertEqual(repository.toggle_calls, [("qq", "100", "mute", False, "200")])

    def test_mode_update_accepts_audit_mode(self) -> None:
        repository = _Repository()
        service = _service(repository=repository)

        result = asyncio.run(
            service.set_group_action_mode(
                platform="qq",
                group_id="100",
                mode="audit",
                updated_by="200",
            )
        )

        self.assertEqual(result, "Chat Filter action policy updated: 100 mode=audit.")
        self.assertEqual(repository.mode_calls, [("qq", "100", "audit", "200")])

    def test_invalid_toggle_returns_usage_without_repository_call(self) -> None:
        repository = _Repository()
        service = _service(repository=repository)

        result = asyncio.run(
            service.set_group_action_toggle(
                platform="qq",
                group_id="100",
                action="mute",
                enabled="maybe",
                updated_by="200",
            )
        )

        self.assertEqual(result, ACTION_POLICY_USAGE)
        self.assertEqual(repository.toggle_calls, [])

    def test_overview_merges_known_groups_with_explicit_policies(self) -> None:
        service = _service(
            state=RuntimeState(
                groups={
                    "qq:100": GroupPolicy(enabled=True),
                    "qq:101": GroupPolicy(enabled=False),
                    "telegram:900": GroupPolicy(enabled=True),
                }
            ),
            repository=_Repository(
                policies=[
                    GroupActionPolicy(
                        platform="qq",
                        group_id="102",
                        mute_enabled=False,
                        recall_enabled=True,
                        forward_enabled=False,
                        mode="audit",
                    )
                ]
            ),
        )

        result = asyncio.run(service.format_action_policy_overview("qq", "csv"))

        self.assertEqual(
            result,
            "group_id,mode,mute,recall,forward,explicit\n"
            "100,strict,on,on,on,false\n"
            "101,strict,on,on,on,false\n"
            "102,audit,off,on,off,true",
        )


def _service(
    *,
    state: RuntimeState | None = None,
    repository: "_Repository | None" = None,
) -> ActionPolicyCommandService:
    return ActionPolicyCommandService(
        repository=repository or _Repository(),  # type: ignore[arg-type]
        state=state or RuntimeState(),
        logger=_Logger(),
    )


class _Repository:
    def __init__(self, policies: list[GroupActionPolicy] | None = None) -> None:
        self._policies = policies or []
        self.toggle_calls: list[tuple[str, str, str, bool, str]] = []
        self.mode_calls: list[tuple[str, str, str, str]] = []

    def get_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> GroupActionPolicy | None:
        for policy in self._policies:
            if policy.platform == platform and policy.group_id == group_id:
                return policy
        return None

    def set_group_action_toggle(
        self,
        *,
        platform: str,
        group_id: str,
        action: str,
        enabled: bool,
        updated_by: str,
    ) -> GroupActionPolicy:
        self.toggle_calls.append((platform, group_id, action, enabled, updated_by))
        return GroupActionPolicy(
            platform=platform,
            group_id=group_id,
            mute_enabled=enabled if action == "mute" else True,
            recall_enabled=enabled if action == "recall" else True,
            forward_enabled=enabled if action == "forward" else True,
        )

    def set_group_action_mode(
        self,
        *,
        platform: str,
        group_id: str,
        mode: str,
        updated_by: str,
    ) -> GroupActionPolicy:
        self.mode_calls.append((platform, group_id, mode, updated_by))
        return GroupActionPolicy(platform=platform, group_id=group_id, mode=mode)

    def list_group_action_policies(self, *, platform: str) -> list[GroupActionPolicy]:
        return [policy for policy in self._policies if policy.platform == platform]


class _Logger:
    def error(self, message: str, *args: object) -> None:
        _ = message, args


if __name__ == "__main__":
    unittest.main()
