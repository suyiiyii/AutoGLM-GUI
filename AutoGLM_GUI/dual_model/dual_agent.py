"""
双模型协调器

协调大模型(决策)和小模型(执行)的协作
"""

import hashlib
import time
import threading
from dataclasses import dataclass
from typing import Callable, Optional
from queue import Queue

from AutoGLM_GUI.config import ModelConfig
from AutoGLM_GUI.logger import logger
from .decision_model import (
    DecisionModel,
    Decision,
    TaskPlan,
    ActionSequence,
    ActionStep,
)
from .vision_model import VisionModel, ScreenDescription, ExecutionResult
from .protocols import (
    DecisionModelConfig,
    DualModelState,
    DualModelEvent,
    DualModelEventType,
    ModelRole,
    ModelStage,
    ThinkingMode,
    DECISION_ERROR_CONTEXT_TEMPLATE,
)


@dataclass
class DualModelCallbacks:
    """双模型回调接口"""

    # 大模型回调
    on_decision_start: Optional[Callable[[], None]] = None
    on_decision_thinking: Optional[Callable[[str], None]] = None
    on_decision_result: Optional[Callable[[Decision], None]] = None
    on_task_plan: Optional[Callable[[TaskPlan], None]] = None
    on_content_generation: Optional[Callable[[str, str], None]] = (
        None  # (content, purpose)
    )

    # 小模型回调
    on_vision_start: Optional[Callable[[], None]] = None
    on_vision_recognition: Optional[Callable[[ScreenDescription], None]] = None
    on_action_start: Optional[Callable[[dict], None]] = None
    on_action_result: Optional[Callable[[ExecutionResult], None]] = None

    # 整体回调
    on_step_complete: Optional[Callable[[int, bool], None]] = None  # (step, success)
    on_task_complete: Optional[Callable[[bool, str], None]] = None  # (success, message)
    on_error: Optional[Callable[[str], None]] = None


@dataclass
class StepResult:
    """单步执行结果"""

    step: int
    success: bool
    finished: bool
    decision: Optional[Decision] = None
    screen_desc: Optional[ScreenDescription] = None
    execution: Optional[ExecutionResult] = None
    error: Optional[str] = None


@dataclass
class AnomalyState:
    """异常状态追踪"""

    consecutive_failures: int = 0
    consecutive_same_screen: int = 0
    last_screenshot_hash: str = ""
    last_action: str = ""
    repeated_actions: int = 0
    max_same_screen: int = 3
    max_failures: int = 5
    max_repeated_actions: int = 3

    def reset(self):
        """重置异常状态"""
        self.consecutive_failures = 0
        self.consecutive_same_screen = 0
        self.last_screenshot_hash = ""
        self.last_action = ""
        self.repeated_actions = 0

    def check_screenshot(self, screenshot_base64: str) -> bool:
        """检查截图是否重复，返回 True 表示重复"""
        current_hash = hashlib.md5(screenshot_base64.encode()[:10000]).hexdigest()
        is_same = current_hash == self.last_screenshot_hash
        if is_same:
            self.consecutive_same_screen += 1
        else:
            self.consecutive_same_screen = 0
        self.last_screenshot_hash = current_hash
        return is_same and self.consecutive_same_screen >= 2

    def check_action(self, action: str, target: str) -> bool:
        """检查动作是否重复，返回 True 表示重复"""
        action_key = f"{action}:{target}"
        if action_key == self.last_action:
            self.repeated_actions += 1
        else:
            self.repeated_actions = 0
        self.last_action = action_key
        return self.repeated_actions >= self.max_repeated_actions

    def record_failure(self):
        """记录失败"""
        self.consecutive_failures += 1

    def record_success(self):
        """记录成功"""
        self.consecutive_failures = 0

    def has_anomaly(self) -> bool:
        """是否存在异常"""
        return (
            self.consecutive_failures >= self.max_failures
            or self.consecutive_same_screen >= self.max_same_screen
            or self.repeated_actions >= self.max_repeated_actions
        )

    def get_error_context(self) -> str:
        """生成异常上下文描述"""
        contexts = []
        if self.consecutive_same_screen >= 2:
            contexts.append(
                f"⚠️ 屏幕连续 {self.consecutive_same_screen} 次无变化，可能原因：网络延迟、点击未生效、页面加载中"
            )
        if self.consecutive_failures >= 2:
            contexts.append(f"⚠️ 连续 {self.consecutive_failures} 次操作失败")
        if self.repeated_actions >= 2:
            contexts.append(f"⚠️ 相同操作已重复 {self.repeated_actions} 次无效果")
        return "\n".join(contexts) if contexts else ""


