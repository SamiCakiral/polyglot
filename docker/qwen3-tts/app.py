"""
Qwen3-TTS FastAPI Server for Language Learning App.

Exposes a simple REST API for text-to-speech synthesis.
Runs on port 9100.

Supported languages:
  Chinese (zh), English (en), Japanese (ja), Korean (ko),
  German (de), French (fr), Russian (ru), Portuguese (pt),
  Spanish (es), Italian (it)

NOT supported: Turkish (tr)

Endpoints:
  POST /tts           - Generate speech from text
  GET  /health        - Health check
  GET  /speakers      - List available speakers
  GET  /languages     - List supported languages
"""
import os
import io
import time
import logging
import numpy as np
import torch
import soundfile as sf
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from huggingface_hub import snapshot_download

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen3-tts")

# =============================================================================
# Configuration
# =============================================================================
HF_TOKEN = os.environ.get("HF_TOKEN")
MODEL_SIZE = os.environ.get("TTS_MODEL_SIZE", "1.7B")  # "0.6B" or "1.7B"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

SUPPORTED_LANGUAGES = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian"
}

SPEAKERS = [
    "aiden", "dylan", "eric", "ono_anna", "ryan", 
    "serena", "sohee", "uncle_fu", "vivian"
]

# Map language codes to Qwen3-TTS language names
LANG_MAP = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian", "auto": "Auto"
}

# =============================================================================
# Global model references
# =============================================================================
tts_model = None


def load_model():
    """Load the Qwen3-TTS CustomVoice model."""
    global tts_model
    
    from qwen_tts import Qwen3TTSModel
    
    model_id = f"Qwen/Qwen3-TTS-12Hz-{MODEL_SIZE}-CustomVoice"
    logger.info(f"Downloading model {model_id}...")
    model_path = snapshot_download(model_id, token=HF_TOKEN)
    
    logger.info(f"Loading model to {DEVICE} (bfloat16)...")
    tts_model = Qwen3TTSModel.from_pretrained(
        model_path,
        device_map=DEVICE,
        dtype=torch.bfloat16,
        token=HF_TOKEN,
    )
    logger.info("Model loaded successfully!")


