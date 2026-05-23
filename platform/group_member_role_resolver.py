from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any, Protocol

from ..domain.models import ChatMessage, PlatformEventSnapshot, normalize_sender_role


ONEBOT_PLATFORM = "aiocqhttp"
ONEBOT_GROUP_MEMBER_INFO_ACTION = "get_group_member_info"
GROUP_MEMBER_ROLE_QUERY_TIMEOUT_SECONDS = 3.0
GROUP_MEMBER_ROLE_CACHE_TTL_SECONDS = 300.0
GROUP_MEMBER_ROLE_CACHE_MAX_ENTRIES = 4096


class GroupMemberRoleActionClient(Protocol):
    async def call_action(self, action: str, **params: Any) -> Any:
        ...


class GroupMemberRoleLogger(Protocol):
    def warning(self, message: str, *args: object) -> None:
        ...


@dataclass(frozen=True, slots=True)
class _RoleCacheEntry:
    role: str
    expires_at: float


class GroupMemberRoleResolver:
    def __init__(
        self,
        *,
        logger: GroupMemberRoleLogger | None = None,
        query_timeout_seconds: float = GROUP_MEMBER_ROLE_QUERY_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = GROUP_MEMBER_ROLE_CACHE_TTL_SECONDS,
        cache_max_entries: int = GROUP_MEMBER_ROLE_CACHE_MAX_ENTRIES,
    ) -> None:
        self._logger = logger
        self._query_timeout_seconds = query_timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_entries = cache_max_entries
        self._cache: dict[tuple[str, str, str], _RoleCacheEntry] = {}

    async def resolve_snapshot(
        self,
        snapshot: PlatformEventSnapshot,
        action_client: object | None,
    ) -> PlatformEventSnapshot:
        if snapshot.sender_role:
            return snapshot
        role = await self._resolve_role(
            platform=snapshot.platform,
            group_id=snapshot.group_id,
            user_id=snapshot.sender_id,
            action_client=action_client,
            use_cache=False,
        )
        if not role:
            return snapshot
        return replace(snapshot, sender_role=role)

    async def resolve_message(
        self,
        message: ChatMessage,
        action_client: object | None,
    ) -> ChatMessage:
        if message.sender_role:
            return message
        role = await self._resolve_role(
            platform=message.platform,
            group_id=message.group_id,
            user_id=message.user_id,
            action_client=action_client,
            use_cache=True,
        )
        if not role:
            return message
        return replace(message, sender_role=role)

    async def _resolve_role(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        action_client: object | None,
        use_cache: bool,
    ) -> str:
        if platform != ONEBOT_PLATFORM or action_client is None:
            return ""
        parsed_group_id = _parse_positive_int(group_id)
        parsed_user_id = _parse_positive_int(user_id)
        if parsed_group_id is None or parsed_user_id is None:
            return ""

        cache_key = (platform, group_id, user_id)
        now = monotonic()
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None and cached.expires_at > now:
                return cached.role
            if cached is not None:
                self._cache.pop(cache_key, None)

        role = await self._query_role(
            action_client,
            group_id=parsed_group_id,
            user_id=parsed_user_id,
        )
        if role:
            self._store_cache_entry(cache_key, role, now)
        return role

    async def _query_role(
        self,
        action_client: object,
        *,
        group_id: int,
        user_id: int,
    ) -> str:
        call_action = getattr(action_client, "call_action", None)
        if call_action is None:
            return ""
        try:
            member_info = await asyncio.wait_for(
                call_action(
                    ONEBOT_GROUP_MEMBER_INFO_ACTION,
                    group_id=group_id,
                    user_id=user_id,
                ),
                timeout=self._query_timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._log_lookup_failure("timeout")
            return ""
        except Exception as exc:
            self._log_lookup_failure(type(exc).__name__)
            return ""

        if not isinstance(member_info, Mapping):
            return ""
        role = member_info.get("role")
        if role is None:
            return ""
        return normalize_sender_role(str(role))

    def _store_cache_entry(
        self,
        cache_key: tuple[str, str, str],
        role: str,
        now: float,
    ) -> None:
        self._prune_cache(now)
        while len(self._cache) >= self._cache_max_entries:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = _RoleCacheEntry(
            role=role,
            expires_at=now + self._cache_ttl_seconds,
        )

    def _prune_cache(self, now: float) -> None:
        for key, entry in tuple(self._cache.items()):
            if entry.expires_at <= now:
                self._cache.pop(key, None)

    def _log_lookup_failure(self, error_type: str) -> None:
        if self._logger is None:
            return
        self._logger.warning(
            "Chat Filter group member role lookup failed: error_type=%s",
            error_type,
        )


def _parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed
