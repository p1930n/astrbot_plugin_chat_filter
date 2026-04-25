from __future__ import annotations

from .models import ChatMessage, MatchResult, RuntimeState
from .rule_snapshot import RuleSnapshot
from .settings import ChatFilterSettings, RegexRule


MAX_REGEX_MATCH_TEXT_LENGTH = 2000
MAX_OBFUSCATED_WORD_MATCH_TEXT_LENGTH = 2000
MIN_OBFUSCATED_WORD_LENGTH = 2
REGEX_MATCH_PREFIX = "regex:"


class ChatFilterMatcher:
    def detect(
        self,
        message: ChatMessage,
        settings: ChatFilterSettings,
        state: RuntimeState,
        rule_snapshot: RuleSnapshot,
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
            rule_snapshot.global_words,
            policy.custom_words,
            policy.inherit_global,
        )
        regex_rules = rule_snapshot.global_regex_rules if policy.inherit_global else ()
        rule_count = len(words) + len(regex_rules)
        if not words and not regex_rules:
            return MatchResult(matched=False)

        matched_word = self._detect_word(
            message.text,
            words,
            case_sensitive=rule_snapshot.case_sensitive,
            obfuscated_matching_enabled=(
                settings.obfuscated_word_matching_enabled
            ),
            obfuscated_max_gap=settings.obfuscated_word_max_gap,
        )
        if matched_word is not None:
            return MatchResult(
                matched=True,
                word_count=rule_count,
                matched_word=matched_word,
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
    def _detect_word(
        text: str,
        words: tuple[str, ...],
        *,
        case_sensitive: bool,
        obfuscated_matching_enabled: bool,
        obfuscated_max_gap: int,
    ) -> str | None:
        if not words:
            return None
        haystack = text if case_sensitive else text.casefold()
        needles = words if case_sensitive else tuple(word.casefold() for word in words)
        for original_word, needle in zip(words, needles, strict=True):
            if needle in haystack:
                return original_word

        if not obfuscated_matching_enabled or obfuscated_max_gap <= 0:
            return None

        target = haystack[:MAX_OBFUSCATED_WORD_MATCH_TEXT_LENGTH]
        for original_word, needle in zip(words, needles, strict=True):
            if (
                len(needle) >= MIN_OBFUSCATED_WORD_LENGTH
                and _has_gapped_word_match(target, needle, obfuscated_max_gap)
            ):
                return original_word
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


def _has_gapped_word_match(text: str, word: str, max_gap: int) -> bool:
    first_char = word[0]
    start = text.find(first_char)
    while start != -1:
        position = start
        matched = True
        for char in word[1:]:
            next_start = position + 1
            next_end = min(len(text), position + max_gap + 2)
            next_position = text.find(char, next_start, next_end)
            if next_position == -1:
                matched = False
                break
            position = next_position
        if matched:
            return True
        start = text.find(first_char, start + 1)
    return False
