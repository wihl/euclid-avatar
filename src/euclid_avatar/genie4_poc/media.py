"""API key discovery, Nano Banana 2.1 seed generation, Ancient Greek TTS, and FFmpeg muxing."""

from __future__ import annotations

import array
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
from typing import Any

from . import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    GENIE_API_VERSION,
    GENIE_AUDIO_CHANNELS,
    GENIE_AUDIO_RATE_HZ,
    GENIE_FPS,
)
from .propositions import DEFAULT_COURSE_REPO, PropositionPlan

PLACEHOLDER_KEY = "your_gemini_api_key_here"
ENV_KEY_RE = re.compile(r"^\s*GEMINI_API_KEY\s*=\s*(.+?)\s*$")

DEFAULT_SEED_ASPECT_RATIO = "16:9"
DEFAULT_SEED_IMAGE_SIZE = "2K"

TTS_SAMPLE_RATE_HZ = 24000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH_BYTES = 2
TTS_SILENCE_TRIM_THRESHOLD = 220
TTS_EDGE_PAD_S = 0.06
TTS_PCM16_PEAK_LIMIT = 28500
TTS_STEP_PAUSE_S = 0.55

VIDEO_CRF = 18
AUDIO_OUT_RATE_HZ = 48000
AUDIO_OUT_BITRATE = "192k"
AMBIENT_MIX_VOLUME = 0.22

ERASMIAN_TTS_STYLE = (
    "Calm, unhurried, authoritative older Greek scholar reciting Euclid in "
    "classical Erasmian Ancient Greek pronunciation with clear distinct vowels, "
    "audible rough breathing, and deliberate pauses on Greek geometric letters."
)


def _read_key_from_env_file(env_path: Path) -> str:
    """Read ``GEMINI_API_KEY`` from a ``.env`` file without logging or mutating it."""
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


def discover_gemini_api_key(
    worktree_root: Path,
    *,
    course_repo_path: Path = DEFAULT_COURSE_REPO,
) -> str:
    """Resolve ``GEMINI_API_KEY`` safely from environment or read-only local ``.env`` files.

    Precedence:
    1. Explicit ``GEMINI_API_KEY`` environment variable.
    2. ``course_repo_path/.env`` (``~/Projects/Courses/26Fall/mathe139/.env``).
    3. ``worktree_root/.env``.
    4. ``~/Projects/agy/euclid-avatar/.env`` (read-only fallback for worktrees).
    5. ``~/Projects/codex/euclid-tts/.env`` (read-only fallback).
    """
    env_val = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_val and env_val != PLACEHOLDER_KEY:
        return env_val

    candidates = (
        course_repo_path / ".env",
        worktree_root / ".env",
        Path.home() / "Projects/agy/euclid-avatar/.env",
        Path.home() / "Projects/codex/euclid-tts/.env",
    )
    for path in candidates:
        key = _read_key_from_env_file(path)
        if key:
            return key
    return ""


def detect_video_frame_codec(frame_bytes: bytes) -> tuple[str, str, str]:
    """Identify the real frame codec from magic header bytes.

    Genie 4 currently labels video deltas ``video/jpeg2000`` on the wire while
    emitting standard JFIF JPEG bytes (``FF D8 FF``). Sniffing the header
    guarantees FFmpeg uses the exact matching decoder.

    Returns:
        Tuple of ``(ffmpeg_vcodec, file_extension, canonical_mime_type)``.
    """
    if frame_bytes.startswith(b"\xff\xd8\xff"):
        return ("mjpeg", ".jpg", "image/jpeg")
    if frame_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("png", ".png", "image/png")
    if frame_bytes.startswith(b"\x00\x00\x00\x0cjP") or frame_bytes.startswith(
        b"\xff\x4f\xff\x51"
    ):
        return ("jpeg2000", ".jp2", "image/jp2")
    if frame_bytes.startswith(b"RIFF") and frame_bytes[8:12] == b"WEBP":
        return ("webp", ".webp", "image/webp")
    return ("mjpeg", ".jpg", "image/jpeg")


def sniff_image_mime_type(image_bytes: bytes) -> str:
    """Detect image MIME type from file bytes."""
    _, _, mime = detect_video_frame_codec(image_bytes)
    return mime


