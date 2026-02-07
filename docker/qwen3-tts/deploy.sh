#!/bin/bash
# =============================================================================
# Deploy Qwen3-TTS on NVIDIA DGX Spark (spark-8144)
# =============================================================================
# This script:
# 1. Copies the Docker files to spark-8144
# 2. Builds the image on spark-8144 (ARM64)
# 3. Starts the container
#
# Usage: bash docker/qwen3-tts/deploy.sh
# =============================================================================

set -e

SPARK_HOST="spark-8144"
REMOTE_DIR="/home/scakiral/docker/qwen3-tts"
TTS_PORT=9100

echo "========================================"
echo "Deploying Qwen3-TTS to ${SPARK_HOST}"
echo "========================================"

# Step 1: Create remote directory
echo ""
echo "[1/5] Creating remote directory..."
ssh ${SPARK_HOST} "mkdir -p ${REMOTE_DIR}"

# Step 2: Copy files
echo "[2/5] Copying Docker files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scp "${SCRIPT_DIR}/Dockerfile" "${SPARK_HOST}:${REMOTE_DIR}/"
scp "${SCRIPT_DIR}/requirements.txt" "${SPARK_HOST}:${REMOTE_DIR}/"
scp "${SCRIPT_DIR}/app.py" "${SPARK_HOST}:${REMOTE_DIR}/"
scp "${SCRIPT_DIR}/download_models.py" "${SPARK_HOST}:${REMOTE_DIR}/"
scp "${SCRIPT_DIR}/docker-compose.yml" "${SPARK_HOST}:${REMOTE_DIR}/"
echo "   Files copied to ${REMOTE_DIR}"

# Step 3: Build image
echo ""
echo "[3/5] Building Docker image (this may take a few minutes)..."
ssh ${SPARK_HOST} "cd ${REMOTE_DIR} && docker build -t qwen3-tts ."

# Step 4: Stop old container if exists
echo ""
echo "[4/5] Stopping old container (if any)..."
ssh ${SPARK_HOST} "docker stop qwen3-tts 2>/dev/null || true && docker rm qwen3-tts 2>/dev/null || true"

# Step 5: Start new container
echo ""
echo "[5/5] Starting Qwen3-TTS container..."
ssh ${SPARK_HOST} "docker run -d \
  --gpus all \
  --name qwen3-tts \
  --shm-size=8g \
  -p ${TTS_PORT}:${TTS_PORT} \
  -v qwen3-tts-models:/app/models \
  -v qwen3-tts-hf-cache:/root/.cache/huggingface \
  -e TTS_MODEL_SIZE=1.7B \
  -e TTS_PORT=${TTS_PORT} \
  --restart unless-stopped \
  qwen3-tts"

echo ""
echo "========================================"
echo "Deployment complete!"
echo "========================================"
echo ""
echo "API URL: http://${SPARK_HOST}.local:${TTS_PORT}"
echo ""
echo "Wait ~2 minutes for model loading, then test:"
echo "  curl http://${SPARK_HOST}.local:${TTS_PORT}/health"
echo ""
echo "Monitor logs:"
echo "  ssh ${SPARK_HOST} 'docker logs -f qwen3-tts'"
echo ""
echo "Test TTS:"
echo "  curl -X POST http://${SPARK_HOST}.local:${TTS_PORT}/tts \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"Bonjour le monde\", \"language\": \"fr\"}' \\"
echo "    --output test.wav"
