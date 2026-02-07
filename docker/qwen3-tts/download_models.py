"""
Pre-download Qwen3-TTS models from HuggingFace.

Run this script to download models before starting the API server,
or uncomment the RUN line in the Dockerfile to bake models into the image.

Models downloaded:
- Qwen3-TTS-12Hz-0.6B-CustomVoice (~1.5GB) - Fast, lightweight
- Qwen3-TTS-12Hz-1.7B-CustomVoice (~4GB)   - Best quality
"""
from huggingface_hub import snapshot_download
import os

MODELS = [
    "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
]

HF_TOKEN = os.environ.get("HF_TOKEN")

def main():
    for model_id in MODELS:
        print(f"Downloading {model_id}...")
        path = snapshot_download(model_id, token=HF_TOKEN)
        print(f"  -> Downloaded to {path}")
    print("\nAll models downloaded!")

if __name__ == "__main__":
    main()
