"""Pytest fixtures for integration tests."""

import pytest
from pathlib import Path


@pytest.fixture
def scenarios_dir() -> Path:
    """Get the test scenarios directory."""
    return Path(__file__).parent / "fixtures" / "scenarios"


@pytest.fixture
def sample_test_case(scenarios_dir: Path) -> Path:
    """Get the sample test case path (美团外卖测试)."""
    return scenarios_dir / "meituan_message" / "scenario.yaml"
