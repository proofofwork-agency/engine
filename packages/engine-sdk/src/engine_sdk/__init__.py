"""Public Engine Plugin v2 contracts; intentionally independent of engine-heart."""

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
    DomainController,
    EffectOracle,
    ExecutiveBrainV2,
    ExperienceProvider,
    Executor,
    RoutineCompiler,
    SpecialistBrainV2,
    WorldPluginV2,
    WorldProvider,
)

__all__ = [
    "DomainController",
    "EffectOracle",
    "ExecutiveBrainV2",
    "ExperienceProvider",
    "Executor",
    "RoutineCompiler",
    "SpecialistBrainV2",
    "WorldPluginV2",
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
