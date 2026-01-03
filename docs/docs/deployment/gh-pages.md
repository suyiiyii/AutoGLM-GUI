---
sidebar_position: 2
---

# GitHub Pages 部署

使用 Docusaurus 的 `deploy` 脚本将文档站发布到 GitHub Pages。

## 前置条件

- 仓库已启用 Pages，并允许从 `gh-pages` 分支发布
- 配置 `GIT_USER` 或使用 `USE_SSH=true`

## 部署命令

```bash
USE_SSH=true pnpm deploy
# 或
GIT_USER=<your-username> pnpm deploy
```

## 路径与 baseUrl

- 若以项目路径托管（`/<repoName>/`），需将 `baseUrl` 设置为 `/<repoName>/`
- 同步检查导航与静态资源路径，避免 404

## 常见问题

- 无法推送：检查身份配置或仓库权限
- 静态资源 404：确认 `baseUrl` 与资源链接一致

