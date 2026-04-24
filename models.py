from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GroupPolicy:
    enabled: bool | None = None
    inherit_global: bool = True
    custom_words: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class RuntimeState:
    global_enabled: bool | None = None
    groups: dict[str, GroupPolicy] = field(default_factory=dict)

    def effective_global_enabled(self, configured_enabled: bool) -> bool:
        if self.global_enabled is None:
            return configured_enabled
        return self.global_enabled

    def get_group_policy(self, group_key: str) -> GroupPolicy:
        return self.groups.get(group_key, GroupPolicy())

    def set_group_policy(self, group_key: str, policy: GroupPolicy) -> None:
        self.groups[group_key] = policy


@dataclass(frozen=True, slots=True)
class ChatMessage:
    platform: str
    group_id: str
    user_id: str
    text: str

    @property
    def group_key(self) -> str:
        return f"{self.platform}:{self.group_id}"


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    word_count: int = 0

