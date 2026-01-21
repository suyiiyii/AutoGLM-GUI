---
id: deployment
title: Docker 部署
---

## 🐳 Docker 部署

AutoGLM-GUI 支持 Docker 容器化部署，适合服务器端远程控制 Android 设备的场景。

### 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/suyiiyii/AutoGLM-GUI.git
cd AutoGLM-GUI

# 2. 创建环境变量文件
cat > .env << EOF
AUTOGLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AUTOGLM_MODEL_NAME=autoglm-phone
AUTOGLM_API_KEY=sk-your-api-key
EOF

# 3. 启动容器
docker-compose up -d

# 4. 访问 http://localhost:8000
```

### 手动构建

```bash
# 构建镜像
docker build -t autoglm-gui:latest .

# 运行容器 (Linux 推荐 host 网络)
docker run -d --network host \
  -e AUTOGLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4 \
  -e AUTOGLM_MODEL_NAME=autoglm-phone \
  -e AUTOGLM_API_KEY=sk-xxx \
  -v autoglm_config:/root/.config/autoglm \
  -v autoglm_logs:/app/logs \
  autoglm-gui:latest
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AUTOGLM_BASE_URL` | 模型 API 地址 | (必填) |
| `AUTOGLM_MODEL_NAME` | 模型名称 | `autoglm-phone` |
| `AUTOGLM_API_KEY` | API 密钥 | (必填) |

### 连接远程设备

Docker 容器中连接 Android 设备推荐使用 **WiFi 调试**：

1. 在 Android 设备上开启「开发者选项」→「无线调试」
2. 记录设备的 IP 地址和端口号
3. 在 Web 界面点击「添加无线设备」→ 输入 IP:端口 → 连接

> ⚠️ **注意**：二维码配对功能在 Docker bridge 网络中可能受限（依赖 mDNS 多播）。Linux 系统建议使用 `network_mode: host`。

### 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/api/health
```
