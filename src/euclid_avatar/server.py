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


AVATAR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Euclid of Alexandria · Elements II.13 Presentation & Q&A (1920x1080)</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    background: radial-gradient(circle at 30% 40%, #1c2536 0%, #0d121c 65%, #070a10 100%);
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
    padding: 28px 64px 36px 64px;
  }
  .header-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 10px 32px;
    border: 1.5px solid rgba(218, 181, 92, 0.45);
    border-radius: 999px;
    background: rgba(12, 17, 28, 0.82);
    letter-spacing: 0.06em;
    font-size: 22px;
    color: #e5c467;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  }
  .header-banner span.sub {
    color: #b7c2d6;
    font-size: 19px;
    letter-spacing: 0.02em;
  }
  .main-row {
    width: 100%;
    height: 670px;
    display: grid;
    grid-template-columns: 540px 1fr;
    gap: 32px;
    align-items: center;
  }
  .diagram-card {
    position: relative;
    width: 540px;
    height: 630px;
    background: rgba(11, 16, 26, 0.92);
    border: 2px solid rgba(229, 196, 103, 0.55);
    border-radius: 22px;
    padding: 22px 26px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
  }
  .diagram-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid rgba(229, 196, 103, 0.32);
    padding-bottom: 10px;
  }
  .diagram-title {
    font-size: 22px;
    font-weight: 700;
    color: #f3d47c;
    letter-spacing: 0.02em;
  }
  .diagram-sub {
    font-size: 14px;
    color: #9aa8c2;
    font-family: -apple-system, sans-serif;
  }
  svg.ii13-fig {
    width: 100%;
    height: 390px;
    overflow: visible;
  }
  .seg-line {
    transition: stroke-width 0.18s ease, filter 0.18s ease, opacity 0.18s ease;
  }
  .seg-line.active-glow {
    stroke-width: 7px !important;
    filter: drop-shadow(0 0 12px rgba(243, 212, 124, 0.95));
  }
  .pt-node {
    transition: transform 0.18s ease, filter 0.18s ease;
    transform-box: fill-box;
    transform-origin: center;
  }
  .pt-node.active-pt {
    filter: drop-shadow(0 0 12px rgba(243, 212, 124, 1));
    transform: scale(1.18);
  }
  .case-legend {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    background: rgba(18, 26, 42, 0.78);
    border: 1px solid rgba(229, 196, 103, 0.28);
    border-radius: 12px;
    padding: 10px 14px;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #dce5f5;
  }
  .legend-swatch {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    display: inline-block;
  }
  .wave-bar-wrap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-top: 6px;
  }
  .wave-label {
    font-family: -apple-system, sans-serif;
    font-size: 13px;
    color: #9aa8c2;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .wave-bars {
    display: flex;
    align-items: center;
    gap: 4px;
    height: 28px;
    flex: 1;
    justify-content: flex-end;
  }
  .wave-bar {
    width: 5px;
    height: 5px;
    border-radius: 999px;
    background: linear-gradient(180deg, #f5d97e 0%, #c49733 100%);
    opacity: 0.45;
    transition: height 0.05s linear, opacity 0.05s linear;
  }
  .slide-card {
    height: 630px;
    background: rgba(11, 16, 26, 0.90);
    border: 2px solid rgba(229, 196, 103, 0.55);
    border-radius: 22px;
    padding: 28px 38px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
    overflow: hidden;
  }
  .slide-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1.5px solid rgba(229, 196, 103, 0.35);
    padding-bottom: 14px;
    margin-bottom: 20px;
  }
  .slide-title {
    font-size: 34px;
    font-weight: 700;
    color: #f3d47c;
  }
  .slide-pill {
    background: #1b263b;
    border: 1.5px solid #e5c467;
    color: #f0d078;
    padding: 5px 18px;
    border-radius: 999px;
    font-size: 18px;
    font-family: -apple-system, sans-serif;
    font-weight: 600;
  }
  .slide-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 16px;
  }
  .slide-row {
    background: rgba(23, 33, 52, 0.72);
    border-left: 4px solid #e5c467;
    border-radius: 10px;
    padding: 14px 20px;
  }
  .slide-row-greek {
    font-family: "New Athena Unicode", "Gentium Plus", "Palatino Linotype", Georgia, serif;
    font-size: 27px;
    line-height: 1.38;
    color: #f7df94;
    margin-bottom: 6px;
  }
  .slide-row-eng {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 22px;
    line-height: 1.34;
    color: #e4ecf7;
  }
  .slide-two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
  .subtitle-wrapper {
    position: relative;
    width: 100%;
  }
  .subtitle-box {
    width: 100%;
    min-height: 210px;
    background: rgba(8, 11, 18, 0.94);
    border: 2.5px solid rgba(229, 196, 103, 0.68);
    border-radius: 20px;
    padding: 20px 40px;
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
    font-size: 29px;
    line-height: 1.34;
    color: #f0d078;
    margin-bottom: 10px;
    font-weight: 500;
    text-shadow: 0 2px 6px rgba(0, 0, 0, 0.95);
    max-width: 1680px;
  }
  .english-sub {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 36px;
    line-height: 1.30;
    font-weight: 700;
    color: #ffffff;
    text-shadow:
      -2px -2px 0 #000,
       2px -2px 0 #000,
      -2px  2px 0 #000,
       2px  2px 0 #000,
       0px  4px 12px rgba(0, 0, 0, 0.95);
    max-width: 1680px;
  }
  .progress-pill {
    position: absolute;
    top: -16px;
    right: 36px;
    background: #1b263b;
    border: 1.5px solid #e5c467;
    color: #f0d078;
    padding: 4px 18px;
    border-radius: 999px;
    font-size: 17px;
    font-family: -apple-system, sans-serif;
    font-weight: 600;
    display: none;
    z-index: 10;
  }
