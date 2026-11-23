"""Async Genie 4 Interactions API WebSocket session runner with guaranteed completion."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import tempfile
import time
from typing import Any

from . import (
    DEFAULT_DURATION_S,
    GENIE_API_VERSION,
    GENIE_AUDIO_CHANNELS,
    GENIE_AUDIO_RATE_HZ,
    GENIE_FPS,
    GENIE_MODEL,
    GENIE_VIDEO_PRICE_PER_1M_TOKENS_USD,
    GENIE_VIDEO_TOKENS_PER_FRAME,
    MAX_SESSION_DURATION_S,
)
from .media import (
    detect_video_frame_codec,
    mux_genie_recording_to_mp4,
    sniff_image_mime_type,
)
from .prompts import build_steering_prompt, build_world_setup_prompt
from .propositions import PropositionPlan

MIN_FIRST_STEER_FRAME = 24  # Let the opening world settle for >= 1.0 s before steering
MIN_TAIL_FRAMES = 24  # Leave >= 1.0 s after final steering prompt before completing
MIN_FRAMES_BETWEEN_STEERS = 24
WALL_TIMEOUT_MULTIPLIER = 3.0
WALL_TIMEOUT_BASE_S = 60.0


@dataclass(frozen=True)
class ScheduledSteer:
    """A mid-session text steering prompt pinned to a target video frame index."""

    frame_index: int
    step_id: str
    label: str
    prompt: str


@dataclass
class GenieRecordingReport:
    """Structured summary of a completed Genie 4 interactive capture run."""

    proposition_id: str
    interaction_id: str
    model: str
    seed_image_path: str
    output_mp4_path: str
    keyframes: list[str]
    video_frames: int
    audio_chunks: int
    audio_bytes: int
    audio_sample_rate_hz: int
    audio_channels: int
    fps: int
    detected_video_codec: str
    reported_video_mime: str
    actual_duration_s: float
    wall_elapsed_s: float
    estimated_video_tokens: int
    estimated_video_cost_usd: float
    completed_cleanly: bool
    steering_events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_steering_schedule(
    plan: PropositionPlan,
    target_frames: int,
    *,
    ambient_only_audio: bool = False,
) -> list[ScheduledSteer]:
    """Map ``plan.steps`` onto strictly increasing frame indices within ``target_frames``."""
    if target_frames <= MIN_FIRST_STEER_FRAME + MIN_TAIL_FRAMES or not plan.steps:
        return []

    max_steer_frame = target_frames - MIN_TAIL_FRAMES
    schedule: list[ScheduledSteer] = []
    last_frame = MIN_FIRST_STEER_FRAME - MIN_FRAMES_BETWEEN_STEERS

    for step in plan.steps:
        desired = int(round(step.offset_fraction * target_frames))
        clamped = max(MIN_FIRST_STEER_FRAME, min(max_steer_frame, desired))
        if clamped < last_frame + MIN_FRAMES_BETWEEN_STEERS:
            clamped = last_frame + MIN_FRAMES_BETWEEN_STEERS
        if clamped > max_steer_frame:
            break
        schedule.append(
            ScheduledSteer(
                frame_index=clamped,
                step_id=step.id,
                label=step.label,
                prompt=build_steering_prompt(
                    step, ambient_only_audio=ambient_only_audio
                ),
            )
        )
        last_frame = clamped

    return schedule


def _estimate_video_cost_usd(video_frames: int) -> tuple[int, float]:
    tokens = video_frames * GENIE_VIDEO_TOKENS_PER_FRAME
    cost = (tokens / 1_000_000.0) * GENIE_VIDEO_PRICE_PER_1M_TOKENS_USD
    return tokens, round(cost, 4)


async def record_genie4_session(
    plan: PropositionPlan,
    api_key: str,
    output_dir: Path,
    *,
    seed_image_path: Path | None = None,
    duration_s: float = DEFAULT_DURATION_S,
    ambient_only_audio: bool = False,
    model: str = GENIE_MODEL,
    client_override: Any | None = None,
) -> GenieRecordingReport:
    """Run an end-to-end Genie 4 WebSocket session and mux the result to MP4.

    Always invokes ``await session.complete()`` in a ``finally`` block so
    server-side Genie 4 generation and billing terminate promptly on completion,
    error, or cancellation.
    """
    if duration_s <= 0.0:
        raise ValueError(f"duration_s must be positive, got {duration_s}.")
    if duration_s > MAX_SESSION_DURATION_S:
        raise ValueError(
            f"duration_s={duration_s} exceeds hard safety cap of "
            f"{MAX_SESSION_DURATION_S:.0f} s to prevent runaway Genie 4 billing."
        )
    if client_override is None and not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY for Genie 4 session.")

    if client_override is not None:
        client = client_override
    else:
        from google import genai

        client = genai.Client(
            api_key=api_key, http_options={"api_version": GENIE_API_VERSION}
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    keyframes_dir = output_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    target_frames = max(1, int(math.ceil(duration_s * GENIE_FPS)))
    world_prompt = build_world_setup_prompt(
        plan, ambient_only_audio=ambient_only_audio
    )
    schedule = build_steering_schedule(
        plan, target_frames, ambient_only_audio=ambient_only_audio
    )
    steer_by_frame = {item.frame_index: item for item in schedule}

    world_setup_event: dict[str, Any] = {
        "event_type": "world_setup",
        "world_prompt": {"text": world_prompt},
    }
    if seed_image_path is not None:
        seed_bytes = seed_image_path.read_bytes()
        world_setup_event["reference_image"] = {
            "data": base64.b64encode(seed_bytes).decode("ascii"),
            "mime_type": sniff_image_mime_type(seed_bytes),
        }

    wall_start = time.monotonic()
    interaction = await client.aio.interactions.create(
        model=model, api_version=GENIE_API_VERSION
    )
    interaction_id = str(getattr(interaction, "id", ""))

    video_frames = 0
    audio_chunks = 0
    audio_bytes = 0
    audio_sr = GENIE_AUDIO_RATE_HZ
    audio_ch = GENIE_AUDIO_CHANNELS
    detected_codec = "mjpeg"
    detected_ext = ".jpg"
    reported_mime = ""
    completed_cleanly = False
    complete_sent = False
    steering_log: list[dict[str, Any]] = []
    errors: list[str] = []
    saved_keyframes: list[str] = []

    wall_timeout_s = duration_s * WALL_TIMEOUT_MULTIPLIER + WALL_TIMEOUT_BASE_S

    with tempfile.TemporaryDirectory(prefix="genie4_frames_") as tmp_str:
        tmp_dir = Path(tmp_str)
        frame_paths: list[Path] = []
        pcm_path = tmp_dir / "audio_stream.pcm"

        async def _stream_loop(session: Any, pcm_fh: Any) -> None:
            nonlocal video_frames, audio_chunks, audio_bytes, audio_sr, audio_ch
            nonlocal detected_codec, detected_ext, reported_mime
            nonlocal completed_cleanly, complete_sent

            await session.send(world_setup_event)
            async for event in session.receive():
                event_type = getattr(event, "event_type", "")
                if event_type == "step.delta":
                    delta = getattr(event, "delta", None)
                    delta_type = getattr(delta, "type", None)
                    if delta_type == "video" and getattr(delta, "data", None):
                        raw_frame = base64.b64decode(delta.data)
                        if video_frames == 0:
                            detected_codec, detected_ext, _ = detect_video_frame_codec(
                                raw_frame
                            )
                            reported_mime = str(getattr(delta, "mime_type", "") or "")
                        video_frames += 1
                        frame_file = tmp_dir / f"frame_{video_frames:06d}{detected_ext}"
                        frame_file.write_bytes(raw_frame)
                        frame_paths.append(frame_file)

                        if video_frames == 1:
                            kf = keyframes_dir / f"keyframe_00_start{detected_ext}"
                            kf.write_bytes(raw_frame)
                            saved_keyframes.append(str(kf))

                        if video_frames in steer_by_frame and not complete_sent:
                            steer = steer_by_frame[video_frames]
                            await session.send(steer.prompt)
                            kf = (
                                keyframes_dir
                                / f"keyframe_{steer.step_id}{detected_ext}"
                            )
                            kf.write_bytes(raw_frame)
                            saved_keyframes.append(str(kf))
                            steering_log.append(
                                {
                                    "frame": video_frames,
                                    "time_s": round(video_frames / float(GENIE_FPS), 2),
                                    "step_id": steer.step_id,
                                    "label": steer.label,
                                }
                            )

                        if video_frames >= target_frames and not complete_sent:
                            kf_end = keyframes_dir / f"keyframe_99_end{detected_ext}"
                            kf_end.write_bytes(raw_frame)
                            saved_keyframes.append(str(kf_end))
                            complete_sent = True
                            await session.complete()

                    elif delta_type == "audio" and getattr(delta, "data", None):
                        raw_pcm = base64.b64decode(delta.data)
                        if getattr(delta, "sample_rate", None):
                            audio_sr = int(delta.sample_rate)
                        if getattr(delta, "channels", None):
                            audio_ch = int(delta.channels)
                        pcm_fh.write(raw_pcm)
                        audio_chunks += 1
                        audio_bytes += len(raw_pcm)

                elif event_type == "interaction.completed":
                    completed_cleanly = True
                    break
                elif event_type in ("interaction.cancelled", "error"):
                    err_obj = getattr(event, "error", None)
                    errors.append(f"{event_type}: {err_obj}")
                    break

        with pcm_path.open("wb") as pcm_fh:
            async with client.aio.interactions.connect(
                interaction_id, api_version=GENIE_API_VERSION
            ) as session:
                try:
                    await asyncio.wait_for(
                        _stream_loop(session, pcm_fh), timeout=wall_timeout_s
                    )
                except asyncio.TimeoutError:
                    errors.append(
                        f"Session timed out after {wall_timeout_s:.1f}s wall clock."
                    )
                finally:
                    if not completed_cleanly:
                        try:
                            await session.complete()
                        except Exception:
                            pass

        out_mp4 = output_dir / f"euclid_{plan.slug}_genie4.mp4"
        mux_genie_recording_to_mp4(
            frame_paths,
            pcm_path if audio_bytes > 0 else None,
            out_mp4,
            fps=GENIE_FPS,
            audio_rate_hz=audio_sr,
            audio_channels=audio_ch,
        )

    wall_elapsed_s = round(time.monotonic() - wall_start, 2)
    actual_duration_s = round(video_frames / float(GENIE_FPS), 3)
    est_tokens, est_cost = _estimate_video_cost_usd(video_frames)

    report = GenieRecordingReport(
        proposition_id=plan.proposition_id,
        interaction_id=interaction_id,
        model=model,
        seed_image_path=str(seed_image_path) if seed_image_path else "",
        output_mp4_path=str(out_mp4),
        keyframes=saved_keyframes,
        video_frames=video_frames,
        audio_chunks=audio_chunks,
        audio_bytes=audio_bytes,
        audio_sample_rate_hz=audio_sr,
        audio_channels=audio_ch,
        fps=GENIE_FPS,
        detected_video_codec=detected_codec,
        reported_video_mime=reported_mime,
        actual_duration_s=actual_duration_s,
        wall_elapsed_s=wall_elapsed_s,
        estimated_video_tokens=est_tokens,
        estimated_video_cost_usd=est_cost,
        completed_cleanly=completed_cleanly,
        steering_events=steering_log,
        errors=errors,
    )
    report_path = output_dir / "session_report.json"
    report_path.write_text(
        json.dumps(report.__dict__, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report
