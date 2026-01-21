---
id: interface
title: 界面预览
---

## 📸 界面预览

快速跳转： [普通模式](/docs/user-guide/ai-modes#mode-classic) · [双模型协作（增强）](/docs/user-guide/ai-modes#mode-dual) · [分层代理（增强）](/docs/user-guide/ai-modes#mode-layered)

### 双模型协作架构

**决策大模型（如 GLM-4.7）+ 视觉小模型（AutoGLM-Phone）**：大模型负责规划与纠错，小模型负责观察与执行，适合更复杂、更长流程的任务。

- 🧠 **决策层**：任务理解 / 步骤规划 / 异常纠错
- 👁️ **执行层**：识别界面元素并点击/滑动/输入完成操作
- 🔄 **运行方式**：规划 → 执行 → 反馈；必要时自动重规划

**模式选择（Thinking Mode）**：TURBO（更省更快，推荐常规流程）/ DEEP（更稳，适合复杂任务）/ FAST（更快，适合轻量任务）。

<img width="879" height="849" alt="双模型协作界面" src="https://github.com/user-attachments/assets/15e5cf51-5a19-403d-9af3-46f77c2068f5" />

### 分层代理

**分层代理（Layered Agent）** 是更“严格”的两层结构：**规划层**专注任务拆解与多轮推理，**执行层**专注观察与操作。规划层会通过工具调用（可在界面中看到每次调用与结果）来驱动执行层完成一个个原子子任务，便于边执行边调整策略，适合需要多轮交互/推理的高级任务。

<img width="939" height="851" alt="图片" src="https://github.com/user-attachments/assets/c054d998-726d-48ed-99e7-bb33581b3745" />

### 任务开始
![任务开始](https://github.com/user-attachments/assets/b8cb6fbc-ca5b-452c-bcf4-7d5863d4577a)

### 任务执行完成
![任务结束](https://github.com/user-attachments/assets/b32f2e46-5340-42f5-a0db-0033729e1605)

### 多设备控制
![多设备控制](https://github.com/user-attachments/assets/f826736f-c41f-4d64-bf54-3ca65c69068d)
