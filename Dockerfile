FROM ghcr.io/mostlygeek/llama-swap:unified-cuda

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir --break-system-packages openai-whisper
