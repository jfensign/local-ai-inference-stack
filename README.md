# Local LLM Inference Stack via Docker & Llama-Swap

A production-optimized local AI inference architecture running containerized backends on Linux with hardware acceleration. This setup utilizes `llama-swap` as a dynamic routing proxy over optimized `llama.cpp` (`llama-server`) engines to manage hot-swapping frontier-class dense and Mixture-of-Experts (MoE) models on demand.

## Overview

- **Routing & Model Management:** `llama-swap` (Dockerized)
- **Inference Engine:** `llama.cpp` / `llama-server` (C++ native execution via Docker)
- **Hardware Profile:** NVIDIA RTX 5090 (32GB VRAM) / Ubuntu Host / CUDA 13.2
- **API Standard:** OpenAI-compatible API endpoints serving local consumer integrations (e.g., Goose, Open WebUI)

## Hardware & Inference Optimizations

To maximize token throughput and context depth without compromising model intelligence, the following optimizations are applied directly via the configuration macros:

* **100% GPU Offloading:** `--n-gpu-layers 99` ensures execution happens entirely within VRAM, bypassing host CPU and PCIe bus latency bottlenecks.
* **8-Bit KV Cache Precision:** `--cache-type-k q8_0` and `--cache-type-v q8_0` preserve high-fidelity mathematical precision over massive context windows, preventing long-context hallucinations.
* **Parallel Prefill Ingestion:** `--batch-size 4096` and `--ubatch-size 4096` saturate the GPU's Tensor Cores during the prompt ingestion phase, drastically lowering Time-to-First-Token (TTFT).
* **Flash Attention:** `--flash-attn on` reduces attention matrix memory consumption during high-context execution.

---









## Services Architecture

The following services are orchestrated via Docker Compose to provide a complete inference and telemetry stack:

| Service | Purpose | Ports |
| :--- | :--- | :--- |
| **llama-swap** | Dynamic routing proxy for managing multiple `llama-server` instances and model hot-swapping. | `8088` |
| **qdrant** | High-performance vector database for RAG (Retrieval-Augmented Generation) workflows. | `6333` (REST), `6334` (gRPC) |
| **prometheus** | Time-series database for collecting and storing system and application metrics. | `9090` |
| **grafana** | Visualization platform for real-time telemetry dashboards and observability. | `3033` |
| **dcgm-exporter** | NVIDIA Data Center GPU Manager exporter for deep GPU telemetry (VRAM, thermals, etc.). | `9400` |
| **ninfer** | From-scratch C++/CUDA single-GPU inference engine (OpenAI/Anthropic-compatible serving, MTP speculative decoding, INT8 paged KV, 128k context, vision). | `8087` |

## NInfer Service

[ninfer](https://github.com/Neroued/ninfer) serves the registered `qwen3.8-27b/nvfp4` artifact on `:8087` with an OpenAI/Anthropic-compatible HTTP API (`--spec mtp --draft-tokens 3 --max-context 131072 --kv-dtype int8 --vision`).

- **Build:** `docker compose build ninfer` — builds from the local clone in `./ninfer` (its own git repo, not tracked here); requires an `sm_120a` GPU (RTX 5090) and CUDA 13.1+.
- **Artifact:** `/models/NInfer/qwen3_8_27b_nvfp4.ninfer` (host `~/models`, bind-mounted read-only).
- **Pinned source:** local commits `fa2c9b4` (Prometheus metrics export) + `275d504` (HTTP status normalization fix) on top of upstream `a05746a`. The pinned state lives in the `./ninfer` clone; a fresh checkout of the public upstream lacks the metrics commits.

## NInfer Metrics

`GET :8087/metrics` (unauthenticated, Prometheus text format 0.0.4) exposes engine runtime stats, device memory arenas, KV cache capacity, HTTP request counters and latency histograms (bounded route labels), and MTP speculative-decoding counters. Prometheus scrapes it via the `ninfer` job in `prometheus/prometheus.yml`, and the **"NInfer - Inference Engine"** Grafana dashboard (`:3033`) is auto-provisioned from `grafana/dashboards/ninfer.json`.

Dashboard queries are pinned to `job="ninfer"`: the existing `llama-swap-exporter` re-exposes the active model's metrics under the `llama-swap-metrics` job with `model`/`upstream` labels, so unfiltered queries would double-count.

## Model Downloading (hf-downloader)

**Convention: all model pulls from the Hugging Face Hub go through the `hf-downloader` container.** This is a hard prerequisite for `goose`, `llama-swap`, and `ninfer` — every one of them consumes artifacts from `${HOME}/models` bound read-only to `/models`, so a download only lands where consumers can see it if it goes through `hf-downloader`.

The service builds from `Dockerfile.hf-downloader` (huggingface_hub 1.x + `hf` CLI + Xet high-performance transfer) and writes into `${HOME}/models`. It runs as uid `1000:1000` so downloaded artifacts are owned by the store owner, not root.

```bash
# Pull a full repo (or a filtered file set) into the model store:
docker compose run --rm hf-downloader download <owner/repo> \
    --local-dir /models/<name> [--include "*.gguf"]

# Discover repos/files before pulling:
docker compose run --rm hf-downloader models ls --search <name>
docker compose run --rm hf-downloader repo files <owner/repo>
```

Notes:

- The CLI is **`hf`** — in huggingface_hub 1.x, `huggingface-cli` is a dead deprecation stub (exits 1).
- High-throughput transfer uses the bundled Xet engine (`HF_XET_HIGH_PERFORMANCE=1` set in compose); the legacy `HF_HUB_ENABLE_HF_TRANSFER` env is deprecated.
- Set `HF_TOKEN` in the environment for authenticated / gated repos: `HF_TOKEN=hf_... docker compose run --rm hf-downloader download ...`
- Do **not** download models on the host or into ad-hoc directories; consumers will not see them.
