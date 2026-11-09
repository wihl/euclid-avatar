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
from .stage_html import AVATAR_HTML


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


class PresentationPlayRequest(BaseModel):
    start_slide: int = 1
    start_segment_id: str | None = None
    single_slide: bool = False
    single_segment: bool = False
    voice: str | None = None


class PresentationSlideSelectRequest(BaseModel):
    slide_number: int
    voice: str | None = None


class PresentationPrebuildRequest(BaseModel):
    voice: str | None = None
    force: bool = False


def create_app(cfg: Config, pipeline: EuclidPipeline) -> FastAPI:
    """Create the FastAPI application for the II.13 presentation and live Q&A."""
    app = FastAPI(title="Euclid Avatar · Elements II.13 Presentation & Q&A")
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
                    "turn": (
                        pipeline.current_turn.to_ui_dict()
                        if pipeline.current_turn
                        else None
                    ),
                    "presentation": pipeline.get_presentation_state(),
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
                "turn": (
                    pipeline.current_turn.to_ui_dict()
                    if pipeline.current_turn
                    else None
                ),
                "presentation": pipeline.get_presentation_state(),
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

    @app.get("/api/presentation")
    async def api_get_presentation() -> JSONResponse:
        state = await asyncio.to_thread(pipeline.get_presentation_state)
        return JSONResponse(state)

    @app.post("/api/presentation/prebuild")
    async def api_prebuild_presentation(
        req: PresentationPrebuildRequest,
    ) -> JSONResponse:
        res = await asyncio.to_thread(
            pipeline.prebuild_presentation_deck,
            voice=req.voice,
            force=req.force,
        )
        return JSONResponse(res)

    @app.post("/api/presentation/play")
    async def api_play_presentation(
        req: PresentationPlayRequest,
    ) -> JSONResponse:
        state = await asyncio.to_thread(
            pipeline.play_presentation,
            start_slide=req.start_slide,
            start_segment_id=req.start_segment_id,
            single_slide=req.single_slide,
            single_segment=req.single_segment,
            voice=req.voice,
            play_audio=True,
            block=False,
        )
        return JSONResponse(state)

    @app.post("/api/presentation/pause")
    async def api_pause_presentation() -> JSONResponse:
        state = await asyncio.to_thread(pipeline.pause_presentation)
        return JSONResponse(state)

    @app.post("/api/presentation/resume")
    async def api_resume_presentation() -> JSONResponse:
        state = await asyncio.to_thread(pipeline.resume_presentation)
        return JSONResponse(state)

    @app.post("/api/presentation/stop")
    async def api_stop_presentation() -> JSONResponse:
        state = await asyncio.to_thread(pipeline.stop_presentation)
        return JSONResponse(state)

    @app.post("/api/presentation/select_slide")
    async def api_select_slide(
        req: PresentationSlideSelectRequest,
    ) -> JSONResponse:
        state = await asyncio.to_thread(
            pipeline.select_presentation_slide,
            req.slide_number,
            req.voice,
        )
        return JSONResponse(state)

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
        turn = await asyncio.to_thread(
            pipeline.approve_current_turn, play_audio=True, block=False
        )
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
        turn = await asyncio.to_thread(
            pipeline.update_turn_text, req.english, req.greek
        )
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/canned")
    async def api_canned(req: CannedRequest) -> JSONResponse:
        turn = await asyncio.to_thread(
            pipeline.play_canned_response,
            req.canned_id,
            play_audio=True,
            block=False,
        )
        return JSONResponse(turn.to_ui_dict())

    @app.post("/api/config")
    async def api_config(req: ConfigUpdateRequest) -> JSONResponse:
        if req.tts_backend:
            cfg.tts_backend = req.tts_backend
        if req.tts_voice:
            if cfg.tts_backend == "google_au_bilingual":
                cfg.tts_voice_english = req.tts_voice
                cfg.tts_voice_erasmian = req.tts_voice
            elif cfg.tts_backend == "google_erasmian":
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



