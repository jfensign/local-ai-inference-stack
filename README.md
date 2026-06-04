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








