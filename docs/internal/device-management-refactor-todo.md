# 设备管理模块精简与结构优化 TODO

更新时间：2026-02-10
状态：Phase 1-4 已完成
范围：`AutoGLM_GUI` 设备管理相关模块（不含前端功能改动）

## 1. 目标与边界

- 目标：清理低价值向后兼容代码，减少跨模块私有字段访问，收敛设备标识与连接类型语义，做小步安全重构。
- 边界：先做后端设备管理层，不做大规模重写，不改变对外 API 行为（除明确标注废弃且确认无依赖的入口）。
- 当前约束：本计划文件仅记录执行步骤，本轮不改业务代码。

## 2. 调研结论（已确认）

- [ ] `DeviceManager` 私有状态被多处直接访问，耦合较高。
  - 证据：`AutoGLM_GUI/api/devices.py`、`AutoGLM_GUI/api/mcp.py`、`AutoGLM_GUI/api/layered_agent.py` 直接读取 `_poll_thread`。
  - 证据：`AutoGLM_GUI/api/media.py`、`AutoGLM_GUI/metrics.py` 直接读取 `_devices`/`_devices_lock`。
- [ ] `DeviceManager.get_device()` 为 deprecated 且仓库内无调用。
  - 证据：`AutoGLM_GUI/device_manager.py:312`。
- [ ] `PhoneAgentManager.abort_streaming_chat()` 为向后兼容同步接口，当前主流程走异步接口。
  - 证据：`AutoGLM_GUI/phone_agent_manager.py:612`；API 使用 `abort_streaming_chat_async`。
- [ ] `AutoGLM_GUI/devices/__init__.py` 中全局 manager 入口 (`get_device_manager`/`set_device_manager`) 仅定义未使用。
- [ ] 连接类型存在历史兼容命名混叠（`ConnectionType.REMOTE` 在 `DeviceManager` 内被映射为 WiFi ADB）。
- [ ] 下列兼容逻辑目前仍有业务价值，暂不作为“直接删除”对象：
  - `_device_id_to_serial` 反向映射（历史记录、截图、指标链路仍依赖）。
  - `get_device_serial()` 失败回退 `device_id`（模拟器/受限设备场景和测试依赖）。
- [x] `/api/init` 依赖已清理：前端不再调用，集成测试迁移到自动初始化链路。

## 3. 执行计划（分阶段）

### Phase 0：建立改动基线（安全准备）

- [ ] 固化当前行为基线。
- [ ] 记录计划涉及的文件清单与影响路径。
- [ ] 跑最小验证命令并保存结果。

建议验证命令：

- [ ] `uv run python scripts/lint.py --backend --check-only`
- [ ] `uv run pytest -v`

### Phase 1：先降耦合（不改语义）

- [x] 在 `DeviceManager` 增加公开只读查询方法，替代外部直接访问私有字段。
- [x] API/metrics/layered/mcp 改为使用公开方法，不再读取 `_poll_thread`、`_devices` 等私有字段。
- [x] 保持接口返回一致，确保行为不变。

完成标准：

- [x] 设备相关 API 响应结构与现状一致。
- [x] `metrics` 数据字段保持兼容。
- [x] 仓库内不再出现设备管理私有字段跨模块直接访问。

### Phase 2：清理低价值兼容入口（小步删除）

- [x] 删除 `DeviceManager.get_device()`（deprecated 且无调用）。
- [x] 评估并移除 `PhoneAgentManager.abort_streaming_chat()` 同步兼容口（前提：确认无外部依赖）。
- [x] 评估并清理 `AutoGLM_GUI/devices/__init__.py` 中未使用的全局 manager 入口。

完成标准：

- [x] 全仓搜索无内部调用残留。
- [x] 测试与 lint 全绿。
- [x] 变更日志清楚说明移除项。

### Phase 3：收敛设备标识与连接类型语义

- [x] 统一文档与注释，明确 `device_id`、`serial`、`primary_device_id` 的职责边界。
- [x] 制定 `ConnectionType` 命名收敛方案（避免 `REMOTE` 同时表达“WiFi ADB”和“HTTP Remote Device”语义混淆）。
- [x] 先做非破坏性整理（注释、映射封装、类型约束），必要时分后续版本做行为级调整。

完成标准：

- [x] 新增/更新的注释与类型声明能直接说明语义。
- [x] 新代码不再引入新的命名歧义。

### Phase 4：处理 `/api/init` 的退役路径

- [x] 先迁移前端调用（改为自动初始化链路）。
- [x] 更新集成测试，移除对 `/api/init` 的硬依赖。
- [x] 完成迁移后再正式删除 `/api/init` 及相关提示文本。

完成标准：

- [x] `frontend` 不再调用 `/api/init`。
- [x] 集成测试不再依赖 `/api/init`。
- [x] API 文档与异常提示同步更新。

## 4. 风险与回滚策略

- [ ] 风险：设备标识链路（`device_id` -> `serial`）改动容易影响历史记录、截图、调度与指标。
- [ ] 风险：并发相关改动（设备锁、轮询状态）容易引入时序问题。
- [ ] 策略：每个 Phase 单独提交；先做“接口封装替换”，再做“兼容删除”；每步都跑最小验证。

## 5. 验证清单（每阶段执行）

- [x] `uv run python scripts/lint.py --backend --check-only`
- [x] `uv run pytest -v`
- [x] `uv run pytest -v tests/test_metrics.py tests/test_device_name_api.py`
- [ ] 手工验证：
- [ ] `GET /api/devices`
- [ ] `POST /api/screenshot`
- [ ] `POST /api/chat/stream` + `POST /api/chat/abort`
- [ ] 指标接口 `/api/metrics`

## 6. 实施顺序建议（当前推荐）

- [x] 先执行 Phase 1（降耦合，不改语义）。
- [x] 再执行 Phase 2（删除已确认低价值兼容入口）。
- [x] 然后执行 Phase 3（术语与类型收敛）。
- [x] 最后执行 Phase 4（`/api/init` 退役）。
