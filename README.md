# local-ai-inference-stack

A Docker Compose stack for running a fully local AI inference environment on a
single-GPU machine: model serving behind one OpenAI-compatible endpoint
(**llama-swap**), agent tooling (**goose**, pi-agent-harness), a knowledge base
with RAG (**SiYuan** + **Qdrant** + **siyuan-ai-companion**), plus optional
**ComfyUI** and a Prometheus/Grafana telemetry stack.

The repo is intended as a **generic foundation**: clone it, run `./setup.sh`,
fill in `.env`, point the model registry at the models you pull, and start.
Machine-specific values (models, tokens, ports) all live in config files you
own — none are baked into the stack.

## Architecture

```
                        ┌────────────────────────────────────────┐
 OpenAI clients ──────► │ llama-swap  :8080                      │
 (goose, companion,    │  OpenAI-compatible proxy that launches  │
  pi-harness, curl)    │  & multiplexes per-model server procs   │
                        │  (ninfer-serve examples below)         │
                        └──────────────┬─────────────────────────┘
                                       │ spawns
                        ┌──────────────▼──────────┐
                        │ ninfer-serve (per model)│  ./models (read-only)
                        └─────────────────────────┘

 goose :3284 (agent server) ──► llama-swap (LLM backend)
 goose ──► qdrant :6333 (RAG, FastEmbed offline cache)
 goose ──► siyuan :6806 (notes; api token from .env)

 siyuan-ai-companion :8001 (host) ──► siyuan :6806, qdrant, llama-swap
 pi-agent-harness :8002 ──► llama-swap (OPENAI_BASE_URL)

 comfyui :8188 (optional)                    ./models (read-only)
 telemetry: prometheus :9090, grafana :3033, dcgm-exporter :9400
```

## Services

| Service | Port(s) | Purpose |
| --- | --- | --- |
| **llama-swap** | 8080 | Swap layer: one OpenAI endpoint over N model server processes, launched on demand from `llama-swap/config.yaml`. |
| **goose** | 3284 | Agent server (`serve --host 0.0.0.0`). LLM backend is llama-swap, not a public API. MCP extensions configured in `goose/config.yaml`. |
| **pi-agent-harness** | 8002 | Headless pi coding-agent container; also uses llama-swap as its OpenAI backend. |
| **hf-downloader** | — | Batch `hf` CLI for pulling model files into `./models` (writes as your host uid). |
| **siyuan** | 6806 | Notes/knowledge base. Port is fixed by the b3log image (override requires customizing the image). |
| **qdrant** | 6333, 6334 | Vector store: goose RAG collections + companion index. |
| **siyuan-ai-companion** | 8001 (host) → 8000 (container) | RAG proxy over SiYuan notes into Qdrant, answering via llama-swap. |
| **comfyui** *(optional)* | 8188 | Image generation; model dirs shared from `./models`. |
| **llama-swap-exporter** | — | Scrape-target exporter for llama-swap. |
| **prometheus / grafana / dcgm-exporter** *(optional)* | 9090 / 3033 / 9400 | Telemetry: llama-swap, qdrant, and GPU metrics. Grafana dashboards in `grafana/dashboards/`. |

## Prerequisites

- NVIDIA GPU + driver. Default model entries assume a **single high-VRAM GPU
  (≥ 24 GB)**; tune `--max-context` / KV settings and model selection to
  whatever you have.
- Docker Engine + Compose plugin + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
- A local **`ninfer:local`** Docker image shipping the ninfer runtime
  (`ninfer-serve`) under `/usr/local` — the root `Dockerfile` copies its
  `/usr/local` into the llama-swap image. Build it from your ninfer clone
  before the first `docker compose up` (the clone is **not** vendored here).
- (Optional) Hugging Face token for gated model repos.
- (Optional) craft CLI binaries on the host (`*-craft-cli` under
  `/usr/bin` or `CRAFT_BIN_SRC`) — staged into `goose/craft-bin/` by
  `setup.sh` for goose's shell tool.

## Quick start

```bash
git clone <your-repo-url> local-ai-inference-stack && cd local-ai-inference-stack
./setup.sh                 # prereqs, runtime dirs, .env, craft CLIs
$EDITOR .env               # at minimum: SiYuan API token (see below)
docker compose up -d       # builds llama-swap (needs ninfer:local) & starts
curl -s localhost:8080/health
```

