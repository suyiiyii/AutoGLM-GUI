# AsyncLayeredAgent 设计方案

**日期**: 2026-01-22
**作者**: AutoGLM Team
**目标**: 实现真正的端到端异步分层代理，提升性能和用户体验

## 概述

AsyncLayeredAgent 是 `layered_agent.py` 的异步版本，核心改进：
- 执行层使用 `AsyncGLMAgent` 替代同步包装
- 真正的端到端异步，无阻塞 I/O
- 取消响应 <1s（vs 同步版本的 10-30s）

## 核心设计决策

### 1. 架构方案：独立文件

**选择**: 新建 `AutoGLM_GUI/api/async_layered_agent.py`

**理由**:
- 零风险：不影响现有代码
- 易于测试：可以 A/B 对比性能
- 清晰分离：async 版本有自己的命名空间
- 灵活迁移：验证后可决定是否替换旧版本

**文件结构**:
```
AutoGLM_GUI/api/
├── layered_agent.py          # 保持不变（现有同步版本）
└── async_layered_agent.py    # 新文件（异步版本）
```

### 2. 异步化范围：真正的端到端异步

**选择**: 执行层直接使用 `AsyncGLMAgent`

**对比**:
- ❌ 同步版本: `asyncio.to_thread(_sync_chat)` → `agent.run()` [阻塞]
- ✅ 异步版本: `await agent.run()` [真正异步]

**优势**:
- 取消响应 <1s（可立即关闭 HTTP 连接）
- 无线程开销
- 更简洁的代码

**权衡**:
- 需要绕过 PhoneAgentManager 的锁机制
- 自行管理 agent 生命周期

### 3. 并发控制：Session 隔离（无锁）

**选择**: 每个 session 独立的 AsyncGLMAgent 实例，暂不加设备锁

**策略**:
- 每个 session_id 持有独立的 agents 字典
- Session 之间完全隔离
- 同一设备的多个 session 可能并发执行（简单优先）

**未来改进**:
- 如果发现设备并发冲突，可在 tool 层添加设备锁
- 当前优先保持简单，专注于异步实现

### 4. 工具实现：返回最终结果

**选择**: Tool 返回最终结果，不返回完整执行过程

```python
@function_tool
async def async_chat(device_id: str, message: str) -> str:
    agent = _get_or_create_async_agent(session_id, device_id)
    result = await agent.run(message)  # 使用 run() 而非 stream()
    return json.dumps({
        "result": result,
        "steps": agent.step_count,
        "success": True
    })
```

**理由**:
- 决策层通常只需要知道"任务完成了吗，结果是什么"
- 简洁的 JSON 返回
- 减少网络传输

### 5. 生命周期管理：懒加载 + 显式清理

**选择**: 懒加载创建，reset 时显式清理

```python
# Session 数据结构
_async_sessions: dict[str, dict] = {}
# {
#   "session_123": {
#       "sqlite_session": SQLiteSession("session_123"),
#       "agents": {
#           "device_001": AsyncGLMAgent(...),  # 按需创建
#           "device_002": AsyncGLMAgent(...)
#       }
#   }
# }
```

**创建时机**: 第一次调用 `chat(device_id)` 时创建
**清理时机**: 调用 `reset_session()` 时清理所有 agents

## 实现细节

### 数据结构

```python
# Session 管理
_async_sessions: dict[str, dict] = {}

# 活跃运行管理（用于 abort）
_async_active_runs: dict[str, "RunResultStreaming"] = {}
_async_active_runs_lock = threading.Lock()

# 全局 planner agent
_async_client: AsyncOpenAI | None = None
_async_agent: Agent[Any] | None = None
_async_cached_config_hash: str | None = None
```

### 核心函数

#### 1. Agent 创建和管理

