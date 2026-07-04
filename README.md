# ai-image

ComfyUI-based local image app for FLUX.2 Klein 4B on consumer NVIDIA GPUs.

## What this repo contains

- `comfyui_app/` — the active app, workflow builders, resolver, and UI
- `Install.bat` — first-time setup
- `Launch.bat` — start ComfyUI and the Gradio UI
- `Update.bat` — in-place update without rebuilding the Python environment

The old Hugging Face diffusers app has been removed from the repository.

## Setup

Run `Install.bat` once on a new machine or when you want a fresh environment.

What it does:

1. Creates the local virtual environment if needed.
2. Installs the CUDA PyTorch stack.
3. Installs the ComfyUI helper dependencies.
4. Clones ComfyUI and the required custom nodes.
5. Resolves and downloads the model files into the ComfyUI model folders.

## Updating

Run `Update.bat` after code changes.

It updates in place:

1. `git pull`
2. `pip install -r requirements-comfyui.txt`
3. `python -m comfyui_app.installer`

`Update.bat` does **not** reinstall PyTorch or rebuild the virtual environment.

## Launch

Run `Launch.bat` and open the app at:

- http://127.0.0.1:7861

ComfyUI itself listens on `127.0.0.1:8188`.

## Model layout

The resolver writes into the standard ComfyUI folders:

- `ComfyUI/models/diffusion_models/`
- `ComfyUI/models/text_encoders/`
- `ComfyUI/models/vae/`
- `ComfyUI/models/upscale_models/`

## RTX 3070 / 8 GB default plan

| Area | Default | Why |
| --- | --- | --- |
| Diffusion | FLUX.2 Klein 4B fp8 | Small enough to fit on 8 GB with ComfyUI offload. |
| Text encoder | Qwen 3 4B fp4 | Lower VRAM than fp16/bf16. |
| VAE | FLUX.2 small decoder | Best default fit for the app's edit flow. |
| Decode | Tiled by default on low-memory tiers | Helps keep 8 GB cards from spiking. |
| Launch flags | `--fast fp16_accumulation --reserve-vram 0.8 --fast-disk` | Ampere-friendly speed and safer Windows headroom. |

Why this stack:

- The RTX 3070 is Ampere, so fp8 is mainly a VRAM win rather than a compute win.
- The small decoder VAE keeps the edit pipeline compact.
- ComfyUI's offload model works well for the 8 GB target.

Sources:

- https://docs.comfy.org/
- https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- https://huggingface.co/black-forest-labs/FLUX.2-small-decoder

## Optional speedups

- **SageAttention 2** is preferred and is auto-used via `--use-sage-attention` when available.
- **Nunchaku INT4** is experimental but can be much faster. Use the `tonera/FLUX.2-klein-4B-Nunchaku` INT4 checkpoint and the experimental installer path if you want to try it.
- **torch.compile** is available in the UI. It can help after warmup, but the first run is slower and resolution changes recompile.

## MrFlow staged sampling (experimental)

MrFlow is a staged-sampling acceleration path inspired by https://github.com/Xingyu-Zheng/MrFlow and https://arxiv.org/abs/2607.01642.

In this app it keeps the same FLUX.2 Klein loaders and defaults, but runs:

1. a low-resolution first pass,
2. VAE decode,
3. 2x upscaling with a Real-ESRGAN model,
4. VAE re-encode,
5. a short high-resolution refinement pass.

Defaults:

- stage 1: 4 steps
- refine: 1 step
- refine denoise: 0.25
- low-res size: 512×512 for a 1024×1024 target

Notes:

- It works with the default FLUX.2 small-decoder VAE.
- It is experimental and can drift more on edits than a direct full-resolution edit.
- It is off by default.

The app auto-downloads `RealESRGAN_x2plus.pth` into `ComfyUI/models/upscale_models/` during the normal model refresh.

## Working with the resolver

The app resolves models from Hugging Face and skips files that are already present locally. That makes normal updates fast after the first run.

## ComfyUI references

- https://github.com/comfyanonymous/ComfyUI
- https://docs.comfy.org/development/comfyui-server/comms_overview
- https://docs.comfy.org/development/core-concepts/models