# =============================================================================
# FastAPI App
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    logger.info(f"GPU available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        logger.info(f"VRAM: {vram:.1f} GB")
    
    load_model()
    yield
    # Cleanup
    logger.info("Shutting down, freeing GPU memory...")
    global tts_model
    del tts_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(
    title="Qwen3-TTS API",
    description="Text-to-Speech API for language learning",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for Flask app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Request / Response Models
# =============================================================================
class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize", max_length=2000)
    language: str = Field(default="auto", description="Language code (zh, en, ja, ko, de, fr, ru, pt, es, it)")
    speaker: str = Field(default="vivian", description="Speaker voice preset")
    instruct: Optional[str] = Field(default=None, description="Style instruction (e.g., 'Speak slowly and clearly')")


class TTSResponse(BaseModel):
    status: str
    duration_ms: float
    sample_rate: int
    language: str
    speaker: str


# =============================================================================
# Endpoints
# =============================================================================
@app.get("/health")
async def health():
    """Health check endpoint."""
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "gpu": torch.cuda.get_device_name(0),
            "vram_allocated_gb": round(torch.cuda.memory_allocated(0) / 1e9, 2),
        }
    
    return {
        "status": "healthy" if tts_model is not None else "loading",
        "model": f"Qwen3-TTS-12Hz-{MODEL_SIZE}-CustomVoice",
        "device": DEVICE,
        "gpu": gpu_info,
    }


@app.get("/speakers")
async def list_speakers():
    """List available speaker presets."""
    return {"speakers": SPEAKERS}


@app.get("/languages")
async def list_languages():
    """List supported languages."""
    return {"languages": SUPPORTED_LANGUAGES}


@app.post("/tts")
async def generate_tts(request: TTSRequest):
    """
    Generate speech from text.
    
    Returns WAV audio as a streaming response.
    """
    if tts_model is None:
        raise HTTPException(status_code=503, detail="Model still loading, please wait...")
    
    # Validate language
    lang_code = request.language.lower()
    if lang_code == "tr":
        raise HTTPException(
            status_code=400, 
            detail="Turkish is not supported by Qwen3-TTS. Supported: zh, en, ja, ko, de, fr, ru, pt, es, it"
        )
    
    lang_name = LANG_MAP.get(lang_code, "Auto")
    
    # Validate speaker
    speaker = request.speaker.lower().replace(" ", "_")
    if speaker not in SPEAKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown speaker '{speaker}'. Available: {', '.join(SPEAKERS)}"
        )
    
    # Generate speech
    try:
        start = time.time()
        
        wavs, sr = tts_model.generate_custom_voice(
            text=request.text.strip(),
            language=lang_name,
            speaker=speaker,
            instruct=request.instruct.strip() if request.instruct else None,
            non_streaming_mode=True,
            max_new_tokens=2048,
        )
        
        duration_ms = (time.time() - start) * 1000
        logger.info(f"TTS: '{request.text[:50]}...' -> {duration_ms:.0f}ms, lang={lang_name}, speaker={speaker}")
        
        # Convert to WAV bytes
        wav_data = wavs[0]
        if isinstance(wav_data, torch.Tensor):
            wav_data = wav_data.cpu().numpy()
        
        # Normalize audio
        wav_data = np.asarray(wav_data, dtype=np.float32)
        max_val = np.max(np.abs(wav_data))
        if max_val > 0:
            wav_data = wav_data / max_val
        
        # Write to buffer
        buffer = io.BytesIO()
        sf.write(buffer, wav_data, sr, format='WAV')
        buffer.seek(0)
        
        return StreamingResponse(
            buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=tts_output.wav",
                "X-TTS-Duration-Ms": str(round(duration_ms)),
                "X-TTS-Sample-Rate": str(sr),
                "X-TTS-Language": lang_name,
                "X-TTS-Speaker": speaker,
            }
        )
        
    except Exception as e:
        logger.error(f"TTS generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


@app.post("/tts/json")
async def generate_tts_info(request: TTSRequest):
    """
    Generate speech and return metadata (for debugging).
    Audio is base64-encoded in the response.
    """
    import base64
    
    if tts_model is None:
        raise HTTPException(status_code=503, detail="Model still loading...")
    
    lang_code = request.language.lower()
    if lang_code == "tr":
        raise HTTPException(status_code=400, detail="Turkish not supported")
    
    lang_name = LANG_MAP.get(lang_code, "Auto")
    speaker = request.speaker.lower().replace(" ", "_")
    
    try:
        start = time.time()
        wavs, sr = tts_model.generate_custom_voice(
            text=request.text.strip(),
            language=lang_name,
            speaker=speaker,
            instruct=request.instruct.strip() if request.instruct else None,
            non_streaming_mode=True,
            max_new_tokens=2048,
        )
        duration_ms = (time.time() - start) * 1000
        
        wav_data = wavs[0]
        if isinstance(wav_data, torch.Tensor):
            wav_data = wav_data.cpu().numpy()
        wav_data = np.asarray(wav_data, dtype=np.float32)
        max_val = np.max(np.abs(wav_data))
        if max_val > 0:
            wav_data = wav_data / max_val
        
        buffer = io.BytesIO()
        sf.write(buffer, wav_data, sr, format='WAV')
        audio_b64 = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "status": "ok",
            "duration_ms": round(duration_ms),
            "sample_rate": sr,
            "language": lang_name,
            "speaker": speaker,
            "audio_length_samples": len(wav_data),
            "audio_base64": audio_b64,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("TTS_PORT", "9100"))
    logger.info(f"Starting Qwen3-TTS API on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
