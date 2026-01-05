# Remote Device 体系架构图

## 1. 整体架构���览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AutoGLM-GUI Phone Agent                            │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    phone_agent/ (第三方核心引擎)                      │  │
│  │                                                                       │  │
│  │  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐          │  │
│  │  │ PhoneAgent  │───▶│ ActionHandler│───▶│ DeviceFactory   │          │  │
│  │  │   (orch.)   │    │  (executor)  │    │  (global) ◀─────┼──replace  │  │
│  │  └─────────────┘    └──────────────┘    └─────────────────┘          │  │
│  │         ▲                                                │            │  │
│  │         │                                                │            │  │
│  │  ┌──────┴────────────────────────────────────────────────┘            │  │
│  │  │                                                              inject │  │
│  │  │  DeviceProtocolAdapter                                        │     │  │
│  │  │  - bridges DeviceProtocol → DeviceFactory                     │     │  │
│  │  │  - routes operations to concrete implementations              │     │  │
│  │  └──────────────────────────────────────────────────────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                 │                                           │
│                                 │ calls                                      │
│                                 ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              AutoGLM_GUI/device_protocol.py                          │  │
│  │                                                                       │  │
│  │  Protocol DeviceProtocol                                             │  │
│  │  ├── get_screenshot() -> Screenshot                                  │  │
│  │  ├── tap(x, y, delay)                                                │  │
│  │  ├── double_tap(x, y, delay)                                         │  │
│  │  ├── long_press(x, y, duration_ms, delay)                            │  │
│  │  ├── swipe(start_x, start_y, end_x, end_y, duration_ms, delay)       │  │
│  │  ├── type_text(text)                                                 │  │
│  │  ├── clear_text()                                                    │  │
│  │  ├── back(delay)                                                     │  │
│  │  ├── home(delay)                                                     │  │
│  │  ├── launch_app(app_name, delay) -> bool                             │  │
│  │  ├── get_current_app() -> str                                        │  │
│  │  ├── detect_and_set_adb_keyboard() -> str                            │  │
│  │  └── restore_keyboard(ime)                                           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                          │                                                 │
│                          │ implements                                      │
│          ┌───────────────┼───────────────┐                               │
│          ▼               ▼               ▼                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                      │
│  │  ADBDevice   │ │ RemoteDevice │ │  MockDevice  │                      │
│  │   (local)    │ │   (HTTP)     │ │   (test)     │                      │
│  └──────────────┘ └──────────────┘ └──────────────┘                      │
│         │               │               │                                  │
│  ┌──────┴───────┐ ┌────┴─────────┐ ┌──┴───────────────┐                  │
│  │ subprocess   │ │ httpx client│ │ state_machine    │                  │
│  │ adb commands │ │ POST/GET    │ │ tap/swipe/assert │                  │
│  └──────────────┘ └──────────────┘ └──────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Device Agent Server (Remote)                         │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Device Agent                              │  │
│  │                                                                       │  │
│  │  POST /device/{device_id}/tap      POST /device/{device_id}/swipe    │  │
│  │  POST /device/{device_id}/screenshot                                   │  │
│  │  GET  /device/{device_id}/current_app                                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                          │                                                 │
│                          │ routes to                                       │
│                          ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              DeviceProtocol Implementation (Server Side)              │  │
│  │                                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │  │
│  │  │  ADBDevice   │  │  Accessibility│  │  MockDevice  │               │  │
│  │  │  (Docker)    │  │   Service    │  │  (testing)   │               │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           │ ADB / Control
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Physical Devices                                      │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │  Android 1   │  │  Android 2   │  │ HarmonyOS    │                     │
│  │  (USB/WiFi)  │  │  (Remote)    │  │  (HDC)       │                     │
│  └──────────────┘  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 分层架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 1: Application Layer (phone_agent/)                                  │
│  ────────────────────────────────────────────────────────────────────────  │
│  • PhoneAgent: Orchestrates multi-step task execution                       │
│  • ActionHandler: Parses LLM output and executes actions                    │
│  • ModelClient: OpenAI-compatible API client for vision models             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ uses
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 2: Abstraction Layer (AutoGLM_GUI/)                                 │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DeviceProtocol (Interface)                                          │   │
│  │ • Defines uniform API for all device types                          │   │
│  │ • Enables swapping implementations without changing business logic   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DeviceProtocolAdapter (Bridge)                                      │   │
│  │ • Injects DeviceProtocol into phone_agent's DeviceFactory           │   │
│  │ • Converts between Protocol and Factory interfaces                  │   │
│  │ • Manages device_id routing                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ implements
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 3: Implementation Layer (devices/)                                   │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │   ADBDevice     │  │  RemoteDevice   │  │   MockDevice    │            │
│  │                 │  │                 │  │                 │            │
│  │ • Local ADB     │  │ • HTTP client   │  │ • State machine │            │
│  │ • subprocess    │  │ • REST API      │  │ • Test only     │            │
│  │ • USB/WiFi/mDNS │  │ • Remote agent  │  │ • No device req │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ uses
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 4: Transport Layer                                                   │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  ADB/HDC CLI    │  │  HTTP/REST      │  │  In-Memory      │            │
│  │                 │  │                 │  │                 │            │
│  │ • adb shell     │  │ • httpx         │  │ • State object  │            │
│  │ • hdc shell     │  │ • JSON payload  │  │ • Dict storage  │            │
│  │ • TCP/IP        │  │ • Status codes  │  │ • Assertions    │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ controls
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 5: Physical Device Layer                                             │
│  ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Android Phone  │  │  Android Emu    │  │  HarmonyOS      │            │
│  │  (USB/WiFi)     │  │  (Local)        │  │  (HDC)          │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. 数据流图

