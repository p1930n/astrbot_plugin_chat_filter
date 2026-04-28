from __future__ import annotations

import asyncio
import inspect
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


class _DummyCommandGroup:
    def __call__(self, func):
        return self

    def command(self, *_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    def group(self, *_args, **_kwargs):
        def decorator(_func):
            return _DummyCommandGroup()

        return decorator


class _DummyFilter:
    EventMessageType = types.SimpleNamespace(GROUP_MESSAGE="group_message")

    @staticmethod
    def event_message_type(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    @staticmethod
    def command_group(*_args, **_kwargs):
        return _DummyCommandGroup()


class _AstrMessageEvent:
    pass


class _Context:
    pass


class _Star:
    def __init__(self, context):
        self.context = context


class _Logger:
    @staticmethod
    def error(*_args, **_kwargs):
        pass

    @staticmethod
    def warning(*_args, **_kwargs):
        pass


def _install_astrbot_stubs() -> None:
    astrbot_module = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    api_module = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
    event_module = sys.modules.setdefault(
        "astrbot.api.event",
        types.ModuleType("astrbot.api.event"),
    )
    star_module = sys.modules.setdefault(
        "astrbot.api.star",
        types.ModuleType("astrbot.api.star"),
    )

    api_module.AstrBotConfig = dict
    api_module.logger = getattr(api_module, "logger", _Logger())
    event_module.AstrMessageEvent = getattr(
        event_module,
        "AstrMessageEvent",
        _AstrMessageEvent,
    )
    event_module.filter = _DummyFilter()
    star_module.Context = getattr(star_module, "Context", _Context)
    star_module.Star = getattr(star_module, "Star", _Star)
    astrbot_module.api = api_module
    api_module.event = event_module
    api_module.star = star_module


_install_astrbot_stubs()

from astrbot_plugin_chat_filter.main import ChatFilterPlugin  # noqa: E402
from astrbot_plugin_chat_filter.runtime.message_filter_service import (  # noqa: E402
    MessageFilterResult,
)


class MainGroupMessageFilterTests(unittest.TestCase):
    def test_group_message_dehydrates_injects_actions_and_assembles_result(
        self,
    ) -> None:
        action_client = object()
        event = _Event(
            text="blocked text",
            platform_name="aiocqhttp",
            group_id="100",
            sender_id="200",
            action_client=action_client,
        )
        service = _MessageFilterService(
            MessageFilterResult(
                stop_event=True,
                warn_user=True,
                warning_message="warn",
            )
        )
        factory = _PlatformActionFactory()
        plugin = _plugin(service=service, factory=factory)

        results = asyncio.run(_collect(plugin.on_group_message(event)))

        self.assertEqual(results, [])
        self.assertTrue(event.stopped)
        self.assertEqual(len(service.calls), 1)
        message, platform_actions = service.calls[0]
        self.assertEqual(message.platform, "aiocqhttp")
        self.assertEqual(message.group_id, "100")
        self.assertEqual(message.user_id, "200")
        self.assertEqual(message.text, "blocked text")
        self.assertIs(platform_actions, factory.actions)
        self.assertEqual(factory.calls, [("aiocqhttp", action_client)])

    def test_group_message_skips_own_command_before_service(self) -> None:
        event = _Event(
            text=" /cf status",
            platform_name="aiocqhttp",
            group_id="100",
            sender_id="200",
            action_client=object(),
        )
        service = _MessageFilterService(MessageFilterResult())
        factory = _PlatformActionFactory()
        plugin = _plugin(service=service, factory=factory)

        results = asyncio.run(_collect(plugin.on_group_message(event)))

        self.assertEqual(results, [])
        self.assertFalse(event.stopped)
        self.assertEqual(service.calls, [])
        self.assertEqual(factory.calls, [])


class _MessageFilterService:
    def __init__(self, result: MessageFilterResult) -> None:
        self._result = result
        self.calls = []

    async def handle_group_message(self, message, platform_actions):
        self.calls.append((message, platform_actions))
        return self._result


class _PlatformActionFactory:
    def __init__(self) -> None:
        self.actions = object()
        self.calls: list[tuple[str, object | None]] = []

    def for_platform(self, platform: str, action_client: object | None) -> object:
        self.calls.append((platform, action_client))
        return self.actions


class _Event:
    def __init__(
        self,
        *,
        text: str,
        platform_name: str,
        group_id: str,
        sender_id: str,
        action_client: object,
    ) -> None:
        self.message_str = text
        self.platform_name = platform_name
        self.group_id = group_id
        self.sender_id = sender_id
        self.bot = SimpleNamespace(api=action_client)
        self.stopped = False

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        _ = text
        raise AssertionError("violation warning should not use plain_result")


def _plugin(
    *,
    service: _MessageFilterService,
    factory: _PlatformActionFactory,
) -> ChatFilterPlugin:
    plugin = object.__new__(ChatFilterPlugin)
    plugin.message_filter_service = service
    plugin._platform_action_factory = factory
    return plugin


async def _collect(async_generator) -> list[object]:
    if inspect.isawaitable(async_generator):
        result = await async_generator
        return [] if result is None else [result]
    return [item async for item in async_generator]


if __name__ == "__main__":
    unittest.main()
