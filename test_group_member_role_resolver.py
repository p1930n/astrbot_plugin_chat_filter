from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    ChatMessage,
    PlatformEventSnapshot,
)
from astrbot_plugin_chat_filter.platform.group_member_role_resolver import (  # noqa: E402
    GroupMemberRoleResolver,
)


class GroupMemberRoleResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_missing_snapshot_role_from_onebot_member_info(self) -> None:
        action_client = _ActionClient({"role": "administrator"})
        resolver = GroupMemberRoleResolver()

        snapshot = await resolver.resolve_snapshot(
            _snapshot(sender_role=""),
            action_client,
        )

        self.assertEqual(snapshot.sender_role, "admin")
        self.assertEqual(
            action_client.calls,
            [("get_group_member_info", {"group_id": 100, "user_id": 200})],
        )

    async def test_keeps_existing_role_without_querying_api(self) -> None:
        action_client = _ActionClient({"role": "member"})
        resolver = GroupMemberRoleResolver()

        snapshot = await resolver.resolve_snapshot(
            _snapshot(sender_role="owner"),
            action_client,
        )

        self.assertEqual(snapshot.sender_role, "owner")
        self.assertEqual(action_client.calls, [])

    async def test_snapshot_resolution_refreshes_role_for_command_authorization(
        self,
    ) -> None:
        action_client = _ActionClient({"role": "owner"})
        resolver = GroupMemberRoleResolver()

        first = await resolver.resolve_snapshot(
            _snapshot(sender_role=""),
            action_client,
        )
        action_client.result = {"role": "member"}
        second = await resolver.resolve_snapshot(
            _snapshot(sender_role=""),
            action_client,
        )

        self.assertEqual(first.sender_role, "owner")
        self.assertEqual(second.sender_role, "member")
        self.assertEqual(len(action_client.calls), 2)

    async def test_resolves_message_role_from_cache_after_first_query(self) -> None:
        action_client = _ActionClient({"role": "owner"})
        resolver = GroupMemberRoleResolver()

        first = await resolver.resolve_message(
            _message(sender_role=""),
            action_client,
        )
        second = await resolver.resolve_message(
            _message(sender_role=""),
            action_client,
        )

        self.assertEqual(first.sender_role, "owner")
        self.assertEqual(second.sender_role, "owner")
        self.assertEqual(len(action_client.calls), 1)

    async def test_skips_non_onebot_or_invalid_scope_without_querying_api(
        self,
    ) -> None:
        action_client = _ActionClient({"role": "owner"})
        resolver = GroupMemberRoleResolver()

        non_onebot = await resolver.resolve_snapshot(
            _snapshot(platform="qq", sender_role=""),
            action_client,
        )
        invalid = await resolver.resolve_snapshot(
            _snapshot(group_id="abc", sender_role=""),
            action_client,
        )

        self.assertEqual(non_onebot.sender_role, "")
        self.assertEqual(invalid.sender_role, "")
        self.assertEqual(action_client.calls, [])

    async def test_action_failure_keeps_role_missing_and_logs_safely(self) -> None:
        logger = _Logger()
        resolver = GroupMemberRoleResolver(logger=logger)

        snapshot = await resolver.resolve_snapshot(
            _snapshot(sender_role=""),
            _FailingActionClient(),
        )

        self.assertEqual(snapshot.sender_role, "")
        self.assertEqual(logger.warning_calls, [("RuntimeError",)])


def _snapshot(
    *,
    platform: str = "aiocqhttp",
    group_id: str = "100",
    sender_id: str = "200",
    sender_role: str,
) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform=platform,
        group_id=group_id,
        sender_id=sender_id,
        sender_role=sender_role,
    )


def _message(*, sender_role: str) -> ChatMessage:
    return ChatMessage(
        platform="aiocqhttp",
        group_id="100",
        user_id="200",
        text="message",
        sender_role=sender_role,
    )


class _ActionClient:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_action(self, action: str, **params: object) -> dict[str, object]:
        self.calls.append((action, params))
        return self.result


class _FailingActionClient:
    async def call_action(self, _action: str, **_params: object) -> object:
        raise RuntimeError("backend failed with private details")


class _Logger:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[object, ...]] = []

    def warning(self, message: str, *args: object) -> None:
        _ = message
        self.warning_calls.append(args)


if __name__ == "__main__":
    unittest.main()
