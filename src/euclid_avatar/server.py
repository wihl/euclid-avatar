"""FastAPI + WebSocket local server for `/avatar` (OBS 1920x1080 Browser Source) and `/control` (Operator UI)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .config import Config
from .devices import inspect_routing
from .pipeline import EuclidPipeline


class AskTextRequest(BaseModel):
    question: str
    tts_backend: str | None = None
    tts_voice: str | None = None


class EditTurnRequest(BaseModel):
    english: str
    greek: str


class ConfigUpdateRequest(BaseModel):
    tts_backend: str | None = None
    tts_voice: str | None = None
    gemini_model: str | None = None


class SceneSwitchRequest(BaseModel):
    scene: str


class CannedRequest(BaseModel):
    canned_id: str


def create_app(cfg: Config, pipeline: EuclidPipeline) -> FastAPI:
    app = FastAPI(title="Euclid Avatar Spike (MATH E-139)")
    clients: set[WebSocket] = set()
    loop_holder: dict[str, asyncio.AbstractEventLoop] = {}

    async def broadcast(payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    def sync_event_callback(payload: dict[str, Any]) -> None:
        loop = loop_holder.get("loop")
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(payload), loop)

    pipeline.event_callback = sync_event_callback

    @app.on_event("startup")
    async def on_startup() -> None:
        loop_holder["loop"] = asyncio.get_running_loop()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients.add(ws)
        try:
            await ws.send_json(
                {
                    "type": "init",
                    "turn": pipeline.current_turn.to_ui_dict() if pipeline.current_turn else None,
                    "config": {
                        "tts_backend": cfg.tts_backend,
                        "tts_voice": cfg.active_tts_voice(),
                        "gemini_model": cfg.gemini_model,
                        "stt_model": pipeline.stt.model_id,
                        "obs_scene": pipeline.obs.current_scene,
                    },
                    "canned": pipeline.canned_responses,
                    "routing": inspect_routing(cfg)["checks"],
                }
            )
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            clients.discard(ws)
        except Exception:
            clients.discard(ws)

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(
            {
                "turn": pipeline.current_turn.to_ui_dict() if pipeline.current_turn else None,
                "config": {
                    "tts_backend": cfg.tts_backend,
                    "tts_voice": cfg.active_tts_voice(),
                    "gemini_model": cfg.gemini_model,
                    "stt_model": pipeline.stt.model_id,
                    "obs_scene": pipeline.obs.current_scene,
                },
                "canned": pipeline.canned_responses,
                "routing": inspect_routing(cfg),
            }
        )

    @app.post("/api/capture/start")
    async def api_capture_start(use_operator_mic: bool = False) -> JSONResponse:
        res = await asyncio.to_thread(pipeline.start_capture, use_operator_mic)
        return JSONResponse(res)

    @app.post("/api/capture/stop")
    async def api_capture_stop() -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.stop_capture_and_process)
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/ask")
    async def api_ask(req: AskTextRequest) -> JSONResponse:
        turn = await asyncio.to_thread(
            pipeline.start_turn_from_text,
            req.question,
            tts_backend=req.tts_backend,
            tts_voice=req.tts_voice,
        )
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/turn/approve")
    async def api_approve() -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.approve_current_turn, play_audio=True, block=False)
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/turn/regenerate")
    async def api_regenerate() -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.regenerate_current_turn)
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/turn/discard")
    async def api_discard() -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.discard_current_turn)
        return JSONResponse({"turn": turn.to_ui_dict() if turn else None})

    @app.post("/api/turn/edit")
    async def api_edit(req: EditTurnRequest) -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.update_turn_text, req.english, req.greek)
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/canned")
    async def api_canned(req: CannedRequest) -> JSONResponse:
        turn = await asyncio.to_thread(pipeline.play_canned_response, req.canned_id, play_audio=True, block=False)
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/config")
    async def api_config(req: ConfigUpdateRequest) -> JSONResponse:
        if req.tts_backend:
            cfg.tts_backend = req.tts_backend
        if req.tts_voice:
            if cfg.tts_backend == "google_erasmian":
                cfg.tts_voice_erasmian = req.tts_voice
            elif cfg.tts_backend == "google_modern":
                cfg.tts_voice_modern = req.tts_voice
            elif cfg.tts_backend == "kokoro_erasmian":
                cfg.tts_voice_kokoro = req.tts_voice
        if req.gemini_model:
            cfg.gemini_model = req.gemini_model
            if hasattr(pipeline.llm, "_resolved_model"):
                delattr(pipeline.llm, "_resolved_model")
        payload = {
            "type": "config_updated",
            "config": {
                "tts_backend": cfg.tts_backend,
                "tts_voice": cfg.active_tts_voice(),
                "gemini_model": cfg.gemini_model,
            },
        }
        await broadcast(payload)
        return JSONResponse(payload["config"])

    @app.post("/api/scene")
    async def api_scene(req: SceneSwitchRequest) -> JSONResponse:
        res = await asyncio.to_thread(pipeline.obs.switch_scene, req.scene)
        await broadcast({"type": "scene_switched", **res})
        return JSONResponse(res)

    @app.get("/avatar", response_class=HTMLResponse)
    async def avatar_view() -> HTMLResponse:
        return HTMLResponse(AVATAR_HTML)

    @app.get("/control", response_class=HTMLResponse)
    async def control_view() -> HTMLResponse:
        return HTMLResponse(CONTROL_HTML)

    @app.get("/", response_class=HTMLResponse)
    async def root_redirect() -> HTMLResponse:
        return HTMLResponse(CONTROL_HTML)

    return app


AVATAR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Euclid of Alexandria · MATH E-139 Avatar (1920x1080)</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    background: radial-gradient(circle at 50% 38%, #1c2536 0%, #0d121c 65%, #070a10 100%);
    font-family: "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
    color: #fdfaf2;
    user-select: none;
  }
  .stage {
    position: relative;
    width: 1920px;
    height: 1080px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: 36px 80px 44px 80px;
  }
  .header-banner {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 10px 32px;
    border: 1.5px solid rgba(218, 181, 92, 0.45);
    border-radius: 999px;
    background: rgba(12, 17, 28, 0.78);
    letter-spacing: 0.08em;
    font-size: 24px;
    color: #e5c467;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  }
  .header-banner span.sub {
    color: #b7c2d6;
    font-size: 20px;
    letter-spacing: 0.03em;
  }
  .bust-container {
    position: relative;
    width: 680px;
    height: 620px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: -10px;
  }
  .aura-ring {
    position: absolute;
    width: 540px;
    height: 540px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(229, 196, 103, 0.28) 0%, rgba(229, 196, 103, 0.06) 55%, transparent 72%);
    transition: transform 0.04s linear, opacity 0.04s linear;
    pointer-events: none;
  }
  svg.euclid-svg {
    width: 620px;
    height: 600px;
    z-index: 2;
    filter: drop-shadow(0 18px 36px rgba(0, 0, 0, 0.75));
  }
  .subtitle-box {
    width: 1740px;
    min-height: 230px;
    background: rgba(8, 11, 18, 0.92);
    border: 2.5px solid rgba(229, 196, 103, 0.65);
    border-radius: 22px;
    padding: 24px 44px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.85);
    z-index: 5;
  }
  .greek-sub {
    font-family: "New Athena Unicode", "Gentium Plus", "Palatino Linotype", Georgia, serif;
    font-size: 33px;
    line-height: 1.35;
    color: #f0d078;
    margin-bottom: 14px;
    font-weight: 500;
    text-shadow: 0 2px 6px rgba(0, 0, 0, 0.95);
    max-width: 1640px;
  }
  .english-sub {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 44px;
    line-height: 1.32;
    font-weight: 700;
    color: #ffffff;
    text-shadow:
      -2px -2px 0 #000,
       2px -2px 0 #000,
      -2px  2px 0 #000,
       2px  2px 0 #000,
       0px  4px 12px rgba(0, 0, 0, 0.95);
    max-width: 1650px;
  }
  .progress-pill {
    position: absolute;
    top: -18px;
    right: 40px;
    background: #1b263b;
    border: 1.5px solid #e5c467;
    color: #f0d078;
    padding: 4px 18px;
    border-radius: 999px;
    font-size: 18px;
    font-family: -apple-system, sans-serif;
    font-weight: 600;
    display: none;
  }
  .subtitle-wrapper {
    position: relative;
  }
</style>
</head>
<body>
  <div class="stage">
    <div class="header-banner">
      <span>ΕΥΚΛΕΙΔΗΣ Ο ΑΛΕΞΑΝΔΡΕΥΣ</span>
      <span class="sub">· MATH E-139 · Elements of Geometry</span>
    </div>

    <div class="bust-container">
      <div class="aura-ring" id="auraRing"></div>
      <svg class="euclid-svg" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="marbleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#f4efe4"/>
            <stop offset="55%" stop-color="#ddd3c0"/>
            <stop offset="100%" stop-color="#b5a78f"/>
          </linearGradient>
          <linearGradient id="robeGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#e5dccb"/>
            <stop offset="100%" stop-color="#9e9078"/>
          </linearGradient>
          <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#f5d97e"/>
            <stop offset="100%" stop-color="#b88c28"/>
          </linearGradient>
        </defs>

        <!-- Sacred Geometry Halo (I.1 & I.47 motif) -->
        <g id="geoHalo" stroke="url(#goldGrad)" fill="none" opacity="0.55">
          <circle cx="300" cy="250" r="220" stroke-width="2" stroke-dasharray="8 6"/>
          <circle cx="300" cy="250" r="190" stroke-width="1.5"/>
          <polygon points="300,60 464,345 136,345" stroke-width="1.5" opacity="0.6"/>
          <polygon points="300,440 464,155 136,155" stroke-width="1.2" opacity="0.35"/>
        </g>

        <!-- Classical Bust Pedestal & Himation Robe -->
        <path d="M120,565 L480,565 L450,435 C415,400 365,385 300,385 C235,385 185,400 150,435 Z"
              fill="url(#robeGrad)" stroke="#7a6d58" stroke-width="3"/>
        <path d="M165,440 C220,485 300,505 425,430" fill="none" stroke="#887a62" stroke-width="5"/>
        <path d="M195,495 C255,530 335,535 445,475" fill="none" stroke="#887a62" stroke-width="4"/>
        <rect x="100" y="555" width="400" height="26" rx="6" fill="url(#goldGrad)"/>

        <!-- Neck & Head -->
        <rect x="256" y="330" width="88" height="75" rx="20" fill="url(#marbleGrad)"/>
        <ellipse cx="300" cy="225" rx="102" ry="125" fill="url(#marbleGrad)" stroke="#8c7f6a" stroke-width="2.5"/>

        <!-- Classical Curly Hair & Fillet Band -->
        <path d="M195,205 C185,130 235,88 300,88 C365,88 415,130 405,205 C395,165 360,138 300,138 C240,138 205,165 195,205 Z"
              fill="#d8cebc" stroke="#8c7f6a" stroke-width="2.5"/>
        <path d="M196,175 Q300,152 404,175" fill="none" stroke="url(#goldGrad)" stroke-width="8"/>

        <!-- Brows & Deep-Set Classical Eyes -->
        <path d="M232,202 Q260,192 282,202" fill="none" stroke="#5c5243" stroke-width="5" stroke-linecap="round"/>
        <path d="M318,202 Q340,192 368,202" fill="none" stroke="#5c5243" stroke-width="5" stroke-linecap="round"/>
        <ellipse cx="258" cy="218" rx="16" ry="9" fill="#fdfbf7" stroke="#5c5243" stroke-width="2.5"/>
        <circle cx="258" cy="218" r="5.5" fill="#3b3328"/>
        <ellipse cx="342" cy="218" rx="16" ry="9" fill="#fdfbf7" stroke="#5c5243" stroke-width="2.5"/>
        <circle cx="342" cy="218" r="5.5" fill="#3b3328"/>

        <!-- Classical Nose -->
        <path d="M300,202 L294,262 L310,266" fill="none" stroke="#6e6250" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>

        <!-- Upper Mustache -->
        <path d="M242,292 Q272,272 300,285 Q328,272 358,292" fill="none" stroke="#bfb39e" stroke-width="12" stroke-linecap="round"/>

        <!-- Animated Mouth & Flowing Philosopher Beard Group (driven at 60 Hz by audio RMS) -->
        <g id="jawGroup">
          <!-- Mouth cavity -->
          <ellipse id="mouthOpening" cx="300" cy="298" rx="22" ry="3" fill="#2b1d19" stroke="#5c4738" stroke-width="2"/>
          <!-- Full sculpted Greek beard -->
          <path d="M204,252 C200,335 242,405 300,412 C358,405 400,335 396,252 C380,282 355,295 332,296 C320,308 280,308 268,296 C245,295 220,282 204,252 Z"
                fill="url(#marbleGrad)" stroke="#857862" stroke-width="2.5"/>
          <path d="M238,315 Q265,365 282,398" fill="none" stroke="#9e9078" stroke-width="3"/>
          <path d="M300,315 Q300,368 300,406" fill="none" stroke="#9e9078" stroke-width="3"/>
          <path d="M362,315 Q335,365 318,398" fill="none" stroke="#9e9078" stroke-width="3"/>
        </g>
      </svg>
    </div>

    <div class="subtitle-wrapper">
      <div class="progress-pill" id="progressPill">Sentence 1 / 1</div>
      <div class="subtitle-box">
        <div class="greek-sub" id="greekSub">Πρὸς τῇ δοθείσῃ εὐθείᾳ καὶ τῷ πρὸς αὐτῇ σημείῳ τῇ δοθείσῃ γωνίᾳ εὐθυγράμμῳ ἴσην γωνίαν εὐθύγραμμον συστήσασθαι.</div>
        <div class="english-sub" id="englishSub">Ready for questions — MATH E-139 (Reading Euclid's Elements in Greek)</div>
      </div>
    </div>
  </div>

<script>
  const jawGroup = document.getElementById('jawGroup');
  const mouthOpening = document.getElementById('mouthOpening');
  const auraRing = document.getElementById('auraRing');
  const geoHalo = document.getElementById('geoHalo');
  const greekSub = document.getElementById('greekSub');
  const englishSub = document.getElementById('englishSub');
  const progressPill = document.getElementById('progressPill');

  let currentRms = 0;
  let smoothRms = 0;

  function animateAvatar() {
    smoothRms = smoothRms * 0.65 + currentRms * 0.35;
    const jawDrop = smoothRms * 18.0;
    const mouthRy = 2.5 + smoothRms * 14.0;
    const scale = 1.0 + smoothRms * 0.22;
    const opacity = 0.35 + smoothRms * 0.65;

    jawGroup.setAttribute('transform', `translate(0, ${jawDrop.toFixed(2)})`);
    mouthOpening.setAttribute('ry', mouthRy.toFixed(2));
    auraRing.style.transform = `scale(${scale.toFixed(3)})`;
    auraRing.style.opacity = opacity.toFixed(2);
    geoHalo.setAttribute('opacity', (0.45 + smoothRms * 0.5).toFixed(2));

    requestAnimationFrame(animateAvatar);
  }
  requestAnimationFrame(animateAvatar);

  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'amplitude') {
        currentRms = msg.rms || 0;
      } else if (msg.type === 'subtitle') {
        greekSub.textContent = msg.greek || '';
        englishSub.textContent = msg.english || '';
        if (msg.total_sentences && msg.total_sentences > 0 && msg.speaking) {
          progressPill.style.display = 'block';
          progressPill.textContent = `Speaking ${msg.sentence_index + 1} / ${msg.total_sentences}`;
        } else {
          progressPill.style.display = 'none';
        }
      }
    };
    ws.onclose = () => setTimeout(connectWS, 1000);
  }
  connectWS();
</script>
</body>
</html>
"""


