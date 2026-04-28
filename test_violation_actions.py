from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


from astrbot_plugin_chat_filter.services import violation_actions  # noqa: E402
from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    ChatMessage,
    MuteEscalationDecision,
    ViolationPushDelivery,
)
from astrbot_plugin_chat_filter.platform.platform_actions import (  # noqa: E402
    PlatformActionCapabilities,
    PlatformActionResult,
    SendFileRequest,
)
from astrbot_plugin_chat_filter.services.violation_actions import (  # noqa: E402
    ViolationActionExecutor,
)


class ViolationActionExecutorRuntimeGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._mute_timeout = violation_actions.MUTE_ACTION_TIMEOUT_SECONDS
        self._recall_timeout = violation_actions.RECALL_ACTION_TIMEOUT_SECONDS
        violation_actions.MUTE_ACTION_TIMEOUT_SECONDS = 0.01
        violation_actions.RECALL_ACTION_TIMEOUT_SECONDS = 0.01

    async def asyncTearDown(self) -> None:
        violation_actions.MUTE_ACTION_TIMEOUT_SECONDS = self._mute_timeout
        violation_actions.RECALL_ACTION_TIMEOUT_SECONDS = self._recall_timeout

    async def test_execute_records_failed_statuses_after_mute_recall_timeouts(
        self,
    ) -> None:
        repository = _Repository()
        logger = _Logger()
        executor = ViolationActionExecutor(
            repository,  # type: ignore[arg-type]
            logger=logger,
            default_mute_duration_seconds=60,
            default_mute_escalation_multiplier=2,
            default_mute_escalation_reset_seconds=3600,
        )

        await executor.execute(
            violation_id=7,
            message=ChatMessage(
                platform="aiocqhttp",
                group_id="100",
                user_id="200",
                text="blocked text",
                message_id="300",
            ),
            platform_actions=_HangingPlatformActions(),
        )

        self.assertEqual(
            repository.status_updates,
            [
                (7, "mute", "failed"),
                (7, "recall", "failed"),
                (7, "forward", "not_scheduled"),
            ],
        )
        self.assertIn(("Chat Filter mute action timed out.", ()), logger.errors)
        self.assertIn(("Chat Filter recall action timed out.", ()), logger.errors)


class _Repository:
    def __init__(self) -> None:
        self.status_updates: list[tuple[int, str, str]] = []
        self.push_deliveries: list[ViolationPushDelivery] = []

    def get_enabled_group_mute_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> None:
        _ = platform, group_id
        return None

    def calculate_mute_escalation(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        base_duration_seconds: int,
        default_multiplier: int,
        default_reset_seconds: int,
        max_duration_seconds: int,
    ) -> MuteEscalationDecision:
        _ = (
            platform,
            group_id,
            user_id,
            default_multiplier,
            default_reset_seconds,
            max_duration_seconds,
        )
        return MuteEscalationDecision(
            duration_seconds=base_duration_seconds,
            violation_count=1,
            multiplier=default_multiplier,
            reset_seconds=default_reset_seconds,
        )

    def list_enabled_push_bindings_for_group(
        self,
        *,
        platform: str,
        listening_group_id: str,
    ) -> list[object]:
        _ = platform, listening_group_id
        return []

    def update_violation_action_status(
        self,
        *,
        violation_id: int,
        action: str,
        status: str,
    ) -> None:
        self.status_updates.append((violation_id, action, status))

    def upsert_violation_push_delivery(
        self,
        delivery: ViolationPushDelivery,
    ) -> int:
        self.push_deliveries.append(delivery)
        return len(self.push_deliveries)


class _HangingPlatformActions:
    def probe_capabilities(self, platform: str) -> PlatformActionCapabilities:
        _ = platform
        return PlatformActionCapabilities(
            mute_user=True,
            recall_message=True,
        )

    async def mute_user(self, request: object) -> PlatformActionResult:
        _ = request
        await asyncio.Event().wait()

    async def recall_message(self, request: object) -> PlatformActionResult:
        _ = request
        await asyncio.Event().wait()

    async def send_forward_message(self, request: object) -> PlatformActionResult:
        _ = request
        raise AssertionError("forward action should not run without bindings")

    async def send_text_log(self, request: object) -> PlatformActionResult:
        _ = request
        raise AssertionError("text log action should not run without bindings")

    async def send_file(self, request: SendFileRequest) -> PlatformActionResult:
        _ = request
        raise AssertionError("file action should not run during violation handling")


class _Logger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, tuple[object, ...]]] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append((message, args))


if __name__ == "__main__":
    unittest.main()
