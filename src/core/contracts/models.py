"""Compatibility facade for shared runtime dataclasses.

Model families live in focused modules, but existing imports from
`core.contracts.models` remain stable.
"""

from core.contracts.basic_models import ActionStep, ApiCall, TimingSample
from core.contracts.deps import Deps
from core.contracts.evaluation_models import (
    EvaluationContext,
    FailureDiagnosis,
    Phase1Metrics,
)
from core.contracts.execution_models import (
    ExecutionArtifact,
    ExecutionResult,
    GeneratedTest,
)
from core.contracts.interaction_models import (
    InteractionActionContract,
    InteractionContainerContract,
    InteractionContract,
    InteractionFieldContract,
    InteractionServiceEffect,
)
from core.contracts.journey_models import (
    JourneyActionContract,
    JourneyCapture,
    JourneyContract,
    ServiceCallRequirement,
    SuccessAssertion,
    SuccessObservation,
)
from core.contracts.locator_models import (
    SNAPSHOT_SELECTOR_PREFIXES,
    LocatorCandidate,
    _is_snapshot_selector,
    _locator_candidates_from_legacy_selector,
    _locator_candidates_from_observation_locator,
    _sanitize_executable_selector,
    is_snapshot_selector,
    locator_candidates_from_legacy_selector,
    locator_candidates_from_observation_locator,
    sanitize_executable_selector,
)
from core.contracts.report_models import (
    CoverageSnapshot,
    ExecutionReport,
    JourneyGuide,
    UseCaseMetadata,
)

__all__ = [
    "ActionStep",
    "ApiCall",
    "CoverageSnapshot",
    "Deps",
    "EvaluationContext",
    "ExecutionArtifact",
    "ExecutionReport",
    "ExecutionResult",
    "FailureDiagnosis",
    "GeneratedTest",
    "InteractionActionContract",
    "InteractionContainerContract",
    "InteractionContract",
    "InteractionFieldContract",
    "InteractionServiceEffect",
    "JourneyActionContract",
    "JourneyCapture",
    "JourneyContract",
    "JourneyGuide",
    "LocatorCandidate",
    "Phase1Metrics",
    "SNAPSHOT_SELECTOR_PREFIXES",
    "ServiceCallRequirement",
    "SuccessAssertion",
    "SuccessObservation",
    "TimingSample",
    "UseCaseMetadata",
    "_is_snapshot_selector",
    "_locator_candidates_from_legacy_selector",
    "_locator_candidates_from_observation_locator",
    "_sanitize_executable_selector",
    "is_snapshot_selector",
    "locator_candidates_from_legacy_selector",
    "locator_candidates_from_observation_locator",
    "sanitize_executable_selector",
]
