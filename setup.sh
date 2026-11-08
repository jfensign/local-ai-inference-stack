#!/usr/bin/env bash
# setup.sh — one-time prep for local-ai-inference-stack.
#
# What it does:
#   1. Checks prerequisites (docker, compose, nvidia toolkit)
#   2. Creates runtime directories with correct ownership
#   3. Creates .env from .env.example if missing
#   4. Stages craft CLI binaries into goose/craft-bin/ (optional)
#
# Usage: ./setup.sh
#   CRAFT_BIN_SRC=/path/to/bin  dir to copy *-cli binaries from
#                               (default: /usr/bin)
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Prerequisites -------------------------------------------------------
say "Checking prerequisites"
command -v docker >/dev/null 2>&1 || fail "docker not found"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin not found"

if docker info --format '{{.Driver}}' >/dev/null 2>&1; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1 \
      || warn "GPU visible but nvidia-container-toolkit may not be configured — GPU services will fail to start"
  else
    warn "No NVIDIA GPU detected (nvidia-smi) — llama-swap/comfyui/dcgm-exporter need a GPU"
  fi
else
  warn "docker daemon not reachable — start it and re-run"
fi

# llama-swap is built FROM a local ninfer:local image (root Dockerfile).
if ! docker image inspect ninfer:local >/dev/null 2>&1; then
  warn "image ninfer:local not found — the llama-swap build needs it (unified runtime with ninfer-serve under /usr/local)"
fi

# --- 2. Runtime directories -------------------------------------------------
say "Creating runtime directories"
for d in models workspace qdrant_data \
         goose/workspace goose/local-share goose/craft-bin \
         comfyui/storage-cache/dot-cache comfyui/storage-cache/dot-config \
         comfyui/storage-nodes/dot-local comfyui/storage-nodes/custom_nodes \
         comfyui/storage-models/hf-hub comfyui/storage-models/torch-hub \
         comfyui/storage-user/input comfyui/storage-user/output \
         comfyui/storage-user/user-profile comfyui/storage-user/user-scripts; do
  mkdir -p "$d"
done
# siyuan (PUID 1000) and hf-downloader (HOST_UID) need to write here
chmod -R a+rwX workspace models 2>/dev/null || true

# --- 3. .env ----------------------------------------------------------------
if [ -f .env ]; then
  say ".env exists — leaving it alone"
else
  say "Creating .env from .env.example"
  cp .env.example .env
fi
# SiYuan refuses to boot via Docker without an access authorization code
# (exactly 20 characters). Generate one if the .env left it empty.
auth_code=$(sed -n 's/^SIYUAN_ACCESS_AUTH_CODE=//p' .env | head -1)
if [ -z "$auth_code" ]; then
  # No `head -c` at the tail: head closing the pipe makes tr die mid-flush
  # and the captured length lands short of 20. Filter a 256-byte sample
  # (≈62 alnum expected) and slice in bash instead.
  while [ ${#auth_code} -lt 20 ]; do
    auth_code=$(head -c 256 /dev/urandom | LC_ALL=C tr -dc 'a-z0-9')
  done
  auth_code=${auth_code:0:20}
  sed -i "s/^SIYUAN_ACCESS_AUTH_CODE=.*/SIYUAN_ACCESS_AUTH_CODE=$auth_code/" .env
  say "Generated SIYUAN_ACCESS_AUTH_CODE in .env (SiYuan requires exactly 20 chars)"
fi
warn "check .env before 'docker compose up' (fill in SIYUAN_TOKEN from the SiYuan UI — Settings → About → API token — once it is running)"

# --- 4. Craft CLIs (optional) -----------------------------------------------
# goose mounts ./goose/craft-bin as /opt/craft/bin (bind mounts need real
# files, not symlinks — hence copies).
SRC="${CRAFT_BIN_SRC:-/usr/bin}"
found=0
for f in "$SRC"/*-craft-cli; do
  [ -e "$f" ] || continue
  cp -f "$f" goose/craft-bin/
  found=1
done
if [ "$found" -eq 1 ]; then
  say "Staged craft CLIs into goose/craft-bin/ (from $SRC)"
else
  warn "no *-craft-cli binaries found in $SRC — craft integrations will be unavailable to goose (optional)"
fi

# --- Summary -----------------------------------------------------------------
say "Setup complete."
echo "  Next steps:"
echo "    1. Fill in .env (SiYuan API token — see step 2 of the README)"
echo "    2. Pull models into ./models via hf-downloader (see README 'Adding models')"
echo "    3. docker compose up -d"
echo "    4. Verify: curl -s localhost:8080/health  (llama-swap)"
