from __future__ import annotations

import asyncio

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .matcher import ChatFilterMatcher
from .models import ChatMessage, GroupPolicy, RuntimeState
from .repository import ChatFilterRepository, default_data_root
from .settings import ChatFilterSettings, validate_single_word


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

        if self.settings.stop_event:
            event.stop_event()
        if self.settings.warn_user:
            yield event.plain_result(self.settings.warning_message)

    @filter.command_group("chatfilter")
    def chatfilter():
        pass

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

    def _dehydrate_group_message(self, event: AstrMessageEvent) -> ChatMessage:
        platform = _safe_value(event.get_platform_name())
        group_id = _safe_value(event.get_group_id())
        user_id = _safe_value(event.get_sender_id())
        text = _safe_value(getattr(event, "message_str", ""))
        return ChatMessage(platform=platform, group_id=group_id, user_id=user_id, text=text)

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
        return text.lstrip().startswith("/chatfilter")


def _safe_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
