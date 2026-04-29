from __future__ import annotations

import asyncio
from typing import Protocol

from ..domain.models import ViolationPushDelivery
from ..persistence.repository import ChatFilterRepository, ViolationActionName
from ..platform.platform_actions import PlatformActionResult


ACTION_MUTE: ViolationActionName = "mute"
ACTION_RECALL: ViolationActionName = "recall"
ACTION_FORWARD: ViolationActionName = "forward"


class ViolationActionAuditLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...


class ViolationActionAudit:
    def __init__(
        self,
        repository: ChatFilterRepository,
        logger: ViolationActionAuditLogger,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def update_status(
        self,
        *,
        violation_id: int | None,
        action: ViolationActionName,
        result: PlatformActionResult,
    ) -> None:
        if violation_id is None:
            return
        try:
            await asyncio.to_thread(
                self._repository.update_violation_action_status,
                violation_id=violation_id,
                action=action,
                status=result.status,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation action status update failed: "
                "action=%s error_type=%s",
                action,
                type(exc).__name__,
            )

    async def record_push_delivery(
        self,
        delivery: ViolationPushDelivery,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._repository.upsert_violation_push_delivery,
                delivery,
            )
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation push delivery update failed: "
                "push_group_id=%s error_type=%s",
                delivery.push_group_id,
                type(exc).__name__,
            )
