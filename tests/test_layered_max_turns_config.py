import pytest

from AutoGLM_GUI.config_manager import (
    LAYERED_MAX_TURNS_DEFAULT,
    ConfigModel,
)


def test_layered_max_turns_default() -> None:
    config = ConfigModel()
    assert config.layered_max_turns == LAYERED_MAX_TURNS_DEFAULT


def test_layered_max_turns_minimum_validation() -> None:
    with pytest.raises(ValueError, match="layered_max_turns must be > 1"):
        ConfigModel(layered_max_turns=0)


def test_layered_max_turns_allows_positive_values() -> None:
    config = ConfigModel(layered_max_turns=1)
    assert config.layered_max_turns == 1
