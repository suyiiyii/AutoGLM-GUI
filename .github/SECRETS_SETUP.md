# GitHub Secrets 配置说明

为了让集成测试能够正常运行，你需要在 GitHub 仓库中配置以下 Secrets。

## 📋 需要配置的 Secrets

| Secret 名称 | 说明 | 示例值 |
|------------|------|--------|
| `AUTOGLM_BASE_URL` | 大模型 API 的 Base URL | `https://open.bigmodel.cn/api/paas/v4` |
| `AUTOGLM_MODEL_NAME` | 使用的模型名称 | `autoglm-phone-9b` |
| `AUTOGLM_API_KEY` | API 密钥 | `sk-xxxxxxxxxxxxx` |

## 🔧 如何配置 Secrets

### 步骤 1：进入仓库设置

1. 打开你的 GitHub 仓库
2. 点击 **Settings** 标签
3. 在左侧菜单中找到 **Secrets and variables** → **Actions**

### 步骤 2：添加 Secrets

点击 **New repository secret** 按钮，依次添加以下 secrets：

#### 1. AUTOGLM_BASE_URL

```
Name: AUTOGLM_BASE_URL
Value: https://open.bigmodel.cn/api/paas/v4
```

或者如果你使用本地部署的模型：
```
Value: http://localhost:8080/v1
```

#### 2. AUTOGLM_MODEL_NAME

```
Name: AUTOGLM_MODEL_NAME
Value: autoglm-phone-9b
```

可选的模型名称：
- `autoglm-phone-9b` - 默认推荐
- `glm-4-flash` - 快速模型
- 其他兼容的模型

#### 3. AUTOGLM_API_KEY

```
Name: AUTOGLM_API_KEY
Value: sk-your-actual-api-key-here
```

⚠️ **注意**：不要在代码中暴露真实的 API Key！

### 步骤 3：验证配置

配置完成后：
1. 创建一个测试 PR
2. 查看 Actions 标签
3. 确认 "Integration Tests" workflow 运行成功

## 🧪 测试配置是否生效

可以手动触发 workflow 来测试：

1. 访问 **Actions** 标签
2. 选择 **Integration Tests** workflow
3. 点击 **Run workflow**
4. 选择分支并运行
5. 查看日志确认环境变量已正确传入

## 📝 配置完成后

配置完成后，workflow 会在以下情况下自动运行：

- ✅ 创建 Pull Request (目标分支为 main 或 dev)
- ✅ 推送到 main 或 dev 分支
- ✅ 手动触发 (workflow_dispatch)

## 🔒 安全说明

- ❌ **永远不要**在代码中硬编码 API Key
- ❌ **永远不要**在 PR 或 Issue 中暴露 Secrets
- ✅ **只在** GitHub Secrets 中配置敏感信息
- ✅ Secrets 对 fork 的仓库不可见（保护隐私）

## 🚨 如果不配置 Secrets 会怎样？

如果不配置 Secrets，集成测试会：
- ⚠️ 环境变量为空
- ⚠️ 测试可能使用默认配置或失败
- ⚠️ 完整的 Agent 测试无法运行

**建议**：即使暂时不运行完整测试，也应该配置一个占位符（如 `EMPTY`），避免测试失败。

## 📖 参考文档

- [GitHub Encrypted Secrets 官方文档](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AutoGLM-GUI 配置管理文档](../../CLAUDE.md)
