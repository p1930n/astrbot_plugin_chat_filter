from __future__ import annotations

from collections.abc import Callable

from .platform_actions import (
    OneBotV11PlatformActions,
    PlatformActions,
    QQPlatformActions,
)


class PlatformActionFactory:
    def __init__(
        self,
        platform_actions_provider: Callable[[], PlatformActions | None],
    ) -> None:
        self._platform_actions_provider = platform_actions_provider

    def for_platform(
        self,
        platform: str,
        action_client: object | None,
    ) -> PlatformActions:
        platform_actions = self._platform_actions_provider()
        if platform_actions is not None:
            return platform_actions

        if platform != "aiocqhttp":
            return QQPlatformActions()
        return OneBotV11PlatformActions(action_client)
