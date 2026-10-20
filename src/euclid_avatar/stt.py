"""Local Apple Silicon Speech-to-Text (STT) using mlx-whisper with startup Metal warm-up."""
from __future__ import annotations

import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import mlx_whisper
import numpy as np

from .config import Config

STT_SAMPLE_RATE = 16000

DOMAIN_INITIAL_PROMPT = (
    "MATH E-139 Reading Euclid's Elements in Greek. "
    "Book I, Proposition I.1, I.4, I.5, I.8, I.9, I.10, I.12, I.15, I.20, I.22, I.23, I.27, I.29, I.31, I.32, I.47, "
    "Definition 15, Definition 23, Postulate 5, Common Notion 1, Common Notion 9, "
    "Pythagorean theorem, Cayley-Klein, hyperbolic, spherical, Poincaré, Hermes model, "
    "Erasmian, protasis, ekthesis, diorismos, kataskeue, apodeixis, symperasma."
)


def load_audio_16k(path: Path) -> tuple[np.ndarray, float]:
    """Load any WAV/AIFF/audio file into 16 kHz mono float32 PCM."""
    try:
        with wave.open(str(path), "rb") as f:
            sr = f.getframerate()
            nch = f.getnchannels()
            sw = f.getsampwidth()
            raw = f.readframes(f.getnframes())
        if sw == 2:
            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif sw == 4:
            arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError("Unsupported sample width")
        if nch > 1:
            arr = arr.reshape(-1, nch).mean(axis=1)
        duration_s = len(arr) / float(sr)
        if sr != STT_SAMPLE_RATE and len(arr) > 0:
            target_len = int(round(duration_s * STT_SAMPLE_RATE))
            arr = np.interp(
                np.linspace(0.0, len(arr) - 1, target_len),
                np.arange(len(arr)),
                arr,
            ).astype(np.float32)
        return arr, duration_s
    except Exception:
        # Fallback via ffmpeg for AIFF/MP3/compressed WAV
        res = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(path),
                "-f", "f32le", "-ac", "1", "-ar", str(STT_SAMPLE_RATE), "pipe:1",
            ],
            capture_output=True,
            check=True,
        )
        arr = np.frombuffer(res.stdout, dtype="<f4").copy()
        return arr, len(arr) / float(STT_SAMPLE_RATE)


@dataclass
class STTResult:
    text: str
    elapsed_ms: float
    audio_duration_s: float
    model: str


MODEL_ALIASES = {
    "mlx-community/whisper-small.en": "mlx-community/whisper-small.en-mlx",
    "mlx-community/whisper-base.en": "mlx-community/whisper-base.en-mlx",
    "mlx-community/whisper-tiny.en": "mlx-community/whisper-tiny.en-mlx",
}


class LocalWhisperSTT:
    """Apple Silicon MLX Whisper wrapper with startup 0.5 s silence warm-up."""

    def __init__(self, cfg: Config, model_id: str | None = None, warmup_on_init: bool = True) -> None:
        self.cfg = cfg
        raw_id = model_id or cfg.stt_model
        self.model_id = MODEL_ALIASES.get(raw_id, raw_id)
        self.warmup_ms: float = 0.0
        if warmup_on_init:
            self.warmup()

    def warmup(self) -> float:
        """Transcribe 0.5 s of silence so Metal shaders and weights are resident in RAM."""
        t0 = time.perf_counter()
        silence = np.zeros(int(0.5 * STT_SAMPLE_RATE), dtype=np.float32)
        mlx_whisper.transcribe(
            silence,
            path_or_hf_repo=self.model_id,
            language="en",
            condition_on_previous_text=False,
            verbose=False,
        )
        self.warmup_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return self.warmup_ms

    def transcribe_pcm(self, audio_16k: np.ndarray, input_sr: int = STT_SAMPLE_RATE) -> STTResult:
        t0 = time.perf_counter()
        arr = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
        duration_s = len(arr) / float(input_sr) if input_sr > 0 else 0.0
        if input_sr != STT_SAMPLE_RATE and len(arr) > 0:
            target_len = int(round(duration_s * STT_SAMPLE_RATE))
            arr = np.interp(
                np.linspace(0.0, len(arr) - 1, target_len),
                np.arange(len(arr)),
                arr,
            ).astype(np.float32)

        out = mlx_whisper.transcribe(
            arr,
            path_or_hf_repo=self.model_id,
            language="en",
            initial_prompt=DOMAIN_INITIAL_PROMPT,
            condition_on_previous_text=False,
            verbose=False,
        )
        text = str(out.get("text", "")).strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return STTResult(
            text=text,
            elapsed_ms=round(elapsed_ms, 1),
            audio_duration_s=round(duration_s, 2),
            model=self.model_id,
        )

    def transcribe_wav(self, wav_path: Path) -> STTResult:
        arr, duration_s = load_audio_16k(wav_path)
        res = self.transcribe_pcm(arr, STT_SAMPLE_RATE)
        res.audio_duration_s = round(duration_s, 2)
        return res
