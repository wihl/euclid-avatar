"""Local HTTP server, preview screenshot exporter, and 1080p MP4 renderer for III.36."""

from __future__ import annotations

import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

from ..iii18_world.render import (
    _MinimalCDPClient,
    _find_chrome_binary,
    _pick_free_port,
)
from .assets import MAX_PRESENTATION_DURATION_S, build_all_world_assets
from .world_html import render_world_html

RENDER_WIDTH_PX = 1920
RENDER_HEIGHT_PX = 1080
DEFAULT_VIDEO_FPS = 24
JPEG_CAPTURE_QUALITY = 92
VIDEO_CRF = 18
AUDIO_OUT_RATE_HZ = 48000
AUDIO_OUT_BITRATE = "192k"

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8791
CDP_READY_TIMEOUT_S = 15.0
CDP_POLL_INTERVAL_S = 0.10
WORLD_READY_TIMEOUT_S = 20.0

RANGE_HEADER_RE = re.compile(r"bytes=(\d+)-(\d*)")


def create_world_http_server(
    spec: dict[str, Any],
    cache_dir: Path,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> ThreadingHTTPServer:
    """Create a multi-threaded HTTP server for the III.36 3D virtual world."""
    html_bytes = render_world_html(spec).encode("utf-8")
    three_bytes = (cache_dir / "vendor" / "three.module.js").read_bytes()

    class WorldHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _serve_file(self, file_path: Path, content_type: str) -> None:
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            size = file_path.stat().st_size
            match = RANGE_HEADER_RE.match(self.headers.get("Range", ""))
            if match:
                start = int(match.group(1))
                end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
                if start > end or start >= size:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                length = end - start + 1
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                with file_path.open("rb") as fh:
                    fh.seek(start)
                    self.wfile.write(fh.read(length))
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            self.wfile.write(file_path.read_bytes())

        def do_GET(self) -> None:  # noqa: N802
            parsed_path = urllib.parse.urlparse(self.path).path
            if parsed_path in ("/", "/index.html", "/iii36"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            if parsed_path == "/vendor/three.module.js":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(three_bytes)))
                self.end_headers()
                self.wfile.write(three_bytes)
                return
            if parsed_path.startswith("/assets/audio/"):
                rel_name = Path(parsed_path.removeprefix("/assets/audio/")).name
                self._serve_file(cache_dir / "audio" / rel_name, "audio/wav")
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    return ThreadingHTTPServer((host, port), WorldHandler)


