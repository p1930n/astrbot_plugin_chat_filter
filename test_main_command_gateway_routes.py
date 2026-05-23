from __future__ import annotations

import sys
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


def _install_asyncio_stub_if_needed() -> None:
    try:
        __import__("asyncio")
    except Exception:
        for key in list(sys.modules):
            if key == "asyncio" or key.startswith("asyncio."):
                sys.modules.pop(key, None)

        asyncio_module = types.ModuleType("asyncio")

        async def to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        asyncio_module.to_thread = to_thread
        sys.modules["asyncio"] = asyncio_module


class _DummyCommandGroup:
    def __call__(self, func: Callable[..., object]) -> "_DummyCommandGroup":
        return self

    def command(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            return func

        return decorator

    def group(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> Callable[[Callable[..., object]], "_DummyCommandGroup"]:
        def decorator(_func: Callable[..., object]) -> "_DummyCommandGroup":
            return _DummyCommandGroup()

        return decorator


class _DummyFilter:
    EventMessageType = types.SimpleNamespace(GROUP_MESSAGE="group_message")

    @staticmethod
    def event_message_type(
        *_args: object,
        **_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            return func

        return decorator

    @staticmethod
    def command_group(*_args: object, **_kwargs: object) -> _DummyCommandGroup:
        return _DummyCommandGroup()


class _AstrMessageEvent:
    pass


class _Context:
    pass


class _Star:
    def __init__(self, context: object) -> None:
        self.context = context


class _Logger:
    @staticmethod
    def error(*_args: object, **_kwargs: object) -> None:
        pass

    @staticmethod
    def warning(*_args: object, **_kwargs: object) -> None:
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


_install_asyncio_stub_if_needed()
_install_astrbot_stubs()

from astrbot_plugin_chat_filter.main import ChatFilterPlugin  # noqa: E402


class MainCommandGatewayRouteTests(unittest.TestCase):
    def test_command_entries_yield_command_gateway_results(self) -> None:
        cases = (
            ("cf_bind", "bind", ("listen-1", "push-1")),
            ("cf_mute", "mute", ("group-1", "30")),
            ("cf_mute_stack", "mute_stack", ("group-1", "2", "60")),
            ("cf_probe", "probe", ()),
            ("cf_forward_probe", "forward_probe", ("group-2",)),
            ("cf_report_dry_run", "report_dry_run", ("listen-1", "7")),
            ("cf_file_probe", "file_probe", ("group-1",)),
            ("cf_help", "help", ()),
            ("cf_status", "status", ()),
            ("cf_overview", "overview", ("csv",)),
            ("cf_regex_skips", "regex_skips", ("5",)),
            ("cf_metrics", "metrics", ()),
            ("cf_action_status", "action_status", ("group-1",)),
            ("cf_action_mode", "action_mode", ("group-1", "audit")),
            ("cf_action_overview", "action_overview", ("csv",)),
            ("cf_enable", "enable", ("group-1",)),
            ("cf_disable", "disable", ("group-1",)),
            ("cf_group_status", "group_status", ()),
            ("cf_group_enable", "group_enable", ()),
            ("cf_group_disable", "group_disable", ()),
            ("cf_group_add", "group_add", ("word",)),
            ("cf_group_add_to", "group_add_to", ("group-1", "word")),
            ("cf_group_remove", "group_remove", ("word",)),
            ("cf_group_remove_to", "group_remove_to", ("group-1", "word")),
            ("cf_group_list", "group_list", ()),
            ("cf_group_bypass_add", "group_bypass_add", ("word",)),
            ("cf_group_bypass_remove", "group_bypass_remove", ("word",)),
            ("cf_group_bypass_list", "group_bypass_list", ()),
            ("cf_group_bypass_add_to", "group_bypass_add_to", ("group-1", "word")),
            ("cf_group_admin_exempt", "group_admin_exempt", ("off",)),
            ("cf_group_exempt", "group_admin_exempt", ("on",)),
        )

        for handler_name, gateway_method, args in cases:
            with self.subTest(handler=handler_name):
                gateway = _CommandGatewayProbe()
                plugin = _plugin(gateway)
                event = _Event()

                results = _collect_async_generator(
                    getattr(plugin, handler_name)(event, *args)
                )

                self.assertEqual(results, [f"gateway:{gateway_method}"])
                self.assertEqual(gateway.calls, [(gateway_method, (event, *args))])

    def test_overview_entries_allow_empty_output_format(self) -> None:
        cases = (
            ("cf_overview", "overview"),
            ("cf_regex_skips", "regex_skips"),
            ("cf_action_status", "action_status"),
            ("cf_action_overview", "action_overview"),
        )

        for handler_name, gateway_method in cases:
            with self.subTest(handler=handler_name):
                gateway = _CommandGatewayProbe()
                plugin = _plugin(gateway)
                event = _Event()

                results = _collect_async_generator(getattr(plugin, handler_name)(event))

                self.assertEqual(results, [f"gateway:{gateway_method}"])
                self.assertEqual(gateway.calls, [(gateway_method, (event, ""))])

    def test_action_toggle_entries_pass_action_name_to_gateway(self) -> None:
        cases = (
            ("cf_action_mute", "mute"),
            ("cf_action_recall", "recall"),
            ("cf_action_forward", "forward"),
        )

        for handler_name, action in cases:
            with self.subTest(handler=handler_name):
                gateway = _CommandGatewayProbe()
                plugin = _plugin(gateway)
                event = _Event()

                results = _collect_async_generator(
                    getattr(plugin, handler_name)(event, "group-1", "off")
                )

                self.assertEqual(results, ["gateway:action_toggle"])
                self.assertEqual(
                    gateway.calls,
                    [("action_toggle", (event, action, "group-1", "off"))],
                )


class _LegacyBridgeFailingPlugin(ChatFilterPlugin):
    def _command_result(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("legacy command result bridge was used")

    async def _group_admin_exempt_command_response(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> str:
        raise AssertionError("legacy admin-exempt response bridge was used")

    async def _group_admin_exempt_command_text(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> str:
        raise AssertionError("legacy admin-exempt text bridge was used")

    def _command_denial(self, *_args: Any, **_kwargs: Any) -> str | None:
        raise AssertionError("legacy command denial bridge was used")

    def _can_use_command(self, *_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("legacy command permission bridge was used")

    def _check_global_permission(self, *_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("legacy global permission bridge was used")

    def _platform_actions_for_event(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("legacy platform action bridge was used")


class _CommandGatewayProbe:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __getattr__(self, name: str) -> Callable[..., Any]:
        async def gateway_method(*args: Any) -> str:
            self.calls.append((name, args))
            return f"gateway:{name}"

        return gateway_method


class _Event:
    pass


def _plugin(gateway: _CommandGatewayProbe) -> ChatFilterPlugin:
    plugin = object.__new__(_LegacyBridgeFailingPlugin)
    plugin._command_gateway = gateway
    return plugin


def _await(awaitable: Any) -> Any:
    try:
        awaitable.send(None)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("awaitable yielded instead of completing synchronously")


def _collect_async_generator(async_generator: Any) -> list[object]:
    items: list[object] = []
    while True:
        try:
            items.append(_await(async_generator.__anext__()))
        except StopAsyncIteration:
            return items


if __name__ == "__main__":
    unittest.main()
