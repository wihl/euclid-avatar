"""Local HTTP server, Genie 4 seed exporter, and 1080p MP4 renderer for III.18.

Pure Python standard library implementation compatible with `/opt/homebrew/bin/python3`.
Uses headless Chrome DevTools Protocol (CDP) with Metal WebGL acceleration and
pipes rendered frames directly into FFmpeg.
"""

from __future__ import annotations

import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

from .assets import build_all_world_assets
from .world_html import render_world_html

# Video & screenshot resolution constants
RENDER_WIDTH_PX = 1920
RENDER_HEIGHT_PX = 1080
DEFAULT_VIDEO_FPS = 24
JPEG_CAPTURE_QUALITY = 92
VIDEO_CRF = 18
AUDIO_OUT_RATE_HZ = 48000
AUDIO_OUT_BITRATE = "192k"

# Server & CDP connection constants
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8790
CDP_READY_TIMEOUT_S = 15.0
CDP_POLL_INTERVAL_S = 0.10
CDP_SOCKET_TIMEOUT_S = 30.0
WORLD_READY_TIMEOUT_S = 20.0

# RFC 6455 WebSocket framing constants
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_TEXT_OPCODE = 0x81
WS_MASK_BIT = 0x80
WS_LEN_16BIT = 126
WS_LEN_64BIT = 127
WS_MAX_16BIT = 65535

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

