# =============================================================================
# Qwen3-TTS Docker Container for NVIDIA DGX Spark (ARM64 / GB10)
# =============================================================================
# Base: NVIDIA PyTorch NGC image (ARM64 compatible, CUDA ready)
# Model: Qwen3-TTS-12Hz-1.7B-CustomVoice (~4GB VRAM)
# API: FastAPI on port 9100
#
# Build:  docker build -t qwen3-tts .
# Run:    docker run --gpus all -p 9100:9100 --name qwen3-tts -d qwen3-tts
# =============================================================================

FROM nvcr.io/nvidia/pytorch:25.01-py3

LABEL maintainer="scakiral"
LABEL description="Qwen3-TTS API for language learning app"

# Environment
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models

WORKDIR /app

# Install system deps needed for torchaudio build + sox
RUN apt-get update && apt-get install -y --no-install-recommends \
    sox \
    libsox-dev \
    ffmpeg \
    git \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Step 1: Build torchaudio from source against the NGC torch (ABI compatible)
# Binary wheels from PyPI are ABI-incompatible with NGC's custom torch 2.6.0a0
# So we MUST compile from source to match the installed torch headers
RUN git clone --depth 1 --branch v2.6.0 https://github.com/pytorch/audio.git /tmp/torchaudio && \
    cd /tmp/torchaudio && \
    BUILD_SOX=1 pip install --no-cache-dir --no-deps --no-build-isolation . && \
    rm -rf /tmp/torchaudio

# Verify torchaudio loads correctly
RUN python -c "import torchaudio; print(f'torchaudio {torchaudio.__version__} loaded OK')"

# Step 2: Install deps that DON'T conflict with NGC pre-installed torch
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: Install qwen-tts WITHOUT its torch dependency (NGC torch is already installed)
RUN pip install --no-cache-dir --no-deps qwen-tts>=0.1.1

# Verify torch is still the NGC version
RUN python -c "import torch; v=torch.__version__; print(f'Torch: {v}'); assert '2.6.0' in v, f'Expected NGC torch 2.6.0, got {v}'"

# Copy application code
COPY app.py .
COPY download_models.py .

# Expose API port
EXPOSE 9100

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import requests; r=requests.get('http://localhost:9100/health'); r.raise_for_status()"

# Start the API server
CMD ["python", "app.py"]
