from __future__ import annotations

import sys
import tempfile
import types
import unittest
from dataclasses import fields
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


class _AstrMessageEvent:
    pass


def _install_astrbot_stubs() -> None:
    astrbot_module = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    api_module = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
    event_module = sys.modules.setdefault(
        "astrbot.api.event",
        types.ModuleType("astrbot.api.event"),
    )

    api_module.AstrBotConfig = dict
    event_module.AstrMessageEvent = getattr(
        event_module,
        "AstrMessageEvent",
        _AstrMessageEvent,
    )
    astrbot_module.api = api_module
    api_module.event = event_module


_install_astrbot_stubs()

from astrbot_plugin_chat_filter.runtime import plugin_runtime  # noqa: E402
from astrbot_plugin_chat_filter.platform.platform_actions import QQPlatformActions  # noqa: E402


class PluginRuntimeBuilderTests(unittest.TestCase):
    def test_runtime_dataclass_exposes_main_mount_fields(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(plugin_runtime.ChatFilterRuntime)),
            (
                "settings",
                "data_root",
                "repository",
                "rule_snapshot",
                "state",
                "command_service",
                "matcher",
                "metrics",
                "platform_actions",
                "violation_action_executor",
                "violation_recorder",
                "violation_job_queue",
                "message_filter_service",
                "report_service",
                "file_probe_service",
                "command_authorizer",
                "command_controller",
                "platform_action_factory",
                "group_member_role_resolver",
                "command_gateway",
            ),
        )

    def test_builder_wires_runtime_and_platform_action_logger(self) -> None:
        logger = _Logger()
        with tempfile.TemporaryDirectory() as data_root:
            runtime = _build_runtime(data_root, logger=logger)

            self.assertEqual(runtime.data_root, data_root)
            self.assertIs(runtime.command_gateway._controller, runtime.command_controller)
            self.assertIs(
                runtime.command_gateway._platform_action_factory,
                runtime.platform_action_factory,
            )
            self.assertIs(
                runtime.command_gateway._group_member_role_resolver,
                runtime.group_member_role_resolver,
            )
            self.assertIs(
                runtime.message_filter_service._violation_job_queue,
                runtime.violation_job_queue,
            )
            self.assertIs(
                runtime.violation_job_queue._violation_recorder,
                runtime.violation_recorder,
            )
            self.assertIs(
                runtime.violation_job_queue._violation_action_executor,
                runtime.violation_action_executor,
            )
            self.assertIs(runtime.message_filter_service._metrics, runtime.metrics)
            platform_actions = runtime.platform_action_factory.for_platform(
                "aiocqhttp",
                object(),
            )
            self.assertIs(platform_actions._logger, logger)

    def test_builder_uses_injected_platform_actions_by_default(self) -> None:
        injected_platform_actions = QQPlatformActions()
        with tempfile.TemporaryDirectory() as data_root:
            runtime = _build_runtime(
                data_root,
                platform_actions=injected_platform_actions,
            )

            self.assertIs(runtime.platform_actions, injected_platform_actions)
            self.assertIs(
                runtime.platform_action_factory.for_platform("qq", None),
                injected_platform_actions,
            )


class _Context:
    def get_config(self) -> dict[str, object]:
        return {"admins_id": ("42",)}


class _Logger:
    def error(self, *_args: object, **_kwargs: object) -> None:
        pass

    def warning(self, *_args: object, **_kwargs: object) -> None:
        pass


def _build_runtime(
    data_root: str,
    *,
    logger: _Logger | None = None,
    platform_actions: QQPlatformActions | None = None,
) -> plugin_runtime.ChatFilterRuntime:
    original_default_data_root = plugin_runtime.default_data_root
    plugin_runtime.default_data_root = lambda: data_root
    try:
        return plugin_runtime.build_chat_filter_runtime(
            _Context(),
            {},
            platform_actions,
            logger or _Logger(),
        )
    finally:
        plugin_runtime.default_data_root = original_default_data_root


if __name__ == "__main__":
    unittest.main()
