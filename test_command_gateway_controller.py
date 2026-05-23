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
    CommandAuthorizer,
)
from astrbot_plugin_chat_filter.commands.command_controller import (  # noqa: E402
    GLOBAL_DIAGNOSTICS_PERMISSION_DENIED,
    GROUP_ADD_TO_USAGE,
    GROUP_ADMIN_EXEMPT_USAGE,
    GROUP_BYPASS_ADD_USAGE,
    GROUP_DISABLE_USAGE,
    GROUP_ENABLE_USAGE,
    GROUP_REMOVE_TO_USAGE,
    TARGET_GROUP_PERMISSION_DENIED,
    CommandController,
)
from astrbot_plugin_chat_filter.domain.models import PlatformEventSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.platform.command_gateway import (  # noqa: E402
    CommandGateway,
)
from astrbot_plugin_chat_filter.platform.group_member_role_resolver import (  # noqa: E402
    GroupMemberRoleResolver,
)
from astrbot_plugin_chat_filter.runtime.metrics import ChatFilterMetrics  # noqa: E402


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

    def test_group_enable_allows_current_group_manager(self) -> None:
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

        self.assertEqual(manager_result, "Chat Filter enabled for this group.")
        self.assertEqual(manager_service.group_enabled_calls, [("qq:100", True)])
        self.assertEqual(admin_result, "Chat Filter enabled for this group.")
        self.assertEqual(admin_service.group_enabled_calls, [("qq:100", True)])

    def test_top_level_enable_updates_current_or_target_group_not_global(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        current_result = _run(
            controller.enable(_snapshot(sender_role="member"), "")
        )
        target_result = _run(
            controller.enable(_snapshot(sender_role="member"), "300")
        )

        self.assertEqual(current_result, "Chat Filter enabled for this group.")
        self.assertEqual(target_result, "Chat Filter enabled for this group.")
        self.assertEqual(
            service.group_enabled_calls,
            [("qq:100", True), ("qq:300", True)],
        )

    def test_top_level_enable_rejects_invalid_target_group_without_saving(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(controller.enable(_snapshot(sender_role="member"), "abc"))

        self.assertEqual(result, GROUP_ENABLE_USAGE)
        self.assertEqual(service.group_enabled_calls, [])

    def test_top_level_disable_target_group_requires_global_admin(self) -> None:
        manager_service = _CommandService()
        manager_controller = _controller(service=manager_service)

        manager_result = _run(
            manager_controller.disable(_snapshot(sender_role="admin"), "300")
        )

        admin_service = _CommandService()
        admin_controller = _controller(service=admin_service, admins=("200",))
        admin_result = _run(
            admin_controller.disable(_snapshot(sender_role="member"), "300")
        )

        self.assertEqual(manager_result, TARGET_GROUP_PERMISSION_DENIED)
        self.assertEqual(manager_service.group_enabled_calls, [])
        self.assertEqual(admin_result, "Chat Filter disabled for this group.")
        self.assertEqual(admin_service.group_enabled_calls, [("qq:300", False)])

    def test_top_level_disable_rejects_invalid_target_without_saving(
        self,
    ) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(controller.disable(_snapshot(sender_role="member"), "abc"))

        self.assertEqual(result, GROUP_DISABLE_USAGE)
        self.assertEqual(service.group_enabled_calls, [])

    def test_explicit_target_group_commands_work_outside_group_context(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))
        snapshot = _snapshot(sender_role="", group_id="")

        enable_result = _run(controller.enable(snapshot, "300"))
        disable_result = _run(controller.disable(snapshot, "300"))
        action_status = _run(controller.action_status(snapshot, "300"))
        action_toggle = _run(controller.action_toggle(snapshot, "mute", "300", "off"))
        action_mode = _run(controller.action_mode(snapshot, "300", "audit"))
        add_result = _run(controller.group_add_to(snapshot, "300", "alpha"))
        remove_result = _run(controller.group_remove_to(snapshot, "300", "alpha"))
        bypass_add_result = _run(controller.group_bypass_add(snapshot, "300", "alpha"))

        self.assertEqual(enable_result, "Chat Filter enabled for this group.")
        self.assertEqual(disable_result, "Chat Filter disabled for this group.")
        self.assertEqual(action_status, "action-status:qq:300")
        self.assertEqual(action_toggle, "action-toggle:qq:300:mute:off:200")
        self.assertEqual(action_mode, "action-mode:qq:300:audit:200")
        self.assertEqual(add_result, "Group word added.")
        self.assertEqual(remove_result, "Group word removed.")
        self.assertEqual(bypass_add_result, "Group bypass word added.")
        self.assertEqual(
            service.group_enabled_calls,
            [("qq:300", True), ("qq:300", False)],
        )
        self.assertEqual(service.action_status_calls, [("qq", "300")])
        self.assertEqual(
            service.action_toggle_calls,
            [("qq", "300", "mute", "off", "200")],
        )
        self.assertEqual(service.action_mode_calls, [("qq", "300", "audit", "200")])
        self.assertEqual(service.group_word_calls, [("qq:300", "alpha")])
        self.assertEqual(service.group_word_remove_calls, [("qq:300", "alpha")])
        self.assertEqual(service.group_bypass_word_calls, [("qq:300", "alpha")])

    def test_overview_uses_platform_scope_and_optional_format(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(controller.overview(_snapshot(sender_role="member"), "csv"))

        self.assertEqual(result, "overview:qq:csv")
        self.assertEqual(service.overview_calls, [("qq", "csv")])

    def test_overview_denies_plain_member_without_touching_service(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(controller.overview(_snapshot(sender_role="member"), "csv"))

        self.assertEqual(result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(service.overview_calls, [])

    def test_regex_skips_requires_global_admin(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(controller.regex_skips(_snapshot(sender_role="admin"), "5"))

        self.assertEqual(result, GLOBAL_DIAGNOSTICS_PERMISSION_DENIED)
        self.assertEqual(service.regex_skip_calls, [])

    def test_regex_skips_uses_snapshot_diagnostics(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(controller.regex_skips(_snapshot(sender_role="member"), "5"))

        self.assertEqual(result, "regex-skips:5")
        self.assertEqual(service.regex_skip_calls, ["5"])

    def test_metrics_requires_global_admin(self) -> None:
        controller = _controller(service=_CommandService())

        result = _run(controller.metrics(_snapshot(sender_role="admin")))

        self.assertEqual(result, GLOBAL_DIAGNOSTICS_PERMISSION_DENIED)

    def test_metrics_formats_aggregate_snapshot_for_global_admin(self) -> None:
        metrics = ChatFilterMetrics()
        metrics.increment("message.matched.total")
        metrics.observe_ms("message.matcher.ms", 2.5)
        controller = _controller(
            service=_CommandService(),
            admins=("200",),
            metrics=metrics,
        )

        result = _run(controller.metrics(_snapshot(sender_role="member")))

        self.assertIn("Chat Filter metrics:", result)
        self.assertIn("message.matched.total: 1", result)
        self.assertIn("message.matcher.ms", result)

    def test_action_status_allows_current_group_manager(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(controller.action_status(_snapshot(sender_role="admin"), ""))

        self.assertEqual(result, "action-status:qq:100")
        self.assertEqual(service.action_status_calls, [("qq", "100")])

    def test_action_toggle_target_group_requires_global_admin(self) -> None:
        manager_service = _CommandService()
        manager_controller = _controller(service=manager_service)

        manager_result = _run(
            manager_controller.action_toggle(
                _snapshot(sender_role="admin"),
                "mute",
                "300",
                "off",
            )
        )

        admin_service = _CommandService()
        admin_controller = _controller(service=admin_service, admins=("200",))
        admin_result = _run(
            admin_controller.action_toggle(
                _snapshot(sender_role="member"),
                "mute",
                "300",
                "off",
            )
        )

        self.assertEqual(manager_result, TARGET_GROUP_PERMISSION_DENIED)
        self.assertEqual(manager_service.action_toggle_calls, [])
        self.assertEqual(admin_result, "action-toggle:qq:300:mute:off:200")
        self.assertEqual(
            admin_service.action_toggle_calls,
            [("qq", "300", "mute", "off", "200")],
        )

    def test_action_mode_accepts_current_group_shorthand(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(controller.action_mode(_snapshot(sender_role="owner"), "audit"))

        self.assertEqual(result, "action-mode:qq:100:audit:200")
        self.assertEqual(service.action_mode_calls, [("qq", "100", "audit", "200")])

    def test_action_overview_uses_platform_scope(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(
            controller.action_overview(_snapshot(sender_role="member"), "csv")
        )

        self.assertEqual(result, "action-overview:qq:csv")
        self.assertEqual(service.action_overview_calls, [("qq", "csv")])

    def test_group_add_to_target_group_requires_global_admin(self) -> None:
        manager_service = _CommandService()
        manager_controller = _controller(service=manager_service)

        manager_result = _run(
            manager_controller.group_add_to(
                _snapshot(sender_role="admin"),
                "300",
                "blocked-word",
            )
        )

        admin_service = _CommandService()
        admin_controller = _controller(service=admin_service, admins=("200",))
        admin_result = _run(
            admin_controller.group_add_to(
                _snapshot(sender_role="member"),
                "300",
                "blocked-word",
            )
        )

        self.assertEqual(manager_result, TARGET_GROUP_PERMISSION_DENIED)
        self.assertEqual(manager_service.group_word_calls, [])
        self.assertEqual(admin_result, "Group word added.")
        self.assertEqual(
            admin_service.group_word_calls,
            [("qq:300", "blocked-word")],
        )

    def test_group_add_to_rejects_invalid_target_or_missing_word(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        invalid_group = _run(
            controller.group_add_to(_snapshot(sender_role="member"), "abc", "word")
        )
        missing_word = _run(
            controller.group_add_to(_snapshot(sender_role="member"), "300", "")
        )

        self.assertEqual(invalid_group, GROUP_ADD_TO_USAGE)
        self.assertEqual(missing_word, GROUP_ADD_TO_USAGE)
        self.assertEqual(service.group_word_calls, [])

    def test_group_add_to_accepts_comma_separated_words(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(
            controller.group_add_to(
                _snapshot(sender_role="member"),
                "300",
                "alpha,beta,gamma",
            )
        )

        self.assertEqual(
            result,
            "Group words added: added=3, exists=0, invalid=0, limit=0, failed=0.",
        )
        self.assertEqual(
            service.group_word_calls,
            [("qq:300", "alpha"), ("qq:300", "beta"), ("qq:300", "gamma")],
        )

    def test_group_add_to_batch_summary_counts_non_added_results(self) -> None:
        service = _CommandService(
            group_word_responses=[
                "Group word added.",
                "Group word already exists.",
                "Invalid word length.",
                "Group word limit reached.",
                "Chat Filter state update failed.",
            ]
        )
        controller = _controller(service=service, admins=("200",))

        result = _run(
            controller.group_add_to(
                _snapshot(sender_role="member"),
                "300",
                "one,two,three,four,five",
            )
        )

        self.assertEqual(
            result,
            "Group words added: added=1, exists=1, invalid=1, limit=1, failed=1.",
        )
        self.assertEqual(
            service.group_word_calls,
            [
                ("qq:300", "one"),
                ("qq:300", "two"),
                ("qq:300", "three"),
                ("qq:300", "four"),
                ("qq:300", "five"),
            ],
        )

    def test_group_remove_to_requires_global_admin_and_accepts_batch(self) -> None:
        manager_service = _CommandService()
        manager_controller = _controller(service=manager_service)

        manager_result = _run(
            manager_controller.group_remove_to(
                _snapshot(sender_role="admin"),
                "300",
                "alpha,beta",
            )
        )

        admin_service = _CommandService()
        admin_controller = _controller(service=admin_service, admins=("200",))
        admin_result = _run(
            admin_controller.group_remove_to(
                _snapshot(sender_role="member"),
                "300",
                "alpha,beta",
            )
        )
        missing_word = _run(
            admin_controller.group_remove_to(
                _snapshot(sender_role="member"),
                "300",
                "",
            )
        )

        self.assertEqual(manager_result, TARGET_GROUP_PERMISSION_DENIED)
        self.assertEqual(manager_service.group_word_remove_calls, [])
        self.assertEqual(
            admin_result,
            "Group words removed: removed=2, not_found=0, failed=0.",
        )
        self.assertEqual(missing_word, GROUP_REMOVE_TO_USAGE)
        self.assertEqual(
            admin_service.group_word_remove_calls,
            [("qq:300", "alpha"), ("qq:300", "beta")],
        )

    def test_group_bypass_current_group_commands_allow_group_manager(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        add_result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="admin"),
                "100",
                "global-word",
            )
        )
        second_add_result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="owner"),
                "100",
                "alias-word",
            )
        )
        remove_result = _run(
            controller.group_bypass_remove(
                _snapshot(sender_role="admin"),
                "global-word",
            )
        )
        list_result = _run(controller.group_bypass_list(_snapshot(sender_role="admin")))

        self.assertEqual(add_result, "Group bypass word added.")
        self.assertEqual(second_add_result, "Group bypass word added.")
        self.assertEqual(remove_result, "Group bypass word removed.")
        self.assertEqual(list_result, "Group bypass word count: 2.")
        self.assertEqual(
            service.group_bypass_word_calls,
            [("qq:100", "global-word"), ("qq:100", "alias-word")],
        )
        self.assertEqual(
            service.group_bypass_word_remove_calls,
            [("qq:100", "global-word")],
        )
        self.assertEqual(service.group_bypass_list_calls, ["qq:100"])

    def test_group_bypass_current_group_commands_deny_plain_member(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        add_result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="member"),
                "100",
                "global-word",
            )
        )
        second_add_result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="member"),
                "100",
                "global-word",
            )
        )
        remove_result = _run(
            controller.group_bypass_remove(
                _snapshot(sender_role="member"),
                "global-word",
            )
        )
        list_result = _run(controller.group_bypass_list(_snapshot(sender_role="member")))

        self.assertEqual(add_result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(second_add_result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(remove_result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(list_result, COMMAND_PERMISSION_DENIED)
        self.assertEqual(service.group_bypass_word_calls, [])
        self.assertEqual(service.group_bypass_word_remove_calls, [])
        self.assertEqual(service.group_bypass_list_calls, [])

    def test_group_bypass_add_accepts_comma_separated_words(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="member"),
                "300",
                "alpha,beta，gamma",
            )
        )
        missing_word = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="member"),
                "300",
                "",
            )
        )

        self.assertEqual(
            result,
            "Group bypass words added: "
            "added=3, exists=0, invalid=0, limit=0, failed=0.",
        )
        self.assertEqual(missing_word, GROUP_BYPASS_ADD_USAGE)
        self.assertEqual(
            service.group_bypass_word_calls,
            [("qq:300", "alpha"), ("qq:300", "beta"), ("qq:300", "gamma")],
        )

    def test_group_bypass_add_accepts_inline_target_group(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))

        result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="member"),
                "300",
                "靠",
            )
        )

        self.assertEqual(result, "Group bypass word added.")
        self.assertEqual(service.group_bypass_word_calls, [("qq:300", "靠")])

    def test_group_bypass_add_requires_group_and_word(self) -> None:
        service = _CommandService()
        controller = _controller(service=service, admins=("200",))
        snapshot = _snapshot(sender_role="member")

        missing_word = _run(controller.group_bypass_add(snapshot, "300", ""))
        missing_group = _run(controller.group_bypass_add(snapshot, "", "靠"))

        self.assertEqual(missing_word, GROUP_BYPASS_ADD_USAGE)
        self.assertEqual(missing_group, GROUP_BYPASS_ADD_USAGE)
        self.assertEqual(service.group_bypass_word_calls, [])

    def test_group_bypass_add_inline_target_group_requires_global_admin(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        result = _run(
            controller.group_bypass_add(
                _snapshot(sender_role="admin"),
                "300",
                "靠",
            )
        )

        self.assertEqual(result, TARGET_GROUP_PERMISSION_DENIED)
        self.assertEqual(service.group_bypass_word_calls, [])

    def test_group_bypass_remove_and_list_use_current_group(self) -> None:
        service = _CommandService()
        controller = _controller(service=service)

        remove_result = _run(
            controller.group_bypass_remove(
                _snapshot(sender_role="admin"),
                "alpha,beta",
            )
        )
        list_result = _run(
            controller.group_bypass_list(_snapshot(sender_role="admin"))
        )

        self.assertEqual(
            remove_result,
            "Group bypass words removed: removed=2, not_found=0, failed=0.",
        )
        self.assertEqual(list_result, "Group bypass word count: 2.")
        self.assertEqual(
            service.group_bypass_word_remove_calls,
            [("qq:100", "alpha"), ("qq:100", "beta")],
        )
        self.assertEqual(service.group_bypass_list_calls, ["qq:100"])


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

    def test_gateway_resolves_missing_group_role_from_onebot_api(self) -> None:
        controller = _GatewayController()
        action_client = _ActionClient({"role": "owner"})
        gateway = CommandGateway(
            controller,
            _PlatformActionFactory(),
            GroupMemberRoleResolver(),
        )
        event = _Event(
            sender_id="200",
            sender_role="",
            platform_name="aiocqhttp",
            action_client=action_client,
        )

        result = _run(gateway.group_admin_exempt(event, "status"))

        self.assertEqual(result, "status:200:owner")
        self.assertEqual(
            action_client.calls,
            [("get_group_member_info", {"group_id": 100, "user_id": 200})],
        )
        self.assertEqual(controller.snapshots[0].sender_role, "owner")

    def test_gateway_passes_optional_group_id_to_top_level_enable(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.enable(event, "300"))

        self.assertEqual(result, "enable:300:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)

    def test_gateway_passes_optional_format_to_overview(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.overview(event, "csv"))

        self.assertEqual(result, "overview:csv:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)

    def test_gateway_passes_regex_skips_to_controller(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.regex_skips(event, "3"))

        self.assertEqual(result, "regex-skips:3:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)

    def test_gateway_passes_metrics_to_controller(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.metrics(event))

        self.assertEqual(result, "metrics:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)

    def test_gateway_passes_action_commands_to_controller(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        status = _run(gateway.action_status(event, "300"))
        toggle = _run(gateway.action_toggle(event, "mute", "300", "off"))
        mode = _run(gateway.action_mode(event, "300", "audit"))
        overview = _run(gateway.action_overview(event, "csv"))

        self.assertEqual(status, "action-status:300:200:admin")
        self.assertEqual(toggle, "action-toggle:mute:300:off:200:admin")
        self.assertEqual(mode, "action-mode:300:audit:200:admin")
        self.assertEqual(overview, "action-overview:csv:200:admin")
        self.assertTrue(event.stopped)

    def test_gateway_passes_group_add_to_arguments_to_controller(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        result = _run(gateway.group_add_to(event, "300", "blocked-word"))

        self.assertEqual(result, "group-add-to:300:blocked-word:200:admin")
        self.assertTrue(event.stopped)
        self.assertEqual(len(controller.snapshots), 1)

    def test_gateway_passes_group_remove_and_bypass_commands_to_controller(self) -> None:
        controller = _GatewayController()
        gateway = CommandGateway(controller, _PlatformActionFactory())
        event = _Event(sender_id="200", sender_role="admin")

        remove_to = _run(gateway.group_remove_to(event, "300", "blocked-word"))
        bypass_add = _run(gateway.group_bypass_add(event, "300", "global-word"))
        bypass_remove = _run(gateway.group_bypass_remove(event, "global-word"))
        bypass_remove_target = _run(
            gateway.group_bypass_remove(event, "300", "靠")
        )
        bypass_list = _run(gateway.group_bypass_list(event, "300"))

        self.assertEqual(remove_to, "group-remove-to:300:blocked-word:200:admin")
        self.assertEqual(
            bypass_add,
            "group-bypass-add:300:global-word:200:admin",
        )
        self.assertEqual(
            bypass_remove,
            "group-bypass-remove:global-word:200:admin",
        )
        self.assertEqual(
            bypass_remove_target,
            "group-bypass-remove:300:靠:200:admin",
        )
        self.assertEqual(bypass_list, "group-bypass-list:300:200:admin")
        self.assertTrue(event.stopped)


def _controller(
    *,
    service: "_CommandService",
    admins: tuple[str, ...] = (),
    metrics: ChatFilterMetrics | None = None,
) -> CommandController:
    return CommandController(
        command_service=service,  # type: ignore[arg-type]
        report_service=None,
        file_probe_service=None,
        authorizer=CommandAuthorizer(lambda: {"admins_id": admins}),
        metrics=metrics,
    )


def _snapshot(
    *,
    sender_id: str = "200",
    sender_role: str,
    group_id: str = "100",
) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform="qq",
        group_id=group_id,
        sender_id=sender_id,
        sender_role=sender_role,
    )


class _CommandService:
    def __init__(self, group_word_responses: list[str] | None = None) -> None:
        self.admin_exempt_calls: list[tuple[str | None, bool]] = []
        self.admin_exempt_status_calls: list[str | None] = []
        self.group_enabled_calls: list[tuple[str | None, bool]] = []
        self.overview_calls: list[tuple[str, str]] = []
        self.regex_skip_calls: list[str] = []
        self.action_status_calls: list[tuple[str, str]] = []
        self.action_toggle_calls: list[tuple[str, str, str, str, str]] = []
        self.action_mode_calls: list[tuple[str, str, str, str]] = []
        self.action_overview_calls: list[tuple[str, str]] = []
        self.group_word_calls: list[tuple[str | None, str]] = []
        self.group_word_remove_calls: list[tuple[str | None, str]] = []
        self.group_bypass_word_calls: list[tuple[str | None, str]] = []
        self.group_bypass_word_remove_calls: list[tuple[str | None, str]] = []
        self.group_bypass_list_calls: list[str | None] = []
        self.group_word_responses = group_word_responses or []

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

    async def add_group_word(self, group_key: str | None, word: str) -> str:
        self.group_word_calls.append((group_key, word))
        if self.group_word_responses:
            return self.group_word_responses.pop(0)
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
        self.group_bypass_list_calls.append(group_key)
        return "Group bypass word count: 2."

    async def format_overview(self, platform: str, output_format: str = "") -> str:
        self.overview_calls.append((platform, output_format))
        return f"overview:{platform}:{output_format}"

    def format_regex_skips(self, limit: str = "") -> str:
        self.regex_skip_calls.append(limit)
        return f"regex-skips:{limit}"

    async def format_group_action_policy(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> str:
        self.action_status_calls.append((platform, group_id))
        return f"action-status:{platform}:{group_id}"

    async def set_group_action_toggle(
        self,
        *,
        platform: str,
        group_id: str,
        action: str,
        enabled: str,
        updated_by: str,
    ) -> str:
        self.action_toggle_calls.append(
            (platform, group_id, action, enabled, updated_by)
        )
        return f"action-toggle:{platform}:{group_id}:{action}:{enabled}:{updated_by}"

    async def set_group_action_mode(
        self,
        *,
        platform: str,
        group_id: str,
        mode: str,
        updated_by: str,
    ) -> str:
        self.action_mode_calls.append((platform, group_id, mode, updated_by))
        return f"action-mode:{platform}:{group_id}:{mode}:{updated_by}"

    async def format_action_policy_overview(
        self,
        platform: str,
        output_format: str = "",
    ) -> str:
        self.action_overview_calls.append((platform, output_format))
        return f"action-overview:{platform}:{output_format}"


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

    async def enable(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return f"enable:{group_id}:{snapshot.sender_id}:{snapshot.sender_role}"

    async def overview(
        self,
        snapshot: PlatformEventSnapshot,
        output_format: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return f"overview:{output_format}:{snapshot.sender_id}:{snapshot.sender_role}"

    async def regex_skips(
        self,
        snapshot: PlatformEventSnapshot,
        limit: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return f"regex-skips:{limit}:{snapshot.sender_id}:{snapshot.sender_role}"

    async def metrics(self, snapshot: PlatformEventSnapshot) -> str:
        self.snapshots.append(snapshot)
        return f"metrics:{snapshot.sender_id}:{snapshot.sender_role}"

    async def action_status(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return f"action-status:{group_id}:{snapshot.sender_id}:{snapshot.sender_role}"

    async def action_toggle(
        self,
        snapshot: PlatformEventSnapshot,
        action: str,
        group_id: str = "",
        enabled: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"action-toggle:{action}:{group_id}:{enabled}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def action_mode(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        mode: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"action-mode:{group_id}:{mode}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def action_overview(
        self,
        snapshot: PlatformEventSnapshot,
        output_format: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"action-overview:{output_format}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def group_add_to(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"group-add-to:{group_id}:{word}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def group_remove_to(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"group-remove-to:{group_id}:{word}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def group_bypass_add(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
        word: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        return (
            f"group-bypass-add:{group_id}:{word}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def group_bypass_remove(
        self,
        snapshot: PlatformEventSnapshot,
        group_id_or_word: str = "",
        word: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        if word:
            return (
                f"group-bypass-remove:{group_id_or_word}:{word}:"
                f"{snapshot.sender_id}:{snapshot.sender_role}"
            )
        return (
            f"group-bypass-remove:{group_id_or_word}:"
            f"{snapshot.sender_id}:{snapshot.sender_role}"
        )

    async def group_bypass_list(
        self,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        self.snapshots.append(snapshot)
        if group_id:
            return f"group-bypass-list:{group_id}:{snapshot.sender_id}:{snapshot.sender_role}"
        return f"group-bypass-list:{snapshot.sender_id}:{snapshot.sender_role}"


class _PlatformActionFactory:
    pass


class _Event:
    def __init__(
        self,
        *,
        sender_id: str,
        sender_role: str,
        platform_name: str = "qq",
        action_client: object | None = None,
    ) -> None:
        self.platform_name = platform_name
        self.group_id = "100"
        self.sender_id = sender_id
        self.sender_role = sender_role
        if action_client is not None:
            self.bot = types.SimpleNamespace(api=action_client)
        self.stopped = False

    def stop_event(self) -> None:
        self.stopped = True

    def plain_result(self, text: str) -> str:
        return text


class _ActionClient:
    def __init__(self, result: dict[str, object]) -> None:
        self._result = result
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_action(self, action: str, **params: object) -> dict[str, object]:
        self.calls.append((action, params))
        return self._result


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
