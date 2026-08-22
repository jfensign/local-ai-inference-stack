# Step 1: Reference local ninfer build stage
FROM ninfer:local AS ninfer-src

# Step 2: Build unified runtime
FROM ghcr.io/mostlygeek/llama-swap:unified-cuda

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir --break-system-packages openai-whisper

# Copy binaries, Python runtime, and libraries from ninfer-src
COPY --from=ninfer-src /usr/local /usr/local
