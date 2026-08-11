"""Public Engine Plugin v2/v3 contracts; independent of engine-heart."""

from . import models as _models
from .conformance import check_plugin
from .manifest import (
    compare_manifests,
    load_static_manifest,
    locate_distribution_manifest,
    validate_manifest,
)
from .models import *  # noqa: F403 - the SDK intentionally re-exports contract types
from .protocols import (
    AutonomyStrategy,
    DomainController,
    EffectOracle,
    ExecutiveBrainV2,
    Executor,
    ExperienceProvider,
    GoalTemplateCompiler,
    LifecycleObserver,
    RoutineCompiler,
    SpecialistBrainV2,
    WorldPluginV2,
    WorldPluginV3,
    WorldProvider,
)

__all__ = [
    "AutonomyStrategy",
    "DomainController",
    "EffectOracle",
    "ExecutiveBrainV2",
    "ExperienceProvider",
    "Executor",
    "GoalTemplateCompiler",
    "RoutineCompiler",
    "LifecycleObserver",
    "SpecialistBrainV2",
    "WorldPluginV2",
    "WorldPluginV3",
    "WorldProvider",
    "check_plugin",
    "compare_manifests",
    "load_static_manifest",
    "locate_distribution_manifest",
    "validate_manifest",
] + [
    name for name in vars(_models)
    if not name.startswith("_") and getattr(vars(_models)[name], "__module__", None) == _models.__name__
]
