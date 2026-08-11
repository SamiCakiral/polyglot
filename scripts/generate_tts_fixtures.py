#!/usr/bin/env python3
"""Generate the fixed local audio used by the pilot curricula."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "tts" / "local-v2"
ITEMS = (
    ("ja-JP", "Kyoko", "こんにちは。わたしはサミです。"),
    ("ja-JP", "Kyoko", "すみません。みずをください。"),
    ("ja-JP", "Kyoko", "もういちどおねがいします。"),
)


def filename(locale: str, voice_id: str, text: str) -> str:
    canonical = json.dumps(
        {"locale": locale, "parameters": {}, "text": text, "voice_id": voice_id},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}.mp3"


def main() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("The canonical local fixtures must be generated with macOS say.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for locale, voice_id, text in ITEMS:
        target = OUTPUT / filename(locale, voice_id, text)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "speech.aiff"
            subprocess.run(
                ("say", "-v", voice_id, "-o", str(source), text),
                check=True,
            )
            subprocess.run(
                (
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    str(target),
                ),
                check=True,
            )
        manifest.append(
            {
                "file": target.name,
                "locale": locale,
                "provider": "macos-say",
                "provider_version": "local-v2",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "text": text,
                "voice_id": voice_id,
            }
        )
    (OUTPUT / "manifest.json").write_text(
        json.dumps({"items": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
