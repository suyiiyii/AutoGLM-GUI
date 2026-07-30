# MobileForge-compatible Qwen3-VL LoRA

This directory documents how to serve or reproduce a **MobileForge-protocol** Qwen3-VL-4B adapter with AutoGLM-GUI. The `mobileforge` agent converts the model's JSON `<tool_call>` output into the GUI's existing Android actions.

## What this PR includes

- The protocol adapter and GUI preset.
- A model-serving command and a small smoke test.
- Guidance for using an adapter trained on data you are permitted to use.

It deliberately excludes LoRA/merged checkpoint weights, screenshots, task data, credentials, and training logs. Those artifacts are both too large for source control and may contain private content. Publish model weights separately only after checking the base-model license, dataset permissions, and a privacy review.

## Pretrained LoRA adapter

A privacy-reviewed LoRA adapter is published separately from the source tree:

- [Qwen3-VL-4B MobileForge LoRA v1](https://github.com/YoungJulY0728/AutoGLM-GUI/releases/tag/mobileforge-qwen3-vl-4b-lora-v1)

The release removes local absolute paths and identity metadata and includes a
SHA-256 checksum. Raw screenshots, device identifiers, credentials, and logs
are not bundled with the adapter.

## Serve a local adapter

Install a Qwen3-VL-compatible vLLM build, then point the GUI's **MobileForge Agent** at an OpenAI-compatible endpoint. For example:

```bash
vllm serve /path/to/Qwen3-VL-4B-Instruct \
  --enable-lora --lora-modules mobileforge=/path/to/lora_adapter \
  --served-model-name qwen3-vl-4b-mobileforge
```

In the GUI configure the endpoint URL, model name `qwen3-vl-4b-mobileforge`, and select **MobileForge Agent**. This repository currently uses Android ADB transport. HarmonyOS/HDC transport requires a separate device backend and is not claimed by this adapter.

## Expected model response

```text
<thinking>The search box is visible.</thinking>
<tool_call>{"action":"click","coordinate":[500,220]}</tool_call>
```

Coordinates are normalized to 0–1000. Allowed actions are `click`, `long_press`, `swipe`, `type`, `open`, `system_button` (`back` or `home`), `wait`, `answer`, and `terminate`.
