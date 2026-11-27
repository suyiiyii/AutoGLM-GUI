# MobileForge-compatible Qwen3-VL LoRA

This directory shows how to fine-tune and serve
`Qwen/Qwen3-VL-4B-Instruct` with MobileForge conversation data. The
`mobileforge` agent translates the model's `mobile_use` JSON tool calls into
AutoGLM-GUI actions.

The recipe is an experimental reference, not an official model release or
benchmark result.

## What this PR includes

- A MobileForge protocol adapter and GUI preset.
- A small LoRA SFT recipe for positive MobileForge action steps.
- Commands for serving either a LoRA adapter or a merged model.
- Offline parser and sanitized action-shape tests.

It deliberately excludes model weights, checkpoints, screenshots, raw task
data, credentials, device identifiers, network addresses, and training or
device logs.

## Pretrained LoRA adapter

A privacy-reviewed LoRA adapter is published separately from the source tree:

- [Qwen3-VL-4B MobileForge LoRA v1](https://github.com/YoungJulY0728/AutoGLM-GUI/releases/tag/mobileforge-qwen3-vl-4b-lora-v1)

The release removes local absolute paths and identity metadata and includes a
SHA-256 checksum. Review the base-model and dataset licenses before publishing
another adapter.

## Install optional training dependencies

Create a separate environment, install AutoGLM-GUI, then install:

```bash
pip install -r examples/mobileforge/requirements.txt
```

Install `bitsandbytes` separately when using `--use-4bit`. Install `vllm` in
the serving environment.

## Prepare data

Download or generate MobileForge training data following the
[MobileForge data documentation](https://github.com/kwai/MobileForge/blob/main/docs/data_release.md).
The JSON file must contain conversation records with an `is_positive` flag,
and image references must be relative to `--image-dir`.

Do not train on or publish screenshots containing personal information unless
you have reviewed and appropriately sanitized them.

## Train

The defaults use up to 2,000 positive samples, two epochs, LoRA rank 16, and
bf16 weights:

```bash
python examples/mobileforge/train_qwen3_vl_4b_lora.py \
  --data-path /path/to/mobileforge_grpo_image_paths.json \
  --image-dir /path/to/mobileforge_images \
  --output-dir /path/to/qwen3-vl-4b-mobileforge-lora
```

On smaller GPUs, add `--use-4bit`. The 4-bit path saves an adapter only because
merging a quantized training model is not reliable. The bf16 path saves both
`lora_adapter/` and a standalone `merged/` model.

## Serve

Serve a LoRA adapter directly:

```bash
vllm serve /path/to/Qwen3-VL-4B-Instruct \
  --enable-lora \
  --lora-modules mobileforge=/path/to/lora_adapter \
  --served-model-name qwen3-vl-4b-mobileforge
```

Or serve the merged model:

```bash
bash examples/mobileforge/serve_qwen3_vl_4b.sh \
  /path/to/qwen3-vl-4b-mobileforge-lora/merged
```

In the GUI, configure the endpoint URL and served model name, then select
**MobileForge Agent**.

## Expected model response

```text
<thinking>The search box is visible.</thinking>
<tool_call>{"name":"mobile_use","arguments":{"action":"click","coordinate":[500,220]}}</tool_call>
```

Coordinates are normalized to 0–1000. Supported actions are `click`,
`long_press`, `swipe`, `type`, `open`, `system_button` (`Back` or `Home`),
`wait`, `answer`, and `terminate`. For compatibility, the parser also accepts
the earlier flat JSON form used by the first version of this PR.

## Device trace privacy and transport compatibility

HDC or ADB screenshots, model responses, prompts, and runtime logs can contain
account details, messages, locations, device identifiers, and private network
addresses. Do not attach raw traces to an issue or pull request. Reduce a
failure to a synthetic protocol response without real task text, coordinates,
identifiers, paths, or network details.

The regression tests include only sanitized action shapes observed during
HarmonyOS 6 experiments. AutoGLM-GUI currently provides an Android ADB device
backend; this PR does not add or claim HarmonyOS/HDC transport support.
