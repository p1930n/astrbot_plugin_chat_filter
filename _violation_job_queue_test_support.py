from __future__ import annotations

import asyncio

from astrbot_plugin_chat_filter.domain.models import (
    ChatMessage,
    ViolationOutboxEntry,
)
from astrbot_plugin_chat_filter.domain.settings import ChatFilterSettings
from astrbot_plugin_chat_filter.persistence.repository import ChatFilterRepository
from astrbot_plugin_chat_filter.platform.platform_actions import PlatformActionResult
from astrbot_plugin_chat_filter.runtime.metrics import ChatFilterMetrics
from astrbot_plugin_chat_filter.runtime.violation_job_queue import ViolationJobQueue


class Recorder:
    def __init__(self, violation_id: int | None) -> None:
        self._violation_id = violation_id
        self.calls: list[tuple[ChatMessage, str | None]] = []

    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
    ) -> int | None:
        self.calls.append((message, matched_word))
        return self._violation_id


class HangingRecorder(Recorder):
    def __init__(self) -> None:
        super().__init__(violation_id=None)
        self.started = False

    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
    ) -> int | None:
        self.calls.append((message, matched_word))
        self.started = True
        await asyncio.Event().wait()
        return None


class Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[int | None, ChatMessage]] = []

    async def execute(
        self,
        *,
        violation_id: int | None,
        message: ChatMessage,
        platform_actions: "PlatformActions",
    ) -> None:
        _ = platform_actions
        self.calls.append((violation_id, message))


class Logger:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[object, ...]] = []
        self.error_calls: list[tuple[object, ...]] = []

    def warning(self, message: str, *args: object) -> None:
        _ = message
        self.warning_calls.append(args)

    def error(self, message: str, *args: object) -> None:
        _ = message
        self.error_calls.append(args)


class PlatformActions:
    def __init__(self, send_error: Exception | None = None) -> None:
        self._send_error = send_error
        self.text_logs: list[tuple[str, str, str]] = []

    async def send_text_log(self, request) -> PlatformActionResult:
        if self._send_error is not None:
            raise self._send_error
        self.text_logs.append(
            (request.platform, request.target_group_id, request.text)
        )
        return PlatformActionResult(status="success")


def queue(
    *,
    repository: ChatFilterRepository,
    recorder,
    executor: Executor,
    settings: ChatFilterSettings | None = None,
    metrics: ChatFilterMetrics | None = None,
    logger: Logger | None = None,
) -> ViolationJobQueue:
    return ViolationJobQueue(
        settings=settings or ChatFilterSettings.from_config({}),
        repository=repository,
        violation_recorder=recorder,
        violation_action_executor=executor,
        metrics=metrics or ChatFilterMetrics(),
        logger=logger or Logger(),
    )


def repository(root: str) -> ChatFilterRepository:
    return ChatFilterRepository(root, max_word_count=20, max_word_length=80)


def message(text: str, *, message_id: str = "") -> ChatMessage:
    return ChatMessage(
        platform="qq",
        group_id="100",
        user_id="200",
        text=text,
        message_id=message_id,
    )


def outbox_entry(key: str, message_id: str) -> ViolationOutboxEntry:
    return ViolationOutboxEntry(
        idempotency_key=key,
        priority=100,
        platform="qq",
        group_id="100",
        user_id="200",
        message_id=message_id,
        message_text="blocked",
        matched_word="blocked",
        max_attempts=3,
    )


async def wait_for(condition) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met")
