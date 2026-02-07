# Guide Docker GPU - PyTorch & NVIDIA

Ce guide explique comment créer et utiliser des containers Docker avec support GPU/CUDA sur le serveur spark.

## Sommaire

- [Prérequis](#prérequis)
- [Images de base NVIDIA NGC](#images-de-base-nvidia-ngc)
- [Créer un Dockerfile](#créer-un-dockerfile)
- [Build et Run](#build-et-run)
- [Accès GPU dans le container](#accès-gpu-dans-le-container)
- [Gestion de la VRAM](#gestion-de-la-vram)
- [Exemples complets](#exemples-complets)
- [Troubleshooting](#troubleshooting)

---

## Prérequis

### Sur le serveur spark-8144

- **NVIDIA Driver**: 580.95.05
- **CUDA**: 13.0
- **Docker**: avec nvidia-container-toolkit
- **GPU**: NVIDIA GB10 (Grace Blackwell, ARM64)

### Vérifier l'installation

```bash
# GPU accessible
nvidia-smi

# Docker avec GPU
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

---

## Images de base NVIDIA NGC

NVIDIA fournit des images Docker pré-configurées sur **NGC** (NVIDIA GPU Cloud):
- Registry: `nvcr.io`
- Catalogue: https://catalog.ngc.nvidia.com/

### Images PyTorch recommandées

| Image | Taille | Usage |
|-------|--------|-------|
| `nvcr.io/nvidia/pytorch:25.01-py3` | ~15GB | Dernière stable (Jan 2026) |
| `nvcr.io/nvidia/pytorch:24.12-py3` | ~14GB | Stable Déc 2024 |
| `nvcr.io/nvidia/pytorch:24.09-py3` | ~14GB | LTS |

### Autres images utiles

```bash
# PyTorch
nvcr.io/nvidia/pytorch:25.01-py3

# TensorFlow
nvcr.io/nvidia/tensorflow:25.01-tf2-py3

# CUDA de base (plus léger)
nvcr.io/nvidia/cuda:13.0-cudnn-devel-ubuntu24.04
nvcr.io/nvidia/cuda:12.6-cudnn-runtime-ubuntu22.04

# Triton (inference server)
nvcr.io/nvidia/tritonserver:25.01-py3

# NeMo (LLM training)
nvcr.io/nvidia/nemo:25.01
```

### Pull une image

```bash
# Login NGC (optionnel pour images publiques)
docker login nvcr.io
# Username: $oauthtoken
# Password: <ton API key NGC>

# Pull l'image
docker pull nvcr.io/nvidia/pytorch:25.01-py3
```

---

## Créer un Dockerfile

### Template de base

```dockerfile
# Base image NVIDIA PyTorch
FROM nvcr.io/nvidia/pytorch:25.01-py3

# Metadata
LABEL maintainer="ton@email.com"
LABEL description="Mon projet ML avec GPU"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

# Répertoire de travail
WORKDIR /app

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Port exposé (si API)
EXPOSE 8000

# Commande par défaut
CMD ["python", "main.py"]
```

### Dockerfile optimisé (multi-stage)

```dockerfile
# ============================================
# Stage 1: Builder
# ============================================
FROM nvcr.io/nvidia/pytorch:25.01-py3 AS builder

WORKDIR /build

# Installer les dépendances de build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# ============================================
# Stage 2: Runtime
# ============================================
FROM nvcr.io/nvidia/pytorch:25.01-py3

# Copier les packages installés
COPY --from=builder /install /usr/local/lib/python3.12/dist-packages/

# Configuration
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app
COPY . .

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s \
  CMD python -c "import torch; assert torch.cuda.is_available()"

EXPOSE 8000
CMD ["python", "main.py"]
```

### Dockerfile pour service vLLM

```dockerfile
FROM nvcr.io/nvidia/pytorch:25.01-py3

# Installer vLLM
RUN pip install vllm

# Variables pour GPU
ENV CUDA_VISIBLE_DEVICES=0
ENV VLLM_USE_V1=1

WORKDIR /app

# Exposer le port API
EXPOSE 8000

# Lancer vLLM serve
CMD ["python", "-m", "vllm.entrypoints.openai.api_server", \
     "--model", "meta-llama/Llama-3.1-8B-Instruct", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
```

---

## Build et Run

### Build l'image

```bash
# Build simple
docker build -t mon-projet-gpu .

# Build avec cache désactivé
docker build --no-cache -t mon-projet-gpu .

# Build pour architecture spécifique (ARM64 sur spark)
docker build --platform linux/arm64 -t mon-projet-gpu .
```

### Run avec GPU

```bash
# Accès à TOUS les GPUs
docker run --gpus all mon-projet-gpu

# Accès à un GPU spécifique
docker run --gpus '"device=0"' mon-projet-gpu

# Accès à plusieurs GPUs
docker run --gpus '"device=0,1"' mon-projet-gpu

# Limiter la mémoire GPU (via variable d'env)
docker run --gpus all \
  -e PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
  mon-projet-gpu
```

### Options Docker importantes

```bash
docker run \
  --gpus all \                          # Accès GPU
  --shm-size=16g \                      # Shared memory (important pour PyTorch DataLoader)
  --ulimit memlock=-1 \                 # Pas de limite mémoire lockée
  --ulimit stack=67108864 \             # Stack size
  -v /data:/data \                      # Monter un volume
  -p 8000:8000 \                        # Port mapping
  --name mon-container \                # Nom du container
  -d \                                  # Detached mode
  mon-projet-gpu
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  ml-service:
    build: .
    image: mon-projet-gpu
    container_name: ml-service
    
    # GPU access
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all  # ou "1" pour un seul GPU
              capabilities: [gpu]
    
    # Resources
    shm_size: '16gb'
    ulimits:
      memlock: -1
      stack: 67108864
    
    # Environment
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
    
    # Ports
    ports:
      - "8000:8000"
    
    # Volumes
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    
    # Restart policy
    restart: unless-stopped
```

---

## Accès GPU dans le container

### Vérifier le GPU dans Python

```python
import torch

# GPU disponible ?
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU count: {torch.cuda.device_count()}")
print(f"GPU name: {torch.cuda.get_device_name(0)}")
print(f"CUDA version: {torch.version.cuda}")

# Mémoire GPU
print(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
print(f"Allocated: {torch.cuda.memory_allocated(0) / 1e9:.1f} GB")
print(f"Cached: {torch.cuda.memory_reserved(0) / 1e9:.1f} GB")
```

### Variables d'environnement GPU

```bash
# Sélectionner les GPUs visibles
CUDA_VISIBLE_DEVICES=0,1

# Toutes les capabilities
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

# Désactiver un GPU
CUDA_VISIBLE_DEVICES=""

# Configuration allocateur PyTorch
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512,expandable_segments:True
```

---

## Gestion de la VRAM

### Voir la VRAM utilisée

```bash
# Depuis l'hôte
nvidia-smi

# Depuis le container
python -c "import torch; print(f'{torch.cuda.memory_allocated()/1e9:.2f} GB used')"

# Monitoring continu
watch -n 1 nvidia-smi
```

### Libérer la VRAM dans Python

```python
import torch
import gc

# Vider le cache CUDA
torch.cuda.empty_cache()

# Garbage collection
gc.collect()

# Reset des stats mémoire
torch.cuda.reset_peak_memory_stats()
torch.cuda.reset_accumulated_memory_stats()
```

### Limiter la VRAM utilisée

```python
# Méthode 1: Fraction de la VRAM
torch.cuda.set_per_process_memory_fraction(0.5, device=0)  # 50% max

# Méthode 2: Via variable d'environnement (avant import torch)
import os
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:512'
```

### Décharger un modèle

```python
# Supprimer le modèle
del model

# Forcer la libération
import gc
gc.collect()
torch.cuda.empty_cache()

# Vérifier
print(f"VRAM after unload: {torch.cuda.memory_allocated()/1e9:.2f} GB")
```

### Mixed Precision (économise VRAM)

```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

with autocast():
    outputs = model(inputs)
    loss = criterion(outputs, targets)

scaler.scale(loss).backward()
scaler.step(optimizer)
scaler.update()
```

---

## Exemples complets

### Exemple 1: API ML simple

**Dockerfile**:
```dockerfile
FROM nvcr.io/nvidia/pytorch:25.01-py3

RUN pip install fastapi uvicorn transformers

WORKDIR /app
COPY app.py .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**app.py**:
```python
from fastapi import FastAPI
import torch
from transformers import pipeline

app = FastAPI()
generator = None

@app.on_event("startup")
async def load_model():
    global generator
    generator = pipeline("text-generation", model="gpt2", device=0)

@app.post("/generate")
async def generate(prompt: str, max_length: int = 100):
    result = generator(prompt, max_length=max_length)
    return {"result": result[0]["generated_text"]}

@app.get("/gpu-status")
async def gpu_status():
    return {
        "cuda_available": torch.cuda.is_available(),
        "vram_used_gb": torch.cuda.memory_allocated() / 1e9,
        "vram_cached_gb": torch.cuda.memory_reserved() / 1e9,
    }
```

**Run**:
```bash
docker build -t ml-api .
docker run --gpus all -p 8000:8000 ml-api
```

### Exemple 2: Training job

**Dockerfile**:
```dockerfile
FROM nvcr.io/nvidia/pytorch:25.01-py3

RUN pip install tensorboard wandb

WORKDIR /app
COPY . .

CMD ["python", "train.py"]
```

**Run avec volumes**:
```bash
docker run --gpus all \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/checkpoints:/app/checkpoints \
  --shm-size=16g \
  ml-training
```

---

## Troubleshooting

### "CUDA out of memory"

```python
# 1. Réduire le batch size
batch_size = 8  # au lieu de 32

# 2. Activer gradient checkpointing
model.gradient_checkpointing_enable()

# 3. Utiliser mixed precision
with torch.cuda.amp.autocast():
    output = model(input)

# 4. Vider le cache régulièrement
torch.cuda.empty_cache()
```

### "RuntimeError: CUDA error: no kernel image is available"

L'image n'est pas compatible avec ton GPU. Solution:
```bash
# Vérifier la compute capability du GPU
nvidia-smi --query-gpu=compute_cap --format=csv

# Utiliser une image compatible
docker pull nvcr.io/nvidia/pytorch:25.01-py3  # Supporte les nouveaux GPUs
```

### Container ne voit pas le GPU

```bash
# Vérifier nvidia-container-toolkit
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi

# Si ça ne marche pas, réinstaller:
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Slow startup (téléchargement modèles)

```dockerfile
# Pré-télécharger les modèles dans l'image
RUN python -c "from transformers import AutoModel; AutoModel.from_pretrained('bert-base-uncased')"

# Ou utiliser un volume pour le cache
# docker run -v ~/.cache/huggingface:/root/.cache/huggingface ...
```

---

## Commandes utiles

```bash
# Voir les containers GPU actifs
docker ps --filter "label=com.nvidia.volumes.needed=nvidia_driver"

# Logs d'un container
docker logs -f mon-container

# Shell dans un container
docker exec -it mon-container bash

# Stats ressources
docker stats mon-container

# Inspecter GPU mapping
docker inspect mon-container | grep -A 20 "DeviceRequests"

# Nettoyer les images non utilisées
docker system prune -a
```

---

## Ressources

- **NGC Catalog**: https://catalog.ngc.nvidia.com/
- **PyTorch Docker**: https://hub.docker.com/r/pytorch/pytorch
- **NVIDIA Container Toolkit**: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/
- **vLLM Docker**: https://docs.vllm.ai/en/latest/serving/deploying_with_docker.html
