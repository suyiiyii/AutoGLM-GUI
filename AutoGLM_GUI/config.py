"""AutoGLM-GUI 核心配置定义

这个模块定义了项目自己的配置类，替代 phone_agent 的配置，
实现配置层的解耦和扩展性。

设计原则:
- 配置类提供 AutoGLM-GUI 核心业务逻辑所需的参数
- 避免在 API 层和业务层直接使用外部库的类型
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """模型配置

    OpenAI 兼容 API 的配置参数。

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


@dataclass
class AgentConfig:
    """Agent 配置

    控制 Agent 的行为参数。

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


@dataclass
class StepResult:
    """Agent 单步执行结果

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
