from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.command_auth import (  # noqa: E402
    COMMAND_PERMISSION_DENIED,
    GROUP_ENABLE_PERMISSION_DENIED,
    CommandAuthorizer,
)
from astrbot_plugin_chat_filter.models import PlatformEventSnapshot  # noqa: E402


class CommandAuthorizerTests(unittest.TestCase):
    def test_group_managers_can_use_normal_commands(self) -> None:
        authorizer = CommandAuthorizer(lambda: {})

        for role in ("owner", "admin"):
            with self.subTest(role=role):
                snapshot = _snapshot(sender_id="200", sender_role=role)

                self.assertTrue(authorizer.can_use_command(snapshot))
                self.assertIsNone(authorizer.command_denial(snapshot))

    def test_plain_member_is_denied_for_normal_commands(self) -> None:
        authorizer = CommandAuthorizer(lambda: {})
        snapshot = _snapshot(sender_id="200", sender_role="member")

        self.assertFalse(authorizer.can_use_command(snapshot))
        self.assertEqual(
            authorizer.command_denial(snapshot),
            COMMAND_PERMISSION_DENIED,
        )

    def test_global_admin_can_use_commands_when_group_manager_auth_is_disabled(
        self,
    ) -> None:
        for config in (
            {"admins_id": "100, 200"},
            {"admin_ids": [100, "200"]},
        ):
            with self.subTest(config=config):
                authorizer = CommandAuthorizer(lambda config=config: config)
                snapshot = _snapshot(sender_id="200", sender_role="member")

                self.assertTrue(
                    authorizer.can_use_command(
                        snapshot,
                        allow_group_manager=False,
                    )
                )
                self.assertIsNone(
                    authorizer.command_denial(
                        snapshot,
                        allow_group_manager=False,
                    )
                )

    def test_group_enable_denies_group_managers_without_global_admin(self) -> None:
        authorizer = CommandAuthorizer(lambda: {})

        for role in ("owner", "admin"):
            with self.subTest(role=role):
                snapshot = _snapshot(sender_id="200", sender_role=role)

                self.assertFalse(
                    authorizer.can_use_command(
                        snapshot,
                        allow_group_manager=False,
                    )
                )
                self.assertEqual(
                    authorizer.command_denial(
                        snapshot,
                        allow_group_manager=False,
                    ),
                    GROUP_ENABLE_PERMISSION_DENIED,
                )

    def test_missing_sender_or_config_error_denies_global_permission(self) -> None:
        authorizer = CommandAuthorizer(lambda: {"admins_id": "200"})
        failing_authorizer = CommandAuthorizer(_raise_config_error)

        self.assertFalse(authorizer.check_global_permission(_snapshot(sender_id="")))
        self.assertFalse(
            failing_authorizer.check_global_permission(_snapshot(sender_id="200"))
        )


def _snapshot(
    *,
    sender_id: str,
    sender_role: str = "",
) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform="qq",
        group_id="100",
        sender_id=sender_id,
        sender_role=sender_role,
    )


def _raise_config_error() -> object:
    raise RuntimeError("config unavailable")


if __name__ == "__main__":
    unittest.main()
