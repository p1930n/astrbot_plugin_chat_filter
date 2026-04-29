from __future__ import annotations

from .repository_base import (
    DATABASE_FILENAME,
    GLOBAL_ENABLED_KEY,
    STATE_FILENAME,
    RepositoryBase,
    default_data_root,
)
from .repository_action_policy import ActionPolicyRepositoryMixin
from .repository_mute import MutePolicyRepositoryMixin
from .repository_push_bindings import PushBindingRepositoryMixin
from .repository_rules import RuleRepositoryMixin
from .repository_runtime_state import RuntimeStateRepositoryMixin
from .repository_schema import RepositorySchemaError
from .repository_violations import ViolationActionName, ViolationRepositoryMixin
from ..domain.rule_models import GlobalRule, RuleType


class ChatFilterRepository(
    RuntimeStateRepositoryMixin,
    ActionPolicyRepositoryMixin,
    PushBindingRepositoryMixin,
    MutePolicyRepositoryMixin,
    ViolationRepositoryMixin,
    RuleRepositoryMixin,
    RepositoryBase,
):
    pass


__all__ = [
    "ChatFilterRepository",
    "DATABASE_FILENAME",
    "GLOBAL_ENABLED_KEY",
    "GlobalRule",
    "RepositorySchemaError",
    "RuleType",
    "STATE_FILENAME",
    "ViolationActionName",
    "default_data_root",
]
