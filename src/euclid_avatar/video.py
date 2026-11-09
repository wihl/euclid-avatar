"""Offline 1080p (16:9) video renderer for the 5-minute Elements II.13 presentation.

Renders the full 5-slide Book II, Proposition 13 presentation (and individual
per-slide videos) as full-bleed 1920x1080 (16:9) H.264/AAC MP4 files ready to
embed directly in Google Slides (Google Presentation), with sample-accurate
single-word sequential karaoke highlighting and animated geometric figure cues.
"""

from __future__ import annotations

import array
import base64
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from typing import Any
import urllib.request
import wave

import yaml

from .stage_html import AVATAR_HTML

# Video resolution, aspect ratio, and encoding constants (16:9 Full HD for Google Slides)
VIDEO_WIDTH_PX = 1920
VIDEO_HEIGHT_PX = 1080
VIDEO_FPS = 30
VIDEO_CRF = 18
AUDIO_INPUT_SAMPLE_RATE_HZ = 24000
AUDIO_OUTPUT_SAMPLE_RATE_HZ = 48000
AUDIO_OUTPUT_CHANNELS = 2
AUDIO_BITRATE = "192k"

# Audio sample scaling and silence-tightening constants
PCM16_MAX_VALUE = 32767
PCM16_MIN_VALUE = -32768
SILENCE_WINDOW_S = 0.010
SILENCE_AMPLITUDE_THRESHOLD = 350
MAX_CONSECUTIVE_SILENT_WINDOWS = 8  # Cap internal pauses at 80 ms (8 * 10 ms)
CROSSFADE_SAMPLES = 96  # 4 ms smooth transition @ 24 kHz inside silent regions

# Presentation pacing constants
DEFAULT_TARGET_DURATION_S = 300.0  # 5 minutes (300 seconds)
FAST_INTER_SEGMENT_PAUSE_S = 0.16
FAST_INTER_SLIDE_PAUSE_S = 0.32
UNABRIDGED_INTER_SEGMENT_PAUSE_S = 0.32
UNABRIDGED_INTER_SLIDE_PAUSE_S = 0.65
GREEK_READING_TEMPO_CAP = 1.22  # Keep pure-Greek enunciation/spec readings deliberate
MIN_TEMPO_FACTOR = 1.0
MAX_TEMPO_FACTOR = 1.48
MIN_FRAME_INTERVAL_S = 0.04  # Minimum 40 ms hold per visual state frame

# Chrome DevTools Protocol (CDP) connection constants
CHROME_BINARY_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
CDP_STARTUP_TIMEOUT_S = 12.0
CDP_POLL_INTERVAL_S = 0.10
CDP_SOCKET_TIMEOUT_S = 30.0
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_TEXT_FRAME_OPCODE = 0x81
WS_MASK_BIT = 0x80
WS_PAYLOAD_LEN_16BIT = 126
WS_PAYLOAD_LEN_64BIT = 127
WS_MAX_16BIT_LEN = 65535

# Segments that re-walk a slide from the top and should reset highlight cursors
RESET_CURSOR_SEGMENT_IDS = frozenset(
    {
        "s1_intro_and_greek",
        "s1_translation",
        "s1_hinge_and_roadmap",
        "s2_spec_reading",
        "s2_three_cases_walkthrough",
        "s2_equation_and_bamberg",
        "s3_word_for_word",
        "s4_square_and_rectangle",
        "s5_comparison_of_two_steps",
    }
)
GREEK_HEAVY_SEGMENT_IDS = frozenset(
    {
        "s1_intro_and_greek",
        "s2_spec_reading",
    }
)


@dataclass
class PreparedSegmentMedia:
    """Processed PCM samples and time-warped word timings for a single presentation segment."""

    segment_id: str
    slide_number: int
    slide_title: str
    pcm_samples: array.array
    duration_s: float
    word_timings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FrameInterval:
    """A single visual state image and its exact duration in seconds."""

    image_path: Path
    duration_s: float
    slide_number: int