CONTROL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Euclid Control Console · MATH E-139</title>
<style>
  :root {
    --bg: #0f1420;
    --panel: #171f30;
    --border: #2c3a57;
    --gold: #e5c467;
    --text: #f3f6fc;
    --muted: #9aa8c2;
    --green: #2ea043;
    --amber: #d29922;
    --red: #f85149;
    --blue: #388bfd;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 18px 24px;
    line-height: 1.45;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
  }
  header h1 {
    font-size: 20px;
    color: var(--gold);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .toolbar {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }
  select, input, textarea, button {
    font-family: inherit;
    font-size: 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #0d121d;
    color: var(--text);
    padding: 8px 12px;
  }
  button {
    cursor: pointer;
    font-weight: 600;
    transition: all 0.12s ease;
  }
  button:hover:not(:disabled) { filter: brightness(1.15); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-capture { background: var(--blue); border-color: #58a6ff; color: #fff; min-width: 175px; }
  .btn-capture.recording { background: var(--red); border-color: #ff7b72; animation: pulse 1s infinite; }
  .btn-approve { background: var(--green); border-color: #3fb950; color: #fff; font-size: 16px; padding: 10px 22px; }
  .btn-regen { background: #9e6a03; border-color: #d29922; color: #fff; }
  .btn-discard { background: #8b1e24; border-color: #f85149; color: #fff; }
  .btn-scene { background: #26334d; border-color: var(--gold); color: var(--gold); }
  .btn-scene.active-scene { background: var(--gold); color: #0b0f19; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .grid {
    display: grid;
    grid-template-columns: 1.45fr 1fr;
    gap: 18px;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
  }
  .panel h2 {
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .capture-bar {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 12px;
  }
  .mic-meter-bg {
    width: 120px;
    height: 12px;
    background: #0b0f18;
    border: 1px solid var(--border);
    border-radius: 999px;
    overflow: hidden;
  }
  .mic-meter-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #2ea043, #e5c467, #f85149);
    transition: width 0.06s linear;
  }
  .manual-box {
    display: flex;
    gap: 8px;
    width: 100%;
  }
  .manual-box input { flex: 1; }

  .metrics-strip {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 8px;
    margin-bottom: 16px;
  }
  .metric-card {
    background: #101624;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
    text-align: center;
  }
  .metric-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; }
  .metric-card .val { font-size: 17px; font-weight: 700; color: var(--gold); margin-top: 2px; }

  .badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 700;
  }
  .badge-idle { background: #21283b; color: var(--muted); }
  .badge-synth { background: rgba(210, 153, 34, 0.2); color: #f0b72f; border: 1px solid #d29922; }
  .badge-ready { background: rgba(46, 160, 67, 0.22); color: #56d364; border: 1px solid #2ea043; }
  .badge-speaking { background: rgba(56, 139, 253, 0.22); color: #79c0ff; border: 1px solid #388bfd; }

  .field-group { margin-bottom: 12px; }
  .field-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 600; }
  textarea { width: 100%; min-height: 76px; resize: vertical; line-height: 1.4; }
  textarea.greek-input {
    font-family: "New Athena Unicode", "Gentium Plus", "Palatino Linotype", Georgia, serif;
    font-size: 17px;
    color: #f0d078;
  }
  .sources-list { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  .source-chip {
    background: #212c42;
    border: 1px solid #3b4e73;
    color: #b8ccf0;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 999px;
  }
  .action-row {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .canned-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background: #101624;
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 8px;
  }
  .canned-item .c-title { font-weight: 600; font-size: 14px; color: var(--gold); }
  .canned-item .c-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
</style>
</head>
<body>
  <header>
    <h1>
      <span>🏛️ Euclid Live Control Console</span>
      <span style="font-size:13px;color:var(--muted);font-weight:400;">MATH E-139 · Speculative Pre-Synthesis</span>
    </h1>
    <div class="toolbar">
      <label style="font-size:12px;color:var(--muted);">Scene:</label>
      <button class="btn-scene" id="sceneDavidBtn" onclick="switchScene('David')">🎥 David (Webcam)</button>
      <button class="btn-scene active-scene" id="sceneEuclidBtn" onclick="switchScene('Euclid')">🏛️ Euclid (Avatar)</button>

      <label style="font-size:12px;color:var(--muted);margin-left:8px;">TTS Mode:</label>
      <select id="ttsPresetSelect" onchange="updateTTSPreset()">
        <option value="google_erasmian|en-US-Neural2-D">Erasmian IPA · Google Male (en-US-Neural2-D)</option>
        <option value="google_erasmian|en-US-Neural2-J">Erasmian IPA · Google Male (en-US-Neural2-J)</option>
        <option value="google_erasmian|en-US-Neural2-H">Erasmian IPA · euclid-tts Baseline (en-US-Neural2-H)</option>
        <option value="kokoro_erasmian|am_adam">Erasmian IPA · Local Kokoro Male (am_adam)</option>
        <option value="kokoro_erasmian|af_heart">Erasmian IPA · Local Kokoro Female (af_heart)</option>
        <option value="google_modern|el-GR-Wavenet-B">Modern Greek · Google Wavenet (el-GR-Wavenet-B)</option>
        <option value="macos_modern|Melina">Modern Greek · Local macOS (Melina)</option>
      </select>
      <a href="/avatar" target="_blank" style="color:var(--gold);font-size:13px;text-decoration:none;margin-left:6px;">Open /avatar ↗</a>
    </div>
  </header>

  <div class="metrics-strip">
    <div class="metric-card"><div class="label">STT (MLX)</div><div class="val" id="mStt">—</div></div>
    <div class="metric-card"><div class="label">Course RAG</div><div class="val" id="mRag">—</div></div>
    <div class="metric-card"><div class="label">Gemini LLM</div><div class="val" id="mLlm">—</div></div>
    <div class="metric-card"><div class="label">TTS Sent 1</div><div class="val" id="mTts1">—</div></div>
    <div class="metric-card"><div class="label">Unattended Total</div><div class="val" id="mUnattended">—</div></div>
    <div class="metric-card"><div class="label">Post-Approval</div><div class="val" id="mPostApprove">—</div></div>
  </div>

  <div class="grid">
    <div>
      <div class="panel">
        <h2>
          <span>1. Question Capture & Manual Override</span>
          <span style="font-size:12px;text-transform:none;">Hotkey: <b>Space</b> (Hold/Toggle Capture)</span>
        </h2>
        <div class="capture-bar">
          <button class="btn-capture" id="captureBtn" onclick="toggleCapture()">🎙️ Start Capture</button>
          <label style="font-size:12px;display:flex;align-items:center;gap:5px;color:var(--muted);">
            <input type="checkbox" id="useOpMicCheck"> Use Operator Mic
          </label>
          <div class="mic-meter-bg"><div class="mic-meter-fill" id="micMeter"></div></div>
          <span id="micDeviceLabel" style="font-size:12px;color:var(--muted);">Idle</span>
        </div>
        <div class="manual-box">
          <input type="text" id="manualQuestionInput" placeholder="Type or edit a MATH E-139 question in English (e.g. 'State the enunciation of Proposition I.23 in Greek and English')..." onkeydown="if(event.key==='Enter') submitManualQuestion()">
          <button onclick="submitManualQuestion()" style="background:#26334d;border-color:#486294;">Ask Euclid ↵</button>
        </div>
      </div>

      <div class="panel">
        <h2>
          <span>2. Operator Review & Speculative Pre-Synthesis</span>
          <span class="badge badge-idle" id="readinessBadge">Idle</span>
        </h2>

        <div class="field-group">
          <label>Captured Transcript</label>
          <input type="text" id="transcriptBox" style="width:100%;" readonly placeholder="Waiting for question...">
        </div>

        <div class="field-group">
          <label>Cited Course Sources (`~/Projects/Courses/26Fall/mathe139/`)</label>
          <div class="sources-list" id="sourcesList"><span style="color:var(--muted);font-size:13px;">None yet</span></div>
        </div>

        <div class="field-group">
          <label>Generated English Answer (Subtitle Track — Editable)</label>
          <textarea id="englishBox" placeholder="English answer will appear here..."></textarea>
        </div>

        <div class="field-group">
          <label>Generated Polytonic Ancient Greek (Voice Track — Editable)</label>
          <textarea class="greek-input" id="greekBox" placeholder="Ἑλληνικὴ ἀπόκρισις..."></textarea>
        </div>

        <div class="action-row">
          <div style="display:flex;gap:8px;">
            <button class="btn-approve" id="approveBtn" onclick="approveTurn()" disabled>✅ Approve & Speak (A)</button>
            <button onclick="saveEdits()" id="editBtn" disabled>✏️ Re-Synthesize Edited Text</button>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="btn-regen" id="regenBtn" onclick="regenerateTurn()" disabled>🔄 Regenerate (R)</button>
            <button class="btn-discard" id="discardBtn" onclick="discardTurn()" disabled>🗑️ Discard (Esc)</button>
          </div>
        </div>
      </div>
    </div>

    <div>
      <div class="panel">
        <h2>
          <span>⚡ One-Click Canned Fallback (`~0 s` Latency Floor)</span>
          <span style="font-size:11px;color:var(--muted);">Pre-Rendered Masters</span>
        </h2>
        <div id="cannedContainer"></div>
      </div>

      <div class="panel">
        <h2><span>Retrieved Course Chunks Breakdown</span></h2>
        <div id="retrievedChunksBox" style="font-size:13px;color:var(--muted);">
          Chunks retrieved from <code>.cache/course_index.sqlite</code> will appear here with match types and entity keys.
        </div>
      </div>
    </div>
  </div>

<script>
  let isCapturing = false;
  let activeTurn = null;

  function renderTurn(turn) {
    activeTurn = turn;
    if (!turn) return;

    document.getElementById('transcriptBox').value = turn.transcript || '';
    if (document.activeElement !== document.getElementById('englishBox')) {
      document.getElementById('englishBox').value = turn.english || '';
    }
    if (document.activeElement !== document.getElementById('greekBox')) {
      document.getElementById('greekBox').value = turn.greek || '';
    }

    // Timings
    const t = turn.timings || {};
    document.getElementById('mStt').textContent = t.stt_ms ? `${t.stt_ms} ms` : '—';
    document.getElementById('mRag').textContent = t.rag_ms ? `${t.rag_ms} ms` : '—';
    document.getElementById('mLlm').textContent = t.llm_ms ? `${t.llm_ms} ms` : '—';
    document.getElementById('mTts1').textContent = t.tts_first_sentence_ms ? `${t.tts_first_sentence_ms} ms` : '—';
    document.getElementById('mUnattended').textContent = t.total_unattended_ms ? `${(t.total_unattended_ms/1000).toFixed(2)} s` : '—';
    document.getElementById('mPostApprove').textContent = t.post_approval_start_ms ? `${t.post_approval_start_ms} ms` : '—';

    // Sources
    const sList = document.getElementById('sourcesList');
    sList.innerHTML = '';
    (turn.sources || []).forEach(s => {
      const span = document.createElement('span');
      span.className = 'source-chip';
      span.textContent = s;
      sList.appendChild(span);
    });

    // Retrieved chunk details
    const rBox = document.getElementById('retrievedChunksBox');
    if (turn.retrieved_details && turn.retrieved_details.length) {
      rBox.innerHTML = turn.retrieved_details.map(d =>
        `<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #222d44;">
          <b style="color:#e5c467;">[${d.match_type.toUpperCase()}] ${d.source_label}</b> — ${d.title}<br>
          <span style="font-size:11px;color:#79c0ff;">Keys: ${(d.entity_keys || []).join(', ') || 'BM25 keyword'}</span>
        </div>`
      ).join('');
    }

    // Readiness badge & buttons
    const badge = document.getElementById('readinessBadge');
    const canAct = ['synthesizing', 'ready', 'speaking', 'completed'].includes(turn.status);
    document.getElementById('approveBtn').disabled = !canAct;
    document.getElementById('editBtn').disabled = !canAct;
    document.getElementById('regenBtn').disabled = !canAct;
    document.getElementById('discardBtn').disabled = !canAct;

    if (turn.status === 'synthesizing') {
      badge.className = 'badge badge-synth';
      badge.textContent = `Synthesizing ${turn.synthesized_count}/${turn.total_sentences}...`;
    } else if (turn.status === 'ready') {
      badge.className = 'badge badge-ready';
      badge.textContent = `Ready (${turn.synthesized_count}/${turn.total_sentences} pre-synthesized)`;
    } else if (turn.status === 'speaking') {
      badge.className = 'badge badge-speaking';
      badge.textContent = `Speaking (${turn.synthesized_count}/${turn.total_sentences})`;
    } else {
      badge.className = 'badge badge-idle';
      badge.textContent = turn.status.toUpperCase();
    }
  }

  function renderCanned(items) {
    const c = document.getElementById('cannedContainer');
    c.innerHTML = (items || []).map(item => `
      <div class="canned-item">
        <div>
          <div class="c-title">${item.title}</div>
          <div class="c-sub">${item.tts_voice} · ${(item.sources || []).join(', ')}</div>
        </div>
        <button onclick="playCanned('${item.id}')" style="background:#1f3225;border-color:#2ea043;color:#7ee787;">▶ Speak</button>
      </div>
    `).join('');
  }

  async function toggleCapture() {
    const btn = document.getElementById('captureBtn');
    if (!isCapturing) {
      const useOp = document.getElementById('useOpMicCheck').checked;
      const r = await fetch(`/api/capture/start?use_operator_mic=${useOp}`, { method: 'POST' });
      const data = await r.json();
      isCapturing = true;
      btn.className = 'btn-capture recording';
      btn.textContent = '⏹️ Stop & Transcribe';
      document.getElementById('micDeviceLabel').textContent = data.device || 'Capturing...';
    } else {
      isCapturing = false;
      btn.className = 'btn-capture';
      btn.textContent = '🎙️ Start Capture';
      await fetch('/api/capture/stop', { method: 'POST' });
    }
  }

  async function submitManualQuestion() {
    const inp = document.getElementById('manualQuestionInput');
    const q = inp.value.trim();
    if (!q) return;
    await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
  }

  async function approveTurn() {
    await fetch('/api/turn/approve', { method: 'POST' });
  }

  async function regenerateTurn() {
    await fetch('/api/turn/regenerate', { method: 'POST' });
  }

  async function discardTurn() {
    await fetch('/api/turn/discard', { method: 'POST' });
  }

  async function saveEdits() {
    const eng = document.getElementById('englishBox').value;
    const grk = document.getElementById('greekBox').value;
    await fetch('/api/turn/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ english: eng, greek: grk }),
    });
  }

  async function playCanned(cannedId) {
    await fetch('/api/canned', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ canned_id: cannedId }),
    });
  }

  async function updateTTSPreset() {
    const val = document.getElementById('ttsPresetSelect').value;
    const [backend, voice] = val.split('|');
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tts_backend: backend, tts_voice: voice }),
    });
  }

  async function switchScene(scene) {
    document.getElementById('sceneDavidBtn').classList.toggle('active-scene', scene === 'David');
    document.getElementById('sceneEuclidBtn').classList.toggle('active-scene', scene === 'Euclid');
    await fetch('/api/scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene }),
    });
  }

  // Keyboard shortcuts when not typing in an input/textarea
  window.addEventListener('keydown', (e) => {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
      if (e.key === 'Escape') document.activeElement.blur();
      return;
    }
    if (e.code === 'Space') {
      e.preventDefault();
      toggleCapture();
    } else if (e.key === 'a' || e.key === 'A') {
      e.preventDefault();
      approveTurn();
    } else if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      regenerateTurn();
    } else if (e.key === 'Escape' || e.key === 'd' || e.key === 'D') {
      e.preventDefault();
      discardTurn();
    }
  });

  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'init') {
        renderCanned(msg.canned || []);
        if (msg.turn) renderTurn(msg.turn);
      } else if (msg.type === 'turn_update') {
        renderTurn(msg.turn);
      } else if (msg.type === 'mic_level') {
        const pct = Math.min(100, Math.round((msg.rms || 0) * 350));
        document.getElementById('micMeter').style.width = `${pct}%`;
      }
    };
    ws.onclose = () => setTimeout(connectWS, 1000);
  }
  connectWS();
</script>
</body>
</html>
"""
