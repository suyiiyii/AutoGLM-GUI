# AutoGLM-GUI 代码优化计划

> 生成日期: 2026-03-22
> 状态: 待执行

## 概述

本文档记录了项目代码优化分析和推荐执行顺序。

---

## 1. 移除 BaseAgent 协议和 is_async_agent() (高优先级)

**工作量**: 小
**收益**: 简化代码，移除不必要的类型检查

### 背景

现在所有注册的 Agent 都是 `AsyncAgent`：
- `glm-async`
- `mai`
- `gemini`
- `droidrun`
- `midscene`

`BaseAgent` 协议已无实际实现类，`is_async_agent()` 总是返回 `True`。

### 需要修改的文件

| 文件 | 操作 |
|------|------|
| `AutoGLM_GUI/agents/protocols.py` | 删除 `BaseAgent` 类定义 |
| `AutoGLM_GUI/agents/factory.py` | 类型注解改为仅 `AsyncAgent` |
| `AutoGLM_GUI/phone_agent_manager.py` | 类型注解改为仅 `AsyncAgent` |
| `AutoGLM_GUI/agents/__init__.py` | 移除 `BaseAgent` 导出 |
| `AutoGLM_GUI/task_manager.py` | 移除 `is_async_agent()` 调用 |
| `AutoGLM_GUI/api/layered_agent.py` | 移除 `is_async_agent()` 调用 |
| `AutoGLM_GUI/api/mcp.py` | 移除 `is_async_agent()` 调用 |
| `AutoGLM_GUI/scheduler_manager.py` | 移除 `is_async_agent()` 调用 |

### 具体改动

```python
# protocols.py - 删除 BaseAgent
class AsyncAgent(Protocol):
    # ... 保持不变

# factory.py - 简化类型
AGENT_REGISTRY: dict[str, Callable[..., AsyncAgent]] = {}
def create_agent(...) -> AsyncAgent:
    ...

# phone_agent_manager.py - 简化类型
self._agents: dict[str, AsyncAgent] = {}
def get_agent(self, device_id: str) -> AsyncAgent:
    ...

# task_manager.py - 移除检查
# 之前:
if is_async_agent(agent):
    async for event in agent.stream(task):
        ...

# 之后:
async for event in agent.stream(task):
    ...
```

---

## 2. 迁移 adb/ 目录到异步 (中优先级)

**工作量**: 中
**收益**: 性能提升，减少事件循环阻塞

### 当前状态

| 文件 | 同步调用数 |
|------|-----------|
| `adb/input.py` | 5 个 `subprocess.run` |
| `adb/device.py` | 9 个 `subprocess.run` |
| `adb/connection.py` | 6 个 `subprocess.run` + 2 个 `time.sleep` |

### 迁移方案

```python
# 之前 (同步)
def tap(x: int, y: int, device_id: str | None = None) -> None:
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])

# 之后 (异步)
async def tap(x: int, y: int, device_id: str | None = None) -> None:
    cmd = build_adb_command(device_id) + ["shell", "input", "tap", str(x), str(y)]
    await run_adb_async(cmd)

# 通用异步 ADB 执行器 (新增到 platform_utils.py)
async def run_adb_async(cmd: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
    """异步执行 ADB 命令"""
    if is_windows():
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=timeout
        )
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        return subprocess.CompletedProcess(
            cmd, process.returncode or -1, stdout.decode(), stderr.decode()
        )
    except asyncio.TimeoutError:
        process.kill()
        raise
```

### 文件迁移顺序

1. `adb/input.py` - 文本输入相关
2. `adb/screenshot.py` - 截图
3. `adb/device.py` - 设备操作 (tap, swipe, etc.)
4. `adb/connection.py` - 连接管理

### 注意事项

- 需要同时更新调用方使用 `await`
- `time.sleep` 改为 `asyncio.sleep`
- 测试覆盖所有改动

---

## 3. 迁移 adb_plus/ 目录到异步 (中优先级)

**工作量**: 中
**收益**: 性能提升

### 当前状态

| 文件 | 同步调用数 |
|------|-----------|
| `adb_plus/screenshot.py` | 1 个 `subprocess.run` |
| `adb_plus/touch.py` | 3 个 `subprocess.run` + 3 个 `time.sleep` |
| `adb_plus/ip.py` | 1 个 `subprocess.run` |
| `adb_plus/serial.py` | 使用 `run_cmd_silently_sync` |
| `adb_plus/pair.py` | 使用 `run_cmd_silently_sync` |

### 已有基础设施

`platform_utils.py` 已有异步版本：
- `run_cmd_silently()` - 异步版本
- `run_cmd_silently_sync()` - 同步版本

### 迁移方案

```python
# adb_plus/touch.py
# 之前
def touch_down(x: int, y: int, device_id: str | None = None) -> None:
    subprocess.run(cmd, ...)
    if delay > 0:
        time.sleep(delay)

# 之后
async def touch_down(x: int, y: int, device_id: str | None = None) -> None:
    await run_cmd_silently(cmd)
    if delay > 0:
        await asyncio.sleep(delay)
```

