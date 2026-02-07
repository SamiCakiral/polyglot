# Guide LLM Local - Spark Server

Ce guide explique comment utiliser les modèles LLM locaux sur le serveur **spark-8144**.

## Sommaire

- [Accès au serveur](#accès-au-serveur)
- [Services disponibles](#services-disponibles)
- [vLLM - API OpenAI-compatible](#vllm---api-openai-compatible)
- [Ollama - Modèles locaux](#ollama---modèles-locaux)
- [Utilisation dans Zloop](#utilisation-dans-zloop)
- [Gestion des modèles](#gestion-des-modèles)
- [Performance et limites](#performance-et-limites)
- [Troubleshooting](#troubleshooting)

---

## Accès au serveur

### SSH

```bash
ssh spark-8144
```

Configuration SSH (automatique via NVIDIA Sync):
- Host: `spark-8144.local`
- User: `scakiral`
- Port: 22

### Réseau local

Le serveur est accessible directement sur le réseau local:
- IP: `192.168.0.101`
- Hostname: `spark-8144.local`

---

## Services disponibles

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| **vLLM** | 8000 | `http://spark-8144.local:8000` | API OpenAI-compatible, GPU optimisé |
| **Ollama** | 11434 | `http://spark-8144.local:11434` | Modèles GGUF, CPU/GPU flexible |

### Vérifier les services

```bash
# Status vLLM
curl http://spark-8144.local:8000/v1/models

# Status Ollama
curl http://spark-8144.local:11434/api/tags
```

### Vérifier et démarrer vLLM

Script complet pour vérifier si vLLM tourne et le démarrer si nécessaire:

```bash
# Vérifier si vLLM répond
if curl -s --max-time 3 http://spark-8144.local:8000/v1/models > /dev/null 2>&1; then
    echo "✅ vLLM est déjà en cours d'exécution"
else
    echo "⚠️ vLLM ne répond pas, démarrage..."
    ssh spark-8144 "docker start vllm-server"
    echo "⏳ Attente du chargement du modèle (~2 min)..."
    sleep 120
    if curl -s --max-time 5 http://spark-8144.local:8000/v1/models > /dev/null 2>&1; then
        echo "✅ vLLM démarré avec succès"
    else
        echo "❌ Erreur: vLLM n'a pas démarré"
    fi
fi
```

### Commandes de gestion vLLM

```bash
# Vérifier le status du container
ssh spark-8144 "docker ps | grep vllm"

# Démarrer vLLM
ssh spark-8144 "docker start vllm-server"

# Arrêter vLLM (libère ~73GB de VRAM)
ssh spark-8144 "docker stop vllm-server"

# Redémarrer vLLM
ssh spark-8144 "docker restart vllm-server"

# Voir les logs de chargement
ssh spark-8144 "docker logs -f vllm-server --tail 20"

# Vérifier la VRAM utilisée
ssh spark-8144 "nvidia-smi | grep VLLM"
```

### Temps de chargement

| Étape | Durée |
|-------|-------|
| Démarrage container | ~5s |
| Chargement modèle (3 shards) | ~90s |
| **Total** | **~2 minutes** |

Le modèle `gpt-oss-20b` utilise **~73GB de VRAM** une fois chargé.

### Vérifier et démarrer Ollama

```bash
# Vérifier si Ollama répond
if curl -s --max-time 3 http://spark-8144.local:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama est en cours d'exécution"
else
    echo "⚠️ Ollama ne répond pas, démarrage..."
    ssh spark-8144 "docker start legalprod-ollama"
    sleep 5
    echo "✅ Ollama démarré"
fi
```

---

## vLLM - API OpenAI-compatible

### Modèles disponibles

| Modèle | Paramètres | VRAM | Usage |
|--------|------------|------|-------|
| `openai/gpt-oss-20b` | 20B | ~76GB | Génération de texte, raisonnement |

### Endpoints API

vLLM expose une API 100% compatible OpenAI:

```
POST /v1/chat/completions   # Chat completion
POST /v1/completions        # Text completion
GET  /v1/models             # Liste des modèles
```

### Exemple: Chat Completion

```bash
curl http://spark-8144.local:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "messages": [{"role": "user", "content": "Bonjour!"}],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Exemple Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://spark-8144.local:8000/v1",
    api_key="not-needed"  # Pas d'auth requise
)

response = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "Écris un article sur le SEO"}],
    max_tokens=500,
    temperature=0.7
)

print(response.choices[0].message.content)
```

### Particularités gpt-oss-20b

Ce modèle est un **modèle de raisonnement**. La réponse peut contenir:
- `content`: Réponse finale (parfois vide)
- `reasoning_content`: Processus de réflexion

```python
# Extraire la réponse
message = response.choices[0].message
content = message.content or message.get("reasoning_content", "")
```

---

## Ollama - Modèles locaux

### Modèles disponibles

| Modèle | Taille | Paramètres | Usage |
|--------|--------|------------|-------|
| `qwen2.5:7b-instruct-q8_0` | 8GB | 7.6B | Chat, instructions |
| `gpt-oss:20b` | 14GB | 20.9B | Génération avancée |
| `gpt-oss:120b` | 65GB | 116.8B | Tâches complexes |
| `nomic-embed-text:latest` | 274MB | 137M | Embeddings |
| `qwen3-embedding:8b-q8_0` | 8GB | 7.6B | Embeddings haute qualité |

### API Ollama

```
POST /api/chat      # Chat completion
POST /api/generate  # Text generation
POST /api/embed     # Embeddings
GET  /api/tags      # Liste des modèles
POST /api/pull      # Télécharger un modèle
DELETE /api/delete  # Supprimer un modèle
```

### Exemple: Chat

```bash
curl http://spark-8144.local:11434/api/chat -d '{
  "model": "qwen2.5:7b-instruct-q8_0",
  "messages": [{"role": "user", "content": "Bonjour!"}],
  "stream": false
}'
```

### Exemple: Embeddings

```bash
curl http://spark-8144.local:11434/api/embed -d '{
  "model": "nomic-embed-text:latest",
  "input": "Texte à encoder"
}'
```

### Exemple Python

```python
import requests

response = requests.post(
    "http://spark-8144.local:11434/api/chat",
    json={
        "model": "qwen2.5:7b-instruct-q8_0",
        "messages": [{"role": "user", "content": "Bonjour!"}],
        "stream": False
    }
)

print(response.json()["message"]["content"])
```

---

## Utilisation dans Zloop

### Module `local_llm`

Zloop inclut un module unifié pour les LLMs locaux:

```python
import os
os.environ["USE_LOCAL_LLM"] = "1"

from zloopToolkit.utils.local_llm import (
    is_local_available,
    local_chat,
    get_local_client,
    get_available_models
)

# Vérifier disponibilité
if is_local_available():
    # Chat simple
    response = local_chat(
        messages=[{"role": "user", "content": "Ta question"}],
        model="qwen2.5:7b-instruct-q8_0",  # Ollama
        # model="openai/gpt-oss-20b",       # vLLM
        max_tokens=500
    )
    print(response)
```

### Client avancé

```python
from zloopToolkit.utils.local_llm import LocalLLMClient

client = LocalLLMClient()

# Chat completion (format OpenAI)
response = client.chat_completion(
    messages=[{"role": "user", "content": "Question"}],
    model="qwen2.5:7b-instruct-q8_0",
    temperature=0.7,
    max_tokens=500
)

# Embeddings
embeddings = client.generate_embeddings(
    texts=["Texte 1", "Texte 2"],
    model="nomic-embed-text:latest"
)
```

### Variables d'environnement

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LOCAL_LLM` | `0` | `1` pour activer les LLMs locaux |
| `SPARK_HOST` | `spark-8144.local` | Hostname du serveur |
| `VLLM_PORT` | `8000` | Port vLLM |
| `OLLAMA_PORT` | `11434` | Port Ollama |
| `LOCAL_LLM_TIMEOUT` | `120` | Timeout en secondes |

---

## Gestion des modèles

### Lister les modèles

```bash
# vLLM
curl http://spark-8144.local:8000/v1/models

# Ollama
curl http://spark-8144.local:11434/api/tags
# ou via SSH:
ssh spark-8144 "ollama list"
```

### Télécharger un modèle Ollama

```bash
# Via SSH
ssh spark-8144 "ollama pull llama3.2:3b"

# Via API
curl http://spark-8144.local:11434/api/pull -d '{
  "name": "llama3.2:3b"
}'
```

### Modèles recommandés à télécharger

```bash
# Chat léger et rapide
ollama pull llama3.2:3b
ollama pull phi3:mini

# Chat qualité
ollama pull llama3.1:8b
ollama pull mistral:7b

# Embeddings
ollama pull mxbai-embed-large
ollama pull snowflake-arctic-embed:335m

# Code
ollama pull codellama:7b
ollama pull deepseek-coder:6.7b
```

### Supprimer un modèle

```bash
# Via SSH
ssh spark-8144 "ollama rm nom-du-modele"

# Via API
curl -X DELETE http://spark-8144.local:11434/api/delete -d '{
  "name": "nom-du-modele"
}'
```

### Nomenclature des modèles Ollama

Format: `nom:variante`

| Suffixe | Signification |
|---------|---------------|
| `:latest` | Version par défaut |
| `:7b`, `:13b`, `:70b` | Taille en milliards de paramètres |
| `:instruct` | Fine-tuné pour les instructions |
| `:chat` | Optimisé pour le dialogue |
| `:q4_0`, `:q8_0` | Niveau de quantization |
| `:fp16` | Précision complète (plus lent, plus précis) |

Exemples:
- `llama3.1:8b-instruct-q8_0` → Llama 3.1, 8B params, instruct, quantization Q8
- `mistral:7b` → Mistral 7B, version par défaut
- `qwen2.5:72b-instruct` → Qwen 2.5, 72B params, instruct

---

## Requêtes parallèles et Load Balancing

vLLM gère automatiquement le **batching** des requêtes côté serveur. Pour maximiser le throughput, il faut envoyer plusieurs requêtes en parallèle côté client.

### Méthode 1: ThreadPoolExecutor (simple)

```python
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

VLLM_URL = "http://spark-8144.local:8000/v1/chat/completions"

def generate(prompt: str) -> str:
    """Génère une réponse pour un prompt."""
    response = requests.post(
        VLLM_URL,
        json={
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.7
        },
        timeout=120
    )
    return response.json()["choices"][0]["message"]["content"]

def generate_batch(prompts: list, max_workers: int = 50) -> list:
    """Génère des réponses pour une liste de prompts en parallèle."""
    results = [None] * len(prompts)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(generate, prompt): idx 
            for idx, prompt in enumerate(prompts)
        }
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = f"Error: {e}"
    
    return results

# Usage
prompts = [f"Écris un article sur le sujet {i}" for i in range(100)]
responses = generate_batch(prompts, max_workers=50)
```

### Méthode 2: AsyncIO (recommandé pour haute performance)

```python
import asyncio
import aiohttp

VLLM_URL = "http://spark-8144.local:8000/v1/chat/completions"

async def generate_async(session: aiohttp.ClientSession, prompt: str) -> str:
    """Génère une réponse de manière asynchrone."""
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.7
    }
    
    async with session.post(VLLM_URL, json=payload) as response:
        data = await response.json()
        return data["choices"][0]["message"]["content"]

async def generate_batch_async(prompts: list, max_concurrent: int = 100) -> list:
    """Génère des réponses en parallèle avec limite de concurrence."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def limited_generate(session, prompt, idx):
        async with semaphore:
            result = await generate_async(session, prompt)
            return idx, result
    
    connector = aiohttp.TCPConnector(limit=max_concurrent)
    timeout = aiohttp.ClientTimeout(total=300)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            limited_generate(session, prompt, idx) 
            for idx, prompt in enumerate(prompts)
        ]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Réordonner les résultats
    results = [None] * len(prompts)
    for item in results_raw:
        if isinstance(item, Exception):
            continue
        idx, content = item
        results[idx] = content
    
    return results

# Usage
async def main():
    prompts = [f"Écris un article sur le sujet {i}" for i in range(200)]
    responses = await generate_batch_async(prompts, max_concurrent=100)
    print(f"Générés: {len([r for r in responses if r])}")

asyncio.run(main())
```

### Méthode 3: Avec le module local_llm

```python
import os
os.environ["USE_LOCAL_LLM"] = "1"

from concurrent.futures import ThreadPoolExecutor
from zloopToolkit.utils.local_llm import local_chat

def generate_article(topic: str) -> str:
    return local_chat(
        messages=[{"role": "user", "content": f"Écris un article sur: {topic}"}],
        model="openai/gpt-oss-20b",
        max_tokens=500
    )

# Batch de 100 articles en parallèle
topics = ["SEO", "Marketing", "E-commerce", ...] # 100 topics

with ThreadPoolExecutor(max_workers=50) as executor:
    articles = list(executor.map(generate_article, topics))
```

### Load Balancing côté vLLM

vLLM gère automatiquement le load balancing interne:

| Mécanisme | Description |
|-----------|-------------|
| **Continuous Batching** | Combine les requêtes en batch dynamique |
| **PagedAttention** | Optimise l'utilisation de la VRAM |
| **Chunked Prefill** | Traite les prompts par morceaux |
| **Preemption** | Priorise les requêtes courtes |

Configuration vLLM sur spark (optimisée):
```
--gpu-memory-utilization 0.6    # 60% de la VRAM pour le modèle
--max-num-batched-tokens 2048   # Taille max du batch
--max-model-len 131072          # Contexte max
```

### Paramètres recommandés par cas d'usage

| Cas d'usage | max_workers | Throughput estimé |
|-------------|-------------|-------------------|
| Dev/test | 5-10 | 100-200 tok/s |
| Production normale | 50-80 | 600-1000 tok/s |
| Batch massif | 100-200 | 1500-2000 tok/s |
| Maximum absolu | 250+ | ~2000 tok/s |

### Monitoring des requêtes

```python
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_with_timing(prompt):
    start = time.time()
    result = generate(prompt)
    return {
        "prompt": prompt[:50],
        "elapsed": time.time() - start,
        "tokens": len(result.split())
    }

# Avec stats
prompts = ["..."] * 100
stats = []

with ThreadPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(generate_with_timing, p) for p in prompts]
    for future in as_completed(futures):
        stats.append(future.result())

# Résumé
total_tokens = sum(s["tokens"] for s in stats)
total_time = max(s["elapsed"] for s in stats)
print(f"Throughput: {total_tokens / total_time:.1f} tokens/s")
```

---

## Performance et limites

### Résultats du stress test (Janvier 2026)

| Requêtes parallèles | Throughput | Latence moyenne |
|---------------------|------------|-----------------|
| 1 | 33 tok/s | 2.4s |
| 50 | 630 tok/s | 6s |
| 100 | 1115 tok/s | 7s |
| 200 | 1750 tok/s | 5.6s |
| 250 | **2019 tok/s** | 6s |
| 500 | 2073 tok/s | 9s |

### Recommandations

| Cas d'usage | Concurrence | Throughput attendu |
|-------------|-------------|-------------------|
| Dev/test | 1-10 | 30-200 tok/s |
| Batch normal | 50-80 | 600-1000 tok/s |
| Batch massif | 200-250 | 1500-2000 tok/s |

### Limites matérielles

- **GPU**: NVIDIA GB10 (Grace Blackwell)
- **VRAM**: ~96GB (76GB utilisés par vLLM)
- **RAM**: 119GB
- **Architecture**: ARM64 (aarch64)

---

## Troubleshooting

### vLLM ne répond pas

```bash
# 1. Vérifier si le container tourne
ssh spark-8144 "docker ps | grep vllm"

# 2. Si arrêté, le démarrer
ssh spark-8144 "docker start vllm-server"

# 3. Attendre le chargement (~2 min) et vérifier les logs
ssh spark-8144 "docker logs -f vllm-server --tail 30"

# 4. Tester l'API
curl http://spark-8144.local:8000/v1/models
```

### Ollama ne répond pas

```bash
# 1. Vérifier si le container tourne
ssh spark-8144 "docker ps | grep ollama"

# 2. Si arrêté, le démarrer
ssh spark-8144 "docker start legalprod-ollama"

# 3. Tester
curl http://spark-8144.local:11434/api/tags
```

### Libérer la VRAM

```bash
# Voir ce qui utilise la VRAM
ssh spark-8144 "nvidia-smi"

# Arrêter vLLM (libère ~73GB)
ssh spark-8144 "docker stop vllm-server"

# Arrêter Ollama
ssh spark-8144 "docker stop legalprod-ollama"

# Vérifier après
ssh spark-8144 "nvidia-smi"
```

### Timeout sur requêtes longues

Augmenter le timeout:

```python
# Python requests
requests.post(url, json=payload, timeout=300)

# Module local_llm
os.environ["LOCAL_LLM_TIMEOUT"] = "300"
```

### Modèle non trouvé

```bash
# Vérifier les modèles disponibles
curl http://spark-8144.local:11434/api/tags | python3 -m json.tool

# Télécharger le modèle manquant
ssh spark-8144 "ollama pull nom-du-modele"
```

### Erreur CUDA / GPU

```bash
# Vérifier le GPU
ssh spark-8144 "nvidia-smi"

# Redémarrer vLLM si problème GPU
ssh spark-8144 "docker restart vllm-server"

# Attendre le rechargement (~2 min)
sleep 120
```

### Containers Docker sur spark

| Container | Service | Port | Commande start |
|-----------|---------|------|----------------|
| `vllm-server` | vLLM API | 8000 | `docker start vllm-server` |
| `legalprod-ollama` | Ollama API | 11434 | `docker start legalprod-ollama` |

```bash
# Voir tous les containers
ssh spark-8144 "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

---

## Contacts

- **Serveur**: spark-8144.local (192.168.0.101)
- **Admin**: scakiral
- **Documentation vLLM**: https://docs.vllm.ai
- **Documentation Ollama**: https://ollama.ai/docs


lancer comfy : ssh spark-8144 "source ~/code/comfyui-env/bin/activate && cd ~/code/ComfyUI && nohup python main.py --listen 0.0.0.0 --port 8188 --highvram > /tmp/comfyui.log 2>&1 &"