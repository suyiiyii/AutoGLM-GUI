"""Preferred model catalog entry point for the general vision agent."""

from ..gemini.models import (
    BENCHMARKS,
    INCOMPATIBLE_MODELS,
    RECOMMENDED_MODELS,
    ModelBenchmark,
    get_compatible_benchmarks,
    get_fastest_models,
)

__all__ = [
    "ModelBenchmark",
    "BENCHMARKS",
    "INCOMPATIBLE_MODELS",
    "RECOMMENDED_MODELS",
    "get_compatible_benchmarks",
    "get_fastest_models",
]
