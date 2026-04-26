from __future__ import annotations

from collections.abc import Callable

from .models import PlatformEventSnapshot


COMMAND_PERMISSION_DENIED = (
    "Chat Filter command permission denied: "
    "requires AstrBot admin or QQ group owner/admin permission."
)
GROUP_ENABLE_PERMISSION_DENIED = (
    "Chat Filter group enable permission denied: "
    "requires AstrBot admin permission."
)


class CommandAuthorizer:
    def __init__(self, config_provider: Callable[[], object]) -> None:
        self._config_provider = config_provider

    def command_denial(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        allow_group_manager: bool = True,
    ) -> str | None:
        if self.can_use_command(
            snapshot,
            allow_group_manager=allow_group_manager,
        ):
            return None
        if not allow_group_manager:
            return GROUP_ENABLE_PERMISSION_DENIED
        return COMMAND_PERMISSION_DENIED

    def can_use_command(
        self,
        snapshot: PlatformEventSnapshot,
        *,
        allow_group_manager: bool = True,
    ) -> bool:
        if self.check_global_permission(snapshot):
            return True
        return allow_group_manager and snapshot.sender_is_group_manager

    def check_global_permission(self, snapshot: PlatformEventSnapshot) -> bool:
        if not snapshot.sender_id:
            return False
        try:
            config = self._config_provider()
        except Exception:
            return False

        admins = _config_value(config, "admins_id")
        if admins is None:
            admins = _config_value(config, "admin_ids")
        return snapshot.sender_id in _normalized_id_set(admins)


def _config_value(config: object, key: str) -> object:
    if hasattr(config, "get"):
        try:
            value = config.get(key)
        except Exception:
            value = None
        if value is not None:
            return value
    try:
        return getattr(config, key, None)
    except Exception:
        return None


def _normalized_id_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {
            item
            for item in (part.strip() for part in value.replace(",", " ").split())
            if item
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return {item for item in (str(raw).strip() for raw in value) if item}
    normalized = str(value).strip()
    if not normalized:
        return set()
    return {normalized}
