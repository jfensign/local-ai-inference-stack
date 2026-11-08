FROM ghcr.io/block/goose:latest

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg ffmpeg python3-full && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir yt-dlp demucs && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /home/goose/.npm /home/goose/.cache /home/goose/.local && \
    chown -R 1000:1000 /home/goose/.npm /home/goose/.cache /home/goose/.local /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
USER goose