---

## 4. 改进异常处理 (低优先级)

**工作量**: 小
**收益**: 可维护性，更好的错误追踪

### 问题

发现 ~40 处过于宽泛的异常处理：

```python
# 不好的做法 - 静默吞掉所有异常
except Exception:
    pass
```

### 主要文件

| 文件 | 问题数量 |
|------|---------|
| `scrcpy_stream.py` | 8 |
| `api/layered_agent.py` | 6 |
| `adb_plus/mdns.py` | 2 |
| `adb_plus/screenshot.py` | 2 |
| `socketio_server.py` | 2 |

### 改进方案

```python
# 之前
except Exception:
    pass

# 之后 - 方案 1: 记录日志
except Exception as e:
    logger.debug(f"Expected error in xxx: {e}")

# 之后 - 方案 2: 捕获特定异常
except (ConnectionError, TimeoutError) as e:
    logger.warning(f"Connection failed: {e}")

# 之后 - 方案 3: 显式忽略（有注释说明原因）
except Exception:
    # Expected: xxx 可能失败，但不影响主流程
    pass
```

---

## 5. 类型注解优化 (低优先级)

**工作量**: 大
**收益**: 类型安全，IDE 支持

### 问题

发现 **188 处** `dict[str, Any]` 使用，缺乏类型安全。

### 改进方案

```python
# 之前
def get_workflow(self, uuid: str) -> dict[str, Any] | None:
    ...

# 之后 - 使用 TypedDict
from typing import TypedDict

class Workflow(TypedDict):
    uuid: str
    name: str
    text: str

def get_workflow(self, uuid: str) -> Workflow | None:
    ...

# 或使用 dataclass
@dataclass
class Workflow:
    uuid: str
    name: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

### 建议优化的区域

- `workflow_manager.py` - Workflow 类型
- `config_manager.py` - ConfigLayer 类型
- `device_manager.py` - DeviceConnection 类型
- API 响应模型 - 已使用 Pydantic，保持现状

---

## 6. 大文件拆分 (可选)

**工作量**: 大
**收益**: 可维护性

### 当前状态

| 文件 | 行数 | 建议 |
|------|------|------|
| `schemas.py` | 1155 | 按功能拆分为多个文件 |
| `device_manager.py` | 1089 | 提取 RemoteDevice 逻辑到单独文件 |
| `api/layered_agent.py` | 805 | 提取 session 管理到单独模块 |

### 拆分建议

```
# schemas.py → schemas/
schemas/
  __init__.py
  device.py      # DeviceResponse, etc.
  task.py        # TaskResponse, etc.
  agent.py       # AgentResponse, etc.
  workflow.py    # WorkflowResponse, etc.

# device_manager.py
device_manager.py          # 核心 DeviceManager 类
remote_device_manager.py   # Remote device 相关逻辑
```

---

## 执行检查清单

### 任务 1: 移除 BaseAgent ✅ PR #286
- [x] 修改 `protocols.py`
- [x] 修改 `factory.py`
- [x] 修改 `phone_agent_manager.py`
- [x] 修改 `agents/__init__.py`
- [x] 修改 `task_manager.py`
- [x] 修改 `api/layered_agent.py`
- [x] 修改 `api/mcp.py`
- [x] 修改 `scheduler_manager.py`
- [x] 运行测试
- [x] 创建 PR

### 任务 2: 迁移 adb/ 到异步 ✅ PR #287
- [x] 添加 `run_adb_async()` 到 `platform_utils.py`
- [x] 创建 `adb/async_device.py` 模块
- [x] 运行测试
- [x] 创建 PR

**注意**: 完整的调用方迁移将在后续 PR 中完成，目前保持向后兼容

### 任务 3: 迁移 adb_plus/ 到异步 ✅ PR #288
- [x] 创建 `adb_plus/async_adb_plus.py` 模块
- [x] 迁移 `capture_screenshot()` 到异步
- [x] 迁移 `touch_down()`, `touch_move()`, `touch_up()` 到异步
- [x] 迁移 `get_wifi_ip()` 到异步
- [x] 迁移 `get_device_serial()` 到异步
- [x] 迁移 `pair_device()` 到异步
- [x] 运行测试
- [x] 创建 PR

**注意**: 完整的调用方迁移将在后续 PR 中完成，目前保持向后兼容

### 任务 4: 改进异常处理
- [ ] 修改 `scrcpy_stream.py`
- [ ] 修改 `api/layered_agent.py`
- [ ] 修改 `adb_plus/mdns.py`
- [ ] 修改 `adb_plus/screenshot.py`
- [ ] 修改 `socketio_server.py`
- [ ] 运行测试
- [ ] 创建 PR

### 任务 5: 类型注解优化
- [ ] 优化 `workflow_manager.py`
- [ ] 优化 `config_manager.py`
- [ ] 优化 `device_manager.py`
- [ ] 运行测试
- [ ] 创建 PR

---

## 备注

- 每个任务建议独立 PR
- 任务 1-3 有依赖关系，建议按顺序执行
- 任务 4-5 可以并行执行
