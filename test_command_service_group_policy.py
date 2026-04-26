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


_ASYNCIO = _install_asyncio_stub_if_needed()

from astrbot_plugin_chat_filter.command_service import (  # noqa: E402
    ChatFilterCommandService,
)
from astrbot_plugin_chat_filter.models import GroupPolicy, RuntimeState  # noqa: E402
from astrbot_plugin_chat_filter.rule_snapshot import RuleSnapshot  # noqa: E402
from astrbot_plugin_chat_filter.settings import ChatFilterSettings  # noqa: E402


class CommandServiceGroupPolicyTests(unittest.TestCase):
    def test_set_group_enabled_updates_policy_and_preserves_fields(self) -> None:
        state = RuntimeState(
            groups={
                "qq:100": GroupPolicy(
                    enabled=None,
                    inherit_global=False,
                    admin_exempt_enabled=False,
                    custom_words=("alpha",),
                )
            }
        )
        repository = _Repository()
        service = _service(state=state, repository=repository)

        result = _run(service.set_group_enabled("qq:100", True))

        self.assertEqual(result, "Chat Filter enabled for this group.")
        self.assertEqual(
            state.groups["qq:100"],
            GroupPolicy(
                enabled=True,
                inherit_global=False,
                admin_exempt_enabled=False,
                custom_words=("alpha",),
            ),
        )
        self.assertEqual(repository.saved_states, [state])

    def test_set_group_enabled_rejects_missing_group_without_saving(self) -> None:
        state = RuntimeState()
        repository = _Repository()
        service = _service(state=state, repository=repository)

        result = _run(service.set_group_enabled(None, True))

        self.assertEqual(result, "This command must be used in a group chat.")
        self.assertEqual(state.groups, {})
        self.assertEqual(repository.saved_states, [])

    def test_set_group_admin_exempt_updates_policy_and_preserves_fields(self) -> None:
        state = RuntimeState(
            groups={
                "qq:100": GroupPolicy(
                    enabled=True,
                    inherit_global=False,
                    admin_exempt_enabled=True,
                    custom_words=("alpha", "beta"),
                )
            }
        )
        repository = _Repository()
        service = _service(state=state, repository=repository)

        result = _run(service.set_group_admin_exempt_enabled("qq:100", False))

        self.assertEqual(
            result,
            "Chat Filter admin exemption disabled for this group.",
        )
        self.assertEqual(
            state.groups["qq:100"],
            GroupPolicy(
                enabled=True,
                inherit_global=False,
                admin_exempt_enabled=False,
                custom_words=("alpha", "beta"),
            ),
        )
        self.assertEqual(repository.saved_states, [state])

    def test_set_group_admin_exempt_rejects_missing_group_without_saving(
        self,
    ) -> None:
        state = RuntimeState()
        repository = _Repository()
        service = _service(state=state, repository=repository)

        result = _run(service.set_group_admin_exempt_enabled(None, False))

        self.assertEqual(result, "This command must be used in a group chat.")
        self.assertEqual(state.groups, {})
        self.assertEqual(repository.saved_states, [])

    def test_format_group_status_uses_default_policy_for_new_group(self) -> None:
        service = _service(
            settings=ChatFilterSettings.from_config(
                {"default_group_enabled": True}
            )
        )

        self.assertEqual(
            service.format_group_status("qq:100"),
            "Chat Filter group status: "
            "group=enabled, "
            "inherit_global=enabled, "
            "admin_exempt=enabled, "
            "custom_words=0.",
        )

    def test_format_group_status_reflects_explicit_policy(self) -> None:
        service = _service(
            state=RuntimeState(
                groups={
                    "qq:100": GroupPolicy(
                        enabled=False,
                        inherit_global=False,
                        admin_exempt_enabled=False,
                        custom_words=("alpha", "beta"),
                    )
                }
            ),
            settings=ChatFilterSettings.from_config(
                {"default_group_enabled": True}
            ),
        )

        self.assertEqual(
            service.format_group_status("qq:100"),
            "Chat Filter group status: "
            "group=disabled, "
            "inherit_global=disabled, "
            "admin_exempt=disabled, "
            "custom_words=2.",
        )

    def test_group_status_and_admin_exempt_status_require_group_key(self) -> None:
        service = _service()

        self.assertEqual(
            service.format_group_status(None),
            "This command must be used in a group chat.",
        )
        self.assertEqual(
            service.format_group_admin_exempt_status(None),
            "This command must be used in a group chat.",
        )

    def test_format_group_admin_exempt_status_reflects_policy(self) -> None:
        service = _service(
            state=RuntimeState(
                groups={
                    "qq:100": GroupPolicy(admin_exempt_enabled=False),
                    "qq:101": GroupPolicy(admin_exempt_enabled=True),
                }
            )
        )

        self.assertEqual(
            service.format_group_admin_exempt_status("qq:100"),
            "Chat Filter group admin exemption: disabled.",
        )
        self.assertEqual(
            service.format_group_admin_exempt_status("qq:101"),
            "Chat Filter group admin exemption: enabled.",
        )

    def test_group_policy_save_failure_reports_state_update_failed(self) -> None:
        state = RuntimeState()
        logger = _Logger()
        service = _service(
            state=state,
            repository=_Repository(save_error=RuntimeError("boom")),
            logger=logger,
        )

        result = _run(service.set_group_enabled("qq:100", True))

        self.assertEqual(result, "Chat Filter state update failed.")
        self.assertEqual(
            state.groups["qq:100"],
            GroupPolicy(enabled=True),
        )
        self.assertEqual(logger.errors, ["Chat Filter state save failed: error_type=%s"])


def _service(
    *,
    state: RuntimeState | None = None,
    settings: ChatFilterSettings | None = None,
    repository: "_Repository | None" = None,
    logger: "_Logger | None" = None,
) -> ChatFilterCommandService:
    return ChatFilterCommandService(
        repository=repository or _Repository(),  # type: ignore[arg-type]
        state=state or RuntimeState(),
        settings=settings or ChatFilterSettings.from_config({}),
        rule_snapshot=RuleSnapshot(
            global_words=(),
            global_regex_rules=(),
            case_sensitive=False,
        ),
        logger=logger or _Logger(),
    )


class _Repository:
    def __init__(self, save_error: Exception | None = None) -> None:
        self._save_error = save_error
        self.saved_states: list[RuntimeState] = []

    def save(self, state: RuntimeState) -> None:
        if self._save_error is not None:
            raise self._save_error
        self.saved_states.append(state)


class _Logger:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append(message)

    def warning(self, message: str, *args: object) -> None:
        self.warnings.append(message)


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
