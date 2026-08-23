# Local LLM Inference Stack via Docker & Llama-Swap

A production-optimized local AI inference architecture running containerized backends on Linux with hardware acceleration. `llama-swap` acts as the unified inference entrypoint: it routes OpenAI-compatible traffic to `ninfer-serve` subprocesses that it spawns and hot-swaps on demand over `.ninfer` model artifacts.

## Overview

- **Routing & Model Management:** `llama-swap` (Dockerized) — OpenAI-compatible proxy, model hot-swap with TTL, health checks
- **Inference Engine:** `ninfer-serve` ([ninfer](https://github.com/Neroued/ninfer)) — from-scratch C++/CUDA single-GPU engine, MTP speculative decoding, INT8 paged KV cache, 131k context, vision; runs as a **subprocess managed by llama-swap** (no standalone service)
- **Agent Frontend:** [goose](https://github.com/block/goose) — `goose serve` on `:3284`, OpenAI provider pointed at llama-swap
- **Hardware Profile:** NVIDIA RTX 5090 (32GB VRAM) / Ubuntu Host / CUDA 13.x
- **API Standard:** OpenAI-compatible API (`llama-swap:8088`) serving local integrations (goose, any OpenAI client)

## Hardware & Inference Optimizations

Applied per model in `llama-swap/config.yaml` (each entry spawns its own `ninfer-serve` subprocess):

* **MTP Speculative Decoding:** `--spec mtp --draft-tokens 3 --lm-head-draft` — the model's native multi-token-prediction head drafts 3 tokens per step, verified in a single pass
* **8-Bit KV Cache Precision:** `--kv-dtype int8 --kv-capacity auto` — halves KV memory vs fp16, preserving long-context fidelity
* **131k Context Window:** `--max-context 131072`
* **Vision:** `--vision` flag enables the multimodal encoder
* **100% GPU:** single-GPU engine on the RTX 5090; `CUDA_DEVICE_MAX_CONNECTIONS=1` set in compose

## Services Architecture

Orchestrated via `docker-compose.yml`; all model consumers bind the project model store `./models` read-only at `/models`:

| Service | Purpose | Ports |
| :--- | :--- | :--- |
| **llama-swap** | Unified inference entrypoint: OpenAI-compatible proxy over `ninfer-serve` subprocesses, model hot-swap, per-model lifecycle. | `8088` |
| **goose** | Block's agent CLI in long-running server mode (`goose serve`); OpenAI provider → llama-swap; MCP extensions (developer, todo, skills, goosedocs, qdrant_rag, playwright, reddit). | `3284` |
| **qdrant** | High-performance vector database for RAG (compliance collections + agent memory). | `6333` (REST), `6334` (gRPC) |
| **hf-downloader** | Single sanctioned Hugging Face model pull path (see below). Ephemeral — `docker compose run --rm`. | — |
| **llama-swap-exporter** | Scrapes llama-swap (`/metrics` re-exposes active model's `ninfer_*` series) and host; pushes to Prometheus. | `9101` |
| **prometheus** | Time-series DB for system/application metrics. | `9090` |
| **grafana** | Telemetry dashboards (auto-provisioned from `grafana/dashboards/`). | `3033` |
| **dcgm-exporter** | NVIDIA DCGM exporter for deep GPU telemetry (VRAM, thermals, clocks, XID). | `9400` |

### Models

Two `qwen3.8-27b` variants registered in `llama-swap/config.yaml`, served from the project store `./models/NInfer/`:

| Model id | Artifact |
| :--- | :--- |
| `qwen3.8-27b` | `qwen3_8_27b_nvfp4.ninfer` (~21GB) |
| `qwen3.8-27b-uncensored` | `qwen3_8_27b_uncensored.ninfer` (~18GB) |

`/v1/models`, `/running`, `/health` on `:8088` inspect the swap layer.

## Getting Started

### 1. Downloading models

All Hugging Face pulls go through the `hf-downloader` container (convention and details in [Model Downloading](#model-downloading-hf-downloader)). The CLI is `hf` (huggingface_hub 1.x):

```bash
# Discover a repo and inspect its contents
docker compose run --rm hf-downloader models ls --search <name>
docker compose run --rm hf-downloader repo files <owner/repo>

# Pull a whole repo into the shared model store
docker compose run --rm hf-downloader download <owner/repo> --local-dir /models/<name>

# Pull a single artifact (e.g. a .ninfer file)
docker compose run --rm hf-downloader download <owner/repo> <name>.ninfer --local-dir /models/NInfer

# Filtered pull (glob include)
docker compose run --rm hf-downloader download <owner/repo> --local-dir /models/<name> --include "*.safetensors"
```

Downloads land in the project store `./models` — immediately visible to every consumer container.

### 2. Adding a model

A model becomes serveable once its `.ninfer` artifact is in the shared store and it is registered in `llama-swap/config.yaml` (bind-mounted into the container; llama-swap loads it at startup and spawns one `ninfer-serve` subprocess per registered model).

```bash
# 1. Artifact in the store (see step 1)
ls ~/models/NInfer/<name>.ninfer

# 2. Register it — append under models: in llama-swap/config.yaml
```

```yaml
# llama-swap/config.yaml
models:
  qwen3.8-27b:
    cmd: "ninfer-serve /models/NInfer/qwen3_8_27b_nvfp4.ninfer --model-id qwen3.8-27b --host 127.0.0.1 --port ${PORT} --spec mtp --draft-tokens 3 --lm-head-draft --max-context 131072 --kv-capacity auto --kv-dtype int8 --vision"
  # new model entry:
  my-new-model:
    cmd: "ninfer-serve /models/NInfer/my_new_model.ninfer --model-id my-new-model --host 127.0.0.1 --port ${PORT} --spec mtp --draft-tokens 3 --lm-head-draft --max-context 131072 --kv-capacity auto --kv-dtype int8 --vision"
```

```bash
# 3. Reload (config is read at startup)
docker compose restart llama-swap

# 4. Verify
curl -s localhost:8088/v1/models      # both ids listed
curl -s localhost:8088/running        # new model: state=ready once loaded
```

Notes:

- `--model-id` is the id clients address the model by (use this in goose `GOOSE_MODEL` / OpenAI clients).
- `--port ${PORT}` is substituted by llama-swap per subprocess — keep it as-is.
- Drop flags to taste: `--spec mtp --draft-tokens 3 --lm-head-draft` (speculative decoding), `--kv-dtype int8 --kv-capacity auto` (KV cache), `--max-context` (context window), `--vision` (multimodal).
- Only one model loads to GPU at a time per concurrency of use — llama-swap hot-swaps the rest (`globalTTL: 600`).

### 3. Running the goose CLI

The `goose` container runs `goose serve` (REST/ACP API on `:3284`). Drive it either through the CLI inside the container or the API. The default provider/model come from `goose/config.yaml` (`openai` → `http://llama-swap:8080`, so runs consume the swap layer above).

```bash
# One-shot agent run (quiet mode: model response only on stdout)
docker compose exec goose goose run -t "Summarize the llama-swap architecture in 5 bullets" -q

# Interactive chat session (TUI; /help inside)
docker compose exec -it goose goose session

# Resume the most recent session (or a named one)
docker compose exec -it goose goose session --resume
docker compose exec -it goose goose session -n research --resume

# Pipe instructions / stdin
echo "List the registered models" | docker compose exec -i goose goose run -i - -q

# Override provider/model for a single run (e.g. host Ollama instead of llama-swap)
docker compose exec goose goose run -t "ping" -q \
  --provider ollama --model "hf.co/unsloth/Qwen3.6-27B-GGUF:UD-Q6_K_XL"

# Long-running autonomous session (detached; logs: docker logs <name>)
docker compose run -d --name research goose goose run -t "Investigate <topic> and write findings to /workspace/findings.md"
```

```bash
# REST surface (goose serve) — health check:
curl -s localhost:3284                # ok
```

Notes:

- Sessions persist as `.jsonl` under `./goose/workspace` (the container's `/workspace`); that's also where agent file work lands.
- `-s/--interactive` continues into interactive mode after initial input; `-r/--resume` keeps execution state across runs.
- Extensions (developer, todo, skills, goosedocs, qdrant_rag, playwright, reddit) are pre-wired in `goose/config.yaml`; ad-hoc stdio servers can be added per-run with `--with-extension "CMD ..."`.

## NInfer Runtime (Unified)

Since the shared-model-store consolidation there is **no standalone `ninfer` service**: the `Dockerfile` builds llama-swap's `unified-cuda` runtime with the `ninfer-serve` binary copied from a local `ninfer:local` build stage. llama-swap spawns one `ninfer-serve` subprocess per registered model on `127.0.0.1` inside the container.

- **Build:** `docker compose build llama-swap` — requires `ninfer:local` to be built first from the local clone in `./ninfer` (its own git repo, not tracked here); needs an `sm_120a` GPU (RTX 5090) and CUDA 13.1+.
- **Artifacts:** `/models/NInfer/*.ninfer` (project store `./models`, bind-mounted read-only).
- **Pinned source:** local commits `fa2c9b4` (Prometheus metrics export) + `275d504` (HTTP status normalization fix) on top of upstream `a05746a`. The pinned state lives in the `./ninfer` clone; a fresh checkout of the public upstream lacks the metrics commits.

## Telemetry

`ninfer-serve` exports Prometheus text-format `ninfer_*` metrics (engine request states, prefill/decode token counters, device memory arenas, KV capacity, HTTP counters/latency histograms, MTP speculative counters). llama-swap re-exposes the active model's series at its own `/metrics`, and `llama-swap-exporter` pushes them (plus host metrics) to Prometheus under **`job="llama-swap-metrics"`** with `model`/`upstream` labels. There is no separate `ninfer` scrape job — the engine has no externally routable port.

Dashboards (auto-provisioned from `grafana/dashboards/`, admin/admin on `:3033`):

| Dashboard | Scope |
| :--- | :--- |
| **llama-swap Full Observability** (`llama-swap.json`) | Consolidated stack view: swap/model health, engine tokens & throughput, GPU (DCGM), host. |
| **NInfer - Inference Engine** (`ninfer.json`) | Deep engine internals: KV cache, speculative acceptance, latency percentiles, HTTP surface. Pinned to `job="llama-swap-metrics"`. |
| **Qdrant** (`qdrant.json`) | Vector-DB observability. |

## goose

- **Image:** `goose.Dockerfile` — `ghcr.io/block/goose:latest` + Node 22 LTS (18.x lacks the undici globals `mcp-remote` requires) + uv/uvx for MCP servers.
- **Command:** `serve --host 0.0.0.0 --port 3284` — set explicitly in compose because the image's default CMD (`--help`) exits 0 and docker restart-loops.
- **Providers** (`goose/config.yaml`): OpenAI provider → `http://llama-swap:8080` (primary); Ollama on the host (secondary, via `host-gateway`).
- **RAG:** `qdrant_rag` extension embeds offline — FastEmbed cache at `/models/.hf/hub` + `HF_HUB_OFFLINE=1`; regulatory collections (CMMC, GDPR, HIPAA, ISO27001, SOC2) and the `memories` collection share the `fast-all-minilm-l6-v2` (384d) named vector.

## Model Downloading (hf-downloader)

**Convention: all model pulls from the Hugging Face Hub go through the `hf-downloader` container.** This is a hard prerequisite for `goose`, `llama-swap`, and the ninfer runtime — every one of them consumes artifacts from the project store `./models` bound read-only to `/models`, so a download only lands where consumers can see it if it goes through `hf-downloader`. See [Getting Started — Downloading models](#1-downloading-models) for the commands.

Implementation details:

- Builds from `Dockerfile.hf-downloader` (huggingface_hub 1.x + `hf` CLI + Xet high-performance transfer); writes into the project store `./models` as the host user (first-user uid `1000` by default; override with `HOST_UID`/`HOST_GID` in `.env`) so artifacts are host-manageable, not root-owned.
- The CLI is **`hf`** — in huggingface_hub 1.x, `huggingface-cli` is a dead deprecation stub (exits 1).
- High-throughput transfer uses the bundled Xet engine (`HF_XET_HIGH_PERFORMANCE=1` set in compose); the legacy `HF_HUB_ENABLE_HF_TRANSFER` env is deprecated.
- `HF_HOME=/models/.hf` keeps the xet/HTTP cache on the writable mount and reuses it across runs.
- Set `HF_TOKEN` in the environment for authenticated / gated repos: `HF_TOKEN=hf_... docker compose run --rm hf-downloader download ...`
- Do **not** download models on the host or into ad-hoc directories; consumers will not see them.
- **Store policy:** `./models` is the stack's single source of truth — consumers bind it read-only, `hf-downloader` is the sole writer. Host-side model dirs (e.g. `$HOME/models`, which still serves host tooling) are deliberately **not** mounted into the stack's containers: the stack stays relocatable (the repo dir contains everything it needs) and a download is always visible to consumers. The derived HF cache `.hf` (~150MB) is kept inside the store so offline RAG (`FASTEMBED_CACHE_PATH`) is turnkey on a fresh machine; it is disposable and re-downloadable.