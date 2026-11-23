"""Interactive local WebRTC studio server for exploring Euclid in Genie 4.

Serves on ``127.0.0.1:8795`` by default (deliberately avoiding ports ``8787``,
``8790``, and ``8791`` used by the main avatar and Three.js class servers).
Mints short-lived, interaction-scoped ephemeral auth tokens on the Python
backend via ``client.interactions.auth_tokens.create(...)`` so the user's
``GEMINI_API_KEY`` never leaves the server.
"""

from __future__ import annotations

import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
import urllib.parse

from . import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    GENIE_API_VERSION,
    GENIE_MODEL,
)
from .media import (
    WEBRTC_SCTP_MAX_MESSAGE_BYTES,
    prepare_webrtc_seed_image,
    sniff_image_mime_type,
)
from .prompts import build_prompt_bundle
from .propositions import PropositionPlan


def render_studio_html(bundle: dict[str, Any]) -> str:
    """Render the interactive WebRTC Genie 4 Euclid studio HTML page."""
    bundle_json = json.dumps(bundle, ensure_ascii=False)
    return STUDIO_HTML_TEMPLATE.replace("__PROMPT_BUNDLE_JSON__", bundle_json)


def create_genie4_http_server(
    plan: PropositionPlan,
    seed_image_path: Path | None,
    api_key: str,
    *,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    ambient_only_audio: bool = False,
    model: str = GENIE_MODEL,
    client_override: Any | None = None,
) -> ThreadingHTTPServer:
    """Create the local HTTP server for live Genie 4 WebRTC sessions."""
    bundle = build_prompt_bundle(plan, ambient_only_audio=ambient_only_audio)
    html_bytes = render_studio_html(bundle).encode("utf-8")

    seed_bytes = (
        seed_image_path.read_bytes()
        if seed_image_path is not None and seed_image_path.exists()
        else b""
    )
    seed_mime = sniff_image_mime_type(seed_bytes) if seed_bytes else ""
    webrtc_seed_bytes, webrtc_seed_mime = (
        prepare_webrtc_seed_image(seed_bytes) if seed_bytes else (b"", "")
    )
    seed_b64 = (
        base64.b64encode(webrtc_seed_bytes).decode("ascii")
        if webrtc_seed_bytes
        else ""
    )
    if seed_b64:
        est_setup_bytes = len(
            json.dumps(
                {
                    "event_type": "world_setup",
                    "world_prompt": {"text": bundle["world_setup_prompt"]},
                    "reference_image": {
                        "data": seed_b64,
                        "mime_type": webrtc_seed_mime,
                    },
                }
            ).encode("utf-8")
        )
        if est_setup_bytes >= WEBRTC_SCTP_MAX_MESSAGE_BYTES:
            raise ValueError(
                f"Prepared WebRTC world_setup payload ({est_setup_bytes} B) exceeds "
                f"SCTP maxMessageSize ({WEBRTC_SCTP_MAX_MESSAGE_BYTES} B)."
            )

    def _mint_session() -> dict[str, Any]:
        if client_override is not None:
            client = client_override
        else:
            from google import genai

            if not api_key:
                raise RuntimeError("Missing GEMINI_API_KEY on backend.")
            client = genai.Client(
                api_key=api_key, http_options={"api_version": GENIE_API_VERSION}
            )
        interaction = client.interactions.create(
            model=model, api_version=GENIE_API_VERSION
        )
        token = client.interactions.auth_tokens.create(
            interaction.id, api_version=GENIE_API_VERSION
        )
        expires = getattr(token, "expires_at", None)
        return {
            "interaction_id": interaction.id,
            "auth_token": token.auth_token,
            "expires_at": expires.isoformat() if hasattr(expires, "isoformat") else str(expires or ""),
            "api_version": GENIE_API_VERSION,
            "world_prompt": bundle["world_setup_prompt"],
            "seed_image_b64": seed_b64,
            "seed_mime_type": webrtc_seed_mime,
        }

    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            if path == "/api/plan":
                self._send_json(
                    {
                        **bundle,
                        "has_seed_image": bool(seed_bytes),
                        "seed_image_url": "/assets/seed" if seed_bytes else "",
                    }
                )
                return
            if path == "/assets/seed":
                if not seed_bytes:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", seed_mime or "image/png")
                self.send_header("Content-Length", str(len(seed_bytes)))
                self.end_headers()
                self.wfile.write(seed_bytes)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/session":
                try:
                    self._send_json(_mint_session())
                except Exception as exc:
                    self._send_json(
                        {"error": f"{type(exc).__name__}: {exc}"},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    return ThreadingHTTPServer((host, port), StudioHandler)


def serve_genie4_studio(
    plan: PropositionPlan,
    seed_image_path: Path | None,
    api_key: str,
    *,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    ambient_only_audio: bool = False,
) -> None:
    """Start the local Genie 4 interactive WebRTC studio server."""
    server = create_genie4_http_server(
        plan,
        seed_image_path,
        api_key,
        host=host,
        port=port,
        ambient_only_audio=ambient_only_audio,
    )
    print(
        f"Euclid Genie 4 Studio ({plan.proposition_id}) listening at http://{host}:{port}/",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


STUDIO_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Euclid in Alexandria · Genie 4 Live Studio</title>
<style>
  :root {
    --bg: #0f1210;
    --panel: #171c19;
    --border: #2c352f;
    --accent: #d4a657;
    --text: #eef0ea;
    --muted: #9aa79f;
    --danger: #d9534f;
    --ok: #3ca374;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: "Optima", "Avenir Next", system-ui, sans-serif;
    min-height: 100vh;
    display: grid;
    grid-template-columns: 1fr 410px;
    gap: 16px;
    padding: 16px;
  }
  .stage {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
  }
  .title { font-size: 19px; font-weight: 700; color: var(--accent); }
  .sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .status-pill {
    font-size: 13px;
    padding: 6px 12px;
    border-radius: 999px;
    background: #222a25;
    border: 1px solid var(--border);
  }
  .video-box {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #060807;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  video#world-video, img#seed-preview {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  img#seed-preview {
    position: absolute;
    inset: 0;
    opacity: 0.92;
  }
  .controls-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px;
  }
  button {
    background: #242d27;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s ease;
  }
  button:hover:not(:disabled) { background: #313d35; }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.primary { background: var(--ok); border-color: #4dc08a; color: #07120c; font-weight: 700; }
  button.danger { background: var(--danger); border-color: #eb6d69; color: #fff; font-weight: 700; }
  .sidebar {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: calc(100vh - 32px);
    overflow-y: auto;
  }
  h2 { font-size: 15px; color: var(--accent); letter-spacing: 0.03em; }
  .step-card {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px;
    background: #121714;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .step-greek {
    font-family: "Palatino Linotype", "Georgia", serif;
    font-size: 13px;
    line-height: 1.45;
    color: #e6dcbe;
  }
  .step-gloss { font-size: 12px; color: var(--muted); }
  textarea {
    width: 100%;
    min-height: 64px;
    background: #101412;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
    font-size: 13px;
    resize: vertical;
  }
  .log {
    font-family: ui-monospace, Menlo, monospace;
    font-size: 11.5px;
    color: var(--muted);
    background: #0d100e;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
    max-height: 150px;
    overflow-y: auto;
    white-space: pre-wrap;
  }
</style>
</head>
<body>
  <div class="stage">
    <div class="header">
      <div>
        <div class="title" id="prop-title">Euclid · Elements</div>
        <div class="sub" id="prop-sub">Historically accurate Alexandria c. 300 BCE · Genie 4 WebRTC</div>
      </div>
      <div class="status-pill" id="status-pill">Idle · $0.00</div>
    </div>

    <div class="video-box">
      <video id="world-video" autoplay playsinline></video>
      <img id="seed-preview" src="/assets/seed" alt="16:9 Seed Frame" onerror="this.style.display='none'" />
    </div>

    <div class="controls-bar">
      <button id="btn-start" class="primary">▶ Start Genie 4 World</button>
      <button id="btn-stop" class="danger" disabled>■ Stop &amp; Complete (End Billing)</button>
      <span style="color: var(--muted); font-size: 13px;">
        Move: <b>W/A/S/D</b> · Look: <b>Arrow Keys</b> · Billing: ~$0.10/sec while live
      </span>
    </div>
    <div id="error-banner" style="display:none;background:#3a1717;border:1px solid #d9534f;color:#ffd4d2;border-radius:10px;padding:10px 14px;font-size:13px;"></div>
  </div>

  <div class="sidebar">
    <h2>Live Proof Steering (Ancient Greek)</h2>
    <div id="steps-list" style="display:flex;flex-direction:column;gap:10px;"></div>

    <h2>Custom Live Steering Prompt</h2>
    <textarea id="custom-prompt" placeholder="Type a live instruction for Euclid..."></textarea>
    <button id="btn-send-custom" disabled>Send Live Instruction</button>

    <h2>Session Log</h2>
    <div class="log" id="log-box">Ready. Click "Start Genie 4 World" to mint an ephemeral token and connect over WebRTC.</div>
  </div>

<script type="module">
  import { GoogleGenAI } from "https://esm.sh/@google/genai@3.6.1";

  const BUNDLE = __PROMPT_BUNDLE_JSON__;
  const KEY_MAP = {
    KeyW: "key_w", KeyA: "key_a", KeyS: "key_s", KeyD: "key_d",
    ArrowUp: "arrow_up", ArrowDown: "arrow_down",
    ArrowLeft: "arrow_left", ArrowRight: "arrow_right",
    Space: "space", KeyE: "key_e",
  };

  document.getElementById("prop-title").textContent =
    `Euclid · Elements ${BUNDLE.proposition_id} · ${BUNDLE.title}`;
  document.getElementById("prop-sub").textContent =
    `${BUNDLE.source_note} · Letters: ${BUNDLE.greek_letters.join(", ")}`;

  const videoEl = document.getElementById("world-video");
  const seedImgEl = document.getElementById("seed-preview");
  const statusPill = document.getElementById("status-pill");
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const btnSendCustom = document.getElementById("btn-send-custom");
  const customInput = document.getElementById("custom-prompt");
  const logBox = document.getElementById("log-box");
  const errorBanner = document.getElementById("error-banner");
  const stepsList = document.getElementById("steps-list");

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.style.display = "block";
  }
  function clearError() {
    errorBanner.textContent = "";
    errorBanner.style.display = "none";
  }

  let activeSession = null;
  let timerHandle = null;
  let startedAtMs = 0;

  function log(msg) {
    const ts = new Date().toLocaleTimeString();
    logBox.textContent += `\n[${ts}] ${msg}`;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function setLiveUI(isLive) {
    btnStart.disabled = isLive;
    btnStop.disabled = !isLive;
    btnSendCustom.disabled = !isLive;
    document.querySelectorAll(".step-trigger").forEach((b) => (b.disabled = !isLive));
  }

  BUNDLE.steering_steps.forEach((step) => {
    const card = document.createElement("div");
    card.className = "step-card";
    const btn = document.createElement("button");
    btn.className = "step-trigger";
    btn.disabled = true;
    btn.textContent = step.label;
    btn.addEventListener("click", async () => {
      if (!activeSession) return;
      log(`Steering → ${step.label}`);
      await activeSession.send({
        event_type: "input",
        content: [{ type: "text", text: step.steering_prompt }],
      });
    });
    const gloss = document.createElement("div");
    gloss.className = "step-gloss";
    gloss.textContent = step.english_summary;
    const grk = document.createElement("div");
    grk.className = "step-greek";
    grk.textContent = step.greek_text;
    card.append(btn, gloss, grk);
    stepsList.append(card);
  });

  async function stopSession() {
    if (!activeSession) return;
    const sess = activeSession;
    activeSession = null;
    if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
    setLiveUI(false);
    try {
      await sess.complete();
      log("Sent interaction.complete() — session stopped cleanly.");
    } catch (err) {
      log(`Stop note: ${err.message || err}`);
    }
    statusPill.textContent = "Completed";
  }

  btnStart.addEventListener("click", async () => {
    clearError();
    btnStart.disabled = true;
    statusPill.textContent = "Minting ephemeral token...";
    log("Requesting ephemeral Genie 4 session token from local backend...");
    try {
      const resp = await fetch("/api/session", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);

      const ai = new GoogleGenAI({ apiKey: data.auth_token, apiVersion: data.api_version });
      const session = await ai.interactions.connect(data.interaction_id, {
        transport: "webrtc",
        api_version: data.api_version,
      });
      activeSession = session;
      session.transport.setVideoElement(videoEl);

      const setupPayload = {
        event_type: "world_setup",
        world_prompt: { text: data.world_prompt },
      };
      if (data.seed_image_b64) {
        setupPayload.reference_image = {
          data: data.seed_image_b64,
          mime_type: data.seed_mime_type || "image/jpeg",
        };
      }
      await session.send(setupPayload);
      seedImgEl.style.display = "none";
      startedAtMs = Date.now();
      setLiveUI(true);
      log(`Connected to Genie 4 (${data.interaction_id}). World streaming live!`);

      timerHandle = setInterval(() => {
        const secs = Math.floor((Date.now() - startedAtMs) / 1000);
        const est = (secs * 0.1008).toFixed(2);
        statusPill.textContent = `LIVE · ${secs}s · ~$${est}`;
      }, 1000);
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      log(`Failed to start Genie 4 session: ${msg}`);
      showError(`Error: ${msg}`);
      if (activeSession) {
        await stopSession();
      }
      statusPill.textContent = "Error";
      setLiveUI(false);
    }
  });

  btnStop.addEventListener("click", stopSession);

  btnSendCustom.addEventListener("click", async () => {
    const txt = customInput.value.trim();
    if (!txt || !activeSession) return;
    log(`Custom steering → ${txt}`);
    await activeSession.send({
      event_type: "input",
      content: [{ type: "text", text: txt }],
    });
    customInput.value = "";
  });

  window.addEventListener("keydown", async (e) => {
    if (!activeSession || document.activeElement === customInput) return;
    const mapped = KEY_MAP[e.code];
    if (!mapped || e.repeat) return;
    e.preventDefault();
    await activeSession.send({ event_type: "user_action", action: "key_down", input: mapped });
  });
  window.addEventListener("keyup", async (e) => {
    if (!activeSession || document.activeElement === customInput) return;
    const mapped = KEY_MAP[e.code];
    if (!mapped) return;
    e.preventDefault();
    await activeSession.send({ event_type: "user_action", action: "key_up", input: mapped });
  });
  window.addEventListener("beforeunload", () => {
    if (activeSession) activeSession.complete();
  });
</script>
</body>
</html>
"""
