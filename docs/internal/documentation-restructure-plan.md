# 文档重构方案

## 1. 背景与目标

当前仓库已经具备较多文档内容，但主要问题不是“缺文档”，而是：

- 入口过多，首次阅读路径不稳定
- 同一主题在多个位置重复维护，导致版本号、命令、链接漂移
- 用户文档、部署文档、开发者文档、内部分析文档混在同一层级
- 英文文档和中文文档同步不及时

本方案目标不是重写全部文档，而是先完成信息架构重整，让后续维护成本显著下降。

## 2. 现状诊断

### 2.1 当前主要问题

1. 根目录 `README.md` 过长，同时承担项目首页、安装说明、部署指南、FAQ、MCP 集成、贡献入口等多个角色。
2. Docusaurus 文档站里同时存在 `quick-start.md` 和 `getting-started/*` 两套入门结构，入口重复。
3. 文档站中有多份页面未进入主导航，例如 `installation.md`、`development.md`、`configuration.md`、`upgrade.md`、`release-notes-v1.5.md`、`user-guide/*`、`layered_agent_analysis.md`。
4. 中英文 README 存在明显事实不同步，下载版本、安装内容和结构均已分叉。
5. 若干贡献和内部文档引用了不存在或已失效的文件、命令和占位仓库地址。
6. 文档工具链说明也发生漂移，例如 `docs/README.md` 仍使用 `yarn`，但实际 `docs/package.json` 已声明 `pnpm`。

### 2.2 受众混杂

当前文档至少服务四类读者：

- 普通用户：想快速装起来并操作手机
- 部署用户：想用 Docker 或服务器长期运行
- 贡献者：想本地开发、跑 lint、提 PR
- 项目维护者：需要架构分析、版本说明、内部规划

文档结构需要显式区分这四类受众，否则任何单一入口都会越来越长。

## 3. 重构原则

1. 一个主题只保留一个“事实来源”文档，其他位置只做跳转或摘要。
2. 根目录 README 只做项目首页，不再承载完整手册。
3. 文档站只保留用户和开发者可消费的正式文档，内部规划文档不进主导航。
4. 中文为主文档时，英文文档要么保持最小但准确，要么明确声明为精简版，不能看起来完整但事实过时。
5. 下载链接、版本号、安装命令这类高漂移信息尽量减少手写散落。

## 4. 目标结构

### 4.1 仓库根目录

建议保留以下入口：

- `README.md`
  - 项目定位
  - 3 条读者路径入口
  - 最短安装方式
  - 核心特性和截图
  - 跳转到文档站、贡献指南、发行页
- `README_EN.md`
  - 精简英文版
  - 只保留项目介绍、快速安装、文档站入口、贡献入口
  - 明确说明完整中文文档在文档站
- `CONTRIBUTING.md`
  - 仅保留贡献者需要的内容
  - 本地开发、提交流程、测试和 PR 要求

### 4.2 文档站

建议将文档站重组为以下顶层结构：

- 开始使用
  - 选择安装方式
  - 首次运行
  - 模型配置
  - 设备连接
- 使用指南
  - 界面总览
  - AI 模式
  - Workflow
  - 多设备
  - 手动控制
  - 历史记录
  - 定时任务
  - 日志
- 部署
  - Docker
  - 服务器部署
  - 桌面版说明
- 开发者
  - 本地开发
  - 项目结构
  - 构建和发布
  - MCP / API 集成说明
- 参考
  - 配置项
  - 升级指南
  - Release Notes
  - FAQ
- 问题排查
  - 常见问题
  - ADB
  - 模型服务

### 4.3 内部文档

以下内容不建议放在正式用户导航中：

- 重构方案
- 架构深度分析
- 技术 TODO
- 版本过程记录

建议统一放在 `docs/internal/`，作为仓库内维护文档，不进入 Docusaurus sidebar。

## 5. 页面迁移映射

### 5.1 建议保留并增强

- `docs/docs/getting-started/install.md`
- `docs/docs/getting-started/first-run.md`
- `docs/docs/getting-started/model-config.md`
- `docs/docs/getting-started/device-connection.md`
- `docs/docs/deployment/docker.md`
- `docs/docs/deployment/server.md`
- `docs/docs/deployment/desktop.md`
- `docs/docs/troubleshooting/*`
- `docs/docs/faq.md`

### 5.2 建议合并

- `docs/docs/quick-start.md`
  - 合并进 `getting-started/*`
  - 不再单独保留第二套“快速开始”
- `docs/docs/installation.md`
  - 合并进“选择安装方式”
- `docs/docs/configuration.md`
  - 合并进“模型配置”
- `docs/docs/development.md`
  - 移入“开发者 / 本地开发”
- `docs/docs/deployment.md`
  - 拆分到 `deployment/docker.md`、`deployment/server.md`、`deployment/desktop.md`
- `docs/docs/upgrade.md`
  - 移入“参考 / 升级指南”

### 5.3 建议重定位

- `docs/docs/layered_agent_analysis.md`
  - 从用户文档中移出
  - 默认迁移到 `docs/internal/architecture/`
