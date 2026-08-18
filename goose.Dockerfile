# goose image for the llama-stack compose service.
#
# Base: official goose. Adds the toolchain required by the stdio MCP
# extensions declared in goose/config.yaml:
#   uv/uvx   -> mcp-server-time, mcp-server-qdrant
#   node/npx -> mcp-remote (goose docs)
#
# Node is 22 LTS via NodeSource: the distro nodejs (18.x) is too old for the
# undici stack that npx mcp-remote pulls ("ReferenceError: File is not
# defined" -> goosedocs extension silently disabled).
FROM ghcr.io/block/goose:latest

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /home/goose/.npm /home/goose/.cache /home/goose/.local && \
    chown -R 1000:1000 /home/goose/.npm /home/goose/.cache /home/goose/.local && \
    uv --version && uvx --version && node --version && npm --version

USER goose