```
User Task Execution Flow:
─────────────────────────

1. User Request
   │
   ├─ "打开美团给小明发消息"
   │
   ▼
2. PhoneAgent.run(task)
   │
   ├─ Loop until task complete
   │  │
   │  ├─[Step N]
   │  │
   │  ├─ screenshot = device.get_screenshot()
   │  │  │
   │  │  ├─ DeviceFactory.get_screenshot(device_id)
   │  │  │  │
   │  │  │  ├─ DeviceProtocolAdapter.get_screenshot(device_id)
   │  │  │  │  │
   │  │  │  │  └─ RemoteDevice.get_screenshot()
   │  │  │  │     │
   │  │  │  │     └─ HTTP POST /device/{id}/screenshot
   │  │  │  │        │
   │  │  │  │        └─ Device Agent Server
   │  │  │  │           │
   │  │  │  │           └─ ADBDevice.get_screenshot()
   │  │  │  │              │
   │  │  │  │              └─ adb shell screencap -p
   │  │  │  │
   │  │  │  └─ Returns Screenshot(base64_data, width, height)
   │  │  │
   │  │  ├─ response = llm_api(screenshot + task_context)
   │  │  │
   │  │  └─ action = parse_action(response)
   │  │     │
   │  │     ├─ {action: "tap", x: 500, y: 1000}
   │  │  ┌─┘
   │  │  │
   │  └─ device.tap(500, 1000)
   │     │
   │     └─ [Same routing path]
   │        └─ adb shell input tap 500 1000
   │
   ▼
3. Task Complete → Return result
```

## 4. 设备连接类型

```
Connection Type Hierarchy:
──────────────────────────

DeviceConnection (Protocol)
    │
    ├─ USB Connection
    │  ├─ ADB over USB
    │  │  └─ device_id: "ABC123DEF456"
    │  │
    │  └─ HDC over USB
    │     └─ device_id: "FMR0223C13000649"
    │
    ├─ WiFi Connection
    │  ├─ ADB over WiFi
    │  │  ├─ device_id: "192.168.1.100:5555"
    │  │  └─ Setup: USB → tcpip 5555 → connect IP:5555
    │  │
    │  └─ HDC over WiFi
    │     ├─ device_id: "192.168.1.100:5555"
    │     └─ Setup: USB → tmode port 5555 → tconn IP:5555
    │
    └─ Remote Connection
       ├─ HTTP Remote Device
       │  ├─ base_url: "http://device-agent:8001"
       │  ├─ device_id: "phone_001"
       │  └─ Protocol: REST API
       │
       └─ Future: gRPC/WebSocket
          └─ Planned for streaming/video
```

## 5. 测试架构