- `docs/docs/release-notes-v1.5.md`
  - 移入 `docs/docs/reference/release-notes/v1.5.md`
- `docs/docs/user-guide/*`
  - 归入“使用指南”
- `docs/docs/features/*`
  - 如果内容面向终端用户，可并入“使用指南”的具体章节

## 6. 内容职责划分

建议建立一张“唯一事实来源”表：

| 主题 | 唯一事实来源 | 其他位置写法 |
|------|--------------|--------------|
| 下载链接 | GitHub Releases 页面 | README 和文档站只放跳转，不重复列版本 |
| 安装命令 | 文档站“开始使用” | README 只保留最短命令 |
| Docker 部署 | 文档站“部署 / Docker” | README 只给摘要和跳转 |
| 本地开发 | `CONTRIBUTING.md` | 文档站“开发者”只保留概览并跳转 |
| 配置字段说明 | 文档站“模型配置” | README 不展开 |
| 架构分析 | 开发者文档或内部文档 | 用户文档只给一句话链接 |
| 发布变更 | Release Notes | README 不堆历史版本内容 |

## 7. README 重写建议

### 7.1 新版 README 建议结构

建议控制在 200 到 300 行内：

1. 项目一句话说明
2. 核心特性 5 到 7 条
3. 选择你的路径
   - 普通用户快速开始
   - Docker / 服务器部署
   - 贡献代码
4. 最短安装命令
5. 一张主界面截图
6. 文档站入口
7. 社区与贡献入口

### 7.2 README 中不建议继续保留的内容

- 大段 FAQ
- 详细 MCP 配置示例
- 大量 Docker 细节
- 完整贡献指南
- 大段版本升级说明
- 架构深潜内容

这些都应移出到文档站或专门文档。

## 8. 英文文档策略

当前更适合采用“精简但准确”的策略，而不是继续维持一份看似完整、实际易过时的英文 README。

建议：

- `README_EN.md` 只保留基础介绍、最短安装方式、文档站入口和贡献入口
- 明确说明完整文档以中文为主，英文内容会优先覆盖入门路径
- 下载版本、命令示例、仓库地址必须与中文文档保持一致

## 9. 文档维护机制

### 9.1 发布前检查项

每次发布至少检查以下文档事实：

- 下载链接版本号
- PyPI 安装命令
- Docker 镜像地址
- 仓库地址
- 文档站本地开发命令
- 不存在的文件引用

### 9.2 建议增加的轻量约束

- 在 PR 模板中加入“文档是否受影响”检查项
- 对 `README.md`、`README_EN.md`、`CONTRIBUTING.md`、`docs/docs` 做简单链接检查
- 将发行版本号相关信息集中在少数文件中维护

这里不强制新增复杂工具，先通过流程约束降低漂移。

### 9.3 兼容与所有权

- 为旧文档路径保留最小限度的跳转或替代页，避免外部链接和历史收藏直接失效
- README 中曾公开使用过的锚点和高频链接，在重构时优先保留或提供显式跳转
- 明确文档维护责任：
  - 产品和用户流程类文档由功能开发者同步更新
  - 发布相关文档由发版负责人更新
  - `README_EN.md` 只要求覆盖入门链路，不要求全文镜像中文 README

## 10. 分阶段实施计划

### Phase 1：止血

目标：先修事实错误，不改大结构。

- 统一版本号和下载链接
- 替换占位仓库地址
- 删除不存在的 `CLAUDE.md` 引用或替换为真实文档
- 将 `docs/README.md` 改为 `pnpm` 命令
- 清理 `frontend/README.md` 的默认模板内容

### Phase 2：收口入口

目标：让用户只看到一条清晰的阅读路径。

- 重写根目录 `README.md`
- 缩短 `README_EN.md`
- 确定唯一 Quick Start
- 清理 sidebar，移除或重定位孤儿页面

### Phase 3：重组文档站

目标：按受众重新分类内容。

- 建立“使用指南 / 部署 / 开发者 / 参考 / 问题排查”结构
- 合并重复页面
- 给每个章节补统一的前言和跳转

### Phase 4：建立维护机制

目标：降低后续再次失控的概率。

- 在发布流程中加入文档检查清单
- 补最小限度的链接检查
- 约定高漂移信息的唯一维护位置

## 11. 验收标准

完成重构后，应满足以下条件：

1. 新用户在 3 次点击内能找到安装、配置、设备连接三步入口。
2. 贡献者不需要翻根 README 即可完成本地开发。
3. 文档站 sidebar 中不存在大量“站内正式页面但导航不可达”的情况。
4. 中英文 README 不再出现事实级冲突。
5. 版本号、仓库地址、命令示例不再散落在多个互相矛盾的位置。

## 12. 推荐的下一步落地动作

如果要开始真正实施，我建议先按以下顺序做：

1. 修 `README_EN.md`、`CONTRIBUTING.md`、`docs/README.md` 中的事实错误和死链
2. 重写根目录 `README.md` 的目录和层级
3. 收敛 Docusaurus sidebar
4. 合并 `quick-start.md` 与 `getting-started/*`
5. 处理内部文档和架构分析文档的归位
