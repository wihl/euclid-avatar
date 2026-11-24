"""Interactive local WebRTC studio server for exploring Euclid in Genie 4.

Serves on ``127.0.0.1:8795`` by default (deliberately avoiding ports ``8787``,
``8790``, and ``8791`` used by the main avatar and Three.js class servers).

Implements the hybrid Option A architecture:
- **Left pane:** Live photorealistic Genie 4 WebRTC video of Euclid in
  Alexandria (c. 300 BCE) speaking and gesturing with authentic bronze dividers
  and an unmarked straightedge, authenticated via backend-minted ephemeral
  ``interactions.auth_tokens.create`` tokens (so ``GEMINI_API_KEY`` never
  leaves the server) and automatic 720p WebRTC seed downscaling (< 256 KiB SCTP).
- **Right pane:** Synchronized, mathematically exact deterministic Euclidean
  construction canvas (Heiberg Greek lettering ``Α, Β, Γ, Δ, Ε, Ζ``) animating
  each hinged-divider arc and unmarked-straightedge stroke in lockstep with
  the proof steps.
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
from .diagram import build_diagram_spec_for_plan
from .media import (
    WEBRTC_SCTP_MAX_MESSAGE_BYTES,
    prepare_webrtc_seed_image,
    sniff_image_mime_type,
)
from .prompts import build_prompt_bundle
from .propositions import PropositionPlan


def render_studio_html(
    bundle: dict[str, Any],
    diagram_spec: dict[str, Any],
) -> str:
    """Render the hybrid Genie 4 WebRTC + exact Euclidean construction studio HTML."""
    bundle_json = json.dumps(bundle, ensure_ascii=False)
    diagram_json = json.dumps(diagram_spec, ensure_ascii=False)
    return STUDIO_HTML_TEMPLATE.replace(
        "__PROMPT_BUNDLE_JSON__", bundle_json
    ).replace("__DIAGRAM_SPEC_JSON__", diagram_json)


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
    """Create the local HTTP server for live Genie 4 WebRTC + exact diagram sessions."""
    bundle = build_prompt_bundle(plan, ambient_only_audio=ambient_only_audio)
    diagram_spec = build_diagram_spec_for_plan(plan)
    html_bytes = render_studio_html(bundle, diagram_spec).encode("utf-8")

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
                        "diagram": diagram_spec,
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
                self.send_header("Content-Type", seed_mime or "image/jpeg")
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
<title>Euclid in Alexandria · Genie 4 + Exact Geometric Studio</title>
<style>
  :root {
    --bg: #0f1210;
    --panel: #171c19;
    --panel-deep: #111613;
    --border: #2c352f;
    --accent: #d4a657;
    --text: #eef0ea;
    --muted: #9aa79f;
    --danger: #d9534f;
    --ok: #3ca374;
    --sand-bg: #dfd0b4;
    --sand-edge: #6f5232;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: "Optima", "Avenir Next", system-ui, sans-serif;
    min-height: 100vh;
    display: grid;
    grid-template-columns: 1fr 370px;
    gap: 14px;
    padding: 14px;
  }
  @media (max-width: 1180px) {
    body { grid-template-columns: 1fr; }
  }
  .stage {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 11px 16px;
  }
  .title { font-size: 18px; font-weight: 700; color: var(--accent); }
  .sub { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
  .status-pill {
    font-size: 13px;
    padding: 6px 12px;
    border-radius: 999px;
    background: #222a25;
    border: 1px solid var(--border);
    white-space: nowrap;
  }
  .dual-stage {
    display: grid;
    grid-template-columns: 1.05fr 0.95fr;
    gap: 12px;
    align-items: stretch;
  }
  @media (max-width: 960px) {
    .dual-stage { grid-template-columns: 1fr; }
  }
  .pane-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .pane-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .pane-badge {
    font-size: 11px;
    color: var(--accent);
    background: rgba(212, 166, 87, 0.12);
    border: 1px solid rgba(212, 166, 87, 0.32);
    padding: 2px 8px;
    border-radius: 999px;
    text-transform: none;
    letter-spacing: 0.01em;
  }
  .video-box {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #060807;
    border: 1px solid var(--border);
    border-radius: 9px;
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
    opacity: 0.94;
  }
  .abax-frame {
    position: relative;
    width: 100%;
    aspect-ratio: 4 / 3;
    border-radius: 9px;
    border: 6px solid var(--sand-edge);
    box-shadow: inset 0 4px 16px rgba(40, 26, 10, 0.35), 0 4px 14px rgba(0, 0, 0, 0.45);
    background:
      radial-gradient(circle at 30% 25%, rgba(255, 248, 232, 0.45), transparent 62%),
      radial-gradient(circle at 78% 76%, rgba(168, 134, 86, 0.25), transparent 55%),
      var(--sand-bg);
    overflow: hidden;
  }
  svg#exact-diagram {
    width: 100%;
    height: 100%;
    display: block;
  }
  .formula-box {
    background: var(--panel-deep);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 9px 11px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .formula-case { font-size: 13px; font-weight: 700; color: var(--accent); }
  .formula-greek {
    font-family: "Palatino Linotype", "Book Antiqua", Georgia, serif;
    font-size: 13.5px;
    line-height: 1.4;
    color: #f0e6cc;
  }
  .formula-num {
    font-family: ui-monospace, Menlo, monospace;
    font-size: 11.5px;
    color: #a9c4b4;
  }
  .badges-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 2px;
  }
  .cite-chip {
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 6px;
    background: #1d2621;
    border: 1px solid #304037;
    color: #c8d6cd;
  }
  .controls-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 11px 12px;
  }
  button {
    background: #242d27;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 13px;
    font-size: 13.5px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  button:hover:not(:disabled) { background: #313d35; }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.primary { background: var(--ok); border-color: #4dc08a; color: #07120c; font-weight: 700; }
  button.danger { background: var(--danger); border-color: #eb6d69; color: #fff; font-weight: 700; }
  .sidebar {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 13px;
    display: flex;
    flex-direction: column;
    gap: 11px;
    max-height: calc(100vh - 28px);
    overflow-y: auto;
  }
  h2 { font-size: 14px; color: var(--accent); letter-spacing: 0.03em; }
  .step-card {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 9px;
    background: #121714;
    display: flex;
    flex-direction: column;
    gap: 5px;
    transition: border-color 0.15s ease, background 0.15s ease;
  }
  .step-card.active {
    border-color: var(--accent);
    background: #1a211c;
    box-shadow: 0 0 0 1px rgba(212, 166, 87, 0.3);
  }
  .step-greek {
    font-family: "Palatino Linotype", "Georgia", serif;
    font-size: 12.5px;
    line-height: 1.42;
    color: #e6dcbe;
  }
  .step-gloss { font-size: 11.5px; color: var(--muted); }
  textarea {
    width: 100%;
    min-height: 58px;
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
    font-size: 11px;
    color: var(--muted);
    background: #0d100e;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
    max-height: 135px;
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
        <div class="sub" id="prop-sub">Hybrid Studio · Live Genie 4 Alexandria World + Exact Heiberg Construction</div>
      </div>
      <div class="status-pill" id="status-pill">Idle · $0.00</div>
    </div>

    <div class="dual-stage">
      <div class="pane-card">
        <div class="pane-label">
          <span>Genie 4 Live World (Alexandria c. 300 BCE)</span>
          <span class="pane-badge">Presence &amp; Voice</span>
        </div>
        <div class="video-box">
          <video id="world-video" autoplay playsinline></video>
          <img id="seed-preview" src="/assets/seed" alt="16:9 Seed Frame" onerror="this.style.display='none'" />
        </div>
        <div style="font-size:12px;color:var(--muted);line-height:1.45;">
          Genie 4 renders Euclid, sunlit courtyard acoustics, and live Ancient Greek speech while the synchronized sand-tray on the right preserves exact Euclidean incidence and lettering.
        </div>
      </div>

      <div class="pane-card">
        <div class="pane-label">
          <span>Exact Euclidean Construction (Abax Sand-Tray)</span>
          <span class="pane-badge" id="diagram-badge">Deterministic · Exact</span>
        </div>
        <div class="abax-frame">
          <svg id="exact-diagram" viewBox="0 0 640 480" role="img" aria-label="Exact Euclidean geometric construction"></svg>
        </div>
        <div class="formula-box">
          <div class="formula-case" id="formula-case">Loading diagram...</div>
          <div class="formula-greek" id="formula-greek"></div>
          <div class="formula-num" id="formula-num"></div>
          <div class="badges-row" id="badges-row"></div>
        </div>
      </div>
    </div>

    <div class="controls-bar">
      <button id="btn-start" class="primary">▶ Start Genie 4 World</button>
      <button id="btn-stop" class="danger" disabled>■ Stop &amp; Complete (End Billing)</button>
      <button id="btn-replay">↺ Replay Construction Step</button>
      <span style="color: var(--muted); font-size: 12.5px;">
        Move: <b>W/A/S/D</b> · Look: <b>Arrows</b> · Click any proof step to preview offline or steer live
      </span>
    </div>
    <div id="error-banner" style="display:none;background:#3a1717;border:1px solid #d9534f;color:#ffd4d2;border-radius:10px;padding:10px 14px;font-size:13px;"></div>
  </div>

  <div class="sidebar">
    <h2>Synchronized Proof Steps (Ancient Greek)</h2>
    <div id="steps-list" style="display:flex;flex-direction:column;gap:9px;"></div>

    <h2>Custom Live Steering Prompt</h2>
    <textarea id="custom-prompt" placeholder="Type a live instruction for Euclid..."></textarea>
    <button id="btn-send-custom" disabled>Send Live Instruction</button>

    <h2>Session Log</h2>
    <div class="log" id="log-box">Ready. Click any proof step to inspect the exact construction offline, or click "Start Genie 4 World" to connect over WebRTC.</div>
  </div>

<script type="module">
  import { GoogleGenAI } from "https://esm.sh/@google/genai@3.6.1";

  const BUNDLE = __PROMPT_BUNDLE_JSON__;
  const DIAGRAM = __DIAGRAM_SPEC_JSON__;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const KEY_MAP = {
    KeyW: "key_w", KeyA: "key_a", KeyS: "key_s", KeyD: "key_d",
    ArrowUp: "arrow_up", ArrowDown: "arrow_down",
    ArrowLeft: "arrow_left", ArrowRight: "arrow_right",
    Space: "space", KeyE: "key_e",
  };
  const SEGMENT_STYLES = {
    secant:       { stroke: "#1b5499", width: 3.1, dash: "" },
    secant_outer: { stroke: "#0e3b73", width: 4.8, dash: "" },
    tangent:      { stroke: "#b83614", width: 3.6, dash: "" },
    radius:       { stroke: "#633294", width: 2.8, dash: "" },
    perp:         { stroke: "#9e6700", width: 2.9, dash: "7 5" },
    hypotenuse:   { stroke: "#2d2a24", width: 2.6, dash: "9 5" },
  };

  document.getElementById("prop-title").textContent =
    `Euclid · Elements ${BUNDLE.proposition_id} · ${BUNDLE.title}`;
  document.getElementById("prop-sub").textContent =
    `${BUNDLE.source_note} · Heiberg Letters: ${BUNDLE.greek_letters.join(", ")}`;

  const videoEl = document.getElementById("world-video");
  const seedImgEl = document.getElementById("seed-preview");
  const statusPill = document.getElementById("status-pill");
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const btnReplay = document.getElementById("btn-replay");
  const btnSendCustom = document.getElementById("btn-send-custom");
  const customInput = document.getElementById("custom-prompt");
  const logBox = document.getElementById("log-box");
  const errorBanner = document.getElementById("error-banner");
  const stepsList = document.getElementById("steps-list");
  const svgEl = document.getElementById("exact-diagram");
  const formulaCaseEl = document.getElementById("formula-case");
  const formulaGreekEl = document.getElementById("formula-greek");
  const formulaNumEl = document.getElementById("formula-num");
  const badgesRowEl = document.getElementById("badges-row");

  let activeSession = null;
  let timerHandle = null;
  let startedAtMs = 0;
  let currentStepId = DIAGRAM.default_step_id || "step_0_enunciation";
  let animRafId = 0;

  function log(msg) {
    const ts = new Date().toLocaleTimeString();
    logBox.textContent += `\n[${ts}] ${msg}`;
    logBox.scrollTop = logBox.scrollHeight;
  }
  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.style.display = "block";
  }
  function clearError() {
    errorBanner.textContent = "";
    errorBanner.style.display = "none";
  }
  function setLiveUI(isLive) {
    btnStart.disabled = isLive;
    btnStop.disabled = !isLive;
    btnSendCustom.disabled = !isLive;
  }

  function svgNode(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  function drawTickMarks(parent, p1, p2, count) {
    const mx = 0.5 * (p1[0] + p2[0]);
    const my = 0.5 * (p1[1] + p2[1]);
    const dx = p2[0] - p1[0];
    const dy = p2[1] - p1[1];
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const nx = -uy, ny = ux;
    const halfTick = 6.5;
    const spacing = 5.5;
    for (let i = 0; i < count; i++) {
      const shift = (i - (count - 1) / 2) * spacing;
      const cx = mx + ux * shift;
      const cy = my + uy * shift;
      parent.appendChild(svgNode("line", {
        x1: (cx - nx * halfTick).toFixed(2),
        y1: (cy - ny * halfTick).toFixed(2),
        x2: (cx + nx * halfTick).toFixed(2),
        y2: (cy + ny * halfTick).toFixed(2),
        stroke: "#4a3319",
        "stroke-width": "2.2",
        "stroke-linecap": "round",
      }));
    }
  }

  function renderExactDiagram(stepId, animate = true) {
    if (animRafId) { cancelAnimationFrame(animRafId); animRafId = 0; }
    currentStepId = stepId;
    document.querySelectorAll(".step-card").forEach((c) => {
      c.classList.toggle("active", c.dataset.stepId === stepId);
    });

    const scene = (DIAGRAM.scenes && DIAGRAM.scenes[stepId]) ||
      (DIAGRAM.scenes && DIAGRAM.scenes[DIAGRAM.default_step_id]);
    if (!scene) return;

    formulaCaseEl.textContent = scene.case_title || "";
    formulaGreekEl.textContent = scene.formula_greek || "";
    formulaNumEl.textContent = scene.formula_numeric || "";
    badgesRowEl.innerHTML = "";
    (scene.citation_badges || []).forEach((b) => {
      const chip = document.createElement("span");
      chip.className = "cite-chip";
      chip.textContent = b;
      badgesRowEl.appendChild(chip);
    });

    svgEl.innerHTML = "";
    if (!DIAGRAM.has_exact_geometry || !scene.circle) {
      const box = svgNode("text", {
        x: "320", y: "225", "text-anchor": "middle",
        fill: "#3a2b18", "font-size": "20", "font-family": "Georgia, serif", "font-weight": "700",
      });
      box.textContent = `Elements ${BUNDLE.proposition_id} (${BUNDLE.greek_letters.join(", ")})`;
      svgEl.appendChild(box);
      const sub = svgNode("text", {
        x: "320", y: "260", "text-anchor": "middle",
        fill: "#5b462b", "font-size": "14", "font-family": "Optima, sans-serif",
      });
      sub.textContent = scene.case_title || "";
      svgEl.appendChild(sub);
      return;
    }

    // Subtle sand-grain groove styling
    const defs = svgNode("defs");
    const filt = svgNode("filter", { id: "sand-groove", x: "-5%", y: "-5%", width: "110%", height: "110%" });
    filt.appendChild(svgNode("feDropShadow", { dx: "0.8", dy: "1.1", stdDeviation: "0.7", "flood-color": "#fff8e8", "flood-opacity": "0.65" }));
    defs.appendChild(filt);
    svgEl.appendChild(defs);

    // 1. Shaded right triangles (subtle translucent ochre-gold wash)
    const triGroup = svgNode("g");
    (scene.triangles || []).forEach((tri) => {
      const ptsStr = tri.pts.map((p) => `${p[0]},${p[1]}`).join(" ");
      triGroup.appendChild(svgNode("polygon", {
        points: ptsStr,
        fill: "rgba(180, 128, 34, 0.17)",
        stroke: "rgba(140, 96, 20, 0.32)",
        "stroke-width": "1.2",
      }));
    });
    svgEl.appendChild(triGroup);

    // 2. Exact circle scribed by hinged bronze divider
    const { cx, cy, r } = scene.circle;
    const circum = 2 * Math.PI * r;
    const circleFill = svgNode("circle", {
      cx, cy, r,
      fill: "rgba(43, 140, 88, 0.08)",
      stroke: "none",
    });
    const circleStroke = svgNode("circle", {
      cx, cy, r,
      fill: "none",
      stroke: "#1f6e43",
      "stroke-width": "3.2",
      filter: "url(#sand-groove)",
      "stroke-dasharray": circum.toFixed(2),
      "stroke-dashoffset": animate ? circum.toFixed(2) : "0",
    });
    svgEl.append(circleFill, circleStroke);

    // 3. Exact segments scribed along unmarked wooden straightedge
    const segGroup = svgNode("g", { filter: "url(#sand-groove)" });
    const segEntries = (scene.segments || []).map((seg) => {
      const st = SEGMENT_STYLES[seg.style] || { stroke: "#2b241a", width: 2.8, dash: "" };
      const len = Math.hypot(seg.p2[0] - seg.p1[0], seg.p2[1] - seg.p1[1]);
      const lineAttrs = {
        x1: seg.p1[0], y1: seg.p1[1], x2: seg.p2[0], y2: seg.p2[1],
        stroke: st.stroke, "stroke-width": st.width, "stroke-linecap": "round",
      };
      if (st.dash) {
        lineAttrs["stroke-dasharray"] = st.dash;
        lineAttrs.opacity = animate ? "0" : "1";
      } else {
        lineAttrs["stroke-dasharray"] = len.toFixed(2);
        lineAttrs["stroke-dashoffset"] = animate ? len.toFixed(2) : "0";
      }
      const el = svgNode("line", lineAttrs);
      segGroup.appendChild(el);
      return { seg, el, len, isDashed: Boolean(st.dash) };
    });
    svgEl.appendChild(segGroup);

    // 4. Right-angle square marks and equal-segment ticks
    const marksGroup = svgNode("g", { opacity: animate ? "0" : "1" });
    (scene.right_angles || []).forEach((ra) => {
      marksGroup.appendChild(svgNode("polyline", {
        points: ra.pts.map((p) => `${p[0]},${p[1]}`).join(" "),
        fill: "none",
        stroke: "#9e6700",
        "stroke-width": "2.3",
        "stroke-linejoin": "miter",
      }));
    });
    (scene.ticks || []).forEach((tk) => drawTickMarks(marksGroup, tk.p1, tk.p2, tk.count));
    svgEl.appendChild(marksGroup);

    // 5. Exact Heiberg Greek capital vertices & labels
    const ptsGroup = svgNode("g", { opacity: animate ? "0.25" : "1" });
    (scene.points || []).forEach((pt) => {
      const fillCol = pt.role === "center" ? "#633294"
        : pt.role === "tangent" ? "#b83614"
        : pt.role === "perp" ? "#9e6700"
        : pt.role === "highlight" ? "#0e3b73"
        : "#2a2117";
      ptsGroup.appendChild(svgNode("circle", {
        cx: pt.xy[0], cy: pt.xy[1], r: "4.6",
        fill: fillCol, stroke: "#f7eedb", "stroke-width": "1.6",
      }));
      const lbl = svgNode("text", {
        x: (pt.xy[0] + pt.offset[0]).toFixed(1),
        y: (pt.xy[1] + pt.offset[1]).toFixed(1),
        fill: "#261b0e",
        "font-family": "'Palatino Linotype', 'Book Antiqua', Georgia, serif",
        "font-size": "21",
        "font-weight": "700",
      });
      lbl.textContent = pt.id;
      ptsGroup.appendChild(lbl);
    });
    svgEl.appendChild(ptsGroup);

    // 6. Animated authentic instrument overlay (two-legged hinged bronze divider + unmarked wooden straightedge)
    const toolGroup = svgNode("g");
    const dividerGroup = svgNode("g", { opacity: "0" });
    const legPivot = svgNode("line", { stroke: "#5c431f", "stroke-width": "4", "stroke-linecap": "round" });
    const legWrite = svgNode("line", { stroke: "#7a5b2b", "stroke-width": "3.6", "stroke-linecap": "round" });
    const hingePin = svgNode("circle", { r: "5.2", fill: "#b58b42", stroke: "#463113", "stroke-width": "1.6" });
    dividerGroup.append(legPivot, legWrite, hingePin);

    const rulerBar = svgNode("polygon", {
      fill: "rgba(155, 114, 65, 0.86)",
      stroke: "#5a3e1e",
      "stroke-width": "1.6",
      opacity: "0",
    });
    const stylusTip = svgNode("circle", { r: "3.5", fill: "#463113", opacity: "0" });
    toolGroup.append(rulerBar, stylusTip, dividerGroup);
    svgEl.appendChild(toolGroup);

    if (!animate) return;

    const circleDurMs = 700;
    const perSegMs = 340;
    const totalSegMs = segEntries.length * perSegMs;
    const totalMs = circleDurMs + totalSegMs + 220;
    const t0 = performance.now();

    function frame(now) {
      const elapsed = now - t0;
      if (elapsed <= circleDurMs) {
        const f = Math.min(1, elapsed / circleDurMs);
        circleStroke.setAttribute("stroke-dashoffset", ((1 - f) * circum).toFixed(2));
        const ang = f * Math.PI * 2;
        const wx = cx + r * Math.cos(ang);
        const wy = cy + r * Math.sin(ang);
        const hx = 0.5 * (cx + wx);
        const hy = 0.5 * (cy + wy) - 62;
        dividerGroup.setAttribute("opacity", "0.95");
        rulerBar.setAttribute("opacity", "0");
        stylusTip.setAttribute("opacity", "0");
        legPivot.setAttribute("x1", hx.toFixed(1));
        legPivot.setAttribute("y1", hy.toFixed(1));
        legPivot.setAttribute("x2", cx.toFixed(1));
        legPivot.setAttribute("y2", cy.toFixed(1));
        legWrite.setAttribute("x1", hx.toFixed(1));
        legWrite.setAttribute("y1", hy.toFixed(1));
        legWrite.setAttribute("x2", wx.toFixed(1));
        legWrite.setAttribute("y2", wy.toFixed(1));
        hingePin.setAttribute("cx", hx.toFixed(1));
        hingePin.setAttribute("cy", hy.toFixed(1));
      } else {
        circleStroke.setAttribute("stroke-dashoffset", "0");
        dividerGroup.setAttribute("opacity", "0");
        const segElapsed = elapsed - circleDurMs;
        const activeIdx = Math.floor(segElapsed / perSegMs);

        segEntries.forEach((entry, idx) => {
          if (idx < activeIdx) {
            if (entry.isDashed) entry.el.setAttribute("opacity", "1");
            else entry.el.setAttribute("stroke-dashoffset", "0");
          } else if (idx === activeIdx) {
            const f = Math.min(1, (segElapsed - idx * perSegMs) / perSegMs);
            if (entry.isDashed) entry.el.setAttribute("opacity", f.toFixed(2));
            else entry.el.setAttribute("stroke-dashoffset", ((1 - f) * entry.len).toFixed(2));
            // Align the plain unmarked wooden straightedge beside the active stroke
            const [x1, y1] = entry.seg.p1;
            const [x2, y2] = entry.seg.p2;
            const dx = x2 - x1, dy = y2 - y1;
            const l = Math.hypot(dx, dy) || 1;
            const ux = dx / l, uy = dy / l;
            const nx = -uy, ny = ux;
            const pad = 18, w = 13;
            const ax = x1 - ux * pad + nx * 3, ay = y1 - uy * pad + ny * 3;
            const bx = x2 + ux * pad + nx * 3, by = y2 + uy * pad + ny * 3;
            const cxp = bx + nx * w, cyp = by + ny * w;
            const dxp = ax + nx * w, dyp = ay + ny * w;
            rulerBar.setAttribute("points", `${ax.toFixed(1)},${ay.toFixed(1)} ${bx.toFixed(1)},${by.toFixed(1)} ${cxp.toFixed(1)},${cyp.toFixed(1)} ${dxp.toFixed(1)},${dyp.toFixed(1)}`);
            rulerBar.setAttribute("opacity", "0.88");
            const tx = x1 + dx * f, ty = y1 + dy * f;
            stylusTip.setAttribute("cx", tx.toFixed(1));
            stylusTip.setAttribute("cy", ty.toFixed(1));
            stylusTip.setAttribute("opacity", "1");
          }
        });

        if (activeIdx >= segEntries.length) {
          rulerBar.setAttribute("opacity", "0");
          stylusTip.setAttribute("opacity", "0");
          marksGroup.setAttribute("opacity", "1");
          ptsGroup.setAttribute("opacity", "1");
        }
      }

      if (elapsed < totalMs) {
        animRafId = requestAnimationFrame(frame);
      } else {
        dividerGroup.setAttribute("opacity", "0");
        rulerBar.setAttribute("opacity", "0");
        stylusTip.setAttribute("opacity", "0");
        marksGroup.setAttribute("opacity", "1");
        ptsGroup.setAttribute("opacity", "1");
        animRafId = 0;
      }
    }
    animRafId = requestAnimationFrame(frame);
  }

  // Build clickable proof steps (Step 0 Enunciation + Steps 1..N)
  const allSteps = [
    {
      id: "step_0_enunciation",
      label: "0. Enunciation (Πρότασις)",
      english_summary: `State Elements ${BUNDLE.proposition_id} and scribe the initial figure.`,
      greek_text: BUNDLE.enunciation_greek || "",
      studio_steering_prompt:
        "Keep the camera steady and keep the existing diagram in the wooden sand-tray unchanged with no extra tools added. Euclid calmly gestures toward the sand-tray while speaking clearly in Ancient Greek (classical Erasmian pronunciation): \"" +
        (BUNDLE.enunciation_greek || "") + "\"",
    },
    ...BUNDLE.steering_steps,
  ];

  allSteps.forEach((step) => {
    const card = document.createElement("div");
    card.className = "step-card";
    card.dataset.stepId = step.id;
    const btn = document.createElement("button");
    btn.className = "step-trigger";
    btn.textContent = step.label;
    btn.addEventListener("click", async () => {
      renderExactDiagram(step.id, true);
      if (!activeSession) {
        log(`Diagram preview → ${step.label} (start Genie 4 to steer live voice)`);
        return;
      }
      log(`Synced Genie 4 + Diagram → ${step.label}`);
      const promptText = step.studio_steering_prompt || step.steering_prompt;
      await activeSession.send({
        event_type: "input",
        content: [{ type: "text", text: promptText }],
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

  // Render initial exact diagram on page load
  renderExactDiagram(currentStepId, false);
  btnReplay.addEventListener("click", () => renderExactDiagram(currentStepId, true));

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
      renderExactDiagram("step_0_enunciation", true);
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
