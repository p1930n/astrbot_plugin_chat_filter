from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_PARENT = PACKAGE_DIR.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from astrbot_plugin_chat_filter.persistence.repository import (  # noqa: E402
    ChatFilterRepository,
)


class RepositoryActionPolicyTests(unittest.TestCase):
    def test_missing_action_policy_returns_none(self) -> None:
        with _temporary_directory() as root:
            repository = _repository(root)

            policy = repository.get_group_action_policy(
                platform="qq",
                group_id="100",
            )

            self.assertIsNone(policy)

    def test_set_toggle_creates_default_policy_and_updates_one_action(self) -> None:
        with _temporary_directory() as root:
            repository = _repository(root)

            policy = repository.set_group_action_toggle(
                platform="qq",
                group_id="100",
                action="recall",
                enabled=False,
                updated_by="200",
            )

            self.assertEqual(policy.platform, "qq")
            self.assertEqual(policy.group_id, "100")
            self.assertTrue(policy.mute_enabled)
            self.assertFalse(policy.recall_enabled)
            self.assertTrue(policy.forward_enabled)
            self.assertEqual(policy.mode, "strict")

    def test_set_mode_preserves_toggles_and_is_scoped_by_platform(self) -> None:
        with _temporary_directory() as root:
            repository = _repository(root)
            repository.set_group_action_toggle(
                platform="qq",
                group_id="100",
                action="mute",
                enabled=False,
                updated_by="200",
            )

            policy = repository.set_group_action_mode(
                platform="qq",
                group_id="100",
                mode="audit",
                updated_by="200",
            )
            telegram_policy = repository.get_group_action_policy(
                platform="telegram",
                group_id="100",
            )

            self.assertFalse(policy.mute_enabled)
            self.assertEqual(policy.mode, "audit")
            self.assertIsNone(telegram_policy)

    def test_list_group_action_policies_filters_by_platform(self) -> None:
        with _temporary_directory() as root:
            repository = _repository(root)
            repository.set_group_action_mode(
                platform="qq",
                group_id="200",
                mode="audit",
                updated_by="1",
            )
            repository.set_group_action_mode(
                platform="qq",
                group_id="100",
                mode="strict",
                updated_by="1",
            )
            repository.set_group_action_mode(
                platform="telegram",
                group_id="300",
                mode="audit",
                updated_by="1",
            )

            policies = repository.list_group_action_policies(platform="qq")

            self.assertEqual([policy.group_id for policy in policies], ["100", "200"])


def _repository(root: str) -> ChatFilterRepository:
    return ChatFilterRepository(root, max_word_count=20, max_word_length=80)


@contextmanager
def _temporary_directory() -> Iterator[str]:
    root = PACKAGE_DIR / f".action-policy-test-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield str(root)
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