RANGE_HEADER_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _find_chrome_binary() -> str:
    for path_str in CHROME_CANDIDATES:
        if Path(path_str).exists():
            return path_str
    which_chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if which_chrome:
        return which_chrome
    raise FileNotFoundError("Google Chrome or Chromium binary not found.")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _MinimalCDPClient:
    """Minimal stdlib RFC 6455 WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url: str) -> None:
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        self._sock = socket.create_connection((host, port), timeout=CDP_SOCKET_TIMEOUT_S)
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(handshake.encode("ascii"))
        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP WebSocket handshake closed prematurely.")
            header_buf += chunk
        self._leftover = header_buf.split(b"\r\n\r\n", 1)[1]
        self._next_id = 1

    def _recv_exact(self, count: int) -> bytes:
        buf = bytearray()
        if self._leftover:
            take = min(count, len(self._leftover))
            buf.extend(self._leftover[:take])
            self._leftover = self._leftover[take:]
        while len(buf) < count:
            chunk = self._sock.recv(min(65536, count - len(buf)))
            if not chunk:
                raise ConnectionError("CDP WebSocket closed while reading frame.")
            buf.extend(chunk)
        return bytes(buf)

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        length = len(payload)
        header = bytearray([WS_TEXT_OPCODE])
        if length < WS_LEN_16BIT:
            header.append(WS_MASK_BIT | length)
        elif length <= WS_MAX_16BIT:
            header.append(WS_MASK_BIT | WS_LEN_16BIT)
            header.extend(struct.pack("!H", length))
        else:
            header.append(WS_MASK_BIT | WS_LEN_64BIT)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _recv_frame(self) -> str:
        while True:
            head = self._recv_exact(2)
            opcode = head[0] & 0x0F
            masked = bool(head[1] & WS_MASK_BIT)
            length = head[1] & 0x7F
            if length == WS_LEN_16BIT:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == WS_LEN_64BIT:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask_key = self._recv_exact(4) if masked else b""
            data = self._recv_exact(length)
            if masked:
                data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
            if opcode == 0x09:  # Ping -> Pong
                pong = bytearray([0x8A, WS_MASK_BIT | len(data)])
                m = os.urandom(4)
                pong.extend(m)
                pong.extend(bytes(b ^ m[i % 4] for i, b in enumerate(data)))
                self._sock.sendall(bytes(pong))
                continue
            if opcode == 0x08:
                raise ConnectionError("CDP WebSocket closed by peer.")
            return data.decode("utf-8", errors="replace")

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        req = {"id": msg_id, "method": method, "params": params or {}}
        self._send_text(json.dumps(req))
        while True:
            raw = self._recv_frame()
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                return msg.get("result", {})

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def create_world_http_server(
    spec: dict[str, Any],
    cache_dir: Path,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> ThreadingHTTPServer:
    """Create a multi-threaded HTTP server for the III.18 3D virtual world."""
    html_bytes = render_world_html(spec).encode("utf-8")
    three_bytes = (cache_dir / "vendor" / "three.module.js").read_bytes()

    class WorldHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return  # Keep server output quiet and non-chatty

        def _serve_file(self, file_path: Path, content_type: str) -> None:
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            size = file_path.stat().st_size
            range_hdr = self.headers.get("Range", "")
            match = RANGE_HEADER_RE.match(range_hdr)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
                end = min(end, size - 1)
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
            if parsed_path in ("/", "/index.html", "/iii18"):
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
                mime = "audio/mpeg" if rel_name.endswith(".mp3") else "audio/wav"
                self._serve_file(cache_dir / "audio" / rel_name, mime)
                return
            if parsed_path.startswith("/assets/images/"):
                rel_name = Path(parsed_path.removeprefix("/assets/images/")).name
                mime = "image/png" if rel_name.endswith(".png") else "image/jpeg"
                self._serve_file(cache_dir / "images" / rel_name, mime)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    return ThreadingHTTPServer((host, port), WorldHandler)


class _HeadlessWorldSession:
    """Context manager launching ephemeral HTTP server + WebGL headless Chrome CDP."""

    def __init__(self, spec: dict[str, Any], cache_dir: Path) -> None:
        self._spec = spec
        self._cache_dir = cache_dir
        self._http_port = _pick_free_port()
        self._cdp_port = _pick_free_port()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._chrome_proc: subprocess.Popen[bytes] | None = None
        self._tmp_profile: tempfile.TemporaryDirectory[str] | None = None
        self.cdp: _MinimalCDPClient | None = None

    def __enter__(self) -> _HeadlessWorldSession:
        self._server = create_world_http_server(
            self._spec, self._cache_dir, host="127.0.0.1", port=self._http_port
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self._tmp_profile = tempfile.TemporaryDirectory()
        chrome_bin = _find_chrome_binary()
        cmd = [
            chrome_bin,
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
        raise RuntimeError("Timed out waiting for Three.js world initialization.")

    def set_state_and_capture(
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
        cap_params: dict[str, Any] = {"format": fmt}
        if fmt == "jpeg":
            cap_params["quality"] = quality
        shot = self.cdp.call("Page.captureScreenshot", cap_params)
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


def _segment_midpoint(spec: dict[str, Any], seg_id: str) -> float:
    segs = spec["timeline"]["segments"]
    match = next((s for s in segs if s["id"] == seg_id), segs[0])
    return 0.5 * (match["start_s"] + match["end_s"])


def export_genie_seeds_and_previews(
    spec: dict[str, Any],
    cache_dir: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Render clean 1080p Genie 4 seed keyframes plus HUD verification screenshots."""
    seeds_dir = output_dir / "genie_seeds"
    previews_dir = output_dir / "previews"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)

    t_claim = _segment_midpoint(spec, "s1_p2_three_tangents")
    t_step1 = _segment_midpoint(spec, "s2_p3_colour_key")
    t_step2 = _segment_midpoint(spec, "s3_p3_true_wedges")
    t_morph = _segment_midpoint(spec, "s6_p1_morph_to_sphere")
    t_sphere = _segment_midpoint(spec, "s6_p2_great_circle_holds")
    t_farfoot = _segment_midpoint(spec, "s6_p3_i16_far_foot")

    outputs: dict[str, Path] = {}
    with _HeadlessWorldSession(spec, cache_dir) as session:
        # 1. Clean HUD-free keyframes tailored for Project Genie (Genie 4) image upload
        seed_jobs = [
            (
                "genie_seed_01_euclidean_pavilion.png",
                t_step1,
                {"hideHud": True, "camPos": [0.35, 1.48, 4.35], "lookAt": [0.15, 0.68, -0.8]},
            ),
            (
                "genie_seed_02_contradiction_fgc.png",
                t_step2,
                {"hideHud": True, "camPos": [0.85, 1.55, 3.85], "lookAt": [0.45, 0.52, -0.5]},
            ),
            ("genie_seed_03_mid_morph_curved.png", t_morph, {"tau": 0.52, "hideHud": True}),
            ("genie_seed_04_spherical_globe.png", t_sphere, {"tau": 1.0, "hideHud": True}),
        ]
        for fname, ts, opts in seed_jobs:
            out_p = seeds_dir / fname
            out_p.write_bytes(session.set_state_and_capture(ts, fmt="png", opts=opts))
            outputs[fname] = out_p

        # 2. Full HUD + 3D Label preview frames for inspection & walkthrough
        preview_jobs = [
            ("preview_01_claim.png", t_claim, {"hideHud": False}),
            ("preview_02_suppose_not.png", t_step2, {"hideHud": False}),
            ("preview_03_morph_midway.png", t_morph, {"tau": 0.52, "hideHud": False}),
            ("preview_04_sphere.png", t_sphere, {"tau": 1.0, "hideHud": False}),
            ("preview_05_sphere_far_foot.png", t_farfoot, {"tau": 1.0, "farFoot": True, "hideHud": False}),
        ]
        for fname, ts, opts in preview_jobs:
            out_p = previews_dir / fname
            out_p.write_bytes(session.set_state_and_capture(ts, fmt="png", opts=opts))
            outputs[fname] = out_p

    return outputs