</style>
</head>
<body>
  <div class="stage">
    <div class="header-banner">
      <span>ΕΥΚΛΕΙΔΗΣ Ο ΑΛΕΞΑΝΔΡΕΥΣ · ELEMENTS II.13</span>
      <span class="sub">Group 4 · Connor Pearson (Diagram) · Euclid / David Wihl (Greek) · Zahid Syed (Proof)</span>
    </div>

    <div class="main-row">
      <div class="diagram-card">
        <div class="diagram-header">
          <div>
            <div class="diagram-title">Elements II.13 · Figure</div>
            <div class="diagram-sub">Acute-angled △ΑΒΓ with altitude ΑΔ ⊥ ΒΓ</div>
          </div>
          <div class="slide-pill" id="activeLettersBadge" style="font-size:15px;">△ ΑΒΓ</div>
        </div>

        <svg class="ii13-fig" viewBox="0 0 480 370" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="acSquareFill" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(243, 212, 124, 0.16)"/>
              <stop offset="100%" stop-color="rgba(243, 212, 124, 0.04)"/>
            </linearGradient>
            <linearGradient id="rectFill" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="rgba(86, 211, 100, 0.18)"/>
              <stop offset="100%" stop-color="rgba(86, 211, 100, 0.05)"/>
            </linearGradient>
          </defs>

          <!-- Faint rectangle 2 · ΓΒ · ΒΔ reference band below base ΒΓ -->
          <rect id="rect-CB-BD" x="72" y="275" width="336" height="46" rx="4"
                fill="url(#rectFill)" stroke="rgba(86, 211, 100, 0.42)" stroke-width="1.5" stroke-dasharray="5 4"/>
          <line x1="196" y1="275" x2="196" y2="321" stroke="rgba(86, 211, 100, 0.5)" stroke-width="1.5" stroke-dasharray="4 3"/>
          <text x="240" y="303" text-anchor="middle" fill="#8ce99a" font-size="15" font-family="Palatino, Georgia, serif">
            τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ (2 · CB · BD)
          </text>

          <!-- Triangle interior fill -->
          <polygon points="196,56 72,275 408,275" fill="rgba(56, 139, 253, 0.07)"/>

          <!-- Acute angle arc at Β (72, 275) -->
          <path d="M 112,275 A 40,40 0 0,0 92,240" fill="none" stroke="#f3d47c" stroke-width="2.2"/>
          <text x="122" y="262" fill="#f3d47c" font-size="14" font-style="italic">ὀξεῖα</text>

          <!-- Right-angle marker at Δ (196, 275) -->
          <polyline points="196,257 214,257 214,275" fill="none" stroke="#56d364" stroke-width="2"/>

          <!-- Base ΓΒ (CB) and segments ΒΔ (BD), ΔΓ (DC) -->
          <line id="seg-CB" class="seg-line" x1="72" y1="275" x2="408" y2="275" stroke="#79c0ff" stroke-width="4.5" stroke-linecap="round"/>
          <line id="seg-BD" class="seg-line" x1="72" y1="275" x2="196" y2="275" stroke="#56d364" stroke-width="5" stroke-linecap="round"/>
          <line id="seg-DC" class="seg-line" x1="196" y1="275" x2="408" y2="275" stroke="#79c0ff" stroke-width="4.5" stroke-linecap="round"/>

          <!-- Side ΒΑ (BA) -->
          <line id="seg-BA" class="seg-line" x1="72" y1="275" x2="196" y2="56" stroke="#79c0ff" stroke-width="4.5" stroke-linecap="round"/>

          <!-- Subtending side ΑΓ (AC) - Nominative subject -->
          <line id="seg-AC" class="seg-line" x1="196" y1="56" x2="408" y2="275" stroke="#f3d47c" stroke-width="5" stroke-linecap="round"/>

          <!-- Perpendicular ΑΔ (AD) - ἡ κάθετος -->
          <line id="seg-AD" class="seg-line" x1="196" y1="56" x2="196" y2="275" stroke="#56d364" stroke-width="3.5" stroke-dasharray="7 5" stroke-linecap="round"/>

          <!-- Midpoint segment labels -->
          <text x="112" y="156" fill="#a5d6ff" font-size="16" font-weight="600">ΒΑ (BA)</text>
          <text x="316" y="156" fill="#f7df94" font-size="17" font-weight="700">ΑΓ (AC)</text>
          <text x="206" y="178" fill="#7ee787" font-size="15" font-weight="600">ἡ κάθετος ΑΔ</text>
          <text x="134" y="294" text-anchor="middle" fill="#7ee787" font-size="15" font-weight="600">ΒΔ (BD)</text>
          <text x="302" y="294" text-anchor="middle" fill="#a5d6ff" font-size="15" font-weight="600">ΔΓ (DC)</text>

          <!-- Vertex Α (A) -->
          <g id="pt-A" class="pt-node">
            <circle cx="196" cy="56" r="16" fill="#172236" stroke="#f3d47c" stroke-width="2.5"/>
            <text x="196" y="62" text-anchor="middle" fill="#ffffff" font-size="18" font-weight="700">Α</text>
            <text x="196" y="30" text-anchor="middle" fill="#b7c2d6" font-size="14" font-family="-apple-system,sans-serif">A</text>
          </g>

          <!-- Vertex Β (B) -->
          <g id="pt-B" class="pt-node">
            <circle cx="72" cy="275" r="16" fill="#172236" stroke="#79c0ff" stroke-width="2.5"/>
            <text x="72" y="281" text-anchor="middle" fill="#ffffff" font-size="18" font-weight="700">Β</text>
            <text x="42" y="280" text-anchor="middle" fill="#b7c2d6" font-size="14" font-family="-apple-system,sans-serif">B</text>
          </g>

          <!-- Vertex Γ (C) -->
          <g id="pt-C" class="pt-node">
            <circle cx="408" cy="275" r="16" fill="#172236" stroke="#f3d47c" stroke-width="2.5"/>
            <text x="408" y="281" text-anchor="middle" fill="#ffffff" font-size="18" font-weight="700">Γ</text>
            <text x="438" y="280" text-anchor="middle" fill="#b7c2d6" font-size="14" font-family="-apple-system,sans-serif">C</text>
          </g>

          <!-- Point Δ (D) -->
          <g id="pt-D" class="pt-node">
            <circle cx="196" cy="275" r="15" fill="#172236" stroke="#56d364" stroke-width="2.5"/>
            <text x="196" y="281" text-anchor="middle" fill="#ffffff" font-size="17" font-weight="700">Δ</text>
          </g>
        </svg>

        <div class="case-legend">
          <div class="legend-item">
            <span class="legend-swatch" style="background:#f3d47c;"></span>
            <span><strong>Nom.</strong> τὸ ἀπὸ τῆς ΑΓ — <em>square on AC</em></span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch" style="background:#79c0ff;"></span>
            <span><strong>Gen.</strong> τῶν ἀπὸ τῶν ΓΒ, ΒΑ — <em>than squares on CB, BA</em></span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch" style="background:#56d364;"></span>
            <span><strong>Dat.</strong> τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ — <em>by 2 · rect(CB, BD)</em></span>
          </div>
        </div>

        <div class="wave-bar-wrap">
          <span class="wave-label" id="voiceStatusLabel">Voice Ready</span>
          <div class="wave-bars" id="waveBars"></div>
        </div>
      </div>

      <div class="slide-card">
        <div class="slide-top">
          <div class="slide-title" id="slideTitle">II.13: the enunciation</div>
          <div class="slide-pill" id="slideBadge">Slide 1 / 5</div>
        </div>
        <div class="slide-body" id="slideBody"></div>
      </div>
    </div>

    <div class="subtitle-wrapper">
      <div class="progress-pill" id="progressPill">Segment 1 / 12</div>
      <div class="subtitle-box">
        <div class="greek-sub" id="greekSub">Ἐν τοῖς ὀξυγωνίοις τριγώνοις τὸ ἀπὸ τῆς τὴν ὀξεῖαν γωνίαν ὑποτεινούσης πλευρᾶς τετράγωνον ἔλαττόν ἐστι...</div>
        <div class="english-sub" id="englishSub">Euclid, Elements II.13 — Ready for 5-Minute Presentation & Professor Q&A</div>
      </div>
    </div>
  </div>