class _HeadlessSession:
    def __init__(self, spec: dict[str, Any], cache_dir: Path) -> None:
        self._spec = spec
        self._cache_dir = cache_dir
        self._http_port = _pick_free_port()
        self._cdp_port = _pick_free_port()
        self._server: ThreadingHTTPServer | None = None
        self._chrome_proc: subprocess.Popen[bytes] | None = None
        self._tmp_profile: tempfile.TemporaryDirectory[str] | None = None
        self.cdp: _MinimalCDPClient | None = None

    def __enter__(self) -> _HeadlessSession:
        self._server = create_world_http_server(
            self._spec, self._cache_dir, host="127.0.0.1", port=self._http_port
        )
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._tmp_profile = tempfile.TemporaryDirectory()
        cmd = [
            _find_chrome_binary(),
            "--headless=new",
            "--enable-webgl",
            "--ignore-gpu-blocklist",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--hide-scrollbars",
            "--mute-audio",
            f"--window-size={RENDER_WIDTH_PX},{RENDER_HEIGHT_PX}",
            f"--remote-debugging-port={self._cdp_port}",
            f"--user-data-dir={self._tmp_profile.name}",
            f"http://127.0.0.1:{self._http_port}/?capture=1",
        ]
        self._chrome_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        deadline = time.monotonic() + CDP_READY_TIMEOUT_S
        ws_url = ""
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self._cdp_port}/json/list", timeout=1.5
                ) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                page = next((t for t in targets if t.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(CDP_POLL_INTERVAL_S)
        if not ws_url:
            raise RuntimeError("Timed out waiting for headless Chrome CDP target.")

        self.cdp = _MinimalCDPClient(ws_url)
        self.cdp.call("Page.enable")
        self.cdp.call("Runtime.enable")
        self.cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": RENDER_WIDTH_PX,
                "height": RENDER_HEIGHT_PX,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        ready_deadline = time.monotonic() + WORLD_READY_TIMEOUT_S
        while time.monotonic() < ready_deadline:
            res = self.cdp.call(
                "Runtime.evaluate",
                {"expression": "Boolean(window.__worldReady)", "returnByValue": True},
            )
            if res.get("result", {}).get("value") is True:
                return self
            time.sleep(CDP_POLL_INTERVAL_S)
        raise RuntimeError("Timed out waiting for III.36 Three.js initialization.")

    def capture_at(
        self,
        t_sec: float,
        fmt: str = "png",
        quality: int = JPEG_CAPTURE_QUALITY,
        opts: dict[str, Any] | None = None,
    ) -> bytes:
        assert self.cdp is not None
        opts_json = json.dumps(opts or {})
        self.cdp.call(
            "Runtime.evaluate",
            {
                "expression": f"window.setVirtualWorldTime({t_sec:.4f}, {opts_json})",
                "returnByValue": True,
            },
        )
        params: dict[str, Any] = {"format": fmt}
        if fmt == "jpeg":
            params["quality"] = quality
        shot = self.cdp.call("Page.captureScreenshot", params)
        return base64.b64decode(shot["data"])

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.cdp:
            self.cdp.close()
        if self._chrome_proc:
            self._chrome_proc.terminate()
            try:
                self._chrome_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_proc.kill()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._tmp_profile:
            self._tmp_profile.cleanup()


def _seg_time_at_frac(spec: dict[str, Any], seg_id: str, frac: float = 0.5) -> float:
    segs = spec["timeline"]["segments"]
    seg = next((s for s in segs if s["id"] == seg_id), segs[0])
    return float(seg["start_s"]) + frac * (float(seg["end_s"]) - float(seg["start_s"]))


def export_preview_frames(
    spec: dict[str, Any], cache_dir: Path, output_dir: Path
) -> dict[str, Path]:
    previews_dir = output_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("preview_01_claim_areas.png", _seg_time_at_frac(spec, "s1_p2_scale_areas", 0.5), {}),
        ("preview_02_area_morph_superpose.png", _seg_time_at_frac(spec, "s1_p3_area_morph", 0.85), {}),
        ("preview_03_case1_ii6_gnomon.png", _seg_time_at_frac(spec, "s2_p2_ii6_gnomon", 0.82), {}),
        ("preview_04_case2_add_fe2.png", _seg_time_at_frac(spec, "s3_p2_add_fe2", 0.78), {}),
        ("preview_05_fan_invariant.png", _seg_time_at_frac(spec, "s4_p2_sweep", 0.35), {}),
        ("preview_06_sphere_morph_mid.png", _seg_time_at_frac(spec, "s5_p1_morph_and_post5", 0.55), {}),
        ("preview_07_sphere_broken_square.png", _seg_time_at_frac(spec, "s5_p3_numbers_diverge", 0.60), {}),
    ]
    outputs: dict[str, Path] = {}
    with _HeadlessSession(spec, cache_dir) as session:
        for fname, ts, opts in jobs:
            p = previews_dir / fname
            p.write_bytes(session.capture_at(ts, fmt="png", opts=opts))
            outputs[fname] = p
    return outputs


def render_world_mp4(
    spec: dict[str, Any],
    cache_dir: Path,
    output_dir: Path,
    fps: int = DEFAULT_VIDEO_FPS,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / "iii36_virtual_world.mp4"
    master_wav = cache_dir / "audio" / "iii36_voiceover_full.wav"
    total_dur = float(spec["timeline"]["total_duration_s"])
    if total_dur > MAX_PRESENTATION_DURATION_S:
        raise RuntimeError(f"Duration {total_dur:.1f}s exceeds 420s ceiling.")
    total_frames = max(1, int(math.ceil(total_dur * fps)))

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-framerate",
        str(fps),
        "-i",
        "-",
        "-i",
        str(master_wav),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        str(VIDEO_CRF),
        "-pix_fmt",
        "yuv420p",
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
        str(out_mp4),
    ]

    with _HeadlessSession(spec, cache_dir) as session:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for frame_idx in range(total_frames):
                t_sec = frame_idx / float(fps)
                proc.stdin.write(
                    session.capture_at(t_sec, fmt="jpeg", quality=JPEG_CAPTURE_QUALITY)
                )
        finally:
            proc.stdin.close()
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"FFmpeg exited with code {ret}.")
    return out_mp4


def build_all_and_render(
    worktree_root: Path,
    output_dir: Path | None = None,
    fps: int = DEFAULT_VIDEO_FPS,
    skip_video: bool = False,
) -> dict[str, Any]:
    resolved_out = output_dir or (worktree_root / "output" / "iii36_world")
    assets = build_all_world_assets(worktree_root)
    shots = export_preview_frames(assets["spec"], assets["cache_dir"], resolved_out)
    mp4_path = None
    if not skip_video:
        mp4_path = render_world_mp4(
            assets["spec"], assets["cache_dir"], resolved_out, fps=fps
        )
    return {
        "assets": assets,
        "screenshots": shots,
        "mp4_path": mp4_path,
        "output_dir": resolved_out,
    }


def serve_interactive_world(
    worktree_root: Path,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> None:
    assets = build_all_world_assets(worktree_root)
    server = create_world_http_server(
        assets["spec"], assets["cache_dir"], host=host, port=port
    )
    print(f"Elements III.36 3D Virtual World live at http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