CONTROL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Euclid II.13 Presentation & Q&A Control Console · MATH E-139</title>
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
    padding: 16px 22px;
    line-height: 1.45;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
    flex-wrap: wrap;
    gap: 10px;
  }
  header h1 {
    font-size: 19px;
    color: var(--gold);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .toolbar {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  select, input, textarea, button {
    font-family: inherit;
    font-size: 13px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #0d121d;
    color: var(--text);
    padding: 7px 11px;
  }
  button {
    cursor: pointer;
    font-weight: 600;
    transition: all 0.12s ease;
  }
  button:hover:not(:disabled) { filter: brightness(1.15); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-play-deck { background: var(--green); border-color: #3fb950; color: #fff; font-size: 14px; padding: 8px 16px; }
  .btn-capture { background: var(--blue); border-color: #58a6ff; color: #fff; min-width: 165px; }
  .btn-capture.recording { background: var(--red); border-color: #ff7b72; animation: pulse 1s infinite; }
  .btn-approve { background: var(--green); border-color: #3fb950; color: #fff; font-size: 15px; padding: 9px 18px; }
  .btn-regen { background: #9e6a03; border-color: #d29922; color: #fff; }
  .btn-discard { background: #8b1e24; border-color: #f85149; color: #fff; }
  .btn-scene { background: #26334d; border-color: var(--gold); color: var(--gold); }
  .btn-scene.active-scene { background: var(--gold); color: #0b0f19; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 16px;
  }
  .panel h2 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .slides-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }
  .slide-tab {
    background: #101624;
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 10px 12px;
    cursor: pointer;
    transition: all 0.12s ease;
  }
  .slide-tab.active-slide {
    border-color: var(--gold);
    background: rgba(229, 196, 103, 0.12);
  }
  .slide-tab .st-num { font-size: 11px; color: var(--gold); font-weight: 700; text-transform: uppercase; }
  .slide-tab .st-title { font-size: 13px; font-weight: 600; color: var(--text); margin-top: 2px; }
  .slide-tab .st-meta { font-size: 11px; color: var(--muted); margin-top: 4px; display: flex; justify-content: space-between; align-items: center; }

  .segments-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .seg-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    background: #101624;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 13px;
  }
  .seg-row.active-seg {
    border-color: #58a6ff;
    background: rgba(56, 139, 253, 0.14);
  }

  .grid {
    display: grid;
    grid-template-columns: 1.45fr 1fr;
    gap: 16px;
  }
  .capture-bar {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 10px;
  }
  .mic-meter-bg {
    width: 110px;
    height: 11px;
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
    margin-bottom: 14px;
  }
  .metric-card {
    background: #101624;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 7px 10px;
    text-align: center;
  }
  .metric-card .label { font-size: 10px; color: var(--muted); text-transform: uppercase; }
  .metric-card .val { font-size: 15px; font-weight: 700; color: var(--gold); margin-top: 2px; }

  .badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
  }
  .badge-idle { background: #21283b; color: var(--muted); }
  .badge-synth { background: rgba(210, 153, 34, 0.2); color: #f0b72f; border: 1px solid #d29922; }
  .badge-ready { background: rgba(46, 160, 67, 0.22); color: #56d364; border: 1px solid #2ea043; }
  .badge-speaking { background: rgba(56, 139, 253, 0.22); color: #79c0ff; border: 1px solid #388bfd; }

  .field-group { margin-bottom: 10px; }
  .field-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 600; }
  textarea { width: 100%; min-height: 68px; resize: vertical; line-height: 1.4; }
  textarea.greek-input {
    font-family: "New Athena Unicode", "Gentium Plus", "Palatino Linotype", Georgia, serif;
    font-size: 16px;
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
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }
  .canned-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 9px 11px;
    background: #101624;
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 7px;
  }
  .canned-item .c-title { font-weight: 600; font-size: 13px; color: var(--gold); }
  .canned-item .c-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
</style>
</head>
<body>
  <header>
    <h1>
      <span>🏛️ Euclid · Elements II.13 Presentation & Q&A Console</span>
      <span style="font-size:12px;color:var(--muted);font-weight:400;">Australian English + Erasmian Greek IPA</span>
    </h1>
    <div class="toolbar">
      <label style="font-size:12px;color:var(--muted);">Scene:</label>
      <button class="btn-scene" id="sceneDavidBtn" onclick="switchScene('David')">🎥 David</button>
      <button class="btn-scene active-scene" id="sceneEuclidBtn" onclick="switchScene('Euclid')">🏛️ Euclid</button>

      <label style="font-size:12px;color:var(--muted);margin-left:6px;">Voice Model:</label>
      <select id="ttsPresetSelect" onchange="updateTTSPreset()">
        <option value="google_au_bilingual|en-AU-Chirp3-HD-Charon">AU Male + Erasmian IPA · Chirp3-HD Charon (Expressive HD, Default)</option>
        <option value="google_au_bilingual|en-AU-Chirp3-HD-Puck">AU Male + Erasmian IPA · Chirp3-HD Puck (Expressive HD)</option>
        <option value="google_au_bilingual|en-AU-Chirp3-HD-Orus">AU Male + Erasmian IPA · Chirp3-HD Orus</option>
        <option value="google_au_bilingual|en-AU-Neural2-D">AU Male + Erasmian IPA · Neural2-D (Fast)</option>
        <option value="google_au_bilingual|en-AU-Polyglot-1">AU Male + Erasmian IPA · Polyglot-1</option>
        <option value="google_au_bilingual|en-AU-News-G">AU Male + Erasmian IPA · News-G</option>
        <option value="google_erasmian|en-AU-Chirp3-HD-Charon">Pure Erasmian Greek Only · en-AU-Chirp3-HD-Charon</option>
        <option value="kokoro_erasmian|bm_george">Local Kokoro Male · bm_george</option>
      </select>
      <button onclick="openZoomStage16x9()" style="background:#26334d;border-color:var(--gold);color:var(--gold);" title="Open a dedicated 16:9 HD stage window for Zoom screen/window capture">📺 Open 16:9 Zoom Stage</button>
      <a href="/avatar" target="_blank" style="color:var(--gold);font-size:13px;text-decoration:none;margin-left:4px;">Open /avatar ↗</a>
    </div>
  </header>

  <!-- SECTION 1: 5-MINUTE II.13 GREEK PRESENTATION -->
  <div class="panel">
    <h2>
      <span>1. 5-Minute Prepared Presentation — Euclid, Elements II.13: The Greek (Slides 1–5)</span>
      <div style="display:flex;gap:8px;align-items:center;">
        <span class="badge badge-idle" id="presStatusBadge">Ready</span>
        <span id="presDurationLabel" style="font-size:12px;color:var(--gold);text-transform:none;">Total: —</span>
        <button class="btn-play-deck" onclick="playPresentation(1, null, false, false)">▶ Play Full 5-Min Presentation</button>
        <button onclick="pauseOrResumePresentation()" id="presPauseBtn">⏸ Pause</button>
        <button class="btn-discard" onclick="stopPresentation()">⏹ Stop</button>
        <button onclick="prebuildPresentation()" id="prebuildBtn" title="Pre-synthesize and cache all 5 slides">⚡ Pre-Render All 5 Slides</button>
      </div>
    </h2>

    <div class="slides-strip" id="slidesStrip"></div>
    <div class="segments-list" id="segmentsList"></div>
  </div>

  <div class="metrics-strip">
    <div class="metric-card"><div class="label">STT (MLX)</div><div class="val" id="mStt">—</div></div>
    <div class="metric-card"><div class="label">Course RAG</div><div class="val" id="mRag">—</div></div>
    <div class="metric-card"><div class="label">Gemini LLM</div><div class="val" id="mLlm">—</div></div>
    <div class="metric-card"><div class="label">TTS Sent 1</div><div class="val" id="mTts1">—</div></div>
    <div class="metric-card"><div class="label">Unattended Total</div><div class="val" id="mUnattended">—</div></div>
    <div class="metric-card"><div class="label">Post-Approval</div><div class="val" id="mPostApprove">—</div></div>
  </div>

  <!-- SECTION 2: PROFESSOR Q&A -->
  <div class="grid">
    <div>
      <div class="panel">
        <h2>
          <span>2. Live Professor Q&A (Paul Bamberg & Graeme Bird — II.13)</span>
          <span style="font-size:12px;text-transform:none;">Hotkey: <b>Space</b> (Capture) · <b>A</b> (Approve)</span>
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
          <input type="text" id="manualQuestionInput" placeholder="Ask a question about Elements II.13 (e.g. 'Parse the verb τέτμηται in II.13' or 'How does II.13 relate to the Law of Cosines?')..." onkeydown="if(event.key==='Enter') submitManualQuestion()">
          <button onclick="submitManualQuestion()" style="background:#26334d;border-color:#486294;">Ask Euclid ↵</button>
        </div>
      </div>

      <div class="panel">
        <h2>
          <span>3. Q&A Review & Speculative Pre-Synthesis</span>
          <span class="badge badge-idle" id="readinessBadge">Idle</span>
        </h2>

        <div class="field-group">
          <label>Captured Professor Question</label>
          <input type="text" id="transcriptBox" style="width:100%;" readonly placeholder="Waiting for question...">
        </div>

        <div class="field-group">
          <label>Cited Course Sources (`~/Projects/Courses/26Fall/mathe139/`)</label>
          <div class="sources-list" id="sourcesList"><span style="color:var(--muted);font-size:13px;">None yet</span></div>
        </div>

        <div class="field-group">
          <label>Spoken Answer (Male Australian English + Embedded Erasmian Greek — Editable)</label>
          <textarea id="englishBox" placeholder="Bilingual Australian English + Erasmian Greek answer will appear here..."></textarea>
        </div>

        <div class="field-group">
          <label>Greek Quotation Display Track (Editable)</label>
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
          <span>⚡ Prepared II.13 Professor Q&A (`1–5` Instant Playback)</span>
          <span style="font-size:11px;color:var(--muted);">Bird & Bamberg Questions</span>
        </h2>
        <div id="cannedContainer"></div>
      </div>

      <div class="panel">
        <h2><span>Retrieved Course Chunks Breakdown</span></h2>
        <div id="retrievedChunksBox" style="font-size:13px;color:var(--muted);">
          Chunks retrieved from <code>.cache/course_index.sqlite</code> will appear here.
        </div>
      </div>
    </div>
  </div>

<script>
  let isCapturing = false;
  let activeTurn = null;
  let presState = null;

  function fmtSec(sec) {
    if (!sec || sec <= 0) return '—';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  function renderPresentation(pres) {
    presState = pres;
    if (!pres || !pres.deck) return;
    const deck = pres.deck;
    document.getElementById('presDurationLabel').textContent = `Total: ${fmtSec(deck.total_duration_s)} (Target ~5m 00s)`;

    const badge = document.getElementById('presStatusBadge');
    const pauseBtn = document.getElementById('presPauseBtn');
    if (pres.playing && !pres.paused) {
      badge.className = 'badge badge-speaking';
      badge.textContent = `🔊 Speaking Slide ${pres.current_slide_number}`;
      pauseBtn.textContent = '⏸ Pause';
    } else if (pres.playing && pres.paused) {
      badge.className = 'badge badge-synth';
      badge.textContent = `⏸ Paused (Slide ${pres.current_slide_number})`;
      pauseBtn.textContent = '▶ Resume';
    } else {
      badge.className = 'badge badge-ready';
      badge.textContent = 'Ready';
      pauseBtn.textContent = '⏸ Pause';
    }

    const strip = document.getElementById('slidesStrip');
    strip.innerHTML = (deck.slides || []).map(s => {
      const isAct = s.slide_number === pres.current_slide_number;
      return `<div class="slide-tab ${isAct ? 'active-slide' : ''}" onclick="selectSlide(${s.slide_number})">
        <div class="st-num">Slide ${s.slide_number}</div>
        <div class="st-title">${s.title}</div>
        <div class="st-meta">
          <span>${s.segments.length} segs · ${fmtSec(s.duration_s)}</span>
          <button onclick="event.stopPropagation(); playPresentation(${s.slide_number}, null, true, false)" style="padding:3px 8px;font-size:11px;background:#26334d;border-color:#486294;">▶ Slide</button>
        </div>
      </div>`;
    }).join('');

    const curSlide = (deck.slides || []).find(s => s.slide_number === pres.current_slide_number) || deck.slides[0];
    const segList = document.getElementById('segmentsList');
    if (curSlide) {
      segList.innerHTML = curSlide.segments.map((seg, i) => {
        const isActSeg = pres.playing && seg.id === pres.current_segment_id;
        return `<div class="seg-row ${isActSeg ? 'active-seg' : ''}">
          <div style="flex:1;">
            <div style="font-weight:600;color:var(--gold);font-size:12px;">Slide ${curSlide.slide_number}.${i+1} (${seg.id}) · ${seg.cached ? fmtSec(seg.duration_s) : 'Not cached yet'}</div>
            <div style="color:var(--text);margin-top:2px;">${seg.english}</div>
          </div>
          <div style="display:flex;gap:6px;">
            <button onclick="playPresentation(${curSlide.slide_number}, '${seg.id}', false, true)" style="padding:5px 10px;font-size:12px;">▶ Seg</button>
            <button onclick="playPresentation(${curSlide.slide_number}, '${seg.id}', false, false)" style="padding:5px 10px;font-size:12px;background:#1f3a27;border-color:#2ea043;">▶ From Here</button>
          </div>
        </div>`;
      }).join('');
    }
  }

  async function selectSlide(slideNum) {
    const r = await fetch('/api/presentation/select_slide', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({slide_number: slideNum})
    });
    renderPresentation(await r.json());
  }

  async function playPresentation(startSlide, startSegId, singleSlide, singleSeg) {
    const r = await fetch('/api/presentation/play', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        start_slide: startSlide,
        start_segment_id: startSegId,
        single_slide: singleSlide,
        single_segment: singleSeg
      })
    });
    renderPresentation(await r.json());
  }

  async function pauseOrResumePresentation() {
    if (!presState) return;
    const url = presState.paused ? '/api/presentation/resume' : '/api/presentation/pause';
    const r = await fetch(url, {method: 'POST'});
    renderPresentation(await r.json());
  }

  async function stopPresentation() {
    const r = await fetch('/api/presentation/stop', {method: 'POST'});
    renderPresentation(await r.json());
  }

  async function prebuildPresentation() {
    const btn = document.getElementById('prebuildBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Pre-Rendering...';
    try {
      await fetch('/api/presentation/prebuild', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({force: false})
      });
    } finally {
      btn.disabled = false;
      btn.textContent = '⚡ Pre-Render All 5 Slides';
    }
  }

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

    const t = turn.timings || {};
    document.getElementById('mStt').textContent = t.stt_ms ? `${t.stt_ms} ms` : '—';
    document.getElementById('mRag').textContent = t.rag_ms ? `${t.rag_ms} ms` : '—';
    document.getElementById('mLlm').textContent = t.llm_ms ? `${t.llm_ms} ms` : '—';
    document.getElementById('mTts1').textContent = t.tts_first_sentence_ms ? `${t.tts_first_sentence_ms} ms` : '—';
    document.getElementById('mUnattended').textContent = t.total_unattended_ms ? `${(t.total_unattended_ms/1000).toFixed(2)} s` : '—';
    document.getElementById('mPostApprove').textContent = t.post_approval_start_ms ? `${t.post_approval_start_ms} ms` : '—';

    const srcBox = document.getElementById('sourcesList');
    if (turn.sources && turn.sources.length) {
      srcBox.innerHTML = turn.sources.map(s => `<span class="source-chip">${s}</span>`).join('');
    } else {
      srcBox.innerHTML = '<span style="color:var(--muted);font-size:13px;">None</span>';
    }

    const chunksBox = document.getElementById('retrievedChunksBox');
    if (turn.retrieved_details && turn.retrieved_details.length) {
      chunksBox.innerHTML = turn.retrieved_details.map((c, idx) =>
        `<div style="margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid #222d44;">
          <b style="color:var(--gold);">${idx+1}. ${c.source_label}</b> <span style="font-size:11px;">(${c.match_type})</span><br>
          <span>${c.title}</span>
        </div>`
      ).join('');
    }

    const badge = document.getElementById('readinessBadge');
    const approveBtn = document.getElementById('approveBtn');
    const editBtn = document.getElementById('editBtn');
    const regenBtn = document.getElementById('regenBtn');
    const discardBtn = document.getElementById('discardBtn');

    if (turn.status === 'synthesizing') {
      if (turn.synthesized_count > 0) {
        badge.className = 'badge badge-ready';
        badge.textContent = `🟢 Ready (Sent ${turn.synthesized_count}/${turn.total_sentences} buffered)`;
        approveBtn.disabled = false;
      } else {
        badge.className = 'badge badge-synth';
        badge.textContent = `🟡 Synthesizing (0/${turn.total_sentences})...`;
        approveBtn.disabled = false;
      }
      editBtn.disabled = false;
      regenBtn.disabled = false;
      discardBtn.disabled = false;
    } else if (turn.status === 'ready') {
      badge.className = 'badge badge-ready';
      badge.textContent = `🟢 Ready (${turn.total_sentences}/${turn.total_sentences} sentences buffered)`;
      approveBtn.disabled = false;
      editBtn.disabled = false;
      regenBtn.disabled = false;
      discardBtn.disabled = false;
    } else if (turn.status === 'speaking') {
      badge.className = 'badge badge-speaking';
      badge.textContent = '🔊 Speaking on /avatar...';
      approveBtn.disabled = true;
      editBtn.disabled = true;
      regenBtn.disabled = false;
      discardBtn.disabled = false;
    } else {
      badge.className = 'badge badge-idle';
      badge.textContent = turn.status.toUpperCase();
      approveBtn.disabled = turn.status !== 'completed';
      editBtn.disabled = !turn.english;
      regenBtn.disabled = !turn.transcript;
      discardBtn.disabled = true;
    }
  }

  function renderCanned(cannedList) {
    const container = document.getElementById('cannedContainer');
    container.innerHTML = (cannedList || []).map((c, idx) => `
      <div class="canned-item">
        <div>
          <div class="c-title">[${idx+1}] ${c.title}</div>
          <div class="c-sub">${c.question}</div>
        </div>
        <button onclick="playCanned('${c.id}')" style="background:#26334d;border-color:var(--gold);color:var(--gold);white-space:nowrap;">▶ Play [${idx+1}]</button>
      </div>
    `).join('');
  }

  async function toggleCapture() {
    const useOp = document.getElementById('useOpMicCheck').checked;
    if (!isCapturing) {
      await fetch(`/api/capture/start?use_operator_mic=${useOp}`, {method: 'POST'});
    } else {
      await fetch('/api/capture/stop', {method: 'POST'});
    }
  }

  async function submitManualQuestion() {
    const q = document.getElementById('manualQuestionInput').value.trim();
    if (!q) return;
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q})
    });
    renderTurn(await res.json());
  }

  async function approveTurn() {
    const res = await fetch('/api/turn/approve', {method: 'POST'});
    renderTurn(await res.json());
  }

  async function regenerateTurn() {
    const res = await fetch('/api/turn/regenerate', {method: 'POST'});
    renderTurn(await res.json());
  }

  async function discardTurn() {
    await fetch('/api/turn/discard', {method: 'POST'});
  }

  async function saveEdits() {
    const english = document.getElementById('englishBox').value;
    const greek = document.getElementById('greekBox').value;
    const res = await fetch('/api/turn/edit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({english, greek})
    });
    renderTurn(await res.json());
  }

  async function playCanned(id) {
    const res = await fetch('/api/canned', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({canned_id: id})
    });
    renderTurn(await res.json());
  }

  async function updateTTSPreset() {
    const val = document.getElementById('ttsPresetSelect').value;
    const [tts_backend, tts_voice] = val.split('|');
    await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tts_backend, tts_voice})
    });
  }

  async function switchScene(scene) {
    await fetch('/api/scene', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scene})
    });
    document.getElementById('sceneDavidBtn').classList.toggle('active-scene', scene === 'David');
    document.getElementById('sceneEuclidBtn').classList.toggle('active-scene', scene === 'Euclid');
  }

  document.addEventListener('keydown', (e) => {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.code === 'Space') {
      e.preventDefault();
      toggleCapture();
    } else if (e.key === 'a' || e.key === 'A') {
      e.preventDefault();
      if (!document.getElementById('approveBtn').disabled) approveTurn();
    } else if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      if (!document.getElementById('regenBtn').disabled) regenerateTurn();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (!document.getElementById('discardBtn').disabled) discardTurn();
    } else if (e.key >= '1' && e.key <= '5') {
      const buttons = document.querySelectorAll('#cannedContainer button');
      const idx = parseInt(e.key, 10) - 1;
      if (buttons[idx]) buttons[idx].click();
    }
  });

  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'init') {
        renderCanned(msg.canned || []);
        if (msg.presentation) renderPresentation(msg.presentation);
        if (msg.turn) renderTurn(msg.turn);
      } else if (msg.type === 'presentation_state') {
        renderPresentation(msg.presentation);
      } else if (msg.type === 'turn_update') {
        renderTurn(msg.turn);
      } else if (msg.type === 'capture_state') {
        isCapturing = msg.capturing;
        const btn = document.getElementById('captureBtn');
        btn.classList.toggle('recording', isCapturing);
        btn.textContent = isCapturing ? '⏹ Stop & Transcribe' : '🎙️ Start Capture';
        document.getElementById('micDeviceLabel').textContent = isCapturing ? `Recording (${msg.device})` : 'Idle';
        if (!isCapturing) document.getElementById('micMeter').style.width = '0%';
      } else if (msg.type === 'mic_level') {
        const pct = Math.min(100, Math.round((msg.rms || 0) * 450));
        document.getElementById('micMeter').style.width = `${pct}%`;
      }
    };
    ws.onclose = () => setTimeout(connectWS, 1000);
  }
  function openZoomStage16x9() {
    window.open(
      '/avatar?zoom16x9=1',
      'EuclidZoomStage16x9',
      'popup=yes,width=1440,height=838,menubar=no,toolbar=no,location=no,status=no'
    );
  }

  connectWS();
</script>
</body>
</html>
"""
