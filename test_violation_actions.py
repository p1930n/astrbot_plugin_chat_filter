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
    GroupActionPolicy,
    MuteEscalationDecision,
    PushBinding,
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

    async def test_execute_without_violation_id_still_runs_actions_without_audit(
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
            violation_id=None,
            message=ChatMessage(
                platform="aiocqhttp",
                group_id="100",
                user_id="200",
                text="blocked text",
                message_id="300",
            ),
            platform_actions=_SuccessfulPlatformActions(),
        )

        self.assertEqual(repository.status_updates, [])
        self.assertEqual(repository.push_deliveries, [])

    async def test_execute_without_violation_id_still_forwards_to_bindings(
        self,
    ) -> None:
        repository = _Repository(
            push_bindings=[
                PushBinding(
                    platform="aiocqhttp",
                    listening_group_id="100",
                    push_group_id="900",
                )
            ]
        )
        logger = _Logger()
        platform_actions = _SuccessfulPlatformActions()
        executor = ViolationActionExecutor(
            repository,  # type: ignore[arg-type]
            logger=logger,
            default_mute_duration_seconds=60,
            default_mute_escalation_multiplier=2,
            default_mute_escalation_reset_seconds=3600,
        )

        await executor.execute(
            violation_id=None,
            message=ChatMessage(
                platform="aiocqhttp",
                group_id="100",
                user_id="200",
                text="blocked text",
                message_id="300",
            ),
            platform_actions=platform_actions,
        )

        self.assertEqual(platform_actions.forward_targets, ["900"])
        self.assertEqual(platform_actions.text_log_targets, ["900"])
        self.assertEqual(repository.push_deliveries, [])

    async def test_execute_audit_mode_skips_mute_and_recall_but_forwards(self) -> None:
        repository = _Repository(
            action_policy=GroupActionPolicy(
                platform="aiocqhttp",
                group_id="100",
                mode="audit",
            ),
            push_bindings=[
                PushBinding(
                    platform="aiocqhttp",
                    listening_group_id="100",
                    push_group_id="900",
                )
            ],
        )
        logger = _Logger()
        platform_actions = _SuccessfulPlatformActions()
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
            platform_actions=platform_actions,
        )

        self.assertEqual(platform_actions.mute_calls, 0)
        self.assertEqual(platform_actions.recall_calls, 0)
        self.assertEqual(platform_actions.forward_targets, ["900"])
        self.assertEqual(
            repository.status_updates,
            [
                (7, "mute", "not_scheduled"),
                (7, "recall", "not_scheduled"),
                (7, "forward", "success"),
            ],
        )


class _Repository:
    def __init__(
        self,
        push_bindings: list[PushBinding] | None = None,
        action_policy: GroupActionPolicy | None = None,
    ) -> None:
        self._push_bindings = push_bindings or []
        self._action_policy = action_policy
        self.status_updates: list[tuple[int, str, str]] = []
        self.push_deliveries: list[ViolationPushDelivery] = []

    def get_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> GroupActionPolicy | None:
        _ = platform, group_id
        return self._action_policy

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
    ) -> list[PushBinding]:
        _ = platform, listening_group_id
        return self._push_bindings

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


class _SuccessfulPlatformActions:
    def __init__(self) -> None:
        self.mute_calls = 0
        self.recall_calls = 0
        self.forward_targets: list[str] = []
        self.text_log_targets: list[str] = []

    def probe_capabilities(self, platform: str) -> PlatformActionCapabilities:
        _ = platform
        return PlatformActionCapabilities(
            mute_user=True,
            recall_message=True,
            send_forward_message=True,
            send_text_log=True,
        )

    async def mute_user(self, request: object) -> PlatformActionResult:
        _ = request
        self.mute_calls += 1
        return PlatformActionResult(status="success")

    async def recall_message(self, request: object) -> PlatformActionResult:
        _ = request
        self.recall_calls += 1
        return PlatformActionResult(status="success")

    async def send_forward_message(self, request: object) -> PlatformActionResult:
        self.forward_targets.append(request.target_group_id)
        return PlatformActionResult(status="success")

    async def send_text_log(self, request: object) -> PlatformActionResult:
        self.text_log_targets.append(request.target_group_id)
        return PlatformActionResult(status="success")

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