def generate_seed_image(
    prompt: str,
    output_path: Path,
    api_key: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    aspect_ratio: str = DEFAULT_SEED_ASPECT_RATIO,
    image_size: str = DEFAULT_SEED_IMAGE_SIZE,
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate a 16:9 photorealistic starting frame for Genie 4 via Interactions API.

    Uses ``gemini-nano-banana-2.1`` by default (or ``--image-model`` for
    legacy ``gemini-3.1-flash-image`` parity with ``iii18_world``) and caches
    by content digest so repeated runs reuse the generated seed frame.
    """
    from google import genai

    digest = hashlib.sha256(
        f"v1:{model}:{aspect_ratio}:{image_size}:{prompt}".encode("utf-8")
    ).hexdigest()[:14]
    cached_path: Path | None = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        for ext in (".png", ".jpg", ".webp"):
            candidate = cache_dir / f"seed_{digest}{ext}"
            if candidate.exists() and candidate.stat().st_size > 10_000 and not force:
                cached_path = candidate
                break

    if cached_path is not None:
        raw = cached_path.read_bytes()
        _, ext, mime = detect_video_frame_codec(raw)
        final_path = output_path.with_suffix(ext)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_path, final_path)
        return {
            "path": final_path,
            "mime_type": mime,
            "bytes": len(raw),
            "model": model,
            "cached": True,
        }

    if not api_key:
        raise RuntimeError(
            f"Missing GEMINI_API_KEY required to generate seed image with {model}."
        )

    client = genai.Client(
        api_key=api_key, http_options={"api_version": GENIE_API_VERSION}
    )
    interaction = client.interactions.create(
        model=model,
        input=prompt,
        response_format={
            "type": "image",
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
    )
    output_image = getattr(interaction, "output_image", None)
    if output_image is None or not getattr(output_image, "data", None):
        raise RuntimeError(f"Model {model} returned no output_image payload.")

    raw_bytes = base64.b64decode(output_image.data)
    _, ext, mime = detect_video_frame_codec(raw_bytes)
    final_path = output_path.with_suffix(ext)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(raw_bytes)
    if cache_dir is not None:
        (cache_dir / f"seed_{digest}{ext}").write_bytes(raw_bytes)

    return {
        "path": final_path,
        "mime_type": mime,
        "bytes": len(raw_bytes),
        "model": model,
        "cached": False,
    }


def _require_ffmpeg() -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg binary not found on PATH (install via Homebrew).")
    return ffmpeg_bin


def _normalize_audio_bytes_to_wav24k(
    raw_bytes: bytes,
    mime_type: str,
    out_wav: Path,
) -> float:
    """Convert raw WAV/PCM audio bytes to trimmed, peak-normalized 24 kHz mono WAV."""
    ffmpeg_bin = _require_ffmpeg()
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        decoded_wav = tmp_dir / "decoded.wav"
        if raw_bytes[:4] == b"RIFF":
            raw_in = tmp_dir / "in.wav"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(raw_in),
                "-ac",
                str(TTS_CHANNELS),
                "-ar",
                str(TTS_SAMPLE_RATE_HZ),
                "-c:a",
                "pcm_s16le",
                str(decoded_wav),
            ]
        else:
            rate_match = re.search(r"rate=(\d+)", mime_type or "")
            in_rate = int(rate_match.group(1)) if rate_match else TTS_SAMPLE_RATE_HZ
            raw_in = tmp_dir / "in.pcm"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "s16le",
                "-ar",
                str(in_rate),
                "-ac",
                str(TTS_CHANNELS),
                "-i",
                str(raw_in),
                "-ac",
                str(TTS_CHANNELS),
                "-ar",
                str(TTS_SAMPLE_RATE_HZ),
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
    while start_idx < n_total and abs(samples[start_idx]) < TTS_SILENCE_TRIM_THRESHOLD:
        start_idx += 1
    end_idx = n_total - 1
    while end_idx > start_idx and abs(samples[end_idx]) < TTS_SILENCE_TRIM_THRESHOLD:
        end_idx -= 1

    pad_samples = int(TTS_EDGE_PAD_S * TTS_SAMPLE_RATE_HZ)
    start_idx = max(0, start_idx - pad_samples)
    end_idx = min(n_total, end_idx + pad_samples + 1)
    trimmed = samples[start_idx:end_idx]

    peak = max((abs(s) for s in trimmed), default=1)
    if peak > 0:
        gain = min(2.2, TTS_PCM16_PEAK_LIMIT / float(peak))
        scaled = array.array(
            "h",
            (max(-32768, min(32767, int(round(s * gain)))) for s in trimmed),
        )
    else:
        scaled = trimmed

    with wave.open(str(out_wav), "wb") as wf_out:
        wf_out.setnchannels(TTS_CHANNELS)
        wf_out.setsampwidth(TTS_SAMPLE_WIDTH_BYTES)
        wf_out.setframerate(TTS_SAMPLE_RATE_HZ)
        wf_out.writeframes(scaled.tobytes())

    return len(scaled) / float(TTS_SAMPLE_RATE_HZ)


def _read_wav_samples(wav_path: Path) -> tuple[float, array.array]:
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    return len(samples) / float(rate), samples


def synthesize_ancient_greek_narration(
    plan: PropositionPlan,
    audio_dir: Path,
    api_key: str,
    *,
    backend: str = "gemini_tts",
    tts_model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_TTS_VOICE,
    force: bool = False,
) -> dict[str, Any]:
    """Synthesize Ancient Greek proposition audio using ``euclid-avatar``'s TTS models.

    Backends:
    - ``gemini_tts``: Calls ``gemini-3.8-flash-tts`` (``Sadaltager`` / ``Charon``)
      via the Gemini Interactions API (``v1beta``) with ``speech_metadata`` style.
    - ``erasmian_ipa``: Uses ``euclid_avatar.tts.EuclidTTS`` (Google Cloud
      ``en-AU-Chirp3-HD-Charon`` with ``bird-handout-and-class-2026-10-08`` IPA
      ``<phoneme>`` rules, requiring Google Cloud ADC).
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    segments_spec = [
        ("step_0_enunciation", "0. Enunciation (Πρότασις)", plan.enunciation_greek),
        *((step.id, step.label, step.greek_text) for step in plan.steps),
    ]

    master_samples = array.array("h")
    timeline: list[dict[str, Any]] = []
    cursor_s = 0.0

    erasmian_engine = None
    gemini_client = None
    if backend == "erasmian_ipa":
        from euclid_avatar.config import load_config
        from euclid_avatar.tts import EuclidTTS

        cfg = load_config()
        cfg.tts_backend = "google_erasmian"
        erasmian_engine = EuclidTTS(cfg)
    elif backend == "gemini_tts":
        from google import genai

        if not api_key:
            raise RuntimeError(
                f"Missing GEMINI_API_KEY required for {tts_model} narration."
            )
        gemini_client = genai.Client(
            api_key=api_key, http_options={"api_version": GENIE_API_VERSION}
        )
    else:
        raise ValueError(
            f"Unsupported TTS backend {backend!r}; choose 'gemini_tts' or 'erasmian_ipa'."
        )

    for idx, (seg_id, label, greek_text) in enumerate(segments_spec):
        digest = hashlib.sha256(
            f"v1:{backend}:{tts_model}:{voice}:{greek_text}".encode("utf-8")
        ).hexdigest()[:12]
        wav_path = audio_dir / f"{seg_id}_{digest}.wav"

        if wav_path.exists() and wav_path.stat().st_size > 1024 and not force:
            dur_s, seg_samples = _read_wav_samples(wav_path)
        elif backend == "gemini_tts":
            assert gemini_client is not None
            interaction = gemini_client.interactions.create(
                model=tts_model,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": greek_text,
                                "annotations": [
                                    {
                                        "type": "speech_metadata",
                                        "style": ERASMIAN_TTS_STYLE,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
            )
            output_audio = getattr(interaction, "output_audio", None)
            if output_audio is None or not getattr(output_audio, "data", None):
                raise RuntimeError(
                    f"Model {tts_model} returned no output_audio for {seg_id}."
                )
            raw_audio = base64.b64decode(output_audio.data)
            mime_type = getattr(output_audio, "mime_type", None) or "audio/wav"
            dur_s = _normalize_audio_bytes_to_wav24k(raw_audio, mime_type, wav_path)
            _, seg_samples = _read_wav_samples(wav_path)
        else:
            assert erasmian_engine is not None
            synth = erasmian_engine.synthesize_sentence(
                greek_text, backend="google_erasmian"
            )
            pcm_bytes = synth.pcm16.tobytes()
            dur_s = _normalize_audio_bytes_to_wav24k(
                pcm_bytes, f"audio/l16;rate={synth.sample_rate}", wav_path
            )
            _, seg_samples = _read_wav_samples(wav_path)

        start_s = cursor_s
        end_s = start_s + dur_s
        master_samples.extend(seg_samples)
        cursor_s = end_s
        if idx < len(segments_spec) - 1:
            pause_samples = int(round(TTS_STEP_PAUSE_S * TTS_SAMPLE_RATE_HZ))
            master_samples.extend([0] * pause_samples)
            cursor_s += TTS_STEP_PAUSE_S

        timeline.append(
            {
                "id": seg_id,
                "label": label,
                "greek_text": greek_text,
                "wav_path": str(wav_path),
                "start_s": round(start_s, 3),
                "end_s": round(end_s, 3),
                "duration_s": round(dur_s, 3),
            }
        )

    master_wav = audio_dir / f"narration_{plan.slug}_{backend}.wav"
    with wave.open(str(master_wav), "wb") as wf_out:
        wf_out.setnchannels(TTS_CHANNELS)
        wf_out.setsampwidth(TTS_SAMPLE_WIDTH_BYTES)
        wf_out.setframerate(TTS_SAMPLE_RATE_HZ)
        wf_out.writeframes(master_samples.tobytes())

    total_s = len(master_samples) / float(TTS_SAMPLE_RATE_HZ)
    manifest = {
        "proposition_id": plan.proposition_id,
        "backend": backend,
        "tts_model": tts_model if backend == "gemini_tts" else "google_erasmian",
        "voice": voice if backend == "gemini_tts" else "en-AU-Chirp3-HD-Charon",
        "master_wav": str(master_wav),
        "total_duration_s": round(total_s, 3),
        "segments": timeline,
    }
    manifest_path = audio_dir / "narration_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def mux_genie_recording_to_mp4(
    frame_paths: list[Path],
    pcm_audio_path: Path | None,
    output_mp4: Path,
    *,
    fps: int = GENIE_FPS,
    audio_rate_hz: int = GENIE_AUDIO_RATE_HZ,
    audio_channels: int = GENIE_AUDIO_CHANNELS,
) -> Path:
    """Mux captured Genie 4 video frames and stereo PCM audio into an H.264/AAC MP4."""
    if not frame_paths:
        raise ValueError("Cannot mux MP4: zero video frames were captured.")
    ffmpeg_bin = _require_ffmpeg()
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    first_bytes = frame_paths[0].read_bytes()
    vcodec, _, _ = detect_video_frame_codec(first_bytes)
    has_audio = (
        pcm_audio_path is not None
        and pcm_audio_path.exists()
        and pcm_audio_path.stat().st_size > 0
    )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "image2pipe",
        "-vcodec",
        vcodec,
        "-framerate",
        str(fps),
        "-i",
        "-",
    ]
    if has_audio:
        cmd.extend(
            [
                "-f",
                "s16le",
                "-ar",
                str(audio_rate_hz),
                "-ac",
                str(audio_channels),
                "-i",
                str(pcm_audio_path),
            ]
        )

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            str(VIDEO_CRF),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
    )
    if has_audio:
        cmd.extend(
            [
                "-c:a",
                "aac",
                "-ar",
                str(AUDIO_OUT_RATE_HZ),
                "-ac",
                "2",
                "-b:a",
                AUDIO_OUT_BITRATE,
                "-shortest",
            ]
        )
    else:
        cmd.append("-an")
    cmd.append(str(output_mp4))

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame_path in frame_paths:
            proc.stdin.write(frame_path.read_bytes())
    finally:
        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"FFmpeg muxing exited with code {ret}.")

    if not output_mp4.exists() or output_mp4.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg produced an empty MP4 at {output_mp4}.")
    return output_mp4