class _LocalCDPClient:
    """Minimal RFC 6455 WebSocket client for local Chrome DevTools Protocol communication."""

    def __init__(self, ws_url: str) -> None:
        # Parse ws://127.0.0.1:<port>/<path>
        without_scheme = ws_url.removeprefix("ws://")
        host_port, _, path = without_scheme.partition("/")
        host, _, port_str = host_port.partition(":")
        self._sock = socket.create_connection(
            (host, int(port_str)), timeout=CDP_SOCKET_TIMEOUT_S
        )
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(handshake.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise RuntimeError("CDP WebSocket handshake closed unexpectedly.")
            response += chunk
        expected_accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept.encode("ascii") not in response:
            raise RuntimeError("CDP WebSocket handshake validation failed.")
        self._buffer = response.split(b"\r\n\r\n", 1)[1]
        self._next_id = 1

    def _recv_exact(self, num_bytes: int) -> bytes:
        while len(self._buffer) < num_bytes:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise RuntimeError("Unexpected EOF from Chrome DevTools WebSocket.")
            self._buffer += chunk
        out = self._buffer[:num_bytes]
        self._buffer = self._buffer[num_bytes:]
        return out

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([WS_TEXT_FRAME_OPCODE])
        length = len(payload)
        if length < WS_PAYLOAD_LEN_16BIT:
            header.append(WS_MASK_BIT | length)
        elif length <= WS_MAX_16BIT_LEN:
            header.append(WS_MASK_BIT | WS_PAYLOAD_LEN_16BIT)
            header.extend(struct.pack("!H", length))
        else:
            header.append(WS_MASK_BIT | WS_PAYLOAD_LEN_64BIT)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytearray(length)
        for i, byte_val in enumerate(payload):
            masked[i] = byte_val ^ mask[i & 3]
        self._sock.sendall(header + masked)

    def _recv_message(self) -> dict[str, Any]:
        while True:
            first_two = self._recv_exact(2)
            opcode = first_two[0] & 0x0F
            masked = bool(first_two[1] & WS_MASK_BIT)
            length = first_two[1] & 0x7F
            if length == WS_PAYLOAD_LEN_16BIT:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == WS_PAYLOAD_LEN_64BIT:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
            if opcode == 0x01:  # Text frame
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x08:  # Close frame
                raise RuntimeError("Chrome DevTools WebSocket closed.")

    def call(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        req = {"id": msg_id, "method": method, "params": params or {}}
        self._send_text(json.dumps(req, ensure_ascii=False))
        while True:
            msg = self._recv_message()
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                return msg.get("result", {})

    def evaluate_js(self, expression: str) -> Any:
        res = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in res:
            raise RuntimeError(
                f"JS exception during video render: {res['exceptionDetails']}"
            )
        return res.get("result", {}).get("value")

    def capture_png(self, dest_path: Path) -> None:
        res = self.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "clip": {
                    "x": 0,
                    "y": 0,
                    "width": VIDEO_WIDTH_PX,
                    "height": VIDEO_HEIGHT_PX,
                    "scale": 1,
                },
            },
        )
        dest_path.write_bytes(base64.b64decode(res["data"]))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _find_chrome_binary() -> str:
    for candidate in CHROME_BINARY_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    which_chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if which_chrome:
        return which_chrome
    raise FileNotFoundError(
        "Google Chrome binary not found for headless 1080p rendering."
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_wav_pcm16(wav_path: Path) -> tuple[array.array, int]:
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    samples = array.array("h")
    samples.frombytes(raw)
    if nch > 1:
        mono = array.array("h", (samples[i] for i in range(0, len(samples), nch)))
        samples = mono
    return samples, sr


def _write_wav_pcm16(
    wav_path: Path, samples: array.array, sr: int = AUDIO_INPUT_SAMPLE_RATE_HZ
) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())


def _tighten_silence_with_time_map(
    samples: array.array,
    sr: int = AUDIO_INPUT_SAMPLE_RATE_HZ,
) -> tuple[array.array, list[float], list[float]]:
    """Cap long internal silent pauses at 80 ms and return (trimmed_pcm, orig_t, trimmed_t)."""
    win_samples = int(round(SILENCE_WINDOW_S * sr))
    out = array.array("h")
    orig_times: list[float] = [0.0]
    trimmed_times: list[float] = [0.0]

    silent_run = 0
    total_samples = len(samples)
    pos = 0
    while pos < total_samples:
        end = min(pos + win_samples, total_samples)
        chunk = samples[pos:end]
        peak = max((abs(x) for x in chunk), default=0)
        if peak < SILENCE_AMPLITUDE_THRESHOLD:
            silent_run += 1
            if silent_run <= MAX_CONSECUTIVE_SILENT_WINDOWS:
                out.extend(chunk)
        else:
            if silent_run > MAX_CONSECUTIVE_SILENT_WINDOWS and len(out) >= CROSSFADE_SAMPLES:
                # Apply a gentle 4 ms fade-in ramp at the end of the kept silence
                fade_len = min(CROSSFADE_SAMPLES, len(chunk))
                for k in range(fade_len):
                    weight = 0.5 * (1.0 - math.cos(math.pi * k / float(fade_len)))
                    chunk[k] = int(round(chunk[k] * weight))
            silent_run = 0
            out.extend(chunk)
        pos = end
        orig_times.append(pos / float(sr))
        trimmed_times.append(len(out) / float(sr))

    return out, orig_times, trimmed_times