```
Testing Infrastructure:
──────────────────────

┌─────────────────────────────────────────────────────────────────────────────┐
│                         Test Environment                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  pytest                                                              │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────┐     │   │
│  │  │  DeviceProtocolContext                                      │     │   │
│  │  │  - Temporarily injects MockDevice                          │     │   │
│  │  │  - Auto-restores original factory on exit                  │     │   │
│  │  └────────────────────────────────────────────────────────────┘     │   │
│  │                               │                                       │   │
│  │  ┌────────────────────────────────────────────────────────────┐     │   │
│  │  │  MockDevice                                                │     │   │
│  │  │  - All operations route to StateMachine                    │     │   │
│  │  │  - Validates tap coordinates in regions                    │     │   │
│  │  │  - Triggers state transitions on actions                   │     │   │
│  │  └────────────────────────────────────────────────────────────┘     │   │
│  │                               │                                       │   │
│  │  ┌────────────────────────────────────────────────────────────┐     │   │
│  │  │  StateMachine                                              │     │   │
│  │  │  ├── States: [home, message, chat, ...]                    │     │   │
│  │  │  ├── Screenshots: Per-state base64 images                  │     │   │
│  │  │  ├── Regions: Tappable areas for each state                │     │   │
│  │  │  └── Transitions: state → action → next_state              │     │   │
│  │  └────────────────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Test Flow:                                                                 │
│  1. Load scenario YAML (states + screenshots + expected actions)            │
│  2. Inject MockDevice with StateMachine                                     │
│  3. Run PhoneAgent with instruction                                         │
│  4. Assert: state transitions, tap coordinates, action sequence             │
│  5. No physical device required                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Remote Device Testing:
──────────────────────

┌──────────────────┐         HTTP          ┌──────────────────────────────┐
│  Test Client     │◄─────────────────────►│  Mock Agent Server          │
│  (pytest)        │     :8001/device/     │  (FastAPI in subprocess)    │
└──────────────────┘                       └──────────────────────────────┘
      │                                              │
      │ RemoteDevice                                │ Records
      │ ┌──────────────────────┐                   │ all
      │ │ POST /device/{id}/tap│                   │ commands
      │ └──────────────────────┘                   ▼
      │                                    ┌────────────────┐
      │                                    │ Command Log    │
      │                                    │ - tap(100,200) │
      │                                    │ - swipe(...)   │
      │                                    │ - back()       │
      │                                    └────────────────┘
                                                        │
                                                        │ Assert
                                                        ▼
                                              ┌────────────────┐
                                              │ Test           │
                                              │ Assertions     │
                                              │ - expect([...])│
                                              │ - assert_state │
                                              │ - assert_tap   │
                                              └────────────────┘
```

## 6. Docker 部署架构

```
Docker Deployment (feat #118):
────────────────────────────

┌─────────────────────────────────────────────────────────────────────────────┐
│  Host Machine (Developer Machine)                                           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  AutoGLM-GUI (Web App)                                              │   │
│  │  • FastAPI Server :8000                                             │   │
│  │  • React Frontend                                                   │   │
│  │  • PhoneAgent Engine                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   │ HTTP Client                             │
│                                   ▼                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Docker Network
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Docker Container: Device Agent                                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Device Agent Server                                        │   │
│  │  • Exposed port: 8001                                               │   │
│  │  • Endpoints: /device/{id}/{action}                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   │ ADB/HDC                                 │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Device Pool                                                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│  │  │  Android 1  │  │  Android 2  │  │  Android 3  │                 │   │
│  │  │  (USB)      │  │  (WiFi)     │  │  (Remote)   │                 │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Benefits:                                                                  │
│  • Isolated device environment                                              │
│  • Easy deployment to remote servers                                        │
│  • Scalable device pooling                                                  │
│  • No local ADB setup required                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 7. 组件交互序列图

```
Normal ADB Flow:
────────────────

PhoneAgent         DeviceFactory      ADBDevice          ADB CLI           Device
    │                   │                 │                  │                │
    │ get_screenshot()  │                 │                  │                │
    ├──────────────────▶│                 │                  │                │
    │                   │ get_screenshot()│                  │                │
    │                   ├────────────────▶│                  │                │
    │                   │                 │ screencap -p     │                │
    │                   │                 ├─────────────────▶│                │
    │                   │                 │                  │ [capture]      │
    │                   │                 │◀─────────────────┤ PNG data       │
    │                   │◀────────────────┤                  │                │
    │◀──────────────────┤                 │                  │                │
    │                                           │                           │
    │ tap(500, 1000)     │                 │                  │                │
    ├──────────────────▶│                 │                  │                │
    │                   │ tap(500, 1000)  │                  │                │
    │                   ├────────────────▶│                  │                │
    │                   │                 │ input tap 500 1000│               │
    │                   │                 ├─────────────────▶│                │
    │                   │                 │                  │ [execute tap]  │
    │◀──────────────────┤                 │                  │                │


