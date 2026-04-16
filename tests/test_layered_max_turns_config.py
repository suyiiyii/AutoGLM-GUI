import json

import pytest

from AutoGLM_GUI.config_manager import (
    LAYERED_MAX_TURNS_DEFAULT,
    ConfigModel,
)


def test_layered_max_turns_default() -> None:
    config = ConfigModel()
    assert config.layered_max_turns == LAYERED_MAX_TURNS_DEFAULT


def test_agent_type_default_is_glm_async() -> None:
    config = ConfigModel()
    assert config.agent_type == "glm-async"


def test_layered_max_turns_minimum_validation() -> None:
    with pytest.raises(ValueError, match="layered_max_turns must be >= 1"):
        ConfigModel(layered_max_turns=0)


def test_layered_max_turns_allows_positive_values() -> None:
    config = ConfigModel(layered_max_turns=1)
    assert config.layered_max_turns == 1


def test_layered_max_turns_env_var_parsing(monkeypatch) -> None:
    from AutoGLM_GUI.config_manager import UnifiedConfigManager

    manager = UnifiedConfigManager()
    monkeypatch.setenv("AUTOGLM_LAYERED_MAX_TURNS", "75")
    manager.load_env_config()
    config = manager.get_effective_config()
    assert config.layered_max_turns == 75


def test_layered_max_turns_env_var_invalid(monkeypatch) -> None:
    from AutoGLM_GUI.config_manager import UnifiedConfigManager

    manager = UnifiedConfigManager()
    monkeypatch.setenv("AUTOGLM_LAYERED_MAX_TURNS", "invalid")
    manager.load_env_config()
    config = manager.get_effective_config()
    assert config.layered_max_turns == 50


def test_load_file_config_migrates_legacy_glm_agent_type(tmp_path, monkeypatch):
    from AutoGLM_GUI.config_manager import UnifiedConfigManager

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "base_url": "https://example.com/v1",
                "model_name": "autoglm-phone-9b",
                "agent_type": "glm",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Use a fresh singleton so this test does not depend on global config state.
    monkeypatch.setattr(UnifiedConfigManager, "_instance", None)
    monkeypatch.setattr(UnifiedConfigManager, "_config_path", config_path)
    manager = UnifiedConfigManager()

    loaded = manager.load_file_config(force_reload=True)

    assert loaded is True
    assert manager.get_effective_config().agent_type == "glm-async"


def test_default_max_steps_allows_none() -> None:
    config = ConfigModel(default_max_steps=None)
    assert config.default_max_steps is None


def test_default_max_steps_env_var_parsing(monkeypatch) -> None:
    from AutoGLM_GUI.config_manager import UnifiedConfigManager

    manager = UnifiedConfigManager()
    monkeypatch.setenv("AUTOGLM_DEFAULT_MAX_STEPS", "10000")
    manager.load_env_config()
    config = manager.get_effective_config()
    assert config.default_max_steps == 10000


def test_save_file_config_persists_explicit_null_default_max_steps(
    tmp_path, monkeypatch
) -> None:
    from AutoGLM_GUI.config_manager import UnifiedConfigManager

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "base_url": "https://example.com/v1",
                "model_name": "autoglm-phone-9b",
                "default_max_steps": 100,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(UnifiedConfigManager, "_instance", None)
    monkeypatch.setattr(UnifiedConfigManager, "_config_path", config_path)
    manager = UnifiedConfigManager()

    saved = manager.save_file_config(
        base_url="https://example.com/v1",
        model_name="autoglm-phone-9b",
        default_max_steps=None,
        default_max_steps_set=True,
        merge_mode=True,
    )

    assert saved is True
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "default_max_steps" in persisted
    assert persisted["default_max_steps"] is None
