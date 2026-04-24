from __future__ import annotations

from .models import ChatMessage, MatchResult, RuntimeState
from .settings import ChatFilterSettings


class ChatFilterMatcher:
    def detect(
        self,
        message: ChatMessage,
        settings: ChatFilterSettings,
        state: RuntimeState,
    ) -> MatchResult:
        if not message.text:
            return MatchResult(matched=False)
        if not state.effective_global_enabled(settings.enabled):
            return MatchResult(matched=False)

        policy = state.get_group_policy(message.group_key)
        group_enabled = (
            settings.default_group_enabled
            if policy.enabled is None
            else policy.enabled
        )
        if not group_enabled:
            return MatchResult(matched=False)

        words = self._effective_words(settings.global_words, policy.custom_words, policy.inherit_global)
        if not words:
            return MatchResult(matched=False)

        haystack = message.text if settings.case_sensitive else message.text.casefold()
        needles = words if settings.case_sensitive else tuple(word.casefold() for word in words)
        for word in needles:
            if word in haystack:
                return MatchResult(matched=True, word_count=len(words))
        return MatchResult(matched=False, word_count=len(words))

    @staticmethod
    def _effective_words(
        global_words: tuple[str, ...],
        custom_words: tuple[str, ...],
        inherit_global: bool,
    ) -> tuple[str, ...]:
        if not inherit_global:
            return custom_words
        return global_words + custom_words

