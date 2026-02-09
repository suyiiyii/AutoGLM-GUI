---
title: Docker 部署（高级用户）
---

如果你需要在服务器上长期运行，可以使用 Docker 方式部署。仓库根目录提供了 `docker-compose.yml` 示例。

## 适用场景

- 需要 7x24 小时运行
- 需要远程访问 Web 界面

## 基本说明

`docker-compose.yml` 中包含以下关键设置：

- 使用 `ghcr.io/suyiiyii/autoglm-gui:main` 镜像
- 使用 `host` 网络模式（便于 USB/mDNS 支持）
- 挂载配置目录与日志目录

