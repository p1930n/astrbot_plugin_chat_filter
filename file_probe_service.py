from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .models import PlatformEventSnapshot
from .platform_actions import PlatformActions, SendFileRequest


MAX_QQ_GROUP_ID_LENGTH = 20
FILE_PROBE_DIRECTORY_NAME = "probes"
FILE_PROBE_DISPLAY_NAME = "chat-filter-file-probe.txt"
FILE_PROBE_TIMEOUT_SECONDS = 30


class FileProbeLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...

    def warning(self, message: str, *args: object) -> None:
        ...


@dataclass(frozen=True, slots=True)
class FileProbeArtifact:
    path: Path
    display_name: str


class FileProbeService:
    def __init__(self, *, data_root: str, logger: FileProbeLogger) -> None:
        self._data_root = Path(data_root)
        self._logger = logger

    async def run_file_probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
        target_group_id: str,
    ) -> str:
        group_id = target_group_id.strip() or snapshot.group_id
        if not _is_valid_qq_group_id(group_id):
            return "Usage: .cf file-probe [group] or /cf file-probe [group]"
        if not snapshot.platform:
            return "Chat Filter file probe failed: platform is unavailable."

        try:
            artifact = await asyncio.to_thread(self._write_probe_file)
        except Exception as exc:
            self._logger.error(
                "Chat Filter file probe artifact write failed: error_type=%s",
                type(exc).__name__,
            )
            return "Chat Filter file probe failed."

        try:
            result = await asyncio.wait_for(
                platform_actions.send_file(
                    SendFileRequest(
                        platform=snapshot.platform,
                        target_group_id=group_id,
                        file_path=artifact.path,
                        display_name=artifact.display_name,
                    )
                ),
                timeout=FILE_PROBE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.warning("Chat Filter file probe timed out.")
            return "Chat Filter file probe: failed (timeout)."

        if result.reason:
            return f"Chat Filter file probe: {result.status} ({result.reason})."
        return f"Chat Filter file probe: {result.status}."

    def _write_probe_file(self) -> FileProbeArtifact:
        probe_dir = self._data_root / FILE_PROBE_DIRECTORY_NAME
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_path = probe_dir / FILE_PROBE_DISPLAY_NAME
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        probe_path.write_text(
            "\n".join(
                [
                    "Chat Filter file probe",
                    f"generated_at={generated_at}",
                    "purpose=manual adapter file upload verification",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return FileProbeArtifact(
            path=probe_path,
            display_name=FILE_PROBE_DISPLAY_NAME,
        )


def _is_valid_qq_group_id(value: str) -> bool:
    return value.isdigit() and 0 < len(value) <= MAX_QQ_GROUP_ID_LENGTH
