from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


from astrbot_plugin_chat_filter.platform.platform_actions import (  # noqa: E402
    FAILED_REASON_ACTION_CALL_FAILED,
    FAILED_REASON_ACTION_CALL_TIMEOUT,
    MuteUserRequest,
    OneBotV11PlatformActions,
    RecallMessageRequest,
    SendTextLogRequest,
)


class OneBotV11PlatformActionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_mute_user_times_out_call_action_with_generic_failure(self) -> None:
        logger = _Logger()
        actions = OneBotV11PlatformActions(
            _HangingActionClient(),
            logger=logger,
            action_timeout_seconds=0.01,
        )

        result = await actions.mute_user(
            MuteUserRequest(
                platform="aiocqhttp",
                group_id="100",
                user_id="200",
                duration_seconds=60,
            )
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason, FAILED_REASON_ACTION_CALL_TIMEOUT)
        expected_errors = [
            (
                "Chat Filter OneBot action call timed out: action=%s",
                ("set_group_ban",),
            )
        ]
        self.assertEqual(logger.errors, expected_errors)

    async def test_recall_message_exception_uses_generic_failure_reason(self) -> None:
        logger = _Logger()
        actions = OneBotV11PlatformActions(
            _FailingActionClient(RuntimeError("secret-token")),
            logger=logger,
            action_timeout_seconds=0.01,
        )

        result = await actions.recall_message(
            RecallMessageRequest(
                platform="aiocqhttp",
                group_id="100",
                message_id="300",
            )
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason, FAILED_REASON_ACTION_CALL_FAILED)
        self.assertNotIn("secret-token", result.reason)
        self.assertEqual(
            logger.errors,
            [
                (
                    "Chat Filter OneBot action call failed: "
                    "action=%s error_type=%s",
                    ("delete_msg", "RuntimeError"),
                )
            ],
        )

    async def test_send_text_log_sends_plain_escaped_group_message(self) -> None:
        action_client = _RecordingActionClient()
        actions = OneBotV11PlatformActions(action_client)

        result = await actions.send_text_log(
            SendTextLogRequest(
                platform="aiocqhttp",
                target_group_id="100",
                text="warn",
            )
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(
            action_client.calls,
            [
                (
                    "send_group_msg",
                    {
                        "group_id": 100,
                        "message": "warn",
                        "auto_escape": True,
                    },
                )
            ],
        )


class _HangingActionClient:
    async def call_action(self, action: str, **params: Any) -> Any:
        _ = action, params
        await asyncio.Event().wait()


class _FailingActionClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def call_action(self, action: str, **params: Any) -> Any:
        _ = action, params
        raise self._exc


class _RecordingActionClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_action(self, action: str, **params: Any) -> Any:
        self.calls.append((action, params))
        return None


class _Logger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, tuple[object, ...]]] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append((message, args))


if __name__ == "__main__":
    unittest.main()