```python
def _get_or_create_async_agent(session_id: str, device_id: str) -> AsyncGLMAgent:
    """获取或创建指定 session 和 device 的 AsyncGLMAgent。

    懒加载模式：
    1. 如果 session 不存在，先创建 session
    2. 如果 session 存在但没有该 device 的 agent，创建 agent
    3. 否则返回已存在的 agent
    """
    # 确保 session 存在
    if session_id not in _async_sessions:
        _async_sessions[session_id] = {
            "sqlite_session": SQLiteSession(session_id),
            "agents": {}
        }

    # 确保 agent 存在
    agents = _async_sessions[session_id]["agents"]
    if device_id not in agents:
        # 从配置创建 AsyncGLMAgent
        config = config_manager.get_effective_config()
        model_config = ModelConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            model_name=config.model_name,
            # ...
        )
        agent_config = AgentConfig(
            max_steps=5,  # MCP 固定 5 步
            system_prompt=MCP_SYSTEM_PROMPT_ZH,
            # ...
        )

        # 获取 device
        device_manager = DeviceManager.get_instance()
        device = device_manager.get_device(device_id)

        # 创建 agent
        agents[device_id] = AsyncGLMAgent(
            model_config=model_config,
            agent_config=agent_config,
            device=device
        )
        logger.info(f"[AsyncLayeredAgent] Created AsyncGLMAgent for session={session_id}, device={device_id}")

    return agents[device_id]
```

#### 2. 工具函数

```python
@function_tool
async def async_chat(device_id: str, message: str) -> str:
    """异步版本：向设备发送任务，使用 AsyncGLMAgent。"""
    session_id = device_id  # TODO: 从 Runner 上下文传递

    try:
        agent = _get_or_create_async_agent(session_id, device_id)

        # 真正的异步调用，带超时保护
        result = await asyncio.wait_for(
            agent.run(message),
            timeout=60.0
        )

        return json.dumps({
            "result": result,
            "steps": agent.step_count,
            "success": True
        }, ensure_ascii=False)

    except asyncio.TimeoutError:
        return json.dumps({
            "result": "Execution timeout (60s)",
            "steps": agent.step_count,
            "success": False
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[AsyncLayeredAgent] async_chat error: {e}")
        return json.dumps({
            "result": str(e),
            "steps": 0,
            "success": False
        }, ensure_ascii=False)


@function_tool
async def async_list_devices() -> str:
    """异步版本：列出所有设备（复用现有逻辑）。"""
    return await asyncio.to_thread(_sync_list_devices)
```

### API 端点

#### 1. 聊天端点

```python
@router.post("/api/async-layered-agent/chat")
async def async_layered_agent_chat(request: LayeredAgentRequest) -> StreamingResponse:
    """异步分层代理聊天 API。

    返回 SSE 流式事件：
    - tool_call: 工具调用开始
    - tool_result: 工具执行结果
    - message: 中间消息
    - done: 任务完成
    - error: 错误
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = datetime.now()
        final_output = ""
        final_success = False

        try:
            # 1. 确保 planner agent 初始化
            agent = _ensure_async_agent()

            # 2. 获取或创建 session
            session_id = request.session_id or request.device_id or "default"
            session = _get_or_create_async_session(session_id)

            # 3. 运行 planner
            effective_config = config_manager.get_effective_config()
            result = Runner.run_streamed(
                agent,
                request.message,
                max_turns=effective_config.layered_max_turns,
                session=session,
            )

            # 4. 保存活跃运行（用于 abort）
            with _async_active_runs_lock:
                _async_active_runs[session_id] = result

            try:
                # 5. 流式处理事件
                async for event in result.stream_events():
                    # 解析和转发事件
                    # ... (与现有代码相同的事件处理逻辑)
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                # 6. 完成
                final_output = result.final_output
                final_success = True
                yield f"data: {json.dumps({'type': 'done', 'content': final_output}, ensure_ascii=False)}\n\n"

            finally:
                # 7. 清理活跃运行
                with _async_active_runs_lock:
                    _async_active_runs.pop(session_id, None)

        except Exception as e:
            logger.exception(f"[AsyncLayeredAgent] Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        finally:
            # 8. 记录历史
            if request.device_id and final_output:
                # 记录到 history_manager
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

#### 2. 取消端点

```python
@router.post("/api/async-layered-agent/abort")
def async_abort_session(request: AbortSessionRequest) -> dict[str, Any]:
    """中止运行中的异步 session。"""
    session_id = request.session_id

    with _async_active_runs_lock:
        if session_id in _async_active_runs:
            result = _async_active_runs[session_id]
            result.cancel(mode="immediate")
            logger.info(f"[AsyncLayeredAgent] Aborted session: {session_id}")
            return {"success": True, "message": f"Session {session_id} abort signal sent"}
        else:
            return {"success": False, "message": f"No active run found"}
