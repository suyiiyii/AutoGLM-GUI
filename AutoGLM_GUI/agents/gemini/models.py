"""Supported models and benchmark results for Gemini Agent.

All models tested via OpenAI-compatible API.
Task: "打开微信" with mock Android home screen screenshot.
Date: 2026-02-22
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelBenchmark:
    """Single model benchmark result."""

    model_id: str
    provider: str
    latency_ms: int
    tool_call: str  # e.g. "launch_app" or "tap" or "NO_TOOL"
    compatible: bool  # supports vision + function calling
    note: str = ""


# Benchmark results (2026-02-22, single-step, vision + function calling)
BENCHMARKS: list[ModelBenchmark] = [
    # --- OpenAI ---
    ModelBenchmark("gpt-4.1", "openai", 2510, "tap", True, "稳定快速"),
    ModelBenchmark("gpt-4.1-mini", "openai", 2521, "tap", True, "性价比高"),
    ModelBenchmark("gpt-4.1-nano", "openai", 2867, "launch_app", True, "最便宜 OpenAI"),
    ModelBenchmark("gpt-4o", "openai", 3055, "tap", True, "经典稳定"),
    ModelBenchmark("gpt-4o-mini", "openai", 2303, "launch_app", True, "便宜快速"),
    ModelBenchmark("gpt-5.2", "openai", 7980, "tap", True, "最新，较慢"),
    ModelBenchmark("gpt-5.2-pro", "openai", 24444, "tap", True, "太慢"),
    ModelBenchmark("gpt-5-mini", "openai", 6969, "tap", True, "比 4.1 慢"),
    ModelBenchmark("gpt-5", "openai", 36153, "NO_TOOL", False, "不支持 tool_choice"),
    ModelBenchmark(
        "gpt-5-nano", "openai", 7443, "NO_TOOL", False, "不支持 tool_choice"
    ),
    # --- 智谱 GLM ---
    ModelBenchmark("glm-4.7", "zhipu", 1488, "launch_app", True, "最快，推荐"),
    ModelBenchmark("glm-5", "zhipu", 3419, "launch_app", True, "最新一代"),
    ModelBenchmark("GLM-4.6V", "zhipu", 9780, "launch_app", True, "视觉专用，较慢"),
    ModelBenchmark(
        "glm-4v-plus", "zhipu", 2303, "NO_TOOL", False, "不支持 function calling"
    ),
    ModelBenchmark(
        "GLM-4.1V-Thinking-Flash",
        "zhipu",
        4105,
        "NO_TOOL",
        False,
        "不支持 function calling",
    ),
    # --- Google Gemini ---
    ModelBenchmark("gemini-3.1-pro-preview", "google", 6288, "tap", True, "坐标精准"),
    ModelBenchmark("gemini-2.5-flash", "google", 4988, "tap", True, "性价比"),
    ModelBenchmark(
        "gemini-3-flash-preview",
        "google",
        47907,
        "launch_app",
        True,
        "异常慢(代理问题)",
    ),
    # --- Anthropic ---
    ModelBenchmark(
        "claude-sonnet-4-20250514",
        "anthropic",
        109272,
        "launch_app",
        True,
        "代理转发极慢",
    ),
]


# Recommended models (compatible + fast + good decisions)
RECOMMENDED_MODELS = [
    "glm-4.7",  # 1.5s, 智谱, launch_app 决策
    "gpt-4o-mini",  # 2.3s, OpenAI, 便宜
    "gpt-4.1",  # 2.5s, OpenAI, 稳定
    "gpt-4.1-mini",  # 2.5s, OpenAI, 性价比
    "gpt-4.1-nano",  # 2.9s, OpenAI, 最便宜
    "glm-5",  # 3.4s, 智谱, 最新
    "gpt-4o",  # 3.1s, OpenAI, 经典
    "gemini-2.5-flash",  # 5.0s, Google
    "gemini-3.1-pro-preview",  # 6.3s, Google, 坐标最准
]

# Models that do NOT work with function calling
INCOMPATIBLE_MODELS = [
    "gpt-5",
    "gpt-5-nano",
    "glm-4v-plus",
    "GLM-4.1V-Thinking-Flash",
]


def get_compatible_benchmarks() -> list[ModelBenchmark]:
    """Return only models that support vision + function calling."""
    return [b for b in BENCHMARKS if b.compatible]


def get_benchmarks_by_provider(provider: str) -> list[ModelBenchmark]:
    """Return benchmarks filtered by provider."""
    return [b for b in BENCHMARKS if b.provider == provider]


def get_fastest_models(top_n: int = 5) -> list[ModelBenchmark]:
    """Return top N fastest compatible models."""
    compatible = get_compatible_benchmarks()
    return sorted(compatible, key=lambda b: b.latency_ms)[:top_n]
