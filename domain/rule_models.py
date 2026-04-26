from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RuleType = Literal["word", "regex"]


@dataclass(frozen=True, slots=True)
class GlobalRule:
    id: int
    rule_type: RuleType
    pattern: str
    position: int
    enabled: bool
    source: str
    created_at: str
