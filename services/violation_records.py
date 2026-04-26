from __future__ import annotations

import asyncio
from hashlib import sha256
from typing import Protocol

from ..domain.models import ChatMessage, ViolationEvent
from ..platform.platform_actions import PlatformActions, ViolationActionStatuses
from ..persistence.repository import ChatFilterRepository


VIOLATION_EXCERPT_LENGTH = 300


class ViolationRecordLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...

    def warning(self, message: str, *args: object) -> None:
        ...


class ViolationRecorder:
    def __init__(
        self,
        repository: ChatFilterRepository,
        logger: ViolationRecordLogger,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def record(
        self,
        message: ChatMessage,
        matched_word: str | None,
        platform_actions: PlatformActions,
    ) -> int | None:
        if not matched_word:
            return None

        action_statuses = self._initial_action_statuses(message, platform_actions)
        violation = ViolationEvent(
            platform=message.platform,
            group_id=message.group_id,
            user_id=message.user_id,
            sender_display_name_snapshot=message.sender_display_name,
            message_id=message.message_id,
            matched_keyword=matched_word,
            matched_content=_matched_excerpt(message.text, matched_word),
            raw_message_digest=_message_digest(message.text),
            action_mute_status=action_statuses.mute,
            action_recall_status=action_statuses.recall,
            action_forward_status=action_statuses.forward,
        )
        try:
            return await asyncio.to_thread(self._repository.record_violation, violation)
        except Exception as exc:
            self._logger.error(
                "Chat Filter violation record failed: error_type=%s",
                type(exc).__name__,
            )
            return None

    def _initial_action_statuses(
        self,
        message: ChatMessage,
        platform_actions: PlatformActions,
    ) -> ViolationActionStatuses:
        try:
            return platform_actions.initial_violation_statuses(message.platform)
        except Exception as exc:
            self._logger.warning(
                "Chat Filter platform action status probe failed: error_type=%s",
                type(exc).__name__,
            )
            return ViolationActionStatuses.unsupported()


def _matched_excerpt(text: str, matched_word: str) -> str:
    if len(text) <= VIOLATION_EXCERPT_LENGTH:
        return text

    haystack = text.casefold()
    needle = matched_word.casefold()
    index = haystack.find(needle)
    if index < 0:
        return text[:VIOLATION_EXCERPT_LENGTH]

    half_window = max((VIOLATION_EXCERPT_LENGTH - len(matched_word)) // 2, 0)
    start = max(index - half_window, 0)
    end = min(start + VIOLATION_EXCERPT_LENGTH, len(text))
    if end - start < VIOLATION_EXCERPT_LENGTH:
        start = max(end - VIOLATION_EXCERPT_LENGTH, 0)
    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt[3:]
    if end < len(text):
        excerpt = excerpt[:-3] + "..."
    return excerpt


def _message_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