def _interp_piecewise(
    t_val: float, x_grid: list[float], y_grid: list[float]
) -> float:
    """Linearly interpolate t_val from x_grid to y_grid using binary search."""
    if not x_grid or t_val <= x_grid[0]:
        return y_grid[0] if y_grid else t_val
    if t_val >= x_grid[-1]:
        return y_grid[-1]
    lo = 0
    hi = len(x_grid) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if x_grid[mid] <= t_val:
            lo = mid
        else:
            hi = mid
    dx = x_grid[hi] - x_grid[lo]
    if dx <= 1e-9:
        return y_grid[lo]
    frac = (t_val - x_grid[lo]) / dx
    return y_grid[lo] + frac * (y_grid[hi] - y_grid[lo])


def _apply_ffmpeg_atempo(
    samples: array.array,
    tempo: float,
    sr: int = AUDIO_INPUT_SAMPLE_RATE_HZ,
) -> array.array:
    """Apply pitch-preserving WSOLA time-scaling via FFmpeg atempo."""
    if abs(tempo - 1.0) < 0.005 or not samples:
        return samples
    clamped_tempo = max(MIN_TEMPO_FACTOR, min(MAX_TEMPO_FACTOR, tempo))
    res = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-af",
            f"atempo={clamped_tempo:.5f}",
            "-f",
            "s16le",
            "pipe:1",
        ],
        input=samples.tobytes(),
        capture_output=True,
        check=True,
        timeout=30,
    )
    out = array.array("h")
    out.frombytes(res.stdout)
    return out