Remote Device Flow:
───────────────────

PhoneAgent      DeviceFactory   ProtocolAdapter   RemoteDevice   HTTP Client   Agent Server    Physical Device
    │                 │                │                │              │              │                │
    │ get_screenshot() │                │                │              │              │                │
    ├────────────────▶│                │                │              │              │                │
    │                 │ get_screenshot()│                │              │              │                │
    │                 ├───────────────▶│                │              │              │                │
    │                 │                │ get_screenshot()│              │              │                │
    │                 │                ├───────────────▶│              │              │                │
    │                 │                │                │ POST /device/id/screenshot   │                │
    │                 │                │                ├─────────────▶│              │                │
    │                 │                │                │              │ route to     │                │
    │                 │                │                │              ├────────────▶│                │
    │                 │                │                │              │              │ get_screenshot()│
    │                 │                │                │              │              ├───────────────▶│
    │                 │                │                │              │              │               │ [capture]
    │                 │                │                │              │              │◀───────────────┤ PNG
    │                 │                │                │              │◀─────────────┤                │
    │                 │                │                │◀─────────────┤ JSON         │                │
    │                 │                │◀───────────────┤              │              │                │
    │                 │◀───────────────┤                │              │              │                │
    │◀────────────────┤                │                │              │              │                │


Mock Device Testing Flow:
─────────────────────────

pytest        DeviceFactory   MockDevice      StateMachine    Scenario File
  │                │               │               │                │
  │ inject()       │               │               │                │
  ├───────────────▶│               │               │                │
  │                │ set adapter   │               │                │
  │                ├──────────────▶│               │                │
  │                                │               │                │
  │ agent.run()    │               │               │                │
  ├───────────────▶│               │               │                │
  │                │ get_screenshot│               │                │
  │                ├──────────────▶│               │                │
  │                │               │ get_screenshot│                │
  │                │               ├──────────────▶│                │
  │                │               │               │ load state img │
  │                │               │               ├───────────────▶│
  │                │               │◀──────────────┤ base64 PNG     │
  │                │◀──────────────┤               │                │
  │◀───────────────┤               │               │                │
  │                                │               │                │
  │                │ tap(500,1000) │               │                │
  │                ├──────────────▶│               │                │
  │                │               │ handle_tap()  │                │
  │                │               ├──────────────▶│                │
  │                │               │               │ validate coord │
  │                │               │               │ transition     │
  │                │               │               ├───────────────▶│
  │                │               │◀──────────────┤ new state      │
  │                │◀──────────────┤               │                │
  │◀───────────────┤               │               │                │
  │                                │               │                │
  │ assert_state("message")        │               │                │
  ├───────────────────────────────▶│               │                │
  │                                │               │                │
```

## 8. 核心文件映射

```
File Structure:
───────────────

AutoGLM_GUI/
├── device_protocol.py              # Protocol interfaces
│   ├── Screenshot (dataclass)
│   ├── DeviceInfo (dataclass)
│   ├── DeviceProtocol (Protocol)
│   └── DeviceManagerProtocol (Protocol)
│
├── device_adapter.py                # Adapter to phone_agent
│   ├── DeviceProtocolAdapter
│   ├── inject_device_protocol()
│   ├── restore_device_factory()
│   └── DeviceProtocolContext
│
└── devices/
    ├── __init__.py                  # Public API exports
    ├── adb_device.py                # ADB implementation
    │   ├── ADBDevice
    │   └── ADBDeviceManager
    │
    ├── remote_device.py             # HTTP implementation
    │   ├── RemoteDevice
    │   └── RemoteDeviceManager
    │
    └── mock_device.py               # Testing implementation
        ├── MockDevice
        └── MockDeviceManager


phone_agent/ (Third-party - DO NOT MODIFY)
├── device_factory.py                # Global factory (replaceable)
│   ├── DeviceFactory
│   └── _device_factory (global)
│
└── adb/
    └── connection.py                # ADB connection management
        ├── ADBConnection
        └── ConnectionType (USB/WIFI/REMOTE)
```

## 9. 扩展点

```
Extension Points:
─────────────────

