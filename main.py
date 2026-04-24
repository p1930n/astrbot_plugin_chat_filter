from __future__ import annotations

import asyncio
from collections import defaultdict
from hashlib import sha256

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .matcher import ChatFilterMatcher
from .models import ChatMessage, GroupPolicy, PushBinding, RuntimeState, ViolationEvent
from .repository import ChatFilterRepository, default_data_root
from .settings import ChatFilterSettings, validate_single_word


ACTION_NOT_SCHEDULED = "not_scheduled"
BIND_LIST_LIMIT = 20
COMMAND_PREFIXES = ("/chatfilter", "/cf", ".cf")
MAX_QQ_GROUP_ID_LENGTH = 20
VIOLATION_EXCERPT_LENGTH = 300


class ChatFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.settings = ChatFilterSettings.from_config(config)
        self.repository = ChatFilterRepository(
            default_data_root(),
            max_word_count=self.settings.max_word_count,
            max_word_length=self.settings.max_word_length,
        )
        self.matcher = ChatFilterMatcher()
        self.state = self._load_state()

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message = self._dehydrate_group_message(event)
        if self._is_own_command(message.text):
            return

        result = self.matcher.detect(message, self.settings, self.state)
        if not result.matched:
            return

        if self.settings.violation_records_enabled:
            await self._try_record_violation(message, result.matched_word)

        if self.settings.stop_event:
            event.stop_event()
        if self.settings.warn_user:
            yield event.plain_result(self.settings.warning_message)

    @filter.command_group("chatfilter")
    def chatfilter():
        pass

    @filter.command_group("cf")
    def cf():
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @cf.command("bind")
    async def cf_bind(
        self,
        event: AstrMessageEvent,
        listening_group: str = "",
        push_group: str = "",
    ):
        if listening_group == "list" and not push_group:
            yield event.plain_result(await self._format_push_bindings(event))
            return

        if not _is_valid_qq_group_id(listening_group) or not _is_valid_qq_group_id(push_group):
            yield event.plain_result("Usage: .cf bind [listening group] [push group]")
            return

        platform = _safe_value(event.get_platform_name())
        if not platform:
            yield event.plain_result("Chat Filter bind failed: platform is unavailable.")
            return

        count = await self._try_add_push_binding(
            platform=platform,
            listening_group_id=listening_group,
            push_group_id=push_group,
            created_by=_safe_value(event.get_sender_id()),
        )
        if count is None:
            yield event.plain_result("Chat Filter bind failed.")
            return

        yield event.plain_result(
            "Chat Filter bind updated: "
            f"{listening_group} has {count} push group(s)."
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("status")
    async def chatfilter_status(self, event: AstrMessageEvent):
        enabled = self.state.effective_global_enabled(self.settings.enabled)
        group_count = len(self.state.groups)
        global_word_count = len(self.settings.global_words)
        yield event.plain_result(
            "Chat Filter status: "
            f"global={'enabled' if enabled else 'disabled'}, "
            f"default_group={'enabled' if self.settings.default_group_enabled else 'disabled'}, "
            f"global_words={global_word_count}, groups={group_count}."
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("enable")
    async def chatfilter_enable(self, event: AstrMessageEvent):
        self.state.global_enabled = True
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Chat Filter enabled globally.")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter.command("disable")
    async def chatfilter_disable(self, event: AstrMessageEvent):
        self.state.global_enabled = False
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Chat Filter disabled globally.")

    @chatfilter.group("group")
    def chatfilter_group():
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("status")
    async def chatfilter_group_status(self, event: AstrMessageEvent):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        policy = self.state.get_group_policy(group_key)
        effective_enabled = (
            self.settings.default_group_enabled
            if policy.enabled is None
            else policy.enabled
        )
        yield event.plain_result(
            "Chat Filter group status: "
            f"group={'enabled' if effective_enabled else 'disabled'}, "
            f"inherit_global={'enabled' if policy.inherit_global else 'disabled'}, "
            f"custom_words={len(policy.custom_words)}."
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("enable")
    async def chatfilter_group_enable(self, event: AstrMessageEvent):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        policy = self._mutable_group_policy(group_key)
        policy.enabled = True
        self.state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Chat Filter enabled for this group.")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("disable")
    async def chatfilter_group_disable(self, event: AstrMessageEvent):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        policy = self._mutable_group_policy(group_key)
        policy.enabled = False
        self.state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Chat Filter disabled for this group.")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("add")
    async def chatfilter_group_add(self, event: AstrMessageEvent, word: str):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        cleaned = validate_single_word(word, max_length=self.settings.max_word_length)
        if cleaned is None:
            yield event.plain_result("Invalid word length.")
            return

        policy = self._mutable_group_policy(group_key)
        if cleaned in policy.custom_words:
            yield event.plain_result("Group word already exists.")
            return
        if len(policy.custom_words) >= self.settings.max_word_count:
            yield event.plain_result("Group word limit reached.")
            return

        policy.custom_words = (*policy.custom_words, cleaned)
        self.state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Group word added.")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("remove")
    async def chatfilter_group_remove(self, event: AstrMessageEvent, word: str):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        policy = self._mutable_group_policy(group_key)
        remaining = tuple(item for item in policy.custom_words if item != word.strip())
        if len(remaining) == len(policy.custom_words):
            yield event.plain_result("Group word not found.")
            return

        policy.custom_words = remaining
        self.state.set_group_policy(group_key, policy)
        if not await self._try_save_state():
            yield event.plain_result("Chat Filter state update failed.")
            return
        yield event.plain_result("Group word removed.")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @chatfilter_group.command("list")
    async def chatfilter_group_list(self, event: AstrMessageEvent):
        group_key = self._current_group_key(event)
        if group_key is None:
            yield event.plain_result("This command must be used in a group chat.")
            return

        policy = self.state.get_group_policy(group_key)
        yield event.plain_result(f"Group custom word count: {len(policy.custom_words)}.")

    def _load_state(self) -> RuntimeState:
        try:
            return self.repository.load()
        except Exception as exc:
            logger.warning("Chat Filter state load failed; using empty runtime state: %s", exc)
            return RuntimeState()

    async def _try_save_state(self) -> bool:
        try:
            await asyncio.to_thread(self.repository.save, self.state)
            return True
        except Exception as exc:
            logger.error("Chat Filter state save failed: %s", exc)
            return False

    async def _try_add_push_binding(
        self,
        *,
        platform: str,
        listening_group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> int | None:
        try:
            return await asyncio.to_thread(
                self.repository.add_push_binding,
                platform=platform,
                listening_group_id=listening_group_id,
                push_group_id=push_group_id,
                created_by=created_by,
            )
        except Exception as exc:
            logger.error("Chat Filter push binding update failed: %s", exc)
            return None

    async def _format_push_bindings(self, event: AstrMessageEvent) -> str:
        platform = _safe_value(event.get_platform_name())
        if not platform:
            return "Chat Filter bind list failed: platform is unavailable."
        try:
            bindings = await asyncio.to_thread(
                self.repository.list_push_bindings,
                platform=platform,
            )
        except Exception as exc:
            logger.error("Chat Filter push binding list failed: %s", exc)
            return "Chat Filter bind list failed."

        if not bindings:
            return "Chat Filter bind list is empty."
        grouped = _group_push_bindings(bindings)
        lines = [
            f"{listening_group}: {', '.join(push_groups)}"
            for listening_group, push_groups in list(grouped.items())[:BIND_LIST_LIMIT]
        ]
        if len(grouped) > BIND_LIST_LIMIT:
            lines.append(f"... and {len(grouped) - BIND_LIST_LIMIT} more group(s).")
        return "Chat Filter bind list:\n" + "\n".join(lines)

    async def _try_record_violation(
        self,
        message: ChatMessage,
        matched_word: str | None,
    ) -> bool:
        if not matched_word:
            return False
        violation = ViolationEvent(
            platform=message.platform,
            group_id=message.group_id,
            user_id=message.user_id,
            sender_display_name_snapshot=message.sender_display_name,
            message_id=message.message_id,
            matched_keyword=matched_word,
            matched_content=_matched_excerpt(message.text, matched_word),
            raw_message_digest=_message_digest(message.text),
            action_mute_status=ACTION_NOT_SCHEDULED,
            action_recall_status=ACTION_NOT_SCHEDULED,
            action_forward_status=ACTION_NOT_SCHEDULED,
        )
        try:
            await asyncio.to_thread(self.repository.record_violation, violation)
            return True
        except Exception as exc:
            logger.error("Chat Filter violation record failed: %s", exc)
            return False

    def _dehydrate_group_message(self, event: AstrMessageEvent) -> ChatMessage:
        platform = _safe_value(event.get_platform_name())
        group_id = _safe_value(event.get_group_id())
        user_id = _safe_value(event.get_sender_id())
        text = _safe_value(getattr(event, "message_str", ""))
        return ChatMessage(
            platform=platform,
            group_id=group_id,
            user_id=user_id,
            text=text,
            message_id=_event_value(event, "get_message_id", "message_id"),
            sender_display_name=_event_value(
                event,
                "get_sender_name",
                "sender_name",
                "nickname",
            ),
        )

    def _current_group_key(self, event: AstrMessageEvent) -> str | None:
        platform = _safe_value(event.get_platform_name())
        group_id = _safe_value(event.get_group_id())
        if not group_id:
            return None
        return f"{platform}:{group_id}"

    def _mutable_group_policy(self, group_key: str) -> GroupPolicy:
        policy = self.state.get_group_policy(group_key)
        return GroupPolicy(
            enabled=policy.enabled,
            inherit_global=policy.inherit_global,
            custom_words=policy.custom_words,
        )

    @staticmethod
    def _is_own_command(text: str) -> bool:
        stripped = text.lstrip()
        return any(stripped.startswith(prefix) for prefix in COMMAND_PREFIXES)


def _safe_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _event_value(event: AstrMessageEvent, *names: str) -> str:
    for name in names:
        value = getattr(event, name, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if value:
            return _safe_value(value)

    message_obj = getattr(event, "message_obj", None)
    if message_obj is not None:
        for name in names:
            value = getattr(message_obj, name, None)
            if value:
                return _safe_value(value)
    return ""


def _is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH


def _group_push_bindings(bindings: list[PushBinding]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for binding in bindings:
        grouped[binding.listening_group_id].append(binding.push_group_id)
    return dict(grouped)


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