class DualModelAgent:
    """
    双模型协调器

    协调大模型(GLM-4.7)和小模型(autoglm-phone)的协作：
    1. 大模型分析任务，制定计划
    2. 小模型识别屏幕，描述内容
    3. 大模型根据屏幕描述做决策
    4. 小模型执行决策
    5. 循环直到任务完成

    Usage:
        agent = DualModelAgent(decision_config, vision_config, device_id)
        result = await agent.run("打开微信发送消息")
    """

    def __init__(
        self,
        decision_config: DecisionModelConfig,
        vision_config: ModelConfig,
        device_id: str,
        max_steps: int = 50,
        callbacks: Optional[DualModelCallbacks] = None,
        thinking_mode: ThinkingMode = ThinkingMode.DEEP,
    ):
        self.decision_model = DecisionModel(decision_config, thinking_mode)
        self.vision_model = VisionModel(vision_config, device_id)
        self.device_id = device_id
        self.max_steps = max_steps
        self.callbacks = callbacks or DualModelCallbacks()
        self.thinking_mode = thinking_mode

        # 状态
        self.state = DualModelState()
        self.current_task: str = ""
        self.task_plan: Optional[TaskPlan] = None
        self.step_count: int = 0
        self.stop_event = threading.Event()

        # TURBO 模式状态
        self.action_sequence: Optional[ActionSequence] = None
        self.current_action_index: int = 0
        self.executed_actions: list[str] = []

        # 异常状态追踪
        self.anomaly_state = AnomalyState()

        # 事件队列(用于SSE)
        self.event_queue: Queue[DualModelEvent] = Queue()

        logger.info(
            f"双模型协调器初始化完成, 设备: {device_id}, 模式: {thinking_mode.value}"
        )

    def _emit_event(
        self,
        event_type: DualModelEventType,
        data: dict,
        model: Optional[ModelRole] = None,
    ):
        """发送事件到队列"""
        event = DualModelEvent(
            type=event_type,
            data=data,
            model=model,
            step=self.step_count,
            timestamp=time.time(),
        )
        self.event_queue.put(event)

    def run(self, task: str) -> dict:
        """
        执行任务(同步版本)

        Args:
            task: 用户任务描述

        Returns:
            执行结果
        """
        self.current_task = task
        self.step_count = 0
        self.stop_event.clear()
        self.anomaly_state.reset()
        self.executed_actions = []
        self.current_action_index = 0

        logger.info(f"开始执行任务: {task[:50]}... (模式: {self.thinking_mode.value})")

        # TURBO 模式使用批量执行
        if self.thinking_mode == ThinkingMode.TURBO:
            return self._run_turbo(task)

        # FAST/DEEP 模式使用原有逻辑
        return self._run_standard(task)

    def _run_standard(self, task: str) -> dict:
        """标准执行模式 (FAST/DEEP)"""

        try:
            # 1. 大模型分析任务
            self._update_state(
                decision_stage=ModelStage.ANALYZING, decision_active=True
            )
            self._emit_event(
                DualModelEventType.DECISION_START,
                {"stage": "analyzing", "task": task},
                ModelRole.DECISION,
            )

            if self.callbacks.on_decision_start:
                self.callbacks.on_decision_start()

            # 分析任务，获取计划
            self.task_plan = self.decision_model.analyze_task(
                task,
                on_thinking=self._on_decision_thinking,
                on_answer=self._on_decision_answer,
            )

            self._emit_event(
                DualModelEventType.TASK_PLAN,
                {"plan": self.task_plan.to_dict()},
                ModelRole.DECISION,
            )

            if self.callbacks.on_task_plan:
                self.callbacks.on_task_plan(self.task_plan)

            self.state.task_plan = self.task_plan.steps
            self.state.total_steps = self.task_plan.estimated_actions

            # 2. 执行循环
            finished = False
            last_message = ""

            while not finished and self.step_count < self.max_steps:
                if self.stop_event.is_set():
                    logger.info("任务被中断")
                    return {
                        "success": False,
                        "message": "任务被用户中断",
                        "steps": self.step_count,
                    }

                self.step_count += 1
                logger.info(f"执行步骤 {self.step_count}/{self.max_steps}")

                step_result = self._execute_step()

                if step_result.error:
                    logger.error(f"步骤执行失败: {step_result.error}")
                    if self.callbacks.on_error:
                        self.callbacks.on_error(step_result.error)
                    # 继续尝试下一步
                    continue

                if step_result.finished:
                    finished = True
                    last_message = (
                        step_result.decision.reasoning
                        if step_result.decision
                        else "任务完成"
                    )

                if self.callbacks.on_step_complete:
                    self.callbacks.on_step_complete(
                        self.step_count, step_result.success
                    )

                # 步骤间延迟
                time.sleep(0.5)

            # 3. 完成
            success = finished
            message = (
                last_message if finished else f"达到最大步数限制({self.max_steps})"
            )

            self._emit_event(
                DualModelEventType.TASK_COMPLETE,
                {"success": success, "message": message, "steps": self.step_count},
            )

            if self.callbacks.on_task_complete:
                self.callbacks.on_task_complete(success, message)

            logger.info(f"任务完成: success={success}, steps={self.step_count}")

            return {
                "success": success,
                "message": message,
                "steps": self.step_count,
            }

        except Exception as e:
            logger.exception(f"任务执行异常: {e}")
            self._emit_event(
                DualModelEventType.ERROR,
                {"message": str(e)},
            )
            return {
                "success": False,
                "message": f"执行异常: {e}",
                "steps": self.step_count,
            }

    def _run_turbo(self, task: str) -> dict:
        """
        TURBO 模式执行

        一次性生成操作序列，批量执行，仅异常时调用决策模型
        """
        try:
            # 1. 大模型一次性生成操作序列
            self._update_state(
                decision_stage=ModelStage.ANALYZING, decision_active=True
            )
            self._emit_event(
                DualModelEventType.DECISION_START,
                {"stage": "analyzing", "task": task, "mode": "turbo"},
                ModelRole.DECISION,
            )

            if self.callbacks.on_decision_start:
                self.callbacks.on_decision_start()

            self.action_sequence = self.decision_model.analyze_task_turbo(
                task,
                on_thinking=self._on_decision_thinking,
                on_answer=self._on_decision_answer,
            )

            self.task_plan = self.action_sequence.to_plan()
            self._emit_event(
                DualModelEventType.TASK_PLAN,
                {
                    "plan": self.task_plan.to_dict(),
                    "actions": self.action_sequence.to_dict(),
                },
                ModelRole.DECISION,
            )

            if self.callbacks.on_task_plan:
                self.callbacks.on_task_plan(self.task_plan)

            self.state.task_plan = self.task_plan.steps
            self.state.total_steps = len(self.action_sequence.actions)

            logger.info(f"[TURBO] 生成 {len(self.action_sequence.actions)} 个操作步骤")

            # 2. 批量执行操作序列
            self.current_action_index = 0
            finished = False
            last_message = ""
            replan_count = 0
            max_replans = 3

            while not finished and self.step_count < self.max_steps:
                if self.stop_event.is_set():
                    logger.info("[TURBO] 任务被中断")
                    return {
                        "success": False,
                        "message": "任务被用户中断",
                        "steps": self.step_count,
                    }

                # 检查是否还有操作需要执行
                if self.current_action_index >= len(self.action_sequence.actions):
                    finished = True
                    last_message = "操作序列执行完成"
                    break

                self.step_count += 1
                action = self.action_sequence.actions[self.current_action_index]
                logger.info(
                    f"[TURBO] 执行步骤 {self.step_count}: {action.action} -> {action.target}"
                )

                # 执行单步操作
                step_result = self._execute_turbo_step(action)

                if step_result.error or not step_result.success:
                    logger.warning(f"[TURBO] 步骤执行失败: {step_result.error}")
                    self.anomaly_state.record_failure()

                    # 检查是否需要重新规划
                    if self.anomaly_state.has_anomaly() and replan_count < max_replans:
                        replan_count += 1
                        logger.info(
                            f"[TURBO] 触发重新规划 ({replan_count}/{max_replans})"
                        )

                        # 获取当前屏幕状态
                        screenshot_base64, _, _ = self.vision_model.capture_screenshot()
                        screen_desc = self.vision_model.describe_screen(
                            screenshot_base64
                        )

                        # 重新规划
                        new_sequence = self.decision_model.replan(
                            current_state=screen_desc.description,
                            executed_actions=self.executed_actions,
                            error_info=step_result.error or "操作失败",
                            on_thinking=self._on_decision_thinking,
                            on_answer=self._on_decision_answer,
                        )

                        if new_sequence.actions:
                            self.action_sequence = new_sequence
                            self.current_action_index = 0
                            self.anomaly_state.reset()
                            logger.info(
                                f"[TURBO] 重新规划成功，新增 {len(new_sequence.actions)} 个步骤"
                            )
                        else:
                            logger.warning("[TURBO] 重新规划返回空序列")

                    if self.callbacks.on_error:
                        self.callbacks.on_error(step_result.error or "执行失败")
                    continue

                # 成功执行
                self.anomaly_state.record_success()
                self.executed_actions.append(f"{action.action}: {action.target}")
                self.current_action_index += 1

                if step_result.finished:
                    finished = True
                    last_message = "任务完成"

                if self.callbacks.on_step_complete:
                    self.callbacks.on_step_complete(
                        self.step_count, step_result.success
                    )

                # 步骤间短延迟
                time.sleep(0.3)

            # 3. 完成
            success = finished
            message = (
                last_message if finished else f"达到最大步数限制({self.max_steps})"
            )

            self._emit_event(
                DualModelEventType.TASK_COMPLETE,
                {"success": success, "message": message, "steps": self.step_count},
            )

            if self.callbacks.on_task_complete:
                self.callbacks.on_task_complete(success, message)

            logger.info(f"[TURBO] 任务完成: success={success}, steps={self.step_count}")

            return {
                "success": success,
                "message": message,
                "steps": self.step_count,
            }

        except Exception as e:
            logger.exception(f"[TURBO] 任务执行异常: {e}")
            self._emit_event(
                DualModelEventType.ERROR,
                {"message": str(e)},
            )
            return {
                "success": False,
                "message": f"执行异常: {e}",
                "steps": self.step_count,
            }

    def _execute_turbo_step(self, action: ActionStep) -> StepResult:
        """
        TURBO 模式执行单步操作

        直接执行操作，不调用决策模型（除非需要生成内容）
        """
        try:
            # 截图
            screenshot_base64, width, height = self.vision_model.capture_screenshot()

            # 检查截图是否重复
            is_same_screen = self.anomaly_state.check_screenshot(screenshot_base64)
            if is_same_screen:
                logger.warning(
                    f"[TURBO] 屏幕连续 {self.anomaly_state.consecutive_same_screen} 次无变化"
                )

            self._update_state(
                vision_stage=ModelStage.EXECUTING,
                vision_active=True,
                decision_active=False,
            )

            # 处理需要生成内容的操作
            content = action.content
            if action.need_generate and action.action == "type":
                logger.info("[TURBO] 需要生成人性化内容，调用决策模型")
                self._update_state(
                    decision_stage=ModelStage.GENERATING, decision_active=True
                )
                self._emit_event(
                    DualModelEventType.DECISION_START,
                    {"stage": "generating", "content_type": action.target},
                    ModelRole.DECISION,
                )

                # 获取屏幕描述作为上下文
                screen_desc = self.vision_model.describe_screen(screenshot_base64)

                content = self.decision_model.generate_humanize_content(
                    task_context=self.current_task,
                    current_scene=screen_desc.description,
                    content_type=action.target or "回复内容",
                    on_thinking=self._on_decision_thinking,
                    on_answer=self._on_decision_answer,
                )

                self._emit_event(
                    DualModelEventType.CONTENT_GENERATION,
                    {"content": content, "purpose": action.target},
                    ModelRole.DECISION,
                )

                if self.callbacks.on_content_generation:
                    self.callbacks.on_content_generation(content, action.target)

            # 构建决策对象
            decision_dict = {
                "action": action.action,
                "target": action.target,
                "content": content,
                "direction": action.direction,
            }

            self._emit_event(
                DualModelEventType.ACTION_START,
                {"action": decision_dict},
                ModelRole.VISION,
            )

            if self.callbacks.on_action_start:
                self.callbacks.on_action_start(decision_dict)

            # 执行操作
            execution = self.vision_model.execute_decision(
                decision=decision_dict,
                screenshot_base64=screenshot_base64,
            )

            self._update_state(
                vision_action=f"{execution.action_type}: {execution.target}",
                vision_stage=ModelStage.IDLE,
                vision_active=False,
            )

            self._emit_event(
                DualModelEventType.ACTION_RESULT,
                {
                    "success": execution.success,
                    "action_type": execution.action_type,
                    "target": execution.target,
                    "position": execution.position,
                    "message": execution.message,
                },
                ModelRole.VISION,
            )

            if self.callbacks.on_action_result:
                self.callbacks.on_action_result(execution)

            self._emit_event(
                DualModelEventType.STEP_COMPLETE,
                {
                    "step": self.step_count,
                    "success": execution.success,
                    "finished": execution.finished,
                },
            )

            return StepResult(
                step=self.step_count,
                success=execution.success,
                finished=execution.finished,
                execution=execution,
            )

        except Exception as e:
            logger.exception(f"[TURBO] 步骤执行异常: {e}")
            return StepResult(
                step=self.step_count,
                success=False,
                finished=False,
                error=str(e),
            )

    def _execute_step(self) -> StepResult:
        """执行单步操作"""
        try:
            # 2.1 小模型识别屏幕
            self._update_state(
                vision_stage=ModelStage.RECOGNIZING,
                vision_active=True,
                decision_active=False,
            )
            self._emit_event(
                DualModelEventType.VISION_START,
                {"stage": "recognizing"},
                ModelRole.VISION,
            )

            if self.callbacks.on_vision_start:
                self.callbacks.on_vision_start()

            # 截图并识别
            screenshot_base64, width, height = self.vision_model.capture_screenshot()

            # 检查截图是否重复
            is_same_screen = self.anomaly_state.check_screenshot(screenshot_base64)
            if is_same_screen:
                logger.warning(
                    f"屏幕连续 {self.anomaly_state.consecutive_same_screen} 次无变化"
                )

            screen_desc = self.vision_model.describe_screen(screenshot_base64)

            self._update_state(
                vision_description=screen_desc.description[:200],
                vision_stage=ModelStage.IDLE,
            )
            self._emit_event(
                DualModelEventType.VISION_RECOGNITION,
                {
                    "description": screen_desc.description,
                    "current_app": screen_desc.current_app,
                    "elements": screen_desc.elements,
                },
                ModelRole.VISION,
            )

            if self.callbacks.on_vision_recognition:
                self.callbacks.on_vision_recognition(screen_desc)

            # 2.2 大模型决策
            self._update_state(
                decision_stage=ModelStage.DECIDING,
                decision_active=True,
                vision_active=False,
            )
            self._emit_event(
                DualModelEventType.DECISION_START,
                {"stage": "deciding"},
                ModelRole.DECISION,
            )

            if self.callbacks.on_decision_start:
                self.callbacks.on_decision_start()

            # 构建任务上下文，包含异常信息
            task_context = f"当前应用: {screen_desc.current_app}"
            error_context = self.anomaly_state.get_error_context()
            if error_context:
                task_context += f"\n\n{DECISION_ERROR_CONTEXT_TEMPLATE.format(error_context=error_context)}"
                logger.info("添加异常上下文到决策请求")

            # 调用决策模型
            decision = self.decision_model.make_decision(
                screen_description=screen_desc.description,
                task_context=task_context,
                on_thinking=self._on_decision_thinking,
                on_answer=self._on_decision_answer,
            )

            # 检查是否重复操作
            if decision.action and decision.target:
                is_repeated = self.anomaly_state.check_action(
                    decision.action, decision.target
                )
                if is_repeated:
                    logger.warning(
                        f"操作重复 {self.anomaly_state.repeated_actions} 次: {decision.action} -> {decision.target}"
                    )

            self._update_state(
                decision_result=f"{decision.action}: {decision.target}",
                decision_thinking=decision.reasoning,
                decision_stage=ModelStage.IDLE,
            )
            self._emit_event(
                DualModelEventType.DECISION_RESULT,
                {
                    "decision": decision.to_dict(),
                    "reasoning": decision.reasoning,
                },
                ModelRole.DECISION,
            )

            if self.callbacks.on_decision_result:
                self.callbacks.on_decision_result(decision)

            # 检查是否完成
            if decision.finished:
                self.anomaly_state.record_success()
                return StepResult(
                    step=self.step_count,
                    success=True,
                    finished=True,
                    decision=decision,
                    screen_desc=screen_desc,
                )

            # 处理等待操作
            if decision.action == "wait":
                logger.info("执行等待操作...")
                time.sleep(2)  # 等待2秒
                return StepResult(
                    step=self.step_count,
                    success=True,
                    finished=False,
                    decision=decision,
                    screen_desc=screen_desc,
                )

            # 2.3 小模型执行
            self._update_state(
                vision_stage=ModelStage.EXECUTING,
                vision_active=True,
                decision_active=False,
            )

            action_dict = {
                "action": decision.action,
                "target": decision.target,
                "content": decision.content,
            }

            self._emit_event(
                DualModelEventType.ACTION_START,
                {"action": action_dict},
                ModelRole.VISION,
            )

            if self.callbacks.on_action_start:
                self.callbacks.on_action_start(action_dict)

            execution = self.vision_model.execute_decision(
                decision=action_dict,
                screenshot_base64=screenshot_base64,
            )

            # 记录执行结果
            if execution.success:
                self.anomaly_state.record_success()
            else:
                self.anomaly_state.record_failure()

            self._update_state(
                vision_action=f"{execution.action_type}: {execution.target}",
                vision_stage=ModelStage.IDLE,
                vision_active=False,
            )
            self._emit_event(
                DualModelEventType.ACTION_RESULT,
                {
                    "success": execution.success,
                    "action_type": execution.action_type,
                    "target": execution.target,
                    "position": execution.position,
                    "message": execution.message,
                },
                ModelRole.VISION,
            )

            if self.callbacks.on_action_result:
                self.callbacks.on_action_result(execution)

            # 步骤完成事件
            self._emit_event(
                DualModelEventType.STEP_COMPLETE,
                {
                    "step": self.step_count,
                    "success": execution.success,
                    "finished": execution.finished,
                },
            )

            return StepResult(
                step=self.step_count,
                success=execution.success,
                finished=execution.finished,
                decision=decision,
                screen_desc=screen_desc,
                execution=execution,
            )

        except Exception as e:
            logger.exception(f"步骤执行异常: {e}")
            self.anomaly_state.record_failure()
            return StepResult(
                step=self.step_count,
                success=False,
                finished=False,
                error=str(e),
            )

    def _update_state(self, **kwargs):
        """更新状态"""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
        self.state.current_step = self.step_count

    def _on_decision_thinking(self, chunk: str):
        """决策思考回调"""
        self._emit_event(
            DualModelEventType.DECISION_THINKING,
            {"chunk": chunk},
            ModelRole.DECISION,
        )
        if self.callbacks.on_decision_thinking:
            self.callbacks.on_decision_thinking(chunk)

    def _on_decision_answer(self, chunk: str):
        """决策答案回调"""
        pass  # 答案通过 DECISION_RESULT 事件发送

    def abort(self):
        """中止任务"""
        logger.info("中止任务")
        self.stop_event.set()

    def reset(self):
        """重置状态"""
        self.current_task = ""
        self.task_plan = None
        self.step_count = 0
        self.stop_event.clear()
        self.state = DualModelState()
        self.anomaly_state.reset()
        self.decision_model.reset()

        # TURBO 模式状态重置
        self.action_sequence = None
        self.current_action_index = 0
        self.executed_actions = []

        # 清空事件队列
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except Exception:
                break

        logger.info("双模型协调器已重置")

    def get_state(self) -> dict:
        """获取当前状态"""
        return self.state.to_dict()

    def get_events(self, timeout: float = 0.1) -> list[DualModelEvent]:
        """获取待处理的事件"""
        events = []
        while True:
            try:
                event = self.event_queue.get(timeout=timeout)
                events.append(event)
            except Exception:
                break
        return events
