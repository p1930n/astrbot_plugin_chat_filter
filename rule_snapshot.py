from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from .rule_models import GlobalRule
from .settings import (
    DEFAULT_MAX_REGEX_RULE_COUNT,
    DEFAULT_MAX_REGEX_RULE_LENGTH,
    ChatFilterSettings,
    RegexRule,
    normalize_regex_rules,
    normalize_words,
)


class GlobalRuleRepository(Protocol):
    def list_global_rules(self) -> list[GlobalRule]:
        ...


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    global_words: tuple[str, ...]
    global_regex_rules: tuple[RegexRule, ...]
    case_sensitive: bool
    global_word_count: int = field(init=False)
    global_regex_rule_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "global_word_count", len(self.global_words))
        object.__setattr__(
            self,
            "global_regex_rule_count",
            len(self.global_regex_rules),
        )

    @classmethod
    def from_repository(
        cls,
        repository: GlobalRuleRepository,
        *,
        settings: ChatFilterSettings,
    ) -> "RuleSnapshot":
        return cls.from_rules(repository.list_global_rules(), settings=settings)

    @classmethod
    def from_rules(
        cls,
        rules: Iterable[GlobalRule],
        *,
        settings: ChatFilterSettings,
    ) -> "RuleSnapshot":
        enabled_rules = tuple(rule for rule in rules if rule.enabled)
        global_words = normalize_words(
            tuple(
                rule.pattern
                for rule in enabled_rules
                if rule.rule_type == "word"
            ),
            max_count=settings.max_word_count,
            max_length=settings.max_word_length,
        )
        global_regex_rules = normalize_regex_rules(
            tuple(
                rule.pattern
                for rule in enabled_rules
                if rule.rule_type == "regex"
            ),
            case_sensitive=settings.case_sensitive,
            max_count=DEFAULT_MAX_REGEX_RULE_COUNT,
            max_length=DEFAULT_MAX_REGEX_RULE_LENGTH,
        )
        return cls(
            global_words=global_words,
            global_regex_rules=global_regex_rules,
            case_sensitive=settings.case_sensitive,
        )