def render_world_mp4(
    spec: dict[str, Any],
    cache_dir: Path,
    output_dir: Path,
    fps: int = DEFAULT_VIDEO_FPS,
) -> Path:
    """Render the full narrated 1920x1080 MP4 virtual world walkthrough."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / "iii18_virtual_world.mp4"
    master_wav = cache_dir / "audio" / "iii18_voiceover_full.wav"
    total_dur = float(spec["timeline"]["total_duration_s"])
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

    with _HeadlessWorldSession(spec, cache_dir) as session:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for frame_idx in range(total_frames):
                t_sec = frame_idx / float(fps)
                jpg_bytes = session.set_state_and_capture(
                    t_sec, fmt="jpeg", quality=JPEG_CAPTURE_QUALITY
                )
                proc.stdin.write(jpg_bytes)
        finally:
            proc.stdin.close()
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"FFmpeg exited with non-zero code {ret}.")

    return out_mp4


def build_all_and_render(
    worktree_root: Path,
    output_dir: Path | None = None,
    fps: int = DEFAULT_VIDEO_FPS,
    skip_video: bool = False,
) -> dict[str, Any]:
    """End-to-end builder: assets, Genie 4 seeds, preview screenshots, and 1080p MP4."""
    resolved_out = output_dir or (worktree_root / "output" / "iii18_world")
    assets = build_all_world_assets(worktree_root)
    spec = assets["spec"]
    cache_dir = assets["cache_dir"]

    # Also copy the standalone voiceover MP3/WAV and AI pavilion concept into output_dir
    resolved_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(assets["master_mp3_path"], resolved_out / "iii18_voiceover_full.mp3")
    shutil.copy2(assets["master_wav_path"], resolved_out / "iii18_voiceover_full.wav")
    if assets["genie_concept_path"] and assets["genie_concept_path"].exists():
        seeds_dir = resolved_out / "genie_seeds"
        seeds_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            assets["genie_concept_path"],
            seeds_dir / "genie_seed_00_ai_architectural_concept.jpg",
        )

    shots = export_genie_seeds_and_previews(spec, cache_dir, resolved_out)
    mp4_path = None
    if not skip_video:
        mp4_path = render_world_mp4(spec, cache_dir, resolved_out, fps=fps)

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
    """Build/load cached assets and run the interactive 3D world HTTP server."""
    assets = build_all_world_assets(worktree_root)
    server = create_world_http_server(
        assets["spec"], assets["cache_dir"], host=host, port=port
    )
    print(f"Elements III.18 3D Virtual World live at http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
