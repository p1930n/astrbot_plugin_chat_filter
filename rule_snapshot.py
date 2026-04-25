from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .rule_models import GlobalRule
from .settings import (
    DEFAULT_GLOBAL_REGEX_RULES,
    DEFAULT_GLOBAL_WORDS,
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
class LegacyRuleSeed:
    words: tuple[str, ...] = ()
    regex_patterns: tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any] | None,
        *,
        settings: ChatFilterSettings,
    ) -> "LegacyRuleSeed":
        data = config or {}
        regex_rules = normalize_regex_rules(
            _config_list_or_default(
                data,
                key="global_regex_rules",
                default=DEFAULT_GLOBAL_REGEX_RULES,
            ),
            case_sensitive=settings.case_sensitive,
            max_count=DEFAULT_MAX_REGEX_RULE_COUNT,
            max_length=DEFAULT_MAX_REGEX_RULE_LENGTH,
        )
        return cls(
            words=normalize_words(
                _config_list_or_default(
                    data,
                    key="global_words",
                    default=DEFAULT_GLOBAL_WORDS,
                ),
                max_count=settings.max_word_count,
                max_length=settings.max_word_length,
            ),
            regex_patterns=tuple(rule.pattern for rule in regex_rules),
        )

    @property
    def source_hash(self) -> str:
        payload = json.dumps(
            {
                "regex_patterns": self.regex_patterns,
                "words": self.words,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _config_list_or_default(
    data: dict[str, Any],
    *,
    key: str,
    default: tuple[str, ...],
) -> object:
    if key not in data:
        return default
    return data[key]