On the **first boot only**: get the SiYuan API token from the UI
(*Settings → About → API Token* at `http://localhost:6806`), put it in
`.env` as `SIYUAN_TOKEN`, and `docker compose up -d` again so
`siyuan-ai-companion` and goose can connect (the companion cannot start
without it — see *Operational notes*).

Then, in the llama-swap UI / API, request one of the model ids defined in
`llama-swap/config.yaml` (e.g. `qwen3.8-27b`). The first request cold-starts
its server process (`healthCheckTimeout: 300` gives it room).

To verify a fresh clone end-to-end, run `scripts/e2e.sh` — it clones the repo
to a temp dir, runs `setup.sh`, brings the whole stack up on host ports
remapped +1000 (so it never clashes with a running stack), exercises the
SiYuan token flow, health-checks every service, and tears itself down on
success. `E2E_REPO=<url-or-path>` points it at a specific clone source.

### Adding models

1. Pull files into `./models` (owned by your host uid via `hf-downloader`):
   ```bash
   docker compose run --rm hf-downloader download <hf-repo> --local-dir ./models/<name>
   ```
2. Add a block to `llama-swap/config.yaml`: model id → server `cmd`
   (the shipped entries are working examples for NInfer `.ninfer` checkpoints).
3. Request that model id on `localhost:8080` — no restart of existing
   processes needed; llama-swap spawns the new one on demand.

## Configuration

- **`.env`** (git-ignored; copy from `.env.example`): host uid/gid, HF token,
  SiYuan access-auth code + API token, companion token, Reddit MCP creds.
  `docker compose` substitutes `${VAR}` from it into service envs.
  `setup.sh` generates the access-auth code if you leave it empty; the API
  token still has to come from the SiYuan UI (see below).
- **`llama-swap/config.yaml`**: model registry (see above).
- **`goose/config.yaml`**: provider block points at
  `OPENAI_HOST=http://llama-swap:8080` with model id `GOOSE_MODEL`;
  MCP extensions (qdrant RAG, siyuan, reddit, …) — most are disabled by
  default; enable + fill in what you use.
- **`comfyui/extra_model_paths.yaml`**: maps the shared `./models` tree into
  ComfyUI's model folders.

## Operational notes

- **GPU concurrency:** model `cmd`s use `--max-concurrency 1` to serialize on
  the single GPU (two long contexts double-allocating KV kills the process);
  `--pending-timeout-ms` keeps queued requests waiting instead of 500ing.
- **FastEmbed offline cache:** the qdrant RAG extension caches embedding
  weights at `/models/.hf/hub` with `HF_HUB_OFFLINE=1`. The cache root **must**
  be `/models/.hf/hub` (not `/models/.hf`) or the offline lookup misses.
  Pre-warm the cache with network access once, or place the hub files
  under `./models/.hf/hub`.
- **SiYuan auth is two-layered:** the *access auth code* gates the web UI;
  the *API token* gates the REST API and is what goose/companion send.
  Both go in `.env`. The API token is **generated by the kernel after first
  boot** — open the SiYuan UI (`http://localhost:6806`, password = the
  access-auth code) → *Settings → About → API Token*, copy it into
  `SIYUAN_TOKEN` in `.env`, then `docker compose up -d` again so goose and
  siyuan-ai-companion pick it up. Until then the companion will not start
  (it aborts startup if it cannot reach the SiYuan API).
- **`hf-downloader`** is a one-shot helper: it exits (code 2) right after
  boot. That is expected — use `docker compose run --rm hf-downloader …`
- **Craft CLIs:** bind mounts don't resolve symlinks, so goose gets **copies**
  in `goose/craft-bin/` (staged by `setup.sh`), mounted at `/opt/craft/bin`
  and prepended to `PATH` inside the container.
- **Host networking:** `goose` and `pi-agent-harness` reach the host via the
  `host.docker.internal` extra host; goose binds `0.0.0.0:3284`.
- **Optional services:** drop `comfyui`, `prometheus`, `grafana`,
  `dcgm-exporter`, and `llama-swap-exporter` (and their network lines) for a
  minimal inference-only stack.

## Security

- All credentials come from `.env` (git-ignored). Never commit tokens,
  client secrets, or refresh tokens — the tracked configs contain only
  placeholders.
- The companion and pi-harness bind published ports for LAN use; front them
  with a reverse proxy or firewall rules if this box isn't isolated.