<script>
  const greekSub = document.getElementById('greekSub');
  const englishSub = document.getElementById('englishSub');
  const progressPill = document.getElementById('progressPill');
  const slideTitle = document.getElementById('slideTitle');
  const slideBadge = document.getElementById('slideBadge');
  const slideBody = document.getElementById('slideBody');
  const activeLettersBadge = document.getElementById('activeLettersBadge');
  const voiceStatusLabel = document.getElementById('voiceStatusLabel');
  const waveBarsContainer = document.getElementById('waveBars');

  const NUM_WAVE_BARS = 24;
  const waveBars = [];
  for (let i = 0; i < NUM_WAVE_BARS; i++) {
    const b = document.createElement('div');
    b.className = 'wave-bar';
    waveBarsContainer.appendChild(b);
    waveBars.push(b);
  }

  let currentRms = 0;
  let smoothRms = 0;
  let wavePhase = 0;

  function highlightDiagramLetters(greekText, engText) {
    const combined = `${greekText || ''} ${engText || ''}`;
    const segMap = {
      'seg-AC': /(ΑΓ|ΓΑ|\bAC\b|\bCA\b)/,
      'seg-CB': /(ΓΒ|ΒΓ|\bCB\b|\bBC\b)/,
      'seg-BA': /(ΒΑ|ΑΒ|\bBA\b|\bAB\b)/,
      'seg-BD': /(ΒΔ|ΔΒ|\bBD\b|\bDB\b)/,
      'seg-AD': /(ΑΔ|ΔΑ|\bAD\b|\bDA\b|κάθετος|καθέτου)/,
      'seg-DC': /(ΔΓ|ΓΔ|\bDC\b|\bCD\b)/
    };
    const activeLabels = [];
    Object.entries(segMap).forEach(([id, regex]) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (regex.test(combined)) {
        el.classList.add('active-glow');
        activeLabels.push(id.replace('seg-', ''));
      } else {
        el.classList.remove('active-glow');
      }
    });
    const ptMap = {
      'pt-A': /[ΑA]/,
      'pt-B': /[ΒB]/,
      'pt-C': /[ΓC]/,
      'pt-D': /[ΔD]/
    };
    Object.entries(ptMap).forEach(([id, regex]) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (regex.test(greekText || '')) {
        el.classList.add('active-pt');
      } else {
        el.classList.remove('active-pt');
      }
    });
    activeLettersBadge.textContent = activeLabels.length ? `Highlighting: ${activeLabels.join(', ')}` : '△ ΑΒΓ';
  }

  function formatMdInline(str) {
    if (!str) return '';
    return str
      .replace(/\\*\\*(.+?)\\*\\*/g, '<strong style="color:#fff;text-decoration:underline;text-decoration-color:#e5c467;">$1</strong>')
      .replace(/\\*(.+?)\\*/g, '<em style="color:#ffd97d;">$1</em>');
  }

  function renderSlideCard(pres) {
    if (!pres || !pres.active_slide) return;
    const s = pres.active_slide;
    const totalSlides = (pres.deck && pres.deck.total_slides) || 5;
    slideTitle.textContent = s.title;
    slideBadge.textContent = `Slide ${s.slide_number} / ${totalSlides}`;

    let html = '';
    if (s.header) {
      html += `<div style="font-size:23px;color:#b8ccf0;font-weight:600;margin-bottom:4px;">${formatMdInline(s.header)}</div>`;
    }
    if (s.layout === 'table_two_col') {
      const h0 = (s.headers && s.headers[0]) || 'II.12, obtuse';
      const h1 = (s.headers && s.headers[1]) || 'II.13, acute';
      html += `<div class="slide-two-col" style="border-bottom:1px solid rgba(229,196,103,0.3);padding-bottom:8px;font-size:21px;color:#b8ccf0;font-weight:700;"><div>${h0}</div><div>${h1}</div></div>`;
      (s.rows || []).forEach(r => {
        html += `<div class="slide-row slide-two-col" style="padding:10px 18px;"><div class="slide-row-greek" style="font-size:24px;margin:0;">${formatMdInline(r.greek)}</div><div class="slide-row-greek" style="font-size:24px;margin:0;color:#ffffff;">${formatMdInline(r.english)}</div></div>`;
      });
    } else {
      (s.rows || []).forEach(r => {
        html += `<div class="slide-row">
          <div class="slide-row-greek">${formatMdInline(r.greek)}</div>
          ${r.english ? `<div class="slide-row-eng">${formatMdInline(r.english)}</div>` : ''}
        </div>`;
      });
    }
    slideBody.innerHTML = html;
  }

  function animateWaveform() {
    smoothRms = smoothRms * 0.72 + currentRms * 0.28;
    wavePhase += 0.18;
    const isSpeaking = smoothRms > 0.015;
    voiceStatusLabel.textContent = isSpeaking ? 'Speaking · Erasmian Greek / en-AU' : 'Standby · Elements II.13';
    for (let i = 0; i < NUM_WAVE_BARS; i++) {
      const centerWeight = 1.0 - Math.abs(i - NUM_WAVE_BARS / 2) / (NUM_WAVE_BARS / 2);
      const harmonic = Math.abs(Math.sin(wavePhase + i * 0.45));
      const h = isSpeaking ? Math.max(4, Math.min(28, 4 + smoothRms * 52 * (0.4 + 0.6 * centerWeight) * (0.5 + 0.5 * harmonic))) : 4;
      waveBars[i].style.height = `${h.toFixed(1)}px`;
      waveBars[i].style.opacity = isSpeaking ? (0.55 + 0.45 * harmonic).toFixed(2) : '0.32';
    }
    requestAnimationFrame(animateWaveform);
  }
  requestAnimationFrame(animateWaveform);

  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'init') {
        if (msg.presentation) renderSlideCard(msg.presentation);
      } else if (msg.type === 'presentation_state') {
        renderSlideCard(msg.presentation);
      } else if (msg.type === 'amplitude') {
        currentRms = msg.rms || 0;
      } else if (msg.type === 'subtitle') {
        greekSub.textContent = msg.greek || '';
        englishSub.textContent = msg.english || '';
        highlightDiagramLetters(msg.greek || '', msg.english || '');
        if (msg.total_sentences && msg.total_sentences > 0 && msg.speaking) {
          progressPill.style.display = 'block';
          progressPill.textContent = `Speaking ${msg.sentence_index + 1} / ${msg.total_sentences}`;
        } else {
          progressPill.style.display = 'none';
        }
      } else if (msg.type === 'turn_update' && msg.turn && msg.turn.status === 'speaking') {
        slideTitle.textContent = 'Professor Q&A · Elements II.13';
        slideBadge.textContent = 'Live Q&A';
        slideBody.innerHTML = `<div class="slide-row"><div class="slide-row-eng" style="color:#9aa8c2;margin-bottom:8px;">Question: ${msg.turn.transcript || ''}</div><div class="slide-row-greek">${msg.turn.greek || ''}</div><div class="slide-row-eng" style="margin-top:8px;">${msg.turn.english || ''}</div></div>`;
        highlightDiagramLetters(msg.turn.greek || '', msg.turn.english || '');
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
  connectWS();
</script>
</body>
</html>
"""
