"""统一配置管理模块 - 四层优先级系统.

配置优先级：CLI 参数 > 环境变量 > 配置文件 > 默认值

Features:
- 类型安全的配置模型（Pydantic 验证）
- 多层配置系统，带源追踪
- 配置冲突检测和提示
- 配置文件热重载（基于 mtime 缓存）
- 原子文件写入
- 环境变量同步（支持 --reload 模式）
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

from AutoGLM_GUI.logger import logger


# ==================== 配置源枚举 ====================


class ConfigSource(str, Enum):
    """配置来源枚举（按优先级从高到低）."""

    CLI = "CLI arguments"
    ENV = "environment variables"
    FILE = "config file (~/.config/autoglm/config.json)"
    DEFAULT = "default"


# ==================== 类型安全配置模型 ====================


class ThinkingMode(str, Enum):
    """思考模式枚举."""

    FAST = "fast"  # 快速响应模式 - 减少思考时间
    DEEP = "deep"  # 深度思考模式 - 完整思考过程


class ConfigModel(BaseModel):
    """类型安全的配置模型，使用 Pydantic 进行验证."""

    base_url: str = ""
    model_name: str = "autoglm-phone-9b"
    api_key: str = "EMPTY"

    # Agent 类型配置
    agent_type: str = "glm"  # Agent type (e.g., "glm", "mai")
    agent_config_params: dict | None = None  # Agent-specific configuration

    # Agent 执行配置
    default_max_steps: int = 100  # 单次任务最大执行步数

    # 决策模型配置（用于分层代理）
    decision_base_url: str | None = None
    decision_model_name: str | None = None
    decision_api_key: str | None = None

    @field_validator("default_max_steps")
    @classmethod
    def validate_default_max_steps(cls, v: int) -> int:
        """验证 default_max_steps 范围."""
        if v <= 0:
            raise ValueError("default_max_steps must be positive")
        if v > 1000:
            raise ValueError("default_max_steps must be <= 1000")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """验证 base_url 格式."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")  # 去除尾部斜杠

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """验证 model_name 非空."""
        if not v or not v.strip():
            raise ValueError("model_name cannot be empty")
        return v.strip()

    @field_validator("decision_base_url")
    @classmethod
    def validate_decision_base_url(cls, v: str | None) -> str | None:
        """验证 decision_base_url 格式."""
        if v is not None:
            if not v.startswith(("http://", "https://")):
                raise ValueError(
                    "decision_base_url must start with http:// or https://"
                )
            return v.rstrip("/")
        return v

    @field_validator("decision_model_name")
    @classmethod
    def validate_decision_model_name(cls, v: str | None) -> str | None:
        """验证 decision_model_name 非空."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("decision_model_name cannot be empty string")
        return v.strip() if v else v


# ==================== 配置层数据类 ====================


@dataclass
class ConfigLayer:
    """单个配置层，带源追踪."""

    base_url: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    # Agent 类型配置
    agent_type: Optional[str] = None
    agent_config_params: Optional[dict] = None
    # Agent 执行配置
    default_max_steps: Optional[int] = None
    # 决策模型配置
    decision_base_url: Optional[str] = None
    decision_model_name: Optional[str] = None
    decision_api_key: Optional[str] = None

    source: ConfigSource = ConfigSource.DEFAULT

    def has_value(self, key: str) -> bool:
        """检查此层是否有非 None 的值.

        Args:
            key: 配置键名

        Returns:
            bool: 如果有值返回 True
        """
        value = getattr(self, key, None)
        return value is not None

    def to_dict(self) -> dict:
        """转换为字典，排除 None 值.

        Returns:
            dict: 配置字典
        """
        return {
            k: v
            for k, v in {
                "base_url": self.base_url,
                "model_name": self.model_name,
                "api_key": self.api_key,
                "agent_type": self.agent_type,
                "agent_config_params": self.agent_config_params,
                "default_max_steps": self.default_max_steps,
                "decision_base_url": self.decision_base_url,
                "decision_model_name": self.decision_model_name,
                "decision_api_key": self.decision_api_key,
            }.items()
            if v is not None
        }


# ==================== 配置冲突数据类 ====================


@dataclass
class ConfigConflict:
    """配置冲突信息."""

    field: str  # 冲突的字段名
    file_value: Optional[str]  # 配置文件中的值
    override_value: str  # 覆盖的值
    override_source: ConfigSource  # 覆盖来源（CLI 或 ENV）


# ==================== 统一配置管理器 ====================


class UnifiedConfigManager:
    """
    统一配置管理器（单例模式）.

    配置优先级：CLI 参数 > 环境变量 > 配置文件 > 默认值

    Features:
    - 类型安全配置（Pydantic 验证）
    - 多层优先级系统
    - 配置冲突检测
    - 文件热重载（基于 mtime 缓存）
    - 原子文件写入
    - 环境变量同步（reload 模式）
    """

    _instance: Optional["UnifiedConfigManager"] = None
    _config_path: Path = Path.home() / ".config" / "autoglm" / "config.json"

    def __new__(cls):
        """单例模式."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化配置管理器."""
        if hasattr(self, "_initialized") and self._initialized:
            return

        # 四层配置
        self._cli_layer = ConfigLayer(source=ConfigSource.CLI)
        self._env_layer = ConfigLayer(source=ConfigSource.ENV)
        self._file_layer = ConfigLayer(source=ConfigSource.FILE)
        self._default_layer = ConfigLayer(
            base_url="",
            model_name="autoglm-phone-9b",
            api_key="EMPTY",
            agent_type="glm",
            agent_config_params=None,
            default_max_steps=100,
            decision_base_url=None,
            decision_model_name=None,
            decision_api_key=None,
            source=ConfigSource.DEFAULT,
        )

        # 文件缓存（带修改时间戳）
        self._file_cache: Optional[dict] = None
        self._file_mtime: Optional[float] = None

        # 有效配置缓存
        self._effective_config: Optional[ConfigModel] = None

        self._initialized = True
        logger.debug("UnifiedConfigManager initialized")

    # ==================== 配置加载 ====================

    def set_cli_config(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        设置 CLI 参数配置（最高优先级）.

        Args:
            base_url: 从 --base-url 获取的值
            model_name: 从 --model 获取的值
            api_key: 从 --apikey 获取的值
        """
        self._cli_layer = ConfigLayer(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            source=ConfigSource.CLI,
        )
        self._effective_config = None  # 清除缓存
        logger.debug(f"CLI config set: {self._cli_layer.to_dict()}")

    def load_env_config(self) -> None:
        """
        从环境变量加载配置.

        读取环境变量：
        - AUTOGLM_BASE_URL
        - AUTOGLM_MODEL_NAME
        - AUTOGLM_API_KEY
        - AUTOGLM_DECISION_BASE_URL
        - AUTOGLM_DECISION_MODEL_NAME
        - AUTOGLM_DECISION_API_KEY
        """
        base_url = os.getenv("AUTOGLM_BASE_URL")
        model_name = os.getenv("AUTOGLM_MODEL_NAME")
        api_key = os.getenv("AUTOGLM_API_KEY")

        # 决策模型环境变量
        decision_base_url = os.getenv("AUTOGLM_DECISION_BASE_URL")
        decision_model_name = os.getenv("AUTOGLM_DECISION_MODEL_NAME")
        decision_api_key = os.getenv("AUTOGLM_DECISION_API_KEY")

        self._env_layer = ConfigLayer(
            base_url=base_url if base_url else None,
            model_name=model_name if model_name else None,
            api_key=api_key if api_key else None,
            decision_base_url=decision_base_url if decision_base_url else None,
            decision_model_name=decision_model_name if decision_model_name else None,
            decision_api_key=decision_api_key if decision_api_key else None,
            source=ConfigSource.ENV,
        )
        self._effective_config = None  # 清除缓存
        logger.debug(f"Environment config loaded: {self._env_layer.to_dict()}")

    def load_file_config(self, force_reload: bool = False) -> bool:
        """
        从文件加载配置，支持热重载.

        基于文件修改时间（mtime）的缓存机制：
        - 如果文件未变化且有缓存，直接使用缓存
        - 否则重新读取文件

        Args:
            force_reload: 强制重新加载，即使文件未变化

        Returns:
            bool: 如果配置被加载/重载返回 True，否则返回 False
        """
        if not self._config_path.exists():
            logger.debug(f"Config file not found: {self._config_path}")
            self._file_layer = ConfigLayer(source=ConfigSource.FILE)
            self._file_cache = None
            self._file_mtime = None
            self._effective_config = None
            return False

        try:
            # 获取文件修改时间
            current_mtime = self._config_path.stat().st_mtime

            # 使用缓存（如果文件未变化）
            if (
                not force_reload
                and self._file_mtime == current_mtime
                and self._file_cache
            ):
                logger.debug("Using cached config file (file unchanged)")
                return False

            # 读取并解析文件
            with open(self._config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            # 更新缓存
            self._file_cache = config_data
            self._file_mtime = current_mtime

            # 更新文件层
            self._file_layer = ConfigLayer(
                base_url=config_data.get("base_url"),
                model_name=config_data.get("model_name"),
                api_key=config_data.get("api_key"),
                agent_type=config_data.get(
                    "agent_type", "glm"
                ),  # 默认 'glm'，兼容旧配置
                agent_config_params=config_data.get("agent_config_params"),
                default_max_steps=config_data.get("default_max_steps"),
                decision_base_url=config_data.get("decision_base_url"),
                decision_model_name=config_data.get("decision_model_name"),
                decision_api_key=config_data.get("decision_api_key"),
                source=ConfigSource.FILE,
            )
            self._effective_config = None  # 清除缓存

            logger.info(f"Config file loaded from {self._config_path}")
            return True

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse config file: {e}")
            self._file_layer = ConfigLayer(source=ConfigSource.FILE)
            self._file_cache = None
            self._file_mtime = None
            self._effective_config = None
            return False
        except Exception as e:
            logger.error(f"Failed to read config file: {e}")
            self._file_layer = ConfigLayer(source=ConfigSource.FILE)
            self._file_cache = None
            self._file_mtime = None
            self._effective_config = None
            return False

    def save_file_config(
        self,
        base_url: str,
        model_name: str,
        api_key: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_config_params: Optional[dict] = None,
        default_max_steps: Optional[int] = None,
        decision_base_url: Optional[str] = None,
        decision_model_name: Optional[str] = None,
        decision_api_key: Optional[str] = None,
        merge_mode: bool = True,
    ) -> bool:
        """
        保存配置到文件，支持合并模式.

        Args:
            base_url: Base URL
            model_name: 模型名称
            api_key: API key（可选）
            agent_type: Agent 类型（可选，如 "glm", "mai"）
            agent_config_params: Agent 特定配置参数（可选）
            default_max_steps: 默认最大执行步数（可选）
            decision_base_url: 决策模型 Base URL（可选）
            decision_model_name: 决策模型名称（可选）
            decision_api_key: 决策模型 API Key（可选）
            merge_mode: 是否合并现有配置（True: 保留未提供的字段）

        Returns:
            bool: 成功返回 True，失败返回 False
        """
        try:
            # 确保目录存在
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            # 准备新配置
            new_config: dict[str, str | bool | int | dict | None] = {
                "base_url": base_url,
                "model_name": model_name,
            }

            if api_key:
                new_config["api_key"] = api_key
            if agent_type is not None:
                new_config["agent_type"] = agent_type
            if agent_config_params is not None:
                new_config["agent_config_params"] = agent_config_params
            if default_max_steps is not None:
                new_config["default_max_steps"] = default_max_steps

            # 决策模型配置
            if decision_base_url is not None:
                new_config["decision_base_url"] = decision_base_url
            if decision_model_name is not None:
                new_config["decision_model_name"] = decision_model_name
            if decision_api_key is not None:
                new_config["decision_api_key"] = decision_api_key

            # 合并模式：保留现有文件中未提供的字段
            if merge_mode and self._config_path.exists():
                try:
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)

                    # 保留未提供的字段
                    preserve_keys = [
                        "api_key",
                        "agent_type",
                        "agent_config_params",
                        "default_max_steps",
                        "decision_base_url",
                        "decision_model_name",
                        "decision_api_key",
                    ]
                    for key in preserve_keys:
                        if key not in new_config and key in existing:
                            new_config[key] = existing[key]

                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Could not merge with existing config: {e}")

            # 原子写入：临时文件 + 重命名
            temp_path = self._config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)

            temp_path.replace(self._config_path)

            logger.info(f"Configuration saved to {self._config_path}")

            # 重新加载文件配置以更新缓存
            self.load_file_config(force_reload=True)

            return True

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def delete_file_config(self) -> bool:
        """
        删除配置文件.

        Returns:
            bool: 成功或文件不存在返回 True，失败返回 False
        """
        if not self._config_path.exists():
            logger.debug("Config file doesn't exist, nothing to delete")
            return True

        try:
            self._config_path.unlink()
            self._file_cache = None
            self._file_mtime = None
            self._file_layer = ConfigLayer(source=ConfigSource.FILE)
            self._effective_config = None
            logger.info(f"Configuration deleted: {self._config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete config file: {e}")
            return False

    # ==================== 配置合并 ====================

    def get_effective_config(self, reload_file: bool = False) -> ConfigModel:
        """
        获取合并后的有效配置.

        配置优先级：CLI > ENV > FILE > DEFAULT

        Args:
            reload_file: 是否强制重新加载配置文件

        Returns:
            ConfigModel: 验证后的配置对象
        """
        # 首次加载：如果文件层为空且配置文件存在，自动加载
        if not self._file_layer.to_dict() and self._config_path.exists():
            logger.debug("Auto-loading config file on first access")
            self.load_file_config()

        # 重新加载文件（热重载支持）
        if reload_file:
            self.load_file_config(force_reload=True)

        # 返回缓存（如果可用）
        if self._effective_config is not None:
            return self._effective_config

        # 按优先级合并配置
        merged = {}

        # 所有配置字段
        config_keys = [
            "base_url",
            "model_name",
            "api_key",
            "agent_type",
            "agent_config_params",
            "default_max_steps",
            "decision_base_url",
            "decision_model_name",
            "decision_api_key",
        ]

        for key in config_keys:
            # 1. CLI 优先
            if self._cli_layer.has_value(key):
                merged[key] = getattr(self._cli_layer, key)
            # 2. 环境变量
            elif self._env_layer.has_value(key):
                merged[key] = getattr(self._env_layer, key)
            # 3. 配置文件
            elif self._file_layer.has_value(key):
                merged[key] = getattr(self._file_layer, key)
            # 4. 默认值（只对 base_url, model_name, api_key 有效）
            elif (
                hasattr(self._default_layer, key)
                and getattr(self._default_layer, key, None) is not None
            ):
                merged[key] = getattr(self._default_layer, key)

        # 验证并缓存
        try:
            self._effective_config = ConfigModel(**merged)
            logger.debug(f"Effective config computed: {merged}")
            return self._effective_config
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            # 降级到默认值
            self._effective_config = ConfigModel()
            return self._effective_config

    def get_config_source(self) -> ConfigSource:
        """
        获取主要配置来源.

        Returns:
            ConfigSource: 最高优先级的非空配置源
        """
        # 检查 CLI 是否有值
        if self._cli_layer.to_dict():
            return ConfigSource.CLI

        # 检查 ENV 是否有值
        if self._env_layer.to_dict():
            return ConfigSource.ENV

        # 检查 FILE 是否有值
        if self._file_layer.to_dict():
            return ConfigSource.FILE

        return ConfigSource.DEFAULT

    def get_field_source(self, field: str) -> ConfigSource:
        """
        获取特定字段的配置来源.

        Args:
            field: 字段名（'base_url', 'model_name', 'api_key'）

        Returns:
            ConfigSource: 该字段的配置来源
        """
        if self._cli_layer.has_value(field):
            return ConfigSource.CLI
        elif self._env_layer.has_value(field):
            return ConfigSource.ENV
        elif self._file_layer.has_value(field):
            return ConfigSource.FILE
        else:
            return ConfigSource.DEFAULT

    # ==================== 配置冲突检测 ====================

    def detect_conflicts(self) -> list[ConfigConflict]:
        """
        检测配置冲突.

        冲突定义：
        1. 配置文件中有某个字段的值
        2. CLI 或 ENV 有该字段的不同值（覆盖）

        Returns:
            list[ConfigConflict]: 冲突列表
        """
        conflicts = []

        if not self._file_layer.to_dict():
            return conflicts  # 无文件配置，无冲突

        for key in ["base_url", "model_name", "api_key"]:
            file_value = getattr(self._file_layer, key, None)

            if file_value is None:
                continue  # 文件中没有此字段

            # 检查 CLI 覆盖
            cli_value = getattr(self._cli_layer, key, None)
            if cli_value is not None and cli_value != file_value:
                conflicts.append(
                    ConfigConflict(
                        field=key,
                        file_value=file_value,
                        override_value=cli_value,
                        override_source=ConfigSource.CLI,
                    )
                )
                continue

            # 检查 ENV 覆盖
            env_value = getattr(self._env_layer, key, None)
            if env_value is not None and env_value != file_value:
                conflicts.append(
                    ConfigConflict(
                        field=key,
                        file_value=file_value,
                        override_value=env_value,
                        override_source=ConfigSource.ENV,
                    )
                )

        return conflicts

    # ==================== 环境变量同步 ====================

    def sync_to_env(self) -> None:
        """
        将有效配置同步到环境变量.

        这是 --reload 模式必需的：
        - uvicorn reload 会启动新进程
        - 新进程继承父进程的环境变量
        - 通过环境变量恢复配置
        """
        config = self.get_effective_config()

        os.environ["AUTOGLM_BASE_URL"] = config.base_url
        os.environ["AUTOGLM_MODEL_NAME"] = config.model_name
        os.environ["AUTOGLM_API_KEY"] = config.api_key

        logger.debug("Configuration synced to environment variables")

    # ==================== 工具方法 ====================

    def get_config_path(self) -> Path:
        """获取配置文件路径.

        Returns:
            Path: 配置文件路径
        """
        return self._config_path

    def to_dict(self) -> dict:
        """
        将有效配置转换为字典.

        Returns:
            dict: 配置字典
        """
        config = self.get_effective_config()
        return {
            "base_url": config.base_url,
            "model_name": config.model_name,
            "api_key": config.api_key,
            "agent_type": config.agent_type,
            "agent_config_params": config.agent_config_params,
            "default_max_steps": config.default_max_steps,
            "decision_base_url": config.decision_base_url,
            "decision_model_name": config.decision_model_name,
            "decision_api_key": config.decision_api_key,
        }


# ==================== 全局单例 ====================


# 全局配置管理器单例
config_manager = UnifiedConfigManager()
