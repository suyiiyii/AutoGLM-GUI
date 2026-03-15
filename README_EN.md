<div align="center">

<img src="https://github.com/user-attachments/assets/bbdaeb1c-b7f2-4a4b-a11a-34db4de0ba12" alt="autoglm-gui" width="130">

# AutoGLM-GUI

Full-stack GUI for AutoGLM Phone Agent, enabling AI-driven Android automation with USB/WiFi device control, workflows, and scheduling.

</div>

## Quick Start

```bash
# Install the package
pip install autoglm-gui

# Start the service (adjust `--base-url` to your model endpoint)
autoglm-gui --base-url http://localhost:8080/v1

# Alternatively, run the latest release without installation (requires `uv`)
uvx autoglm-gui --base-url http://localhost:8080/v1
```

All configuration happens in the Web UI once the server is running; no extra CLI flags are required.

## Key Capabilities

- Wireless QR-paired control for Android 11+ devices
- Multi-device chat/automation workflows with per-device isolation
- Cron-style scheduler plus Workflow macros for repeatable tasks
- scrcpy-based live preview plus direct tap/swipe controls
- Docker-native deployment for long-running servers

## Documentation & Support

- [Chinese documentation site](https://auto-glm-gui-docs.vercel.app/docs) provides step-by-step installation, deployment, and feature guides.
- Refer to [CONTRIBUTING.md](./CONTRIBUTING.md) for developer setup, testing, and PR expectations.
- Issues and roadmap live under [GitHub Issues](https://github.com/suyiiyii/AutoGLM-GUI/issues); mention `help wanted` or `good first issue` to find mentoring opportunities.

## Community

- Join the QQ group for real-time discussions: https://qm.qq.com/q/J5eAs9tn0W
- Follow release announcements via the [releases page](https://github.com/suyiiyii/AutoGLM-GUI/releases)

## License

Apache License 2.0
