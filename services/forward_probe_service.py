from __future__ import annotations

from ..commands.command_validation import is_valid_qq_group_id
from ..domain.models import PlatformEventSnapshot
from ..platform.platform_actions import (
    ForwardMessageNode,
    PlatformActions,
    SendForwardMessageRequest,
)


FORWARD_PROBE_TEXT = "phase04b forward probe"


class ForwardProbeService:
    async def run_forward_probe(
        self,
        snapshot: PlatformEventSnapshot,
        platform_actions: PlatformActions,
        target_group_id: str,
    ) -> str:
        group_id = target_group_id.strip() or snapshot.group_id
        if not is_valid_qq_group_id(group_id):
            return "Usage: .cf forward-probe [group] or /cf forward-probe [group]"
        if not snapshot.platform:
            return "Chat Filter forward probe failed: platform is unavailable."
        if not snapshot.sender_id:
            return "Chat Filter forward probe failed: sender is unavailable."

        result = await platform_actions.send_forward_message(
            SendForwardMessageRequest(
                platform=snapshot.platform,
                target_group_id=group_id,
                nodes=(
                    ForwardMessageNode(
                        sender_id=snapshot.sender_id,
                        sender_display_name=snapshot.sender_display_name,
                        text=FORWARD_PROBE_TEXT,
                    ),
                ),
            )
        )
        if result.reason:
            return f"Chat Filter forward probe: {result.status} ({result.reason})."
        return f"Chat Filter forward probe: {result.status}."
