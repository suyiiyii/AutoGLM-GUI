# Reverse Android Agent 使用指南

本指南说明如何使用 PR #336 引入的 **Reverse Android Agent** 模式，让 Android 手机通过 outbound WebSocket 反向连接到 AutoGLM-GUI 后端。

> 适用版本：`android-agent-unified` 分支及后续合并版本。
> 当前模式为 **Phase 1 MVP**：支持同一局域网/可达网络内的配对与基础命令，不等价于完整的公网远程控制。

---

## 前置条件

1. **AutoGLM-GUI 后端已启动**
   - 参考项目 README：`uv sync` 安装依赖后运行
   - 默认监听 `http://0.0.0.0:8080`
   - 确保运行后端的电脑与手机处于同一局域网，或手机能访问到该地址

2. **Android 手机**
   - Android 11+ 推荐
   - 已开启「开发者选项」并允许安装 APK（如果是本地编译安装）

---

## 第一步：编译并安装 Android Agent APK

```bash
cd android-agent
ANDROID_SDK_ROOT=/path/to/android-sdk \
ANDROID_HOME=/path/to/android-sdk \
./gradlew assembleDebug
```

编译完成后 APK 位于：

```
android-agent/app/build/outputs/apk/debug/app-debug.apk
```

使用 adb 安装到手机：

```bash
adb install android-agent/app/build/outputs/apk/debug/app-debug.apk
```

> CI 也提供 `Build Android Debug APK` 任务，可直接下载产物安装。

---

## 第二步：在 AutoGLM-GUI 网页端创建配对码

1. 打开 AutoGLM-GUI 网页（例如 `http://localhost:5173` 或 Vercel 预览地址）
2. 在左侧设备栏点击 **「添加 Android Agent」** / **「Add Android Agent」**
3. 切换到 **Android Agent** 标签页
4. 点击 **生成配对码**（Generate Pairing Code）
5. 记下弹出的 **6 位配对码**（例如 `AB3D9K`）
6. 同时记下后端地址，例如 `http://192.168.1.100:8080`

> 配对码有效期 10 分钟，且只能使用一次。

---

## 第三步：在 Android Agent App 中完成配对

1. 打开 Android Agent App
2. 按引导完成以下权限：
   - **前台服务**：允许应用保持后台运行
   - **无障碍服务**：点击「开启无障碍」，在系统设置中找到 `AutoGLM Agent` 并启用
   - **屏幕录制**：点击「授权屏幕录制」，按提示允许录制
3. 在「服务器地址」输入框填入后端地址，例如：
   ```
   http://192.168.1.100:8080
   ```
4. 在「配对码」输入框填入网页端生成的 6 位配对码
5. 点击 **「配对」**（Pair）

配对成功后，App 会显示：
- 状态变为 `paired` → `connecting` → `connected`
- 服务器地址、agent_id、pairing_id

---

## 第四步：在网页端使用设备

1. 回到 AutoGLM-GUI 网页
2. 左侧设备列表会出现一个 **Android Agent** 设备卡片
3. 点击选中该设备
4. 中间聊天面板可以输入任务，例如：
   - "打开微信"
   - "截图看看当前页面"
5. 右侧会实时显示手机屏幕截图（每 0.5 秒刷新）

---

## 第五步：首次连接验证（可选但推荐）

Android Agent App 底部有 **「运行首次验证」**（Run Validation）按钮，会依次检测：

1. 前台服务是否运行
2. 无障碍服务是否启用
3. 屏幕录制权限是否已授权
4. 反向连接是否已建立
5. 能否正常截图并识别当前应用

全部通过后，设备状态即为「可执行」。

---

## 常见问题

### 状态卡在 `paired` / `connecting`

- 检查手机网络是否能访问 `http://<pc-ip>:8080/api/health`
- 检查后端是否监听 `0.0.0.0`（默认是）
- 检查电脑防火墙是否放行 8080 端口
- 点击 App 里的 **「重新连接」** 或重新启动前台服务

### 状态变成 `stale`

- 表示心跳超时（默认 45 秒未收到心跳）
- 通常会在网络恢复后自动重连
- 若长时间未恢复，点击 **「重新连接」**

### 无障碍服务被系统自动关闭

- 部分国产 ROM 会杀后台并关闭无障碍服务
- 建议为 Android Agent App 设置「允许后台运行」「电池优化忽略」

### 配对码过期/失效

- 在网页端重新生成配对码
- 在 App 中重新输入新配对码

---

## 安全提示

- 当前 MVP 中，配对接口是开放的，**请勿把 AutoGLM-GUI 后端直接暴露到公网**
- 建议在受信任的家庭/办公局域网内使用
- 后续版本会增加配对创建认证、Token 加密存储等加固

---

## 命令支持情况（Phase 1）

| 命令 | 说明 |
|------|------|
| `screenshot` | 截图并返回 base64 |
| `tap` | 点击屏幕指定坐标 |
| `swipe` | 滑动 |
| `type_text` | 输入文本 |
| `current_app` | 获取当前前台应用包名 |

`back`、`home`、`launch_app` 等命令在 Phase 1 尚未实现，会在后续版本补齐。
