"""Asset caching and Gemini 3.8 TTS scholarly voiceover synthesis for III.36.

Pure Python standard library + FFmpeg implementation compatible with
`/opt/homebrew/bin/python3`. Enforces the < 7-minute (`420.0 s`) total duration
ceiling and never logs or prints API keys.
"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request
import wave

from .geometry import build_world_spec

# Network & Gemini TTS constants ("Sadaltager" = Google's calm, knowledgeable academic voice)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"
GEMINI_TTS_VOICE_NAME = "Sadaltager"
THREE_JS_CDN_URL = "https://unpkg.com/three@0.170.0/build/three.module.js"
HTTP_TIMEOUT_S = 90.0
MAX_API_RETRIES = 3
RETRY_BACKOFF_BASE_S = 2.0

# Audio format & timeline pacing constants
AUDIO_SAMPLE_RATE_HZ = 24000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH_BYTES = 2
PCM16_PEAK_LIMIT = 28500
SILENCE_TRIM_THRESHOLD = 220
EDGE_PAD_S = 0.06
INTER_SEGMENT_PAUSE_S = 0.28
INTER_SLIDE_PAUSE_S = 0.58
OPENING_LEAD_IN_S = 0.30
CLOSING_TAIL_S = 0.70
MAX_PRESENTATION_DURATION_S = 420.0  # Strict 7-minute ceiling

PLACEHOLDER_KEY = "your_gemini_api_key_here"
ENV_KEY_RE = re.compile(r"^\s*GEMINI_API_KEY\s*=\s*(.+?)\s*$")


def _read_key_from_env_file(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = ENV_KEY_RE.match(raw_line)
        if not match:
            continue
        candidate = match.group(1).strip().strip("'\"")
        if candidate and candidate != PLACEHOLDER_KEY:
            return candidate
    return ""


def discover_gemini_api_key(worktree_root: Path) -> str:
    """Resolve GEMINI_API_KEY safely from local course .env or environment."""
    course_key = _read_key_from_env_file(
        Path.home() / "Projects/Courses/26Fall/mathe139/.env"
    )
    if course_key:
        return course_key
    env_val = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_val and env_val != PLACEHOLDER_KEY:
        return env_val
    local_key = _read_key_from_env_file(worktree_root / ".env")
    if local_key:
        return local_key
    return _read_key_from_env_file(Path.home() / "Projects/codex/euclid-tts/.env")


def _gemini_post_json(model: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY for III.36 voiceover synthesis.")
    url = f"{GEMINI_API_BASE_URL}/{model}:generateContent?key={api_key}"
    body_bytes = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(MAX_API_RETRIES):
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            if attempt + 1 < MAX_API_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE_S * (attempt + 1))
    raise RuntimeError(f"Gemini API call to {model} failed: {type(last_err).__name__}")


def ensure_three_js_cached(cache_dir: Path) -> Path:
    vendor_dir = cache_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    target = vendor_dir / "three.module.js"
    if target.exists() and target.stat().st_size > 100_000:
        return target
    req = urllib.request.Request(
        THREE_JS_CDN_URL,
        headers={"User-Agent": "euclid-avatar-iii36-world/1.0"},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
        target.write_bytes(resp.read())
    return target


def _normalize_audio_to_wav24k(raw_bytes: bytes, mime_type: str, out_wav: Path) -> float:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        decoded_wav = tmp_dir / "decoded.wav"
        if raw_bytes[:4] == b"RIFF":
            raw_in = tmp_dir / "in.wav"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(raw_in),
                "-ac",
                str(AUDIO_CHANNELS),
                "-ar",
                str(AUDIO_SAMPLE_RATE_HZ),
                "-c:a",
                "pcm_s16le",
                str(decoded_wav),
            ]
        else:
            rate_match = re.search(r"rate=(\d+)", mime_type or "")
            in_rate = int(rate_match.group(1)) if rate_match else AUDIO_SAMPLE_RATE_HZ
            raw_in = tmp_dir / "in.pcm"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "s16le",
                "-ar",
                str(in_rate),
                "-ac",
                str(AUDIO_CHANNELS),
                "-i",
                str(raw_in),
                "-ac",
                str(AUDIO_CHANNELS),
                "-ar",
                str(AUDIO_SAMPLE_RATE_HZ),
                "-c:a",
                "pcm_s16le",
                str(decoded_wav),
            ]
        subprocess.run(cmd, check=True)
        with wave.open(str(decoded_wav), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        samples = array.array("h")
        samples.frombytes(frames)

    if not samples:
        raise RuntimeError("Decoded TTS audio contained zero samples.")

    n_total = len(samples)
    start_idx = 0
    while start_idx < n_total and abs(samples[start_idx]) < SILENCE_TRIM_THRESHOLD:
        start_idx += 1
    end_idx = n_total - 1
    while end_idx > start_idx and abs(samples[end_idx]) < SILENCE_TRIM_THRESHOLD:
        end_idx -= 1

    pad_samples = int(EDGE_PAD_S * AUDIO_SAMPLE_RATE_HZ)
    start_idx = max(0, start_idx - pad_samples)
    end_idx = min(n_total, end_idx + pad_samples + 1)
    trimmed = samples[start_idx:end_idx]

    peak = max((abs(s) for s in trimmed), default=1)
    if peak > 0:
        gain = min(2.2, PCM16_PEAK_LIMIT / float(peak))
        scaled = array.array(
            "h",
            (max(-32768, min(32767, int(round(s * gain)))) for s in trimmed),
        )
    else:
        scaled = trimmed

    with wave.open(str(out_wav), "wb") as wf_out:
        wf_out.setnchannels(AUDIO_CHANNELS)
        wf_out.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
        wf_out.setframerate(AUDIO_SAMPLE_RATE_HZ)
        wf_out.writeframes(scaled.tobytes())

    return len(scaled) / float(AUDIO_SAMPLE_RATE_HZ)


def _read_wav_duration_and_samples(wav_path: Path) -> tuple[float, array.array]:
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    return len(samples) / float(rate), samples


def synthesize_segment_wav(
    segment_id: str,
    spoken_text: str,
    audio_cache_dir: Path,
    api_key: str,
) -> tuple[Path, float]:
    digest = hashlib.sha256(
        f"v1:{GEMINI_TTS_MODEL}:{GEMINI_TTS_VOICE_NAME}:{spoken_text}".encode("utf-8")
    ).hexdigest()[:12]
    wav_path = audio_cache_dir / f"{segment_id}_{digest}.wav"
    if wav_path.exists() and wav_path.stat().st_size > 1024:
        dur, _ = _read_wav_duration_and_samples(wav_path)
        return wav_path, dur

    payload = {
        "contents": [{"parts": [{"text": spoken_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE_NAME}
                }
            },
        },
    }
    resp = _gemini_post_json(GEMINI_TTS_MODEL, payload, api_key)
    candidates = resp.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"No audio candidates returned for {segment_id}.")
    parts = candidates[0].get("content", {}).get("parts", [])
    inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
    if not inline or not inline.get("data"):
        raise RuntimeError(f"Missing inlineData audio payload for {segment_id}.")

    raw_bytes = base64.b64decode(inline["data"])
    mime_type = inline.get("mimeType", "audio/wav")
    dur = _normalize_audio_to_wav24k(raw_bytes, mime_type, wav_path)
    return wav_path, dur


def build_all_world_assets(worktree_root: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    """Prepare Three.js and synthesize all 14 III.36 voiceover segments (< 7 min)."""
    resolved_cache = cache_dir or (worktree_root / ".cache" / "iii36_world")
    audio_dir = resolved_cache / "audio"
    resolved_cache.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    api_key = discover_gemini_api_key(worktree_root)
    three_path = ensure_three_js_cached(resolved_cache)

    spec = build_world_spec()
    cursor_s = OPENING_LEAD_IN_S
    master_samples = array.array(
        "h", [0] * int(round(OPENING_LEAD_IN_S * AUDIO_SAMPLE_RATE_HZ))
    )

    timeline_segments: list[dict[str, Any]] = []
    slides = spec["slides"]
    for slide_idx, slide in enumerate(slides):
        segs = slide["segments"]
        for seg_idx, seg in enumerate(segs):
            wav_path, dur_s = synthesize_segment_wav(
                seg["id"], seg["spoken"], audio_dir, api_key
            )
            _, seg_samples = _read_wav_duration_and_samples(wav_path)
            start_s = cursor_s
            end_s = start_s + dur_s
            master_samples.extend(seg_samples)
            cursor_s = end_s

            is_last_slide = slide_idx == len(slides) - 1
            is_last_seg_in_slide = seg_idx == len(segs) - 1
            if is_last_slide and is_last_seg_in_slide:
                pause_after_s = CLOSING_TAIL_S
            elif is_last_seg_in_slide:
                pause_after_s = INTER_SLIDE_PAUSE_S
            else:
                pause_after_s = INTER_SEGMENT_PAUSE_S

            master_samples.extend(
                [0] * int(round(pause_after_s * AUDIO_SAMPLE_RATE_HZ))
            )
            cursor_s += pause_after_s

            seg_entry = {
                **seg,
                "slide_number": slide["slide_number"],
                "slide_id": slide["id"],
                "slide_title": slide["title"],
                "wav_filename": wav_path.name,
                "wav_path": str(wav_path),
                "start_s": round(start_s, 4),
                "end_s": round(end_s, 4),
                "hold_end_s": round(end_s + pause_after_s, 4),
                "duration_s": round(dur_s, 4),
            }
            seg.update(seg_entry)
            timeline_segments.append(seg_entry)

    total_duration_s = len(master_samples) / float(AUDIO_SAMPLE_RATE_HZ)
    if total_duration_s > MAX_PRESENTATION_DURATION_S:
        raise RuntimeError(
            f"Presentation duration {total_duration_s:.1f}s exceeds 7-minute limit ({MAX_PRESENTATION_DURATION_S}s)."
        )

    master_wav_path = audio_dir / "iii36_voiceover_full.wav"
    with wave.open(str(master_wav_path), "wb") as wf_master:
        wf_master.setnchannels(AUDIO_CHANNELS)
        wf_master.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
        wf_master.setframerate(AUDIO_SAMPLE_RATE_HZ)
        wf_master.writeframes(master_samples.tobytes())

    spec["timeline"] = {
        "total_duration_s": round(total_duration_s, 4),
        "opening_lead_in_s": OPENING_LEAD_IN_S,
        "closing_tail_s": CLOSING_TAIL_S,
        "master_wav_url": "/assets/audio/iii36_voiceover_full.wav",
        "segments": timeline_segments,
    }
    manifest_path = resolved_cache / "world_manifest.json"
    manifest_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    return {
        "spec": spec,
        "cache_dir": resolved_cache,
        "three_path": three_path,
        "master_wav_path": master_wav_path,
        "manifest_path": manifest_path,
    }
