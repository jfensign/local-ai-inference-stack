# siyuan-ai-companion — local patched image
#
# Base: firefox2100/siyuan-ai-companion:latest (the `testing` tag referenced
# in upstream docs does not exist on Docker Hub; verified via registry API).
#
# Patch: views/utils.py forward_request()
#   1. Drops hop-by-hop / body-descriptor headers (Content-Length, Host, ...)
#      inherited from the incoming request before forwarding. The RAG handler
#      rewrites the user message, so the client's stale Content-Length no
#      longer matches the forwarded body -> httpx/h11 LocalProtocolError
#      "Too much data for declared Content-Length" (the upstream 500).
#   2. Returns response.content (raw bytes) instead of response.text, so the
#      upstream Content-Length is never broken by charset re-encoding.
#   3. Non-stream forward timeout 30s -> 300s: llama-swap + ninfer-serve
#      prefill for long RAG prompts on a 27B model can exceed 30s.
#
# Patch: model/rag_driver.py add_blocks()
#   4. Batches the Qdrant upsert (1000 points per call). On a first boot,
#      update_index() pushes the whole note corpus in one upsert; with a
#      large corpus the JSON payload exceeds Qdrant's 32 MiB upload limit
#      (HTTP 400) -> LifespanFailureError -> restart loop. The rest of the
#      upstream file is unchanged.
#   5. Encodes the whole corpus in a single transformer.encode() call
#      instead of one call per block. The per-block version re-dispatches
#      the torch thread pool once per block; on a large first-boot corpus
#      (11,532 blocks) the encode kept the before_serving lifespan — and
#      with it /health and the 8000 bind — blocked for many hours of CPU
#      time before any point ever reached Qdrant.
#
# NOTE: the image ships the app in BOTH site-packages (the runtime import
# path, per container logs) and /app/siyuan-ai-companion/src (source tree).
# Both copies are overwritten so a `pip install -e /app/...` can't resurrect
# the upstream bug.
FROM firefox2100/siyuan-ai-companion:latest

COPY utils.py /usr/local/lib/python3.10/site-packages/siyuan_ai_companion/views/utils.py
COPY utils.py /app/siyuan-ai-companion/src/siyuan_ai_companion/views/utils.py
COPY rag_driver.py /usr/local/lib/python3.10/site-packages/siyuan_ai_companion/model/rag_driver.py
COPY rag_driver.py /app/siyuan-ai-companion/src/siyuan_ai_companion/model/rag_driver.py