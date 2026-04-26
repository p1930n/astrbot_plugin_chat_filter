from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


def _install_asyncio_stub_if_needed():
    try:
        return __import__("asyncio")
    except Exception:
        for key in list(sys.modules):
            if key == "asyncio" or key.startswith("asyncio."):
                sys.modules.pop(key, None)

        asyncio_module = types.ModuleType("asyncio")

        async def to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        asyncio_module.to_thread = to_thread
        sys.modules["asyncio"] = asyncio_module
        return asyncio_module


def _install_astrbot_stubs() -> None:
    astrbot_module = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    api_module = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
    event_module = sys.modules.setdefault(
        "astrbot.api.event",
        types.ModuleType("astrbot.api.event"),
    )

    event_module.AstrMessageEvent = getattr(
        event_module,
        "AstrMessageEvent",
        type("AstrMessageEvent", (), {}),
    )
    astrbot_module.api = api_module
    api_module.event = event_module


_ASYNCIO = _install_asyncio_stub_if_needed()
_install_astrbot_stubs()

from astrbot_plugin_chat_filter.commands.command_auth import (  # noqa: E402
    COMMAND_PERMISSION_DENIED,
    GROUP_ENABLE_PERMISSION_DENIED,
    CommandAuthorizer,
)
from astrbot_plugin_chat_filter.commands.command_controller import (  # noqa: E402
    GROUP_ADMIN_EXEMPT_USAGE,
    CommandController,
)
from astrbot_plugin_chat_filter.platform.command_gateway import CommandGateway  # noqa: E402
from astrbot_plugin_chat_filter.domain.models import PlatformEventSnapshot  # noqa: E402


class CommandControllerAdminExemptTests(unittest.TestCase):
    def test_admin_exempt_denies_plain_member_without_touching_service(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(
            controller.group_admin_exempt_response(
                _snapshot(sender_role="member"),
                "disable",
            )
        )

        self.assertEqual(result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(service.admin_exempt_calls, [])
        self.assertEqual(service.admin_exempt_status_calls, [])

    def test_admin_exempt_allows_group_manager_to_toggle_policy(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(
            controller.group_admin_exempt_response(
                _snapshot(sender_role="admin"),
                "off",
            )
        )

        self.assertEqual(
            result,
            "Chat Filter admin exemption disabled for this group.",
        )
        self.assertEqual(service.admin_exempt_calls, [("qq:100", False)])

    def test_admin_exempt_status_and_invalid_action_do_not_toggle_policy(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)
        snapshot = _snapshot(sender_role="owner")

        status = _run(controller.group_admin_exempt_response(snapshot, ""))
        invalid = _run(controller.group_admin_exempt_response(snapshot, "maybe"))

        self.assertEqual(status, "Chat Filter group admin exemption: enabled.")
        self.assertEqual(invalid, GROUP_ADMIN_EXEMPT_USAGE)
        self.assertEqual(service.admin_exempt_status_calls, ["qq:100"])
        self.assertEqual(service.admin_exempt_calls, [])

    def test_group_enable_uses_stricter_global_admin_authorization(self) -> None:
        manager_service = _CommandService()
        manager_controller = _controller(service=manager_service)

        manager_result = _run(
            manager_controller.group_enable(_snapshot(sender_role="admin"))
        )

        admin_service = _CommandService()
        admin_controller = _controller(service=admin_service, admins=("200",))
        admin_result = _run(
            admin_controller.group_enable(_snapshot(sender_role="member"))
        )

        self.assertEqual(manager_result, GROUP_ENABLE_PERMISSION_DENIED)
        self.assertEqual(manager_service.group_enabled_calls, [])
        self.assertEqual(admin_result, "Chat Filter enabled for this group.")
        self.assertEqual(admin_service.group_enabled_calls, [("qq:100", True)])


class CommandGatewayAdminExemptTests(unittest.TestCase):
    def test_gateway_stops_event_and_dehydrates_snapshot_for_admin_exempt(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.group_admin_exempt(event, "disable"))

        self.assertEqual(result, "disable:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)
        self.assertEqual(controller.snapshots[0].platform, "qq")
        self.assertEqual(controller.snapshots[0].group_id, "100")
        self.assertEqual(controller.snapshots[0].sender_id, "200")
        self.assertEqual(controller.snapshots[0].sender_role, "admin")


def _controller(
    *,
    service: "_CommandService",
    admins: tuple[str, ...] = (),
) -> CommandController:
    return CommandController(
        command_service=service,  # type: ignore[arg-type]
        report_service=None,
        file_probe_service=None,
        authorizer=CommandAuthorizer(lambda: {"admins_id": admins}),
    )


def _snapshot(
    *,
    sender_id: str = "200",
    sender_role: str,
) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform="qq",
        group_id="100",
        sender_id=sender_id,
        sender_role=sender_role,
    )


class _CommandService:
    def __init__(self) -> None:
        self.admin_exempt_calls: list[tuple[str | None, bool]] = []
        self.admin_exempt_status_calls: list[str | None] = []
        self.group_enabled_calls: list[tuple[str | None, bool]] = []

    def format_group_admin_exempt_status(self, group_key: str | None) -> str:
        self.admin_exempt_status_calls.append(group_key)
        return "Chat Filter group admin exemption: enabled."

    async def set_group_admin_exempt_enabled(
        self,
        group_key: str | None,
        enabled: bool,
    ) -> str:
        self.admin_exempt_calls.append((group_key, enabled))
        if enabled:
            return "Chat Filter admin exemption enabled for this group."
        return "Chat Filter admin exemption disabled for this group."

    async def set_group_enabled(self, group_key: str | None, enabled: bool) -> str:
        self.group_enabled_calls.append((group_key, enabled))
        if enabled:
            return "Chat Filter enabled for this group."
        return "Chat Filter disabled for this group."


class _GatewayController:
    def __init__(self) -> None:
        self.snapshots: list[PlatformEventSnapshot] = []

    async def group_admin_exempt_response(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
    ) -> str:
        self.snapshots.append(snapshot)
        return f"{action}:{snapshot.sender_id}:{snapshot.sender_role}"


class _PlatformActionFactory:
    pass


class _Event:
    def __init__(self, *, sender_id: str, sender_role: str) -> None:
        self.platform_name = "qq"
        self.group_id = "100"
        self.sender_id = sender_id
        self.sender_role = sender_role
        self.stopped = False

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


def _run(awaitable):
    run = getattr(_ASYNCIO, "run", None)
    if run is not None:
        return run(awaitable)
    try:
        awaitable.send(None)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("awaitable yielded instead of completing synchronously")


if __name__ == "__main__":
    unittest.main()
