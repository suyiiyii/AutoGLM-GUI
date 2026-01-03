---
sidebar_position: 3
---

# Docker 部署

通过 Docker 快速启动后端服务与必要组件，便于一致性与隔离。

## 准备

- 安装 Docker 与 Docker Compose
- 获取仓库中的 `docker-compose.yml`

## 启动

```bash
docker compose up -d
```

## 配置

- 环境变量：在 Compose 文件或 `.env` 中设置
- 网络策略：按需开放端口并配置防火墙

## 常见问题

- 容器无法启动：检查镜像版本与日志
- 端口冲突：调整映射并释放占用