def _mp4_has_audio_stream(mp4_path: Path) -> bool:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return True
    proc = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(mp4_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(proc.stdout.strip())


def mux_video_with_narration_mp4(
    genie_mp4: Path,
    narration_wav: Path,
    output_mp4: Path,
    *,
    ambient_volume: float = AMBIENT_MIX_VOLUME,
) -> Path:
    """Blend Genie 4's ambient audio gently beneath an Ancient Greek narration WAV."""
    ffmpeg_bin = _require_ffmpeg()
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if _mp4_has_audio_stream(genie_mp4):
        filter_graph = (
            f"[0:a]volume={ambient_volume:.3f}[amb];"
            f"[1:a]aformat=sample_rates={AUDIO_OUT_RATE_HZ}:channel_layouts=stereo[vox];"
            "[amb][vox]amix=inputs=2:duration=shortest:normalize=0[aout]"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(genie_mp4),
            "-i",
            str(narration_wav),
            "-filter_complex",
            filter_graph,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            str(AUDIO_OUT_RATE_HZ),
            "-ac",
            "2",
            "-b:a",
            AUDIO_OUT_BITRATE,
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_mp4),
        ]
    else:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(genie_mp4),
            "-i",
            str(narration_wav),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            str(AUDIO_OUT_RATE_HZ),
            "-ac",
            "2",
            "-b:a",
            AUDIO_OUT_BITRATE,
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_mp4),
        ]
    subprocess.run(cmd, check=True)
    return output_mp4
