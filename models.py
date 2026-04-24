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
    message_id: str = ""
    sender_display_name: str = ""
    group_display_name: str = ""

    @property
    def group_key(self) -> str:
        return f"{self.platform}:{self.group_id}"


@dataclass(frozen=True, slots=True)
class PlatformEventSnapshot:
    platform: str
    group_id: str
    sender_id: str
    message_id: str = ""
    sender_display_name: str = ""
    group_display_name: str = ""


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    word_count: int = 0
    matched_word: str | None = None


@dataclass(frozen=True, slots=True)
class PushBinding:
    platform: str
    listening_group_id: str
    push_group_id: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class GroupMutePolicy:
    platform: str
    group_id: str
    mute_duration_seconds: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class GroupMuteEscalationPolicy:
    platform: str
    group_id: str
    multiplier: int
    reset_seconds: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MuteEscalationDecision:
    duration_seconds: int
    violation_count: int
    multiplier: int
    reset_seconds: int


@dataclass(frozen=True, slots=True)
class ViolationEvent:
    platform: str
    group_id: str
    user_id: str
    sender_display_name_snapshot: str
    message_id: str
    matched_keyword: str
    matched_content: str
    raw_message_digest: str
    action_mute_status: str
    action_recall_status: str
    action_forward_status: str


@dataclass(frozen=True, slots=True)
class ViolationReportRecord:
    violation_id: int
    created_at: str
    platform: str
    group_id: str
    user_id: str
    sender_display_name_snapshot: str
    matched_keyword: str
    matched_content: str
    action_mute_status: str
    action_recall_status: str
    action_forward_status: str


@dataclass(frozen=True, slots=True)
class ViolationPushDelivery:
    violation_id: int
    platform: str
    listening_group_id: str
    push_group_id: str
    action_status: str
    error_code: str = ""