```

#### 3. 重置端点

```python
@router.post("/api/async-layered-agent/reset")
def async_reset_session(request: ResetSessionRequest) -> dict[str, Any]:
    """重置 session，清空对话历史和所有 agents。"""
    session_id = request.session_id

    if session_id in _async_sessions:
        # 清理所有 agents
        agents = _async_sessions[session_id]["agents"]
        for agent in agents.values():
            agent.reset()  # 重置 agent 状态

        # 删除整个 session
        del _async_sessions[session_id]
        logger.info(f"[AsyncLayeredAgent] Reset session: {session_id}")
        return {"success": True, "message": f"Session {session_id} reset"}

    return {"success": True, "message": f"Session {session_id} not found"}
```

## 错误处理

### 主要错误场景

1. **Agent 创建失败**: 捕获异常，清理部分状态，抛出友好错误
2. **Device 不存在**: 返回结构化 JSON 错误
3. **执行超时**: `asyncio.wait_for()` 超时保护（60s）
4. **配置缺失**: 友好的配置指引
5. **并发访问**: 当前无锁（简单优先），如需要可后续添加

### 错误返回格式

所有工具函数统一返回 JSON 格式：
```json
{
  "result": "错误描述或结果",
  "steps": 0,
  "success": false
}
```

## 集成和配置

### 路由注册

在 `AutoGLM_GUI/api/__init__.py` 中：
```python
from AutoGLM_GUI.api import async_layered_agent

app.include_router(async_layered_agent.router)
```

### 配置复用

- **Prompt**: 复用 `MCP_SYSTEM_PROMPT_ZH` 和 `PLANNER_INSTRUCTIONS`
- **Config**: 使用 `config_manager.get_effective_config()`
- **Device**: 从 `DeviceManager.get_instance()` 获取

### 依赖组件

- `DeviceManager` - 获取 device 实例
- `config_manager` - 读取配置
- `history_manager` - 记录对话历史
- `AsyncGLMAgent` - 执行层 agent
- `openai-agents` SDK - 决策层框架

## 测试策略

### 单元测试

- Agent 创建和复用逻辑
- Session 生命周期管理
- 工具函数错误处理
- 超时保护机制

### 集成测试

- 端到端流式输出
- 取消机制验证
- 与现有端点共存

### 性能基准

对比同步版本和异步版本：
- 首次响应延迟
- 取消响应时间
- 内存占用
- 并发能力

## 预期收益

### 性能提升

- 首次响应延迟减少 ~30%（无线程启动开销）
- 取消响应从 10-30s 降至 <1s
- 内存占用减少（无需 worker 线程）

### 代码质量

- 更简洁（无需 queue、线程同步）
- 更易维护（标准 asyncio 模式）
- 更易调试（标准 async/await）

### 用户体验

- 更快的交互响应
- 立即取消能力
- 更流畅的流式输出

## 部署计划

1. **代码实现**: 创建 `async_layered_agent.py`
2. **单元测试**: 验证核心逻辑
3. **集成测试**: 端到端验证
4. **性能基准**: 对比同步版本
5. **文档更新**: 更新 CLAUDE.md
6. **代码审查**: 检查错误处理和日志
7. **提交和部署**: 提交 PR，合并到主分支
8. **前端集成（可选）**: 添加异步模式选项
9. **监控观察**: 上线后监控性能指标

## 未来改进

### 短期（如需要）

- 添加设备级并发锁
- 改进 session_id 传递机制
- 添加更详细的性能指标

### 长期

- 考虑完全替换同步版本
- 统一 agent 管理机制
- 优化资源使用

## 附录

### 文件清单

**新增文件**:
- `AutoGLM_GUI/api/async_layered_agent.py` (~500 行)
- `tests/unit/api/test_async_layered_agent.py`
- `tests/integration/test_async_layered_agent_e2e.py`

**修改文件**:
- `AutoGLM_GUI/api/__init__.py` (注册路由)
- `docs/CLAUDE.md` (文档更新)

### API 端点总结

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/async-layered-agent/chat` | POST | 异步聊天（SSE 流） |
| `/api/async-layered-agent/abort` | POST | 取消执行 |
| `/api/async-layered-agent/reset` | POST | 重置 session |

### 与同步版本对比

| 维度 | 同步版本 | 异步版本 |
|------|----------|----------|
| 执行层 | `asyncio.to_thread(agent.run)` | `await agent.run()` |
| 取消响应 | 10-30s | <1s |
| 线程开销 | 有（worker 线程） | 无 |
| 代码复杂度 | 较高（queue、同步） | 简洁（标准 async） |
| 内存占用 | 较高 | 较低 |

---

**设计完成日期**: 2026-01-22
**实现优先级**: 高
**预计工作量**: 2-3 天
