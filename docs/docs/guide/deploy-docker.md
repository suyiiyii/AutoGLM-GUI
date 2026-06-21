---
title: Docker 部署
sidebar_label: Docker 部署
sidebar_position: 12
---

# 用 Docker 部署 AutoGLM-GUI

本指南介绍如何用 Docker 部署 AutoGLM-GUI，让它在一台常开的服务器上以守护方式 7x24 小时运行。这样即使关掉自己的电脑，服务器上的[定时任务](./schedule-task.md)也会照常执行。

## 选哪种安装方式

AutoGLM-GUI 有三种装法，按使用场景选：

- 桌面版：下载对应平台的安装包直接双击运行，内置全部依赖，适合在自己电脑上随手用。
- Python 包：`pip install autoglm-gui` 或 `uvx autoglm-gui` 启动，适合已有 Python 环境、想跟代码一起用的场景。
- Docker：拉取预构建镜像后台运行，适合部署到服务器做 7x24 自动化。

如果你的目标是「把后端放到一台常开机器上、配合定时任务无人值守地跑」，那就用 Docker，这也是本篇要讲的。如果只是在本机临时试用，用桌面版或 Python 包更省事。

镜像支持 `linux/amd64` 和 `linux/arm64` 两种架构，VPS、NAS、闲置的 x86 或 ARM 机器都能跑。

## 用 docker-compose 部署（推荐）

docker-compose 把网络模式、数据卷、重启策略都写在一个文件里，是最省心的方式。

先下载官方的 compose 文件：

```bash
curl -O https://raw.githubusercontent.com/suyiiyii/AutoGLM-GUI/main/docker-compose.yml
```

然后在同一目录下启动服务：

```bash
docker compose up -d
```

`-d` 表示后台运行。首次启动会自动拉取镜像 `ghcr.io/suyiiyii/autoglm-gui:main`，拉完即启动。

启动后在浏览器打开 `http://localhost:8000`，进入 Web 界面。如果你是通过服务器访问，把 `localhost` 换成服务器的 IP。

模型 API 不需要提前在命令行里配，直接在 Web 界面的设置页面填 base URL、模型名和 API Key 即可，详见[配置模型](./configure-model.md)。如果希望在启动时就预置好，可以编辑 `docker-compose.yml`，取消注释里面的 `environment` 部分，填入对应环境变量，变量含义见[环境变量参考](../reference/env-vars.md)。

## 用 docker run 部署

如果不想用 compose，也可以直接 `docker run`。推荐用 host 网络模式，并挂载两个数据卷：

```bash
docker run -d --network host \
  -v autoglm_config:/root/.config/autoglm \
  -v autoglm_logs:/app/logs \
  ghcr.io/suyiiyii/autoglm-gui:main
```

几个参数的作用：

- `--network host`：容器直接复用宿主机网络，便于 ADB 设备发现和二维码配对（原因见下文）。
- `-v autoglm_config:/root/.config/autoglm`：持久化配置和对话历史（`~/.config/autoglm/history/` 下每台设备一个 JSON 文件），容器重建后数据不丢。
- `-v autoglm_logs:/app/logs`：持久化日志和 trace 文件，方便事后排查。

同样访问 http://localhost:8000 进入界面配模型。镜像标签、端口修改、bridge 网络下的端口映射等更多选项，见 [Docker 参考](../reference/docker.md)。

## 连接远程设备：用 WiFi 调试

容器跑在服务器上，通常没法插 USB 数据线，所以推荐用 WiFi 无线调试来连设备：

1. 在 Android 设备上打开「开发者选项」→「无线调试」。
2. 记下设备显示的 IP 地址和端口号。
3. 在 Web 界面点「添加无线设备」，输入 `IP:端口` 后连接。

设备和服务器要能在网络上互通。完整的设备连接方式参见[连接设备](./connect-device.md)。

## 关于二维码配对与 host 网络

二维码配对（Android 11+）依赖 mDNS 多播来发现设备。在 Docker 的 bridge 网络里，多播报文通常出不去容器，配对会失败。

所以强烈建议用 `--network host` 模式运行（compose 文件里默认就是 host 网络）。这样容器和宿主机共用网络栈，mDNS 才能正常工作，二维码配对和设备发现才完整可用。

需要注意 host 网络模式只在 Linux 上生效；macOS 和 Windows 的 Docker 没有真正的 host 网络，此时请改用 bridge 网络加端口映射，并优先用 WiFi 调试连设备，具体配置见 [Docker 参考](../reference/docker.md)。

## 健康检查

服务起来后，可以用健康检查接口确认它是否正常：

```bash
curl http://localhost:8000/api/health
```

返回正常说明后端已就绪，可以开始连设备、配模型了。这个接口也适合放进监控脚本，定期探测服务存活。

## 下一步

服务跑起来之后，推荐继续看：

- [服务器部署](./deploy-server.md)：把服务长期稳定地放到服务器上运行的完整做法。
- [创建定时任务](./schedule-task.md)：配合定时任务实现 7x24 无人值守自动化。
