from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

astrbot_module = types.ModuleType("astrbot")
astrbot_api_module = types.ModuleType("astrbot.api")
astrbot_event_module = types.ModuleType("astrbot.api.event")


class AstrMessageEvent:
    pass


astrbot_event_module.AstrMessageEvent = AstrMessageEvent
sys.modules.setdefault("astrbot", astrbot_module)
sys.modules.setdefault("astrbot.api", astrbot_api_module)
sys.modules.setdefault("astrbot.api.event", astrbot_event_module)

from astrbot_plugin_chat_filter.platform.astrbot_event_adapter import (  # noqa: E402
    dehydrate_event_snapshot,
)


class AstrbotEventAdapterTests(unittest.TestCase):
    def test_snapshot_ignores_plain_event_role_for_group_manager(self) -> None:
        event = SimpleNamespace(
            platform_name="aiocqhttp",
            group_id="100",
            sender_id="200",
            role="admin",
        )

        snapshot = dehydrate_event_snapshot(event)

        self.assertEqual(snapshot.sender_role, "")
        self.assertFalse(snapshot.sender_is_group_manager)

    def test_snapshot_ignores_plain_event_admin_bool_for_group_manager(self) -> None:
        event = SimpleNamespace(
            platform_name="aiocqhttp",
            group_id="100",
            sender_id="200",
            role="admin",
            is_admin=lambda: True,
        )

        snapshot = dehydrate_event_snapshot(event)

        self.assertEqual(snapshot.sender_role, "")
        self.assertFalse(snapshot.sender_is_group_manager)

    def test_snapshot_accepts_sender_manager_bool_sources(self) -> None:
        for name, message_obj, expected_role in (
            (
                "message_obj_sender_admin",
                SimpleNamespace(sender=SimpleNamespace(is_admin=lambda: True)),
                "admin",
            ),
            (
                "raw_sender_owner",
                SimpleNamespace(raw_message={"sender": {"is_owner": True}}),
                "owner",
            ),
        ):
            with self.subTest(name=name):
                event = SimpleNamespace(
                    platform_name="aiocqhttp",
                    group_id="100",
                    sender_id="200",
                    message_obj=message_obj,
                )

                snapshot = dehydrate_event_snapshot(event)

                self.assertEqual(snapshot.sender_role, expected_role)
                self.assertTrue(snapshot.sender_is_group_manager)

    def test_snapshot_prioritizes_onebot_raw_sender_role_over_event_role(self) -> None:
        for raw_name, raw_role, expected_role in (
            ("raw_message", "owner", "owner"),
            ("raw_event", "admin", "admin"),
            ("raw", "administrator", "admin"),
        ):
            with self.subTest(raw_name=raw_name):
                event = SimpleNamespace(
                    platform_name="aiocqhttp",
                    group_id="100",
                    sender_id="200",
                    role="member",
                    message_obj=SimpleNamespace(
                        **{
                            raw_name: {
                                "sender": {
                                    "role": raw_role,
                                }
                            }
                        }
                    ),
                )

                snapshot = dehydrate_event_snapshot(event)

                self.assertEqual(snapshot.sender_role, expected_role)
                self.assertTrue(snapshot.sender_is_group_manager)

    def test_snapshot_normalizes_sender_role_aliases(self) -> None:
        for raw_role, expected_role in (
            ("administrator", "admin"),
            ("manager", "admin"),
            ("moderator", "admin"),
            ("群主", "owner"),
            ("主人", "owner"),
            ("管理员", "admin"),
        ):
            with self.subTest(raw_role=raw_role):
                event = SimpleNamespace(
                    platform_name="aiocqhttp",
                    group_id="100",
                    sender_id="200",
                    message_obj=SimpleNamespace(
                        sender=SimpleNamespace(role=raw_role),
                    ),
                )

                snapshot = dehydrate_event_snapshot(event)

                self.assertEqual(snapshot.sender_role, expected_role)
                self.assertTrue(snapshot.sender_is_group_manager)


if __name__ == "__main__":
    unittest.main()