def _prepare_all_segments(
    slides_raw: list[dict[str, Any]],
    cache_dir: Path,
    voice: str,
    target_duration_s: float | None,
) -> tuple[list[PreparedSegmentMedia], float, float]:
    """Load cached segment WAVs/timings and time-calibrate to target_duration_s if set."""
    safe_voice = voice.replace("/", "_")
    raw_items: list[tuple[dict[str, Any], int, str, array.array, list[dict[str, Any]]]] = []
    for s_raw in slides_raw:
        s_num = int(s_raw["slide_number"])
        s_title = str(s_raw["title"])
        for seg_raw in s_raw.get("segments", []):
            seg_id = str(seg_raw["id"])
            wav_path = cache_dir / f"{seg_id}_{safe_voice}.wav"
            timings_path = cache_dir / f"{seg_id}_{safe_voice}.timings.json"
            if not wav_path.exists():
                raise FileNotFoundError(f"Cached segment WAV missing: {wav_path}")
            pcm, _ = _read_wav_pcm16(wav_path)
            timings = json.loads(timings_path.read_text(encoding="utf-8"))
            raw_items.append((seg_raw, s_num, s_title, pcm, timings))

    if target_duration_s is None:
        # Unabridged 1.0x mode
        prepared: list[PreparedSegmentMedia] = []
        for seg_raw, s_num, s_title, pcm, timings in raw_items:
            dur_s = len(pcm) / float(AUDIO_INPUT_SAMPLE_RATE_HZ)
            prepared.append(
                PreparedSegmentMedia(
                    segment_id=str(seg_raw["id"]),
                    slide_number=s_num,
                    slide_title=s_title,
                    pcm_samples=pcm,
                    duration_s=dur_s,
                    word_timings=timings,
                )
            )
        return (
            prepared,
            UNABRIDGED_INTER_SEGMENT_PAUSE_S,
            UNABRIDGED_INTER_SLIDE_PAUSE_S,
        )

    # First pass: tighten excessive internal silent pauses (>80 ms)
    tightened_items: list[
        tuple[dict[str, Any], int, str, array.array, list[float], list[float], list[dict[str, Any]]]
    ] = []
    greek_heavy_dur = 0.0
    other_dur = 0.0
    for seg_raw, s_num, s_title, pcm, timings in raw_items:
        seg_id = str(seg_raw["id"])
        trimmed_pcm, orig_grid, trim_grid = _tighten_silence_with_time_map(
            pcm, AUDIO_INPUT_SAMPLE_RATE_HZ
        )
        trim_dur = len(trimmed_pcm) / float(AUDIO_INPUT_SAMPLE_RATE_HZ)
        if seg_id in GREEK_HEAVY_SEGMENT_IDS:
            greek_heavy_dur += trim_dur
        else:
            other_dur += trim_dur
        tightened_items.append(
            (seg_raw, s_num, s_title, trimmed_pcm, orig_grid, trim_grid, timings)
        )

    num_slides = len(slides_raw)
    num_segments = len(raw_items)
    total_pauses_s = (
        (num_segments - num_slides) * FAST_INTER_SEGMENT_PAUSE_S
        + max(0, num_slides - 1) * FAST_INTER_SLIDE_PAUSE_S
    )
    available_speech_s = max(60.0, target_duration_s - total_pauses_s)
    greek_after_tempo_s = greek_heavy_dur / GREEK_READING_TEMPO_CAP
    remaining_budget_s = max(30.0, available_speech_s - greek_after_tempo_s)
    general_tempo = max(
        MIN_TEMPO_FACTOR,
        min(MAX_TEMPO_FACTOR, other_dur / remaining_budget_s),
    )

    prepared_fast: list[PreparedSegmentMedia] = []
    for (
        seg_raw,
        s_num,
        s_title,
        trimmed_pcm,
        orig_grid,
        trim_grid,
        timings,
    ) in tightened_items:
        seg_id = str(seg_raw["id"])
        tempo = (
            GREEK_READING_TEMPO_CAP
            if seg_id in GREEK_HEAVY_SEGMENT_IDS
            else general_tempo
        )
        scaled_pcm = _apply_ffmpeg_atempo(
            trimmed_pcm, tempo, AUDIO_INPUT_SAMPLE_RATE_HZ
        )
        trim_dur = max(1e-6, len(trimmed_pcm) / float(AUDIO_INPUT_SAMPLE_RATE_HZ))
        final_dur = len(scaled_pcm) / float(AUDIO_INPUT_SAMPLE_RATE_HZ)
        exact_scale = final_dur / trim_dur

        warped_timings: list[dict[str, Any]] = []
        for w in timings:
            t0_trim = _interp_piecewise(float(w["start_s"]), orig_grid, trim_grid)
            t1_trim = _interp_piecewise(float(w["end_s"]), orig_grid, trim_grid)
            w_copy = dict(w)
            w_copy["start_s"] = round(t0_trim * exact_scale, 4)
            w_copy["end_s"] = round(
                max(t0_trim * exact_scale + 0.02, t1_trim * exact_scale), 4
            )
            warped_timings.append(w_copy)

        prepared_fast.append(
            PreparedSegmentMedia(
                segment_id=seg_id,
                slide_number=s_num,
                slide_title=s_title,
                pcm_samples=scaled_pcm,
                duration_s=final_dur,
                word_timings=warped_timings,
            )
        )

    return prepared_fast, FAST_INTER_SEGMENT_PAUSE_S, FAST_INTER_SLIDE_PAUSE_S


def _encode_mp4_from_intervals(
    intervals: list[FrameInterval],
    audio_wav_path: Path,
    output_mp4_path: Path,
    work_dir: Path,
) -> dict[str, Any]:
    """Encode a 1920x1080 30fps H.264 + 48kHz stereo AAC MP4 from timed still intervals."""
    concat_file = work_dir / f"concat_{output_mp4_path.stem}.txt"
    lines: list[str] = []
    for item in intervals:
        safe_path = str(item.image_path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
        lines.append(f"duration {max(MIN_FRAME_INTERVAL_S, item.duration_s):.6f}")
    if intervals:
        last_safe = str(intervals[-1].image_path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{last_safe}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-i",
        str(audio_wav_path),
        "-vf",
        f"fps={VIDEO_FPS},scale={VIDEO_WIDTH_PX}:{VIDEO_HEIGHT_PX}:flags=lanczos,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(VIDEO_CRF),
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-c:a",
        "aac",
        "-b:a",
        AUDIO_BITRATE,
        "-ar",
        str(AUDIO_OUTPUT_SAMPLE_RATE_HZ),
        "-ac",
        str(AUDIO_OUTPUT_CHANNELS),
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_mp4_path),
    ]
    subprocess.run(cmd, check=True, timeout=300)
    size_mb = round(output_mp4_path.stat().st_size / (1024.0 * 1024.0), 2)
    total_dur_s = round(sum(i.duration_s for i in intervals), 2)
    return {
        "path": str(output_mp4_path),
        "duration_s": total_dur_s,
        "duration_min": round(total_dur_s / 60.0, 2),
        "size_mb": size_mb,
        "resolution": f"{VIDEO_WIDTH_PX}x{VIDEO_HEIGHT_PX}",
        "aspect_ratio": "16:9",
        "fps": VIDEO_FPS,
    }


