"""AutoGLM-GUI 核心配置定义

这个模块定义了项目自己的配置类，替代 phone_agent 的配置，
实现配置层的解耦和扩展性。

设计原则:
- 配置类与 phone_agent 的配置类字段完全兼容
- 提供 to_phone_agent_config() 适配器方法用于转换
- 避免在 API 层和业务层直接使用 phone_agent 的类型
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """模型配置

    OpenAI 兼容 API 的配置参数。
    这个类替代 phone_agent.model.ModelConfig，提供相同的功能。

    Attributes:
        base_url: API 端点 URL (例如: "http://localhost:8000/v1")
        api_key: API 认证密钥 (本地部署可选)
        model_name: 模型标识符 (例如: "autoglm-phone-9b")
        max_tokens: 响应最大 token 数 (默认: 3000)
        temperature: 采样温度 0-1 (默认: 0.0)
        top_p: Nucleus 采样阈值 (默认: 0.85)
        frequency_penalty: 频率惩罚 -2 到 2 (默认: 0.2)
        extra_body: 特定后端的额外参数
        lang: UI 消息语言: 'cn' 或 'en'
    """

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "autoglm-phone-9b"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)
    lang: str = "cn"

    def to_phone_agent_config(self):
        """转换为 phone_agent.model.ModelConfig

        这个方法用于在需要与 phone_agent 交互时（如创建 PhoneAgent 实例）
        将配置转换为 phone_agent 期望的类型。

        Returns:
            phone_agent.model.ModelConfig 实例
        """
        from phone_agent.model import ModelConfig as PhoneModelConfig

        return PhoneModelConfig(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            extra_body=self.extra_body,
            lang=self.lang,
        )


@dataclass
class AgentConfig:
    """Agent 配置

    控制 Agent 的行为参数。
    这个类替代 phone_agent.agent.AgentConfig，提供相同的功能。

    Attributes:
        max_steps: 单次任务最大执行步数 (默认: 100)
        device_id: 设备标识符 (USB serial 或 IP:port)
        lang: 语言设置 'cn' 或 'en'
        system_prompt: 自定义系统提示词 (None 则使用默认)
        verbose: 是否输出详细日志
    """

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True

    def __post_init__(self):
        if self.system_prompt is None:
            from phone_agent.config import get_system_prompt

            self.system_prompt = get_system_prompt(self.lang)

    def to_phone_agent_config(self):
        """转换为 phone_agent.agent.AgentConfig

        这个方法用于在需要与 phone_agent 交互时（如创建 PhoneAgent 实例）
        将配置转换为 phone_agent 期望的类型。

        Returns:
            phone_agent.agent.AgentConfig 实例
        """
        from phone_agent.agent import AgentConfig as PhoneAgentConfig

        return PhoneAgentConfig(
            max_steps=self.max_steps,
            device_id=self.device_id,
            lang=self.lang,
            system_prompt=self.system_prompt,
            verbose=self.verbose,
        )


@dataclass
class StepResult:
    """Agent 单步执行结果

    这个类从 phone_agent.agent.StepResult 复制而来，避免类型泄露到业务层。

    Attributes:
        success: 本步骤是否执行成功
        finished: 整个任务是否已完成
        action: 执行的动作字典 (包含 action type 和参数)
        thinking: Agent 的思考过程
        message: 结果消息 (可选)
    """

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None

    @classmethod
    def from_phone_agent_result(cls, result) -> "StepResult":
        """从 phone_agent.agent.StepResult 转换

        Args:
            result: phone_agent.agent.StepResult 实例

        Returns:
            AutoGLM_GUI.config.StepResult 实例
        """
        return cls(
            success=result.success,
            finished=result.finished,
            action=result.action,
            thinking=result.thinking,
            message=result.message,
        )

    def to_phone_agent_result(self):
        """转换为 phone_agent.agent.StepResult

        用于需要传递给 phone_agent 相关代码的场景。

        Returns:
            phone_agent.agent.StepResult 实例
        """
        from phone_agent.agent import StepResult as PhoneStepResult

        return PhoneStepResult(
            success=self.success,
            finished=self.finished,
            action=self.action,
            thinking=self.thinking,
            message=self.message,
        )
