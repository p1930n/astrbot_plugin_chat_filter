from __future__ import annotations

from .models import ChatMessage, MatchResult, RuntimeState
from .settings import ChatFilterSettings, RegexRule


MAX_REGEX_MATCH_TEXT_LENGTH = 2000
REGEX_MATCH_PREFIX = "regex:"


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

        words = self._effective_words(
            settings.global_words,
            policy.custom_words,
            policy.inherit_global,
        )
        regex_rules = settings.global_regex_rules if policy.inherit_global else ()
        rule_count = len(words) + len(regex_rules)
        if not words and not regex_rules:
            return MatchResult(matched=False)

        haystack = message.text if settings.case_sensitive else message.text.casefold()
        needles = words if settings.case_sensitive else tuple(word.casefold() for word in words)
        for original_word, needle in zip(words, needles, strict=True):
            if needle in haystack:
                return MatchResult(
                    matched=True,
                    word_count=rule_count,
                    matched_word=original_word,
                )

        matched_regex = self._detect_regex(message.text, regex_rules)
        if matched_regex is not None:
            return MatchResult(
                matched=True,
                word_count=rule_count,
                matched_word=f"{REGEX_MATCH_PREFIX}{matched_regex}",
            )
        return MatchResult(matched=False, word_count=rule_count)

    @staticmethod
    def _detect_regex(text: str, rules: tuple[RegexRule, ...]) -> str | None:
        if not rules:
            return None
        target = text[:MAX_REGEX_MATCH_TEXT_LENGTH]
        for rule in rules:
            if rule.compiled.search(target):
                return rule.pattern
        return None

    @staticmethod
    def _effective_words(
        global_words: tuple[str, ...],
        custom_words: tuple[str, ...],
        inherit_global: bool,
    ) -> tuple[str, ...]:
        if not inherit_global:
            return custom_words
        return global_words + custom_words