def render_presentation_videos(
    presentation_yaml_path: Path,
    cache_dir: Path,
    output_dir: Path,
    *,
    voice: str = "en-AU-Chirp3-HD-Charon",
    target_duration_s: float | None = None,
    render_per_slide: bool = False,
) -> dict[str, Any]:
    """Render the full 16:9 (1920x1080) presentation MP4 at original speed and spacing."""
    t0 = time.perf_counter()
    raw_yaml = yaml.safe_load(presentation_yaml_path.read_text(encoding="utf-8")) or {}
    pres_spec = raw_yaml.get("presentation", {})
    slides_raw: list[dict[str, Any]] = list(pres_spec.get("slides", []))
    total_slides = len(slides_raw)

    segments, seg_pause_s, slide_pause_s = _prepare_all_segments(
        slides_raw, cache_dir, voice, target_duration_s
    )

    # Calculate total timeline duration for progress bar
    total_speech_s = sum(s.duration_s for s in segments)
    total_timeline_s = (
        total_speech_s
        + max(0, len(segments) - total_slides) * seg_pause_s
        + max(0, total_slides - 1) * slide_pause_s
    )

    chrome_bin = _find_chrome_binary()
    debug_port = _pick_free_port()

    with tempfile.TemporaryDirectory(prefix="euclid_video_render_") as tmp_str:
        work_dir = Path(tmp_str)
        html_file = work_dir / "stage.html"
        html_file.write_text(AVATAR_HTML, encoding="utf-8")
        user_data_dir = work_dir / "chrome_profile"
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        chrome_proc = subprocess.Popen(
            [
                chrome_bin,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--hide-scrollbars",
                f"--user-data-dir={user_data_dir}",
                f"--window-size={VIDEO_WIDTH_PX},{VIDEO_HEIGHT_PX}",
                f"--remote-debugging-port={debug_port}",
                f"file://{html_file.resolve()}?video=1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            # Wait for Chrome DevTools JSON endpoint
            ws_url = ""
            deadline = time.perf_counter() + CDP_STARTUP_TIMEOUT_S
            while time.perf_counter() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{debug_port}/json", timeout=1.0
                    ) as resp:
                        targets = json.loads(resp.read().decode("utf-8"))
                        for t in targets:
                            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                                ws_url = t["webSocketDebuggerUrl"]
                                break
                    if ws_url:
                        break
                except Exception:
                    pass
                time.sleep(CDP_POLL_INTERVAL_S)

            if not ws_url:
                raise RuntimeError("Failed to connect to headless Chrome DevTools.")

            cdp = _LocalCDPClient(ws_url)
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": VIDEO_WIDTH_PX,
                    "height": VIDEO_HEIGHT_PX,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )

            # Verify zero layout overflow across all 5 slides
            layout_checks: list[dict[str, Any]] = []
            for s_raw in slides_raw:
                slide_json = json.dumps(s_raw, ensure_ascii=False)
                cdp.evaluate_js(
                    f"window.prepareSlideForVideo({slide_json}, {total_slides});"
                )
                metrics = cdp.evaluate_js(
                    """(() => {
                      const sc = document.querySelector('.slide-card');
                      const sb = document.getElementById('slideBody');
                      const dc = document.querySelector('.diagram-card');
                      return {
                        slide_client_h: sc.clientHeight,
                        slide_scroll_h: sc.scrollHeight,
                        body_client_h: sb.clientHeight,
                        body_scroll_h: sb.scrollHeight,
                        diag_client_h: dc.clientHeight,
                        diag_scroll_h: dc.scrollHeight
                      };
                    })()"""
                )
                layout_checks.append(
                    {"slide_number": int(s_raw["slide_number"]), **metrics}
                )

            # Step through each slide and segment to capture visual state keyframes
            state_image_cache: dict[str, Path] = {}
            all_intervals: list[FrameInterval] = []
            per_slide_intervals: dict[int, list[FrameInterval]] = {
                int(s["slide_number"]): [] for s in slides_raw
            }
            full_pcm = array.array("h")
            per_slide_pcm: dict[int, array.array] = {
                int(s["slide_number"]): array.array("h") for s in slides_raw
            }

            seg_pause_samples = array.array(
                "h", [0] * int(round(seg_pause_s * AUDIO_INPUT_SAMPLE_RATE_HZ))
            )
            slide_pause_samples = array.array(
                "h", [0] * int(round(slide_pause_s * AUDIO_INPUT_SAMPLE_RATE_HZ))
            )

            global_elapsed_s = 0.0
            frame_counter = 0

            def capture_state_sig(sig: str) -> Path:
                nonlocal frame_counter
                # Quantize progress bar to 1% buckets in cache key so identical visual states reuse PNGs
                if sig in state_image_cache:
                    return state_image_cache[sig]
                frame_counter += 1
                img_path = frames_dir / f"state_{frame_counter:04d}.png"
                cdp.capture_png(img_path)
                state_image_cache[sig] = img_path
                return img_path

            # Group segments by slide
            segs_by_slide: dict[int, list[PreparedSegmentMedia]] = {}
            for seg in segments:
                segs_by_slide.setdefault(seg.slide_number, []).append(seg)

            for s_idx, s_raw in enumerate(slides_raw):
                s_num = int(s_raw["slide_number"])
                slide_segs = segs_by_slide.get(s_num, [])
                slide_json = json.dumps(s_raw, ensure_ascii=False)
                cdp.evaluate_js(
                    f"window.prepareSlideForVideo({slide_json}, {total_slides});"
                )

                for seg_idx, seg in enumerate(slide_segs):
                    reset_cursors = (
                        seg_idx == 0 or seg.segment_id in RESET_CURSOR_SEGMENT_IDS
                    )
                    timings_json = json.dumps(seg.word_timings, ensure_ascii=False)
                    cdp.evaluate_js(
                        f"window.prepareSegmentForVideo({timings_json}, {str(reset_cursors).lower()});"
                    )

                    full_pcm.extend(seg.pcm_samples)
                    per_slide_pcm[s_num].extend(seg.pcm_samples)

                    w_list = seg.word_timings
                    seg_dur = seg.duration_s

                    if not w_list:
                        pct = (global_elapsed_s / max(1.0, total_timeline_s)) * 100.0
                        sig = cdp.evaluate_js(
                            f"window.stepVideoWord(-1, ['acute_triangle'], '', {pct:.2f});"
                        )
                        img_p = capture_state_sig(sig)
                        interval = FrameInterval(img_p, seg_dur, s_num)
                        all_intervals.append(interval)
                        per_slide_intervals[s_num].append(interval)
                        global_elapsed_s += seg_dur
                    else:
                        # Lead-in before word 0 if start_s > 0
                        first_start = max(0.0, float(w_list[0]["start_s"]))
                        if first_start > 0.01:
                            pct = (global_elapsed_s / max(1.0, total_timeline_s)) * 100.0
                            cues0 = json.dumps(
                                w_list[0].get("diagram_cues", ["acute_triangle"]),
                                ensure_ascii=False,
                            )
                            ban0 = json.dumps(
                                w_list[0].get("cue_banner", ""), ensure_ascii=False
                            )
                            sig = cdp.evaluate_js(
                                f"window.stepVideoWord(-1, {cues0}, {ban0}, {pct:.2f});"
                            )
                            img_p = capture_state_sig(sig)
                            interval = FrameInterval(img_p, first_start, s_num)
                            all_intervals.append(interval)
                            per_slide_intervals[s_num].append(interval)

                        for w_i, w in enumerate(w_list):
                            w_start = max(0.0, float(w["start_s"]))
                            w_next = (
                                float(w_list[w_i + 1]["start_s"])
                                if w_i + 1 < len(w_list)
                                else seg_dur
                            )
                            dt = max(0.0, w_next - w_start)
                            pct = (
                                (global_elapsed_s + w_start)
                                / max(1.0, total_timeline_s)
                            ) * 100.0
                            cues_js = json.dumps(
                                w.get("diagram_cues", []), ensure_ascii=False
                            )
                            ban_js = json.dumps(
                                w.get("cue_banner", ""), ensure_ascii=False
                            )
                            sig = cdp.evaluate_js(
                                f"window.stepVideoWord({w_i}, {cues_js}, {ban_js}, {pct:.2f});"
                            )
                            if dt <= 1e-4:
                                continue
                            img_p = capture_state_sig(sig)
                            # Merge with previous interval if identical image on same slide
                            if (
                                all_intervals
                                and all_intervals[-1].image_path == img_p
                                and all_intervals[-1].slide_number == s_num
                            ):
                                all_intervals[-1].duration_s += dt
                                per_slide_intervals[s_num][-1].duration_s += dt
                            else:
                                interval = FrameInterval(img_p, dt, s_num)
                                all_intervals.append(interval)
                                per_slide_intervals[s_num].append(
                                    FrameInterval(img_p, dt, s_num)
                                )

                        global_elapsed_s += seg_dur

                    # Add inter-segment pause within the same slide
                    if seg_idx < len(slide_segs) - 1:
                        full_pcm.extend(seg_pause_samples)
                        per_slide_pcm[s_num].extend(seg_pause_samples)
                        if all_intervals:
                            all_intervals[-1].duration_s += seg_pause_s
                        if per_slide_intervals[s_num]:
                            per_slide_intervals[s_num][-1].duration_s += seg_pause_s
                        global_elapsed_s += seg_pause_s

                # Add inter-slide pause between slides in the full deck video
                if s_idx < len(slides_raw) - 1:
                    full_pcm.extend(slide_pause_samples)
                    if all_intervals:
                        all_intervals[-1].duration_s += slide_pause_s
                    global_elapsed_s += slide_pause_s

            cdp.close()
        finally:
            chrome_proc.terminate()
            try:
                chrome_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome_proc.kill()

        # Write combined WAV and encode full MP4
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = (
            f"_{int(target_duration_s)}s"
            if target_duration_s is not None
            else ""
        )
        full_wav_path = work_dir / f"full{suffix}.wav"
        _write_wav_pcm16(full_wav_path, full_pcm, AUDIO_INPUT_SAMPLE_RATE_HZ)

        full_mp4_path = output_dir / f"euclid_ii13_presentation{suffix}.mp4"
        full_video_meta = _encode_mp4_from_intervals(
            all_intervals, full_wav_path, full_mp4_path, work_dir
        )

        slide_videos_meta: list[dict[str, Any]] = []
        if render_per_slide:
            for s_raw in slides_raw:
                s_num = int(s_raw["slide_number"])
                s_id = str(s_raw["id"])
                s_wav = work_dir / f"{s_id}{suffix}.wav"
                _write_wav_pcm16(
                    s_wav, per_slide_pcm[s_num], AUDIO_INPUT_SAMPLE_RATE_HZ
                )
                s_mp4 = output_dir / f"{s_id}{suffix}.mp4"
                meta = _encode_mp4_from_intervals(
                    per_slide_intervals[s_num], s_wav, s_mp4, work_dir
                )
                meta["slide_number"] = s_num
                meta["slide_title"] = str(s_raw["title"])
                slide_videos_meta.append(meta)

        elapsed_s = round(time.perf_counter() - t0, 2)
        return {
            "mode": "original_pacing" if target_duration_s is None else f"{target_duration_s}s",
            "voice": voice,
            "unique_visual_states": frame_counter,
            "total_intervals": len(all_intervals),
            "render_elapsed_s": elapsed_s,
            "layout_checks": layout_checks,
            "full_video": full_video_meta,
            "slide_videos": slide_videos_meta,
        }


def main(argv: list[str] | None = None) -> int:
    """Standalone CLI entry point for rendering the 16:9 presentation video."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Render the 1920x1080 (16:9) Elements II.13 presentation MP4 video."
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path("presentation_ii13.yaml"),
        help="Path to presentation_ii13.yaml",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/presentation_ii13"),
        help="Path to cached TTS segment WAVs and .timings.json files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/videos"),
        help="Output directory for generated MP4 video",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="en-AU-Chirp3-HD-Charon",
        help="Voice identifier used in cached filenames",
    )
    args = parser.parse_args(argv)

    summary = render_presentation_videos(
        args.yaml.resolve(),
        args.cache_dir.resolve(),
        args.output_dir.resolve(),
        voice=args.voice,
        target_duration_s=None,
        render_per_slide=False,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
