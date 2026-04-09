"""General vision agent exports.

This package is the preferred import path for the OpenAI-compatible
vision + function-calling agent implementation.
"""

from ..gemini import (
    AsyncGeneralVisionAgent,
    BENCHMARKS,
    INCOMPATIBLE_MODELS,
    RECOMMENDED_MODELS,
    get_compatible_benchmarks,
    get_fastest_models,
)

__all__ = [
    "AsyncGeneralVisionAgent",
    "BENCHMARKS",
    "INCOMPATIBLE_MODELS",
    "RECOMMENDED_MODELS",
    "get_compatible_benchmarks",
    "get_fastest_models",
]
