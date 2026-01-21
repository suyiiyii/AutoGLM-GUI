"""轨迹记忆数据结构 - MAI Agent 内部实现

本模块定义了 MAI Agent 的轨迹记忆系统，用于存储和管理 Agent 执行过程中的历史信息。

设计说明：
- 从 mai_agent/unified_memory.py 迁移而来
- 适配 Python 3.10+ 类型注解
- 与 AutoGLM_GUI 架构集成
"""

from dataclasses import dataclass, field
from typing import Any

from PIL import Image


@dataclass
class TrajStep:
    """轨迹中的单个步骤

    记录 Agent 在某一步的完整状态，包括观察、思考、动作和结果。

    Attributes:
        screenshot: 当前步骤的截图 (PIL Image 格式)
        accessibility_tree: 可访问性树数据（可选，用于辅助 UI 理解）
        prediction: 模型的原始响应文本（包含 <thinking> 和 <tool_call>）
        action: 解析后的动作字典（如 {"action": "click", "coordinate": [0.5, 0.8]}）
        conclusion: 本步骤的结论或总结
        thought: 模型的思考过程（从 <thinking> 标签中提取）
        step_index: 步骤索引（从 0 开始）
        agent_type: 生成此步骤的 Agent 类型（如 "InternalMAIAgent"）
        model_name: 使用的模型名称（如 "qwen2-vl-7b"）
        screenshot_bytes: 截图的字节数据（可选，用于序列化）
        structured_action: 结构化的动作数据（可选，包含额外元数据）
    """

    screenshot: Image.Image
    accessibility_tree: dict[str, Any] | None
    prediction: str
    action: dict[str, Any]
    conclusion: str
    thought: str
    step_index: int
    agent_type: str
    model_name: str
    screenshot_bytes: bytes | None = None
    structured_action: dict[str, Any] | None = None


@dataclass
class TrajMemory:
    """完整任务的轨迹记忆容器

    存储一个完整任务的所有步骤，提供历史查询和状态管理功能。

    Attributes:
        task_goal: 任务目标描述（用户的原始指令）
        task_id: 任务唯一标识符
        steps: 步骤列表（按执行顺序）
    """

    task_goal: str
    task_id: str
    steps: list[TrajStep] = field(default_factory=list)

    def add_step(self, step: TrajStep) -> None:
        self.steps.append(step)

    def get_history_images(self, n: int = -1) -> list[bytes]:
        images = [step.screenshot_bytes for step in self.steps if step.screenshot_bytes]
        if n > 0:
            return images[-n:]
        return images

    def get_history_thoughts(self, n: int = -1) -> list[str]:
        thoughts = [step.thought for step in self.steps if step.thought]
        if n > 0:
            return thoughts[-n:]
        return thoughts

    def get_history_actions(self, n: int = -1) -> list[dict[str, Any]]:
        actions = [step.action for step in self.steps]
        if n > 0:
            return actions[-n:]
        return actions

    def clear(self) -> None:
        self.steps.clear()

    def __len__(self) -> int:
        return len(self.steps)
