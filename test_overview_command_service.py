from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.commands.overview_command_service import (  # noqa: E402
    OverviewCommandService,
)
from astrbot_plugin_chat_filter.domain.models import (  # noqa: E402
    GroupPolicy,
    PushBinding,
    RuntimeState,
)


class OverviewCommandServiceTests(unittest.TestCase):
    def test_overview_summary_counts_enabled_groups_and_push_bindings(self) -> None:
        service = _service(
            state=RuntimeState(
                groups={
                    "qq:100": GroupPolicy(enabled=True),
                    "qq:101": GroupPolicy(enabled=False),
                    "qq:102": GroupPolicy(enabled=True),
                    "telegram:200": GroupPolicy(enabled=True),
                }
            ),
            bindings=[
                _binding("100", "900"),
                _binding("100", "901"),
                _binding("103", "902"),
            ],
        )

        result = asyncio.run(service.format_overview("qq"))

        self.assertEqual(
            result,
            "Chat Filter overview:\n"
            "enabled_groups=2\n"
            "listening_groups=2\n"
            "push_bindings=3\n"
            "Use .cf overview csv for details.",
        )

    def test_overview_csv_merges_enabled_groups_and_listening_groups(self) -> None:
        service = _service(
            state=RuntimeState(
                groups={
                    "qq:100": GroupPolicy(enabled=True),
                    "qq:102": GroupPolicy(enabled=True),
                    "qq:104": GroupPolicy(enabled=False),
                    "telegram:100": GroupPolicy(enabled=True),
                }
            ),
            bindings=[
                _binding("100", "901"),
                _binding("100", "900"),
                _binding("103", "902"),
            ],
        )

        result = asyncio.run(service.format_overview("qq", "csv"))

        self.assertEqual(
            result,
            "group_id,filter_enabled,push_groups\n"
            "100,true,900;901\n"
            "102,true,\n"
            "103,false,902",
        )

    def test_overview_rejects_missing_platform_without_repository_call(self) -> None:
        repository = _Repository([])
        service = _service(repository=repository)

        result = asyncio.run(service.format_overview(""))

        self.assertEqual(
            result,
            "Chat Filter overview failed: platform is unavailable.",
        )
        self.assertEqual(repository.list_calls, [])

    def test_overview_reports_repository_failure_without_leaking_exception(self) -> None:
        logger = _Logger()
        service = _service(
            repository=_Repository(RuntimeError("secret")),
            logger=logger,
        )

        result = asyncio.run(service.format_overview("qq"))

        self.assertEqual(result, "Chat Filter overview failed.")
        self.assertEqual(
            logger.errors,
            [
                (
                    "Chat Filter overview bind list failed: error_type=%s",
                    ("RuntimeError",),
                )
            ],
        )


def _service(
    *,
    state: RuntimeState | None = None,
    bindings: list[PushBinding] | None = None,
    repository: "_Repository | None" = None,
    logger: "_Logger | None" = None,
) -> OverviewCommandService:
    return OverviewCommandService(
        repository=repository or _Repository(bindings or []),  # type: ignore[arg-type]
        state=state or RuntimeState(),
        logger=logger or _Logger(),
    )


def _binding(listening_group_id: str, push_group_id: str) -> PushBinding:
    return PushBinding(
        platform="qq",
        listening_group_id=listening_group_id,
        push_group_id=push_group_id,
    )


class _Repository:
    def __init__(self, result: list[PushBinding] | Exception) -> None:
        self._result = result
        self.list_calls: list[str] = []

    def list_push_bindings(self, *, platform: str) -> list[PushBinding]:
        self.list_calls.append(platform)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _Logger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, tuple[object, ...]]] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append((message, args))


if __name__ == "__main__":
    unittest.main()
