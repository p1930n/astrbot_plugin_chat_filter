from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..commands.command_auth import CommandAuthorizer
from ..commands.command_controller import CommandController
from ..platform.command_gateway import CommandGateway
from ..commands.command_service import ChatFilterCommandService, load_runtime_state
from ..services.file_probe_service import FileProbeService
from ..domain.matcher import ChatFilterMatcher
from .message_filter_service import MessageFilterService
from ..domain.models import RuntimeState
from ..platform.platform_action_factory import PlatformActionFactory
from ..platform.platform_actions import PlatformActions
from ..services.report_service import ViolationReportService
from ..persistence.repository import ChatFilterRepository, default_data_root
from ..domain.rule_snapshot import RuleSnapshot
from ..domain.settings import ChatFilterSettings
from ..services.violation_actions import ViolationActionExecutor
from ..services.violation_records import ViolationRecorder
from .metrics import ChatFilterMetrics
from .violation_job_queue import ViolationJobQueue


class ChatFilterRuntimeContext(Protocol):
    def get_config(self) -> object:
        ...


class ChatFilterRuntimeLogger(Protocol):
    def error(self, message: str, *args: object) -> None:
        ...

    def warning(self, message: str, *args: object) -> None:
        ...


PlatformActionsProvider = Callable[[], PlatformActions | None]


@dataclass(frozen=True, slots=True)
class ChatFilterRuntime:
    settings: ChatFilterSettings
    data_root: str
    repository: ChatFilterRepository
    rule_snapshot: RuleSnapshot
    state: RuntimeState
    command_service: ChatFilterCommandService
    matcher: ChatFilterMatcher
    metrics: ChatFilterMetrics
    platform_actions: PlatformActions | None
    violation_action_executor: ViolationActionExecutor
    violation_recorder: ViolationRecorder
    violation_job_queue: ViolationJobQueue
    message_filter_service: MessageFilterService
    report_service: ViolationReportService
    file_probe_service: FileProbeService
    command_authorizer: CommandAuthorizer
    command_controller: CommandController
    platform_action_factory: PlatformActionFactory
    command_gateway: CommandGateway


def build_chat_filter_runtime(
    context: ChatFilterRuntimeContext,
    config: object | None,
    platform_actions: PlatformActions | None,
    logger: ChatFilterRuntimeLogger,
    *,
    platform_actions_provider: PlatformActionsProvider | None = None,
) -> ChatFilterRuntime:
    settings = ChatFilterSettings.from_config(config)
    data_root = default_data_root()
    repository = ChatFilterRepository(
        data_root,
        max_word_count=settings.max_word_count,
        max_word_length=settings.max_word_length,
    )
    rule_snapshot = RuleSnapshot.from_repository(
        repository,
        settings=settings,
    )
    state = load_runtime_state(repository, logger)
    metrics = ChatFilterMetrics()
    command_service = ChatFilterCommandService(
        repository,
        state,
        settings,
        rule_snapshot,
        logger,
    )
    matcher = ChatFilterMatcher()
    violation_action_executor = ViolationActionExecutor(
        repository,
        logger=logger,
        default_mute_duration_seconds=settings.mute_duration_seconds,
        default_mute_escalation_multiplier=settings.mute_escalation_multiplier,
        default_mute_escalation_reset_seconds=settings.mute_escalation_reset_seconds,
        metrics=metrics,
    )
    violation_recorder = ViolationRecorder(repository, logger, metrics)
    violation_job_queue = ViolationJobQueue(
        settings=settings,
        repository=repository,
        violation_recorder=violation_recorder,
        violation_action_executor=violation_action_executor,
        metrics=metrics,
        logger=logger,
    )
    message_filter_service = MessageFilterService(
        matcher=matcher,
        settings=settings,
        state=state,
        rule_snapshot=rule_snapshot,
        violation_job_queue=violation_job_queue,
        metrics=metrics,
        logger=logger,
    )
    report_service = ViolationReportService(
        repository,
        data_root=data_root,
        default_report_days=settings.default_report_days,
        logger=logger,
    )
    file_probe_service = FileProbeService(
        data_root=data_root,
        logger=logger,
    )
    command_authorizer = CommandAuthorizer(context.get_config)
    command_controller = CommandController(
        command_service,
        report_service,
        file_probe_service,
        command_authorizer,
        metrics,
    )
    platform_action_factory = PlatformActionFactory(
        platform_actions_provider or (lambda: platform_actions),
        logger=logger,
    )
    command_gateway = CommandGateway(
        command_controller,
        platform_action_factory,
    )
    return ChatFilterRuntime(
        settings=settings,
        data_root=data_root,
        repository=repository,
        rule_snapshot=rule_snapshot,
        state=state,
        command_service=command_service,
        matcher=matcher,
        metrics=metrics,
        platform_actions=platform_actions,
        violation_action_executor=violation_action_executor,
        violation_recorder=violation_recorder,
        violation_job_queue=violation_job_queue,
        message_filter_service=message_filter_service,
        report_service=report_service,
        file_probe_service=file_probe_service,
        command_authorizer=command_authorizer,
        command_controller=command_controller,
        platform_action_factory=platform_action_factory,
        command_gateway=command_gateway,
    )