How to add a new device type:
──────────────────────────────

1. Implement DeviceProtocol
   ┌─────────────────────────────────────────────────────────────┐
   │ class MyDevice:                                             │
   │     def __init__(self, device_id: str, ...):               │
   │         ...                                                 │
   │                                                             │
   │     @property                                              │
   │     def device_id(self) -> str:                            │
   │         return self._device_id                             │
   │                                                             │
   │     def get_screenshot(self, timeout: int) -> Screenshot:  │
   │         # Your implementation                              │
   │                                                             │
   │     def tap(self, x: int, y: int, delay: float = None):    │
   │         # Your implementation                              │
   │                                                             │
   │     # ... implement all other methods                      │
   └─────────────────────────────────────────────────────────────┘

2. Create Device Manager (optional)
   ┌─────────────────────────────────────────────────────────────┐
   │ class MyDeviceManager:                                     │
   │     def list_devices(self) -> list[DeviceInfo]:            │
   │         ...                                                 │
   │                                                             │
   │     def get_device(self, device_id: str) -> MyDevice:      │
   │         ...                                                 │
   └─────────────────────────────────────────────────────────────┘

3. Export from devices/__init__.py
   ┌─────────────────────────────────────────────────────────────┐
   │ from AutoGLM_GUI.devices.my_device import MyDevice         │
   │                                                             │
   │ __all__ = [..., "MyDevice"]                                │
   └─────────────────────────────────────────────────────────────┘

4. Inject into phone_agent
   ┌─────────────────────────────────────────────────────────────┐
   │ from AutoGLM_GUI.device_adapter import inject_device_protocol│
   │                                                             │
   │ devices = {"phone_1": MyDevice("phone_1", ...)}           │
   │ inject_device_protocol(lambda did: devices[did])          │
   └─────────────────────────────────────────────────────────────┘

5. Use PhoneAgent normally
   ┌─────────────────────────────────────────────────────────────┐
   │ agent = PhoneAgent(...)                                    │
   │ agent.run("打开微信")  # Uses MyDevice internally         │
   └─────────────────────────────────────────────────────────────┘


Potential New Implementations:
───────────────────────────────

• AccessibilityServiceDevice
  └─ Android Accessibility Service (no ADB needed)

• iOSDevice
  └─ WebDriverAgent / XCUITest for iOS automation

• GRPCDevice
  └─ gRPC streaming for real-time bidirectional control

• WebSocketDevice
  └─ WebSocket for event-driven communication

• CloudDevicePool
  └─ Load balancer across multiple device agent servers
```

## 10. 关键设计模式

```
Design Patterns Used:
─────────────────────

1. Protocol Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ DeviceProtocol defines "WHAT" operations can be done        │
   │ Concrete classes define "HOW" to do them                   │
   │                                                             │
   │ Benefit: Swap implementations without changing business     │
   └─────────────────────────────────────────────────────────────┘

2. Adapter Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ DeviceProtocolAdapter bridges DeviceProtocol to            │
   │ phone_agent's DeviceFactory interface                      │
   │                                                             │
   │ Benefit: Non-invasive integration with third-party code     │
   └─────────────────────────────────────────────────────────────┘

3. Factory Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ DeviceManager creates and caches Device instances          │
   │                                                             │
   │ Benefit: Centralized device lifecycle management            │
   └─────────────────────────────────────────────────────────────┘

4. Singleton Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ _device_factory is a global singleton in phone_agent       │
   │                                                             │
   │ Benefit: Single point of device access                      │
   └─────────────────────────────────────────────────────────────┘

5. Context Manager Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ DeviceProtocolContext ensures proper cleanup                │
   │                                                             │
   │ Benefit: Automatic restoration in tests                     │
   └─────────────────────────────────────────────────────────────┘

6. Strategy Pattern
   ┌─────────────────────────────────────────────────────────────┐
   │ Different transport strategies (ADB/HTTP/In-Memory)         │
   │                                                             │
   │ Benefit: Runtime selection of optimal strategy              │
   └─────────────────────────────────────────────────────────────┘
```

---

## 总结

Remote Device 体系的核心价值：

1. **灵活性**: 统一接口，多种实现
2. **可扩展性**: 轻松添加新的设备类型
3. **可测试性**: MockDevice 实现无设备测试
4. **非侵入性**: 不修改 phone_agent 第三方代码
5. **分布式**: 支持远程设备池部署
