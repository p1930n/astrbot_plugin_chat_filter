from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


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


_install_asyncio_stub_if_needed()
_install_astrbot_stubs()

from astrbot_plugin_chat_filter.commands.command_auth import CommandAuthorizer  # noqa: E402
from astrbot_plugin_chat_filter.commands.command_controller import CommandController  # noqa: E402
from astrbot_plugin_chat_filter.commands.command_controller import (  # noqa: E402
    TARGET_GROUP_PERMISSION_DENIED,
)
from astrbot_plugin_chat_filter.platform.command_gateway import CommandGateway  # noqa: E402
from astrbot_plugin_chat_filter.main import (  # noqa: E402
    COMMAND_PERMISSION_DENIED,
    GROUP_ADMIN_EXEMPT_USAGE,
    ChatFilterPlugin,
)
from astrbot_plugin_chat_filter.platform.platform_action_factory import (  # noqa: E402
    PlatformActionFactory,
)


class MainCommandPermissionTests(unittest.TestCase):
    def test_group_owner_and_admin_can_use_normal_command_gateway(self) -> None:
        for role in ("owner", "admin"):
            with self.subTest(role=role):
                plugin = _plugin(admins=())
                event = _event(sender_id="200", role=role)

                results = _collect_async_generator(plugin.cf_status(event))

                self.assertEqual(results, ["status response"])
                self.assertTrue(event.stopped)
                self.assertEqual(plugin.command_service.status_calls, 1)

    def test_plain_group_member_cannot_use_normal_command_gateway(self) -> None:
        plugin = _plugin(admins=())
        event = _event(sender_id="200", role="member")

        results = _collect_async_generator(plugin.cf_status(event))

        self.assertEqual(results, [COMMAND_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(plugin.command_service.status_calls, 0)

    def test_astrbot_admin_can_use_normal_command_gateway(self) -> None:
        plugin = _plugin(admins=("200",))
        event = _event(sender_id="200", role="member")

        results = _collect_async_generator(plugin.cf_status(event))

        self.assertEqual(results, ["status response"])
        self.assertTrue(event.stopped)
        self.assertEqual(plugin.command_service.status_calls, 1)

    def test_group_enable_allows_group_admin_for_current_group(
        self,
    ) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin")

        results = _collect_async_generator(plugin.cf_group_enable(event))

        self.assertEqual(results, ["Chat Filter enabled for this group."])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [("qq:100", True)])

    def test_group_enable_allows_group_owner_for_current_group(
        self,
    ) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="owner")

        results = _collect_async_generator(plugin.cf_group_enable(event))

        self.assertEqual(results, ["Chat Filter enabled for this group."])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [("qq:100", True)])

    def test_enable_allows_group_admin_for_explicit_current_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(plugin.cf_enable(event, "100"))

        self.assertEqual(results, ["Chat Filter enabled for this group."])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [("qq:100", True)])

    def test_enable_denies_group_admin_for_other_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(plugin.cf_enable(event, "200"))

        self.assertEqual(results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [])

    def test_disable_allows_group_admin_for_explicit_current_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(plugin.cf_disable(event, "100"))

        self.assertEqual(results, ["Chat Filter disabled for this group."])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [("qq:100", False)])

    def test_disable_denies_group_admin_for_other_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(plugin.cf_disable(event, "200"))

        self.assertEqual(results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [])

    def test_group_add_to_denies_group_admin_for_target_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(
            plugin.cf_group_add_to(event, "200", "blocked-word")
        )

        self.assertEqual(results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_word_calls, [])

    def test_group_add_to_allows_astrbot_admin_for_target_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=("200",), command_service=command_service)
        event = _event(sender_id="200", role="member", group_id="100")

        results = _collect_async_generator(
            plugin.cf_group_add_to(event, "200", "blocked-word")
        )

        self.assertEqual(results, ["Group word added."])
        self.assertTrue(event.stopped)
        self.assertEqual(
            command_service.group_word_calls,
            [("qq:200", "blocked-word")],
        )

    def test_group_remove_to_denies_group_admin_for_target_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        results = _collect_async_generator(
            plugin.cf_group_remove_to(event, "200", "blocked-word")
        )

        self.assertEqual(results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_word_remove_calls, [])

    def test_group_remove_to_allows_astrbot_admin_for_target_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=("200",), command_service=command_service)
        event = _event(sender_id="200", role="member", group_id="100")

        results = _collect_async_generator(
            plugin.cf_group_remove_to(event, "200", "blocked-word")
        )

        self.assertEqual(results, ["Group word removed."])
        self.assertTrue(event.stopped)
        self.assertEqual(
            command_service.group_word_remove_calls,
            [("qq:200", "blocked-word")],
        )

    def test_group_bypass_commands_require_astrbot_admin(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="admin", group_id="100")

        add_results = _collect_async_generator(
            plugin.cf_group_bypass_add(event, "global-word")
        )
        remove_results = _collect_async_generator(
            plugin.cf_group_bypass_remove(event, "global-word")
        )
        list_results = _collect_async_generator(plugin.cf_group_bypass_list(event))
        add_to_results = _collect_async_generator(
            plugin.cf_group_bypass_add_to(event, "200", "global-word")
        )

        self.assertEqual(add_results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertEqual(remove_results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertEqual(list_results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertEqual(add_to_results, [TARGET_GROUP_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_bypass_word_calls, [])

    def test_group_bypass_add_allows_astrbot_admin_for_current_group(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=("200",), command_service=command_service)
        event = _event(sender_id="200", role="member", group_id="100")

        results = _collect_async_generator(
            plugin.cf_group_bypass_add(event, "global-word")
        )

        self.assertEqual(results, ["Group bypass word added."])
        self.assertTrue(event.stopped)
        self.assertEqual(
            command_service.group_bypass_word_calls,
            [("qq:100", "global-word")],
        )

    def test_group_enable_allows_astrbot_admin_when_managers_disallowed(
        self,
    ) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=("200",), command_service=command_service)
        event = _event(sender_id="200", role="member")

        results = _collect_async_generator(plugin.cf_group_enable(event))

        self.assertEqual(results, ["Chat Filter enabled for this group."])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.group_enabled_calls, [("qq:100", True)])

    def test_admin_exempt_command_gateway_denies_plain_group_member(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(admins=(), command_service=command_service)
        event = _event(sender_id="200", role="member")

        results = _collect_async_generator(
            plugin.cf_group_admin_exempt(event, "disable")
        )

        self.assertEqual(results, [COMMAND_PERMISSION_DENIED])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.admin_exempt_calls, [])

    def test_admin_exempt_command_gateway_allows_group_manager(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(command_service=command_service)
        event = _event(sender_id="200", role="admin")

        results = _collect_async_generator(
            plugin.cf_group_admin_exempt(event, "disable")
        )

        self.assertEqual(
            results,
            ["Chat Filter admin exemption disabled for this group."],
        )
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.admin_exempt_calls, [("qq:100", False)])

    def test_admin_exempt_alias_gateway_toggles_service(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(command_service=command_service)
        event = _event(sender_id="200", role="owner")

        results = _collect_async_generator(plugin.cf_group_exempt(event, "on"))

        self.assertEqual(
            results,
            ["Chat Filter admin exemption enabled for this group."],
        )
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.admin_exempt_calls, [("qq:100", True)])

    def test_admin_exempt_command_gateway_reports_status(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(command_service=command_service)
        event = _event(sender_id="200", role="admin")

        results = _collect_async_generator(plugin.cf_group_admin_exempt(event))

        self.assertEqual(
            results,
            ["Chat Filter group admin exemption: enabled."],
        )
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.admin_exempt_status_calls, ["qq:100"])

    def test_admin_exempt_command_gateway_rejects_unknown_action(self) -> None:
        command_service = _CommandService()
        plugin = _plugin(command_service=command_service)
        event = _event(sender_id="200", role="admin")

        results = _collect_async_generator(
            plugin.cf_group_admin_exempt(event, "maybe")
        )

        self.assertEqual(results, [GROUP_ADMIN_EXEMPT_USAGE])
        self.assertTrue(event.stopped)
        self.assertEqual(command_service.admin_exempt_calls, [])


class _Config:
    def __init__(self, admins: tuple[str, ...]) -> None:
        self._admins = admins

    def get(self, key: str):
        if key == "admins_id":
            return self._admins
        return None


class _ContextWithConfig:
    def __init__(self, admins: tuple[str, ...]) -> None:
        self._config = _Config(admins)

    def get_config(self):
        return self._config


class _Event:
    def __init__(
        self,
        *,
        platform_name: str,
        group_id: str,
        sender_id: str,
        role: str,
    ) -> None:
        self.platform_name = platform_name
        self.group_id = group_id
        self.sender_id = sender_id
        self.sender_role = role
        self.role = role
        self.stopped = False

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


class _CommandService:
    def __init__(self) -> None:
        self.status_calls = 0
        self.group_enabled_calls: list[tuple[str | None, bool]] = []
        self.group_word_calls: list[tuple[str | None, str]] = []
        self.group_word_remove_calls: list[tuple[str | None, str]] = []
        self.group_bypass_word_calls: list[tuple[str | None, str]] = []
        self.group_bypass_word_remove_calls: list[tuple[str | None, str]] = []
        self.admin_exempt_calls: list[tuple[str | None, bool]] = []
        self.admin_exempt_status_calls: list[str | None] = []

    def format_status(self) -> str:
        self.status_calls += 1
        return "status response"

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        self.group_enabled_calls.append((group_key, enabled))
        if enabled:
            return "Chat Filter enabled for this group."
        return "Chat Filter disabled for this group."

    async def add_group_word(self, group_key: str | None, word: str) -> str:
        self.group_word_calls.append((group_key, word))
        return "Group word added."

    async def remove_group_word(self, group_key: str | None, word: str) -> str:
        self.group_word_remove_calls.append((group_key, word))
        return "Group word removed."

    async def add_group_bypass_word(
        self,
        group_key: str | None,
        word: str,
    ) -> str:
        self.group_bypass_word_calls.append((group_key, word))
        return "Group bypass word added."

    async def remove_group_bypass_word(
        self,
        group_key: str | None,
        word: str,
    ) -> str:
        self.group_bypass_word_remove_calls.append((group_key, word))
        return "Group bypass word removed."

    def format_group_bypass_words(self, group_key: str | None) -> str:
        _ = group_key
        return "Group bypass word count: 1."

    async def set_group_admin_exempt_enabled(
        self,
        group_key: str | None,
        enabled: bool,
    ) -> str:
        self.admin_exempt_calls.append((group_key, enabled))
        if enabled:
            return "Chat Filter admin exemption enabled for this group."
        return "Chat Filter admin exemption disabled for this group."

    def format_group_admin_exempt_status(self, group_key: str | None) -> str:
        self.admin_exempt_status_calls.append(group_key)
        return "Chat Filter group admin exemption: enabled."


def _plugin(
    *,
    admins: tuple[str, ...] = (),
    command_service: _CommandService | None = None,
) -> ChatFilterPlugin:
    plugin = object.__new__(ChatFilterPlugin)
    plugin.context = _ContextWithConfig(admins)
    plugin.command_service = command_service or _CommandService()
    command_authorizer = CommandAuthorizer(plugin.context.get_config)
    command_controller = CommandController(
        plugin.command_service,
        report_service=None,
        file_probe_service=None,
        authorizer=command_authorizer,
    )
    plugin._command_gateway = CommandGateway(
        command_controller,
        PlatformActionFactory(lambda: None),
    )
    return plugin


def _event(
    *,
    sender_id: str = "200",
    role: str = "member",
    platform_name: str = "qq",
    group_id: str = "100",
) -> _Event:
    return _Event(
        platform_name=platform_name,
        group_id=group_id,
        sender_id=sender_id,
        role=role,
    )


def _await(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("awaitable yielded instead of completing synchronously")


def _collect_async_generator(async_generator) -> list[object]:
    items: list[object] = []
    while True:
        try:
            items.append(_await(async_generator.__anext__()))
        except StopAsyncIteration:
            return items


if __name__ == "__main__":
    unittest.main()
