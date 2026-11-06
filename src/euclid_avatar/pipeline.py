"""End-to-end turn pipeline with speculative background pre-synthesis, live audio capture, playback, and JSONL logging."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import sounddevice as sd
import yaml

from .config import Config
from .devices import OBSController, find_device_index
from .index import CourseRetriever, RetrievedChunk
from .llm import EuclidLLM
from .presentation import (
    INTER_SEGMENT_PAUSE_S,
    INTER_SLIDE_PAUSE_S,
    PresentationDeck,
    load_presentation_deck,
    prebuild_presentation,
    synthesize_or_load_segment,
)
from .stt import STT_SAMPLE_RATE, LocalWhisperSTT
from .tts import (
    SAMPLE_RATE,
    GreekTTSAdapter,
    SentenceAudioChunk,
    _extract_phrase_word_timings,
    read_wav_mono24k,
    strip_prosody_markers,
    write_wav_mono24k,
)


@dataclass
class TurnState:
    turn_id: str
    question_source: str  # "mic", "text", "wav", "canned"
    transcript: str = ""
    sources: list[str] = field(default_factory=list)
    retrieved_details: list[dict[str, Any]] = field(default_factory=list)
    english: str = ""
    greek: str = ""
    sentences: list[dict[str, str]] = field(default_factory=list)
    llm_model: str = ""
    tts_backend: str = ""
    tts_voice: str = ""

    # Stage timestamps (perf_counter seconds)
    t_capture_start: float = 0.0
    t_capture_end: float = 0.0
    t_stt_done: float = 0.0
    t_rag_done: float = 0.0
    t_llm_done: float = 0.0
    t_tts_first_ready: float = 0.0
    t_tts_all_ready: float = 0.0
    t_approved: float = 0.0
    t_playback_start: float = 0.0
    t_playback_end: float = 0.0

    # Stage durations (ms)
    capture_ms: float = 0.0
    stt_ms: float = 0.0
    rag_ms: float = 0.0
    llm_ms: float = 0.0
    tts_first_sentence_ms: float = 0.0
    tts_total_ms: float = 0.0
    approval_wait_ms: float = 0.0
    post_approval_start_ms: float = 0.0
    total_unattended_ms: float = 0.0

    # Synthesis & approval state
    status: str = "idle"  # capturing, stt, rag, llm, synthesizing, ready, speaking, completed, discarded, regenerated
    synthesized_count: int = 0
    total_sentences: int = 0
    decision: str = "pending"  # pending, approved, regenerated, discarded
    wav_path: str = ""

    # Internal synchronization for speculative pre-synthesis
    audio_chunks: list[SentenceAudioChunk] = field(default_factory=list, repr=False)
    sentence_events: list[threading.Event] = field(default_factory=list, repr=False)
    all_ready_event: threading.Event = field(default_factory=threading.Event, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_ui_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "question_source": self.question_source,
            "status": self.status,
            "transcript": self.transcript,
            "sources": self.sources,
            "retrieved_details": self.retrieved_details,
            "english": self.english,
            "greek": self.greek,
            "sentences": self.sentences,
            "llm_model": self.llm_model,
            "tts_backend": self.tts_backend,
            "tts_voice": self.tts_voice,
            "synthesized_count": self.synthesized_count,
            "total_sentences": self.total_sentences,
            "decision": self.decision,
            "wav_path": self.wav_path,
            "timings": {
                "capture_ms": round(self.capture_ms, 1),
                "stt_ms": round(self.stt_ms, 1),
                "rag_ms": round(self.rag_ms, 1),
                "llm_ms": round(self.llm_ms, 1),
                "tts_first_sentence_ms": round(self.tts_first_sentence_ms, 1),
                "tts_total_ms": round(self.tts_total_ms, 1),
                "approval_wait_ms": round(self.approval_wait_ms, 1),
                "post_approval_start_ms": round(self.post_approval_start_ms, 1),
                "total_unattended_ms": round(self.total_unattended_ms, 1),
            },
        }

    def to_log_record(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "turn_id": self.turn_id,
            "question_source": self.question_source,
            "decision": self.decision,
            "llm_model": self.llm_model,
            "tts_backend": self.tts_backend,
            "tts_voice": self.tts_voice,
            "capture_ms": round(self.capture_ms, 1),
            "stt_ms": round(self.stt_ms, 1),
            "rag_ms": round(self.rag_ms, 1),
            "llm_ms": round(self.llm_ms, 1),
            "tts_first_sentence_ms": round(self.tts_first_sentence_ms, 1),
            "tts_total_ms": round(self.tts_total_ms, 1),
            "approval_wait_ms": round(self.approval_wait_ms, 1),
            "post_approval_start_ms": round(self.post_approval_start_ms, 1),
            "total_unattended_ms": round(self.total_unattended_ms, 1),
            "stage_timestamps": {
                "t_capture_end": round(self.t_capture_end, 4),
                "t_stt_done": round(self.t_stt_done, 4),
                "t_rag_done": round(self.t_rag_done, 4),
                "t_llm_done": round(self.t_llm_done, 4),
                "t_tts_first_ready": round(self.t_tts_first_ready, 4),
                "t_tts_all_ready": round(self.t_tts_all_ready, 4),
                "t_approved": round(self.t_approved, 4),
                "t_playback_start": round(self.t_playback_start, 4),
            },
            "transcript": self.transcript,
            "sources": self.sources,
            "english": self.english,
            "greek": self.greek,
            "sentences": self.sentences,
            "wav_path": self.wav_path,
        }


class EuclidPipeline:
    """Orchestrates capture, STT, RAG, Gemini LLM, speculative Greek TTS, playback, and logging."""

    def __init__(
        self,
        cfg: Config,
        *,
        warmup_stt: bool = True,
        preload_kokoro: bool = True,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.event_callback = event_callback
        self.retriever = CourseRetriever(cfg)
        self.llm = EuclidLLM(cfg)
        self.tts = GreekTTSAdapter(cfg, preload_kokoro=preload_kokoro)
        self.stt = LocalWhisperSTT(cfg, warmup_on_init=warmup_stt)
        self.obs = OBSController(cfg)

        self.current_turn: TurnState | None = None
        self._capture_stream: sd.InputStream | None = None
        self._capture_frames: list[np.ndarray] = []
        self._capturing = False
        self._capture_start_time = 0.0
        self._playback_lock = threading.Lock()
        self.canned_responses = self._load_canned_responses()

        # 5-Minute II.13 Presentation state
        self._pres_playing = False
        self._pres_paused = False
        self._pres_cancel = threading.Event()
        self._pres_pause_gate = threading.Event()
        self._pres_pause_gate.set()
        self._pres_slide_number = 1
        self._pres_segment_id = ""
        self._pres_global_index = 0
        self._pres_voice = self.cfg.tts_voice_english

    def _load_canned_responses(self) -> list[dict[str, Any]]:
        if not self.cfg.canned_file.exists():
            return []
        data = yaml.safe_load(self.cfg.canned_file.read_text(encoding="utf-8")) or {}
        return list(data.get("canned_responses", []))

    def emit(self, payload: dict[str, Any]) -> None:
        if self.event_callback is not None:
            try:
                self.event_callback(payload)
            except Exception:
                pass

    def emit_turn_update(self, turn: TurnState) -> None:
        self.emit({"type": "turn_update", "turn": turn.to_ui_dict()})

    def log_turn(self, turn: TurnState) -> None:
        self.cfg.turns_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = turn.to_log_record()
        with self.cfg.turns_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # --- Manual Audio Capture ---

    def start_capture(self, use_operator_mic: bool = False) -> dict[str, Any]:
        if self._capturing:
            return {"status": "already_capturing"}
        if self.current_turn and self.current_turn.status in {"synthesizing", "ready", "speaking"}:
            self.current_turn.cancel_event.set()

        target_dev_name = self.cfg.operator_mic_device if use_operator_mic else self.cfg.audio_input_device
        dev_idx, matched_name, _ = find_device_index(target_dev_name, kind="input", fallback_to_default=True)

        self._capture_frames = []
        self._capturing = True
        self._capture_start_time = time.perf_counter()

        def audio_callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
            if not self._capturing:
                return
            mono = indata[:, 0].copy()
            self._capture_frames.append(mono)
            rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0
            self.emit({"type": "mic_level", "rms": round(rms, 4), "device": matched_name})

        self._capture_stream = sd.InputStream(
            samplerate=STT_SAMPLE_RATE,
             device=dev_idx,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=audio_callback,
        )
        self._capture_stream.start()
        self.emit({"type": "capture_state", "capturing": True, "device": matched_name})
        return {"status": "capturing", "device": matched_name, "device_index": dev_idx}

    def stop_capture_and_process(self) -> TurnState:
        if not self._capturing:
            raise RuntimeError("Not currently capturing audio.")
        self._capturing = False
        t_capture_end = time.perf_counter()
        if self._capture_stream is not None:
            try:
                self._capture_stream.stop()
                self._capture_stream.close()
            except Exception:
                pass
            self._capture_stream = None

        self.emit({"type": "capture_state", "capturing": False})
        pcm = (
            np.concatenate(self._capture_frames)
            if self._capture_frames
            else np.zeros(int(0.5 * STT_SAMPLE_RATE), dtype=np.float32)
        )
        capture_ms = (t_capture_end - self._capture_start_time) * 1000.0
        return self.start_turn_from_audio(
            pcm,
            input_sr=STT_SAMPLE_RATE,
            t_capture_start=self._capture_start_time,
            t_capture_end=t_capture_end,
            capture_ms=capture_ms,
            question_source="mic",
        )

    # --- Turn Execution & Speculative Pre-Synthesis ---

    def start_turn_from_audio(
        self,
        pcm: np.ndarray,
        *,
        input_sr: int = STT_SAMPLE_RATE,
        t_capture_start: float | None = None,
        t_capture_end: float | None = None,
        capture_ms: float = 0.0,
        question_source: str = "mic",
        tts_backend: str | None = None,
        tts_voice: str | None = None,
        wait_for_synthesis: bool = False,
    ) -> TurnState:
        now = time.perf_counter()
        turn = TurnState(
            turn_id=uuid.uuid4().hex[:8],
            question_source=question_source,
            t_capture_start=t_capture_start or now,
            t_capture_end=t_capture_end or now,
            capture_ms=capture_ms,
            status="stt",
            tts_backend=tts_backend or self.cfg.tts_backend,
            tts_voice=tts_voice or self.cfg.active_tts_voice(tts_backend or self.cfg.tts_backend),
        )
        self.current_turn = turn
        self.emit_turn_update(turn)

        # Stage 1: Speech-to-Text
        stt_res = self.stt.transcribe_pcm(pcm, input_sr=input_sr)
        turn.t_stt_done = time.perf_counter()
        turn.stt_ms = (turn.t_stt_done - turn.t_capture_end) * 1000.0
        turn.transcript = stt_res.text or "(No speech detected)"
        return self._continue_turn_after_stt(turn, wait_for_synthesis=wait_for_synthesis)

    def start_turn_from_text(
        self,
        question_text: str,
        *,
        tts_backend: str | None = None,
        tts_voice: str | None = None,
        wait_for_synthesis: bool = False,
    ) -> TurnState:
        now = time.perf_counter()
        turn = TurnState(
            turn_id=uuid.uuid4().hex[:8],
            question_source="text",
            transcript=question_text.strip(),
            t_capture_start=now,
            t_capture_end=now,
            t_stt_done=now,
            capture_ms=0.0,
            stt_ms=0.0,
            tts_backend=tts_backend or self.cfg.tts_backend,
            tts_voice=tts_voice or self.cfg.active_tts_voice(tts_backend or self.cfg.tts_backend),
        )
        self.current_turn = turn
        return self._continue_turn_after_stt(turn, wait_for_synthesis=wait_for_synthesis)

    def _continue_turn_after_stt(
        self,
        turn: TurnState,
        *,
        temperature: float = 0.2,
        wait_for_synthesis: bool = False,
    ) -> TurnState:
        # Stage 2: Course RAG Retrieval
        turn.status = "rag"
        self.emit_turn_update(turn)
        chunks, rag_ms = self.retriever.retrieve(turn.transcript, k=4)
        turn.t_rag_done = time.perf_counter()
        turn.rag_ms = rag_ms
        turn.retrieved_details = [
            {
                "source_label": c.source_label,
                "rel_path": c.rel_path,
                "title": c.title,
                "match_type": c.match_type,
                "entity_keys": c.entity_keys,
            }
            for c in chunks
        ]

        # Stage 3: Single-pass Gemini LLM generation (English + Ancient Greek)
        turn.status = "llm"
        self.emit_turn_update(turn)
        llm_res = self.llm.generate(turn.transcript, chunks, temperature=temperature)
        turn.t_llm_done = time.perf_counter()
        turn.llm_ms = (turn.t_llm_done - turn.t_rag_done) * 1000.0
        turn.sources = llm_res.sources
        turn.english = llm_res.english
        turn.greek = llm_res.greek
        turn.sentences = llm_res.sentences
        turn.llm_model = llm_res.model
        turn.total_sentences = len(turn.sentences)
        turn.synthesized_count = 0
        turn.audio_chunks = []
        turn.sentence_events = [threading.Event() for _ in range(turn.total_sentences)]
        turn.all_ready_event = threading.Event()
        turn.status = "synthesizing"

        # Immediately update control window & launch speculative background pre-synthesis
        self.emit_turn_update(turn)
        synth_thread = threading.Thread(
            target=self._speculative_tts_worker,
            args=(turn,),
            daemon=True,
        )
        synth_thread.start()
        if wait_for_synthesis:
            synth_thread.join()
        return turn

    def _speculative_tts_worker(self, turn: TurnState) -> None:
        """Background worker that synthesizes Sentence 1..N while operator reviews the text."""
        try:
            for idx, s in enumerate(turn.sentences):
                if turn.cancel_event.is_set():
                    return
                chunk = self.tts.synthesize_sentence(
                    s["greek"],
                    english_sentence=s.get("english", ""),
                    spoken_sentence=s.get("spoken", ""),
                    index=idx,
                    backend=turn.tts_backend,
                    voice=turn.tts_voice,
                )
                if turn.cancel_event.is_set():
                    return
                now = time.perf_counter()
                turn.audio_chunks.append(chunk)
                turn.synthesized_count = idx + 1
                if idx == 0:
                    turn.t_tts_first_ready = now
                    turn.tts_first_sentence_ms = (now - turn.t_llm_done) * 1000.0
                    turn.total_unattended_ms = (now - turn.t_capture_end) * 1000.0
                if idx < len(turn.sentence_events):
                    turn.sentence_events[idx].set()
                if turn.synthesized_count == turn.total_sentences and turn.status == "synthesizing":
                    turn.status = "ready"
                self.emit_turn_update(turn)

            turn.t_tts_all_ready = time.perf_counter()
            turn.tts_total_ms = (turn.t_tts_all_ready - turn.t_llm_done) * 1000.0
            turn.all_ready_event.set()
            if turn.status == "synthesizing":
                turn.status = "ready"
            self.emit_turn_update(turn)

            # Save combined WAV asynchronously off the critical path
            self._save_turn_wav_async(turn)
        except Exception as exc:
            turn.status = f"error: {type(exc).__name__}"
            turn.all_ready_event.set()
            for ev in turn.sentence_events:
                ev.set()
            self.emit_turn_update(turn)

    def _save_turn_wav_async(self, turn: TurnState) -> None:
        def _writer() -> None:
            if not turn.audio_chunks or turn.cancel_event.is_set():
                return
            pause_samples = np.zeros(int(0.45 * SAMPLE_RATE), dtype=np.float32)
            parts: list[np.ndarray] = []
            for idx, ch in enumerate(turn.audio_chunks):
                parts.append(ch.pcm)
                if idx < len(turn.audio_chunks) - 1:
                    parts.append(pause_samples)
            full_pcm = np.concatenate(parts)
            wav_file = self.cfg.audio_log_dir / f"turn_{turn.turn_id}_{turn.tts_backend}.wav"
            write_wav_mono24k(wav_file, full_pcm, SAMPLE_RATE)
            turn.wav_path = str(wav_file.relative_to(self.cfg.logs_dir.parent))
            self.emit_turn_update(turn)

        threading.Thread(target=_writer, daemon=True).start()

    # --- Operator Controls: Approve, Edit, Regenerate, Discard, Canned ---

    def update_turn_text(self, english: str, greek: str, sentences: list[dict[str, str]] | None = None) -> TurnState:
        """Allow operator to edit English/Greek in control UI and re-trigger background pre-synthesis."""
        turn = self.current_turn
        if turn is None:
            raise RuntimeError("No active turn to edit.")
        turn.cancel_event.set()
        time.sleep(0.02)

        turn.english = english.strip()
        turn.greek = greek.strip()
        if sentences:
            turn.sentences = sentences
        else:
            turn.sentences = [{"english": turn.english, "greek": turn.greek}]
        turn.total_sentences = len(turn.sentences)
        turn.synthesized_count = 0
        turn.audio_chunks = []
        turn.cancel_event = threading.Event()
        turn.sentence_events = [threading.Event() for _ in range(turn.total_sentences)]
        turn.all_ready_event = threading.Event()
        turn.t_llm_done = time.perf_counter()
        turn.status = "synthesizing"
        self.emit_turn_update(turn)
        threading.Thread(target=self._speculative_tts_worker, args=(turn,), daemon=True).start()
        return turn

    def approve_current_turn(self, *, play_audio: bool = True, block: bool = False) -> TurnState:
        """Approve the current turn and start speaking immediately from Sentence 1 buffer."""
        turn = self.current_turn
        if turn is None:
            raise RuntimeError("No active turn to approve.")

        turn.t_approved = time.perf_counter()
        turn.approval_wait_ms = max(0.0, (turn.t_approved - turn.t_llm_done) * 1000.0)
        turn.decision = "approved"
        turn.status = "speaking"
        self.emit_turn_update(turn)

        if block:
            self._playback_worker(turn, play_audio=play_audio)
        else:
            threading.Thread(
                target=self._playback_worker,
                args=(turn,),
                kwargs={"play_audio": play_audio},
                daemon=True,
            ).start()
        return turn

    def _playback_worker(self, turn: TurnState, *, play_audio: bool = True) -> None:
        with self._playback_lock:
            # Wait for Sentence 1 if still synthesizing; if already ready, returns in < 0.05 ms!
            if turn.sentence_events:
                turn.sentence_events[0].wait(timeout=20.0)
            if turn.cancel_event.is_set() or not turn.audio_chunks:
                return

            turn.t_playback_start = time.perf_counter()
            turn.post_approval_start_ms = (turn.t_playback_start - turn.t_approved) * 1000.0
            self.emit_turn_update(turn)

            # Resolve output device (BlackHole 16ch or system default fallback)
            out_idx, out_name, _ = find_device_index(
                self.cfg.audio_output_device, kind="output", fallback_to_default=True
            )

            for idx in range(turn.total_sentences):
                if turn.cancel_event.is_set():
                    break
                turn.sentence_events[idx].wait(timeout=30.0)
                if idx >= len(turn.audio_chunks) or turn.cancel_event.is_set():
                    break
                chunk = turn.audio_chunks[idx]

                if not chunk.word_timings and len(chunk.pcm):
                    spoken_src = f"{chunk.english} {chunk.greek}".strip()
                    chunk.word_timings = _extract_phrase_word_timings(
                        spoken_src, chunk.pcm, 0.0, SAMPLE_RATE, 0, spoken_src
                    )

                # Emit synchronized subtitle for /avatar and /control
                self.emit(
                    {
                        "type": "subtitle",
                        "turn_id": turn.turn_id,
                        "sentence_index": idx,
                        "total_sentences": turn.total_sentences,
                        "english": chunk.english,
                        "greek": chunk.greek,
                        "spoken": chunk.english,
                        "word_timings": chunk.word_timings,
                        "speaking": True,
                    }
                )

                if play_audio:
                    self._stream_pcm_with_rms(
                        chunk.pcm,
                        SAMPLE_RATE,
                        out_idx,
                        turn.cancel_event,
                        word_timings=chunk.word_timings,
                    )
                else:
                    # In headless dry-run mode, emit simulated RMS frames quickly
                    rms = float(np.sqrt(np.mean(chunk.pcm**2))) if len(chunk.pcm) else 0.0
                    self.emit({"type": "amplitude", "rms": round(rms, 4)})

                # Inter-sentence breath pause (350 ms)
                if play_audio and idx < turn.total_sentences - 1 and not turn.cancel_event.is_set():
                    self.emit({"type": "amplitude", "rms": 0.0})
                    time.sleep(0.35)

            turn.t_playback_end = time.perf_counter()
            self.emit({"type": "amplitude", "rms": 0.0})
            self.emit(
                {
                    "type": "subtitle",
                    "turn_id": turn.turn_id,
                    "sentence_index": turn.total_sentences - 1,
                    "total_sentences": turn.total_sentences,
                    "english": turn.english,
                    "greek": turn.greek,
                    "speaking": False,
                }
            )
            if not turn.cancel_event.is_set():
                turn.status = "completed"
                # Ensure WAV path is populated before logging
                turn.all_ready_event.wait(timeout=5.0)
                if not turn.wav_path:
                    wav_file = self.cfg.audio_log_dir / f"turn_{turn.turn_id}_{turn.tts_backend}.wav"
                    if turn.audio_chunks:
                        full_pcm = np.concatenate([c.pcm for c in turn.audio_chunks])
                        write_wav_mono24k(wav_file, full_pcm, SAMPLE_RATE)
                        turn.wav_path = str(wav_file.relative_to(self.cfg.logs_dir.parent))
                self.emit_turn_update(turn)
                self.log_turn(turn)

    @staticmethod
    def _find_word_at_time(
        word_timings: list[dict[str, Any]] | None, elapsed_s: float
    ) -> dict[str, Any] | None:
        if not word_timings:
            return None
        active = None
        for w in word_timings:
            if w["start_s"] <= elapsed_s + 0.02:
                active = w
                if elapsed_s <= w["end_s"] + 0.05:
                    return w
            else:
                break
        return active

    def _stream_pcm_with_rms(
        self,
        pcm: np.ndarray,
        sr: int,
        device_idx: int | None,
        cancel_event: threading.Event,
        *,
        word_timings: list[dict[str, Any]] | None = None,
    ) -> None:
        """Stream mono float32 PCM to CoreAudio while broadcasting 60 Hz RMS & word/diagram cues."""
        hop = int(sr / 60)  # 400 samples @ 24 kHz = 16.67 ms (60 Hz)
        total = len(pcm)
        try:
            with sd.OutputStream(
                samplerate=sr,
                device=device_idx,
                channels=1,
                dtype="float32",
                blocksize=hop,
            ) as stream:
                pos = 0
                while pos < total and not cancel_event.is_set():
                    end = min(pos + hop, total)
                    frame = pcm[pos:end]
                    rms = float(np.sqrt(np.mean(frame**2))) if len(frame) else 0.0
                    norm_rms = min(1.0, rms * 4.2)
                    elapsed_s = pos / float(sr)
                    aw = self._find_word_at_time(word_timings, elapsed_s)
                    payload: dict[str, Any] = {
                        "type": "amplitude",
                        "rms": round(norm_rms, 4),
                        "elapsed_s": round(elapsed_s, 3),
                    }
                    if aw is not None:
                        payload.update(
                            {
                                "word_index": aw["index"],
                                "word": aw["word"],
                                "norm": aw["norm"],
                                "is_greek": aw["is_greek"],
                                "diagram_cues": aw["diagram_cues"],
                                "cue_banner": aw["cue_banner"],
                            }
                        )
                    self.emit(payload)
                    stream.write(frame.reshape(-1, 1))
                    pos = end
        except Exception:
            # Fallback if audio device is unavailable in CI/headless environment
            duration = total / float(sr)
            time.sleep(min(duration, 0.2))

    def discard_current_turn(self) -> TurnState | None:
        turn = self.current_turn
        if turn is None:
            return None
        turn.cancel_event.set()
        turn.decision = "discarded"
        turn.status = "discarded"
        self.emit({"type": "amplitude", "rms": 0.0})
        self.emit(
            {
                "type": "subtitle",
                "turn_id": turn.turn_id,
                "sentence_index": 0,
                "total_sentences": 0,
                "english": "",
                "greek": "",
                "speaking": False,
            }
        )
        self.emit_turn_update(turn)
        self.log_turn(turn)
        return turn

    def regenerate_current_turn(self) -> TurnState:
        turn = self.current_turn
        if turn is None:
            raise RuntimeError("No active turn to regenerate.")
        turn.cancel_event.set()
        turn.decision = "regenerated"
        turn.status = "regenerated"
        self.log_turn(turn)

        # Create a fresh turn with the same transcript and higher temperature (0.55)
        now = time.perf_counter()
        new_turn = TurnState(
            turn_id=uuid.uuid4().hex[:8],
            question_source=turn.question_source,
            transcript=turn.transcript,
            t_capture_start=now,
            t_capture_end=now,
            t_stt_done=now,
            capture_ms=0.0,
            stt_ms=0.0,
            tts_backend=turn.tts_backend,
            tts_voice=turn.tts_voice,
        )
        self.current_turn = new_turn
        return self._continue_turn_after_stt(new_turn, temperature=0.55)

    def play_canned_response(self, canned_id: str, *, play_audio: bool = True, block: bool = False) -> TurnState:
        item = next((c for c in self.canned_responses if c["id"] == canned_id), None)
        if item is None:
            raise ValueError(f"Unknown canned response ID: {canned_id}")

        if self.current_turn:
            self.current_turn.cancel_event.set()

        now = time.perf_counter()
        wav_path = Path(item["wav_path"])
        if not wav_path.is_absolute():
            wav_path = self.cfg.logs_dir.parent / wav_path

        sentences = item.get("sentences") or [{"english": item["english"], "greek": item["greek"]}]

        # Load pre-rendered WAV or synthesize and cache on first use
        chunks: list[SentenceAudioChunk] = []
        if wav_path.exists() and len(sentences) == 1:
            pcm, _ = read_wav_mono24k(wav_path)
            chunks.append(
                SentenceAudioChunk(
                    index=0,
                    english=sentences[0]["english"],
                    greek=sentences[0]["greek"],
                    pcm=pcm,
                    duration_s=round(len(pcm) / float(SAMPLE_RATE), 3),
                    synthesis_ms=0.0,
                    backend=item.get("tts_backend", "canned"),
                    voice=item.get("tts_voice", "pre-rendered"),
                )
            )
        elif wav_path.exists() and len(sentences) > 1:
            pcm, _ = read_wav_mono24k(wav_path)
            # Split proportionally by character length across sentences so subtitles advance cleanly
            total_chars = max(1, sum(len(s["greek"]) for s in sentences))
            pos = 0
            for idx, s in enumerate(sentences):
                frac = len(s["greek"]) / total_chars
                end = len(pcm) if idx == len(sentences) - 1 else min(len(pcm), pos + int(len(pcm) * frac))
                sub_pcm = pcm[pos:end]
                pos = end
                chunks.append(
                    SentenceAudioChunk(
                        index=idx,
                        english=s["english"],
                        greek=s["greek"],
                        pcm=sub_pcm,
                        duration_s=round(len(sub_pcm) / float(SAMPLE_RATE), 3),
                        synthesis_ms=0.0,
                        backend=item.get("tts_backend", "canned"),
                        voice=item.get("tts_voice", "pre-rendered"),
                    )
                )
        else:
            # Synthesize and cache to wav_path
            for idx, s in enumerate(sentences):
                ch = self.tts.synthesize_sentence(
                    s["greek"],
                    english_sentence=s.get("english", ""),
                    spoken_sentence=s.get("spoken", ""),
                    index=idx,
                    backend=item.get("tts_backend", self.cfg.tts_backend),
                    voice=item.get("tts_voice", self.cfg.tts_voice_english),
                )
                chunks.append(ch)
            write_wav_mono24k(wav_path, np.concatenate([c.pcm for c in chunks]), SAMPLE_RATE)

        ready_time = time.perf_counter()
        events = [threading.Event() for _ in chunks]
        for ev in events:
            ev.set()
        all_ev = threading.Event()
        all_ev.set()

        turn = TurnState(
            turn_id=f"canned_{canned_id[:10]}_{uuid.uuid4().hex[:4]}",
            question_source="canned",
            transcript=item["question"],
            sources=list(item.get("sources", ["canned_responses.yaml"])),
            english=item["english"],
            greek=item["greek"],
            sentences=sentences,
            llm_model="canned_pre_rendered",
            tts_backend=item.get("tts_backend", "canned"),
            tts_voice=item.get("tts_voice", "pre-rendered"),
            t_capture_start=now,
            t_capture_end=now,
            t_stt_done=now,
            t_rag_done=now,
            t_llm_done=now,
            t_tts_first_ready=ready_time,
            t_tts_all_ready=ready_time,
            tts_first_sentence_ms=round((ready_time - now) * 1000.0, 2),
            tts_total_ms=round((ready_time - now) * 1000.0, 2),
            total_unattended_ms=round((ready_time - now) * 1000.0, 2),
            status="ready",
            synthesized_count=len(chunks),
            total_sentences=len(chunks),
            wav_path=str(wav_path),
            audio_chunks=chunks,
            sentence_events=events,
            all_ready_event=all_ev,
        )
        self.current_turn = turn
        self.emit_turn_update(turn)
        return self.approve_current_turn(play_audio=play_audio, block=block)

    # --- 5-Minute Book II Proposition 13 Greek Presentation Runner ---

    def get_presentation_state(self, voice: str | None = None) -> dict[str, Any]:
        """Return the loaded 5-slide II.13 presentation deck and live playback status."""
        active_voice = voice or self._pres_voice or self.cfg.tts_voice_english
        deck = load_presentation_deck(self.cfg, voice=active_voice)
        active_slide = next(
            (s for s in deck.slides if s.slide_number == self._pres_slide_number),
            deck.slides[0] if deck.slides else None,
        )
        return {
            "playing": self._pres_playing,
            "paused": self._pres_paused,
            "current_slide_number": self._pres_slide_number,
            "current_segment_id": self._pres_segment_id,
            "current_global_index": self._pres_global_index,
            "active_slide": active_slide.to_ui_dict() if active_slide else None,
            "deck": deck.to_ui_dict(),
        }

    def emit_presentation_state(self, voice: str | None = None) -> None:
        self.emit({"type": "presentation_state", "presentation": self.get_presentation_state(voice=voice)})

    def prebuild_presentation_deck(self, *, voice: str | None = None, force: bool = False) -> dict[str, Any]:
        active_voice = voice or self.cfg.tts_voice_english
        self._pres_voice = active_voice
        summary = prebuild_presentation(self.cfg, self.tts, voice=active_voice, force=force)
        self.emit_presentation_state(voice=active_voice)
        return summary

    def select_presentation_slide(self, slide_number: int, voice: str | None = None) -> dict[str, Any]:
        """Switch the displayed slide on /avatar and /control without auto-playing."""
        deck = load_presentation_deck(self.cfg, voice=voice or self._pres_voice)
        target = next((s for s in deck.slides if s.slide_number == slide_number), None)
        if target is None:
            raise ValueError(f"Unknown slide_number: {slide_number}")
        self._pres_slide_number = target.slide_number
        if target.segments:
            self._pres_segment_id = target.segments[0].id
            self._pres_global_index = target.segments[0].global_index
        self.emit_presentation_state(voice=voice)
        return self.get_presentation_state(voice=voice)

    def pause_presentation(self) -> dict[str, Any]:
        if self._pres_playing and not self._pres_paused:
            self._pres_paused = True
            self._pres_pause_gate.clear()
            self.emit({"type": "amplitude", "rms": 0.0})
            self.emit_presentation_state()
        return self.get_presentation_state()

    def resume_presentation(self) -> dict[str, Any]:
        if self._pres_playing and self._pres_paused:
            self._pres_paused = False
            self._pres_pause_gate.set()
            self.emit_presentation_state()
        return self.get_presentation_state()

    def stop_presentation(self) -> dict[str, Any]:
        self._pres_cancel.set()
        self._pres_pause_gate.set()
        self._pres_playing = False
        self._pres_paused = False
        self.emit({"type": "amplitude", "rms": 0.0})
        self.emit(
            {
                "type": "subtitle",
                "turn_id": "presentation_ii13",
                "sentence_index": 0,
                "total_sentences": 0,
                "english": "",
                "greek": "",
                "speaking": False,
            }
        )
        self.emit_presentation_state()
        return self.get_presentation_state()

    def play_presentation(
        self,
        *,
        start_slide: int = 1,
        start_segment_id: str | None = None,
        single_slide: bool = False,
        single_segment: bool = False,
        voice: str | None = None,
        play_audio: bool = True,
        block: bool = False,
    ) -> dict[str, Any]:
        """Play the 5-minute II.13 presentation (full deck, single slide, or single segment)."""
        if self.current_turn:
            self.current_turn.cancel_event.set()
        if self._pres_playing:
            self._pres_cancel.set()
            self._pres_pause_gate.set()
            time.sleep(0.05)

        active_voice = voice or self.cfg.tts_voice_english
        self._pres_voice = active_voice
        deck = load_presentation_deck(self.cfg, voice=active_voice)

        # Build target segment list
        target_segments = []
        for slide in deck.slides:
            if start_segment_id:
                for seg in slide.segments:
                    if seg.id == start_segment_id or (target_segments and not single_segment):
                        if single_slide and seg.slide_number != slide.slide_number:
                            continue
                        target_segments.append(seg)
                        if single_segment:
                            break
                if target_segments and single_segment:
                    break
            else:
                if slide.slide_number < start_slide:
                    continue
                if single_slide and slide.slide_number > start_slide:
                    break
                for seg in slide.segments:
                    target_segments.append(seg)
                    if single_segment:
                        break
                if single_segment and target_segments:
                    break

        if not target_segments:
            raise ValueError("No presentation segments matched the requested start point.")

        self._pres_cancel = threading.Event()
        self._pres_pause_gate = threading.Event()
        self._pres_pause_gate.set()
        self._pres_playing = True
        self._pres_paused = False
        self._pres_slide_number = target_segments[0].slide_number
        self._pres_segment_id = target_segments[0].id
        self._pres_global_index = target_segments[0].global_index
        self.emit_presentation_state(voice=active_voice)

        def _runner() -> None:
            with self._playback_lock:
                out_idx, _, _ = find_device_index(
                    self.cfg.audio_output_device, kind="output", fallback_to_default=True
                )
                total_segs = deck.total_segments
                for i, seg in enumerate(target_segments):
                    self._pres_pause_gate.wait()
                    if self._pres_cancel.is_set():
                        break
                    prev_slide = self._pres_slide_number
                    self._pres_slide_number = seg.slide_number
                    self._pres_segment_id = seg.id
                    self._pres_global_index = seg.global_index
                    self.emit_presentation_state(voice=active_voice)

                    chunk = synthesize_or_load_segment(
                        self.cfg, self.tts, seg, voice=active_voice, force=False
                    )
                    if self._pres_cancel.is_set():
                        break

                    self.emit(
                        {
                            "type": "subtitle",
                            "turn_id": f"ii13_slide_{seg.slide_number}",
                            "sentence_index": seg.global_index,
                            "total_sentences": total_segs,
                            "english": seg.english,
                            "greek": seg.greek,
                            "spoken": strip_prosody_markers(seg.spoken),
                            "word_timings": chunk.word_timings,
                            "speaking": True,
                        }
                    )

                    if play_audio:
                        self._stream_pcm_with_rms_pausable(
                            chunk.pcm,
                            SAMPLE_RATE,
                            out_idx,
                            self._pres_cancel,
                            self._pres_pause_gate,
                            word_timings=chunk.word_timings,
                        )
                    else:
                        rms = float(np.sqrt(np.mean(chunk.pcm**2))) if len(chunk.pcm) else 0.0
                        self.emit({"type": "amplitude", "rms": round(rms, 4)})

                    if play_audio and i < len(target_segments) - 1 and not self._pres_cancel.is_set():
                        self.emit({"type": "amplitude", "rms": 0.0})
                        next_slide = target_segments[i + 1].slide_number
                        pause_s = INTER_SLIDE_PAUSE_S if next_slide != seg.slide_number else INTER_SEGMENT_PAUSE_S
                        time.sleep(pause_s)

                self._pres_playing = False
                self._pres_paused = False
                self.emit({"type": "amplitude", "rms": 0.0})
                self.emit(
                    {
                        "type": "subtitle",
                        "turn_id": "presentation_ii13",
                        "sentence_index": self._pres_global_index,
                        "total_sentences": total_segs,
                        "english": target_segments[-1].english if target_segments else "",
                        "greek": target_segments[-1].greek if target_segments else "",
                        "speaking": False,
                    }
                )
                self.emit_presentation_state(voice=active_voice)

        if block:
            _runner()
        else:
            threading.Thread(target=_runner, daemon=True).start()
        return self.get_presentation_state(voice=active_voice)

    def _stream_pcm_with_rms_pausable(
        self,
        pcm: np.ndarray,
        sr: int,
        device_idx: int | None,
        cancel_event: threading.Event,
        pause_gate: threading.Event,
        *,
        word_timings: list[dict[str, Any]] | None = None,
    ) -> None:
        """Stream mono float32 PCM to CoreAudio with pause/resume support and 60 Hz RMS/word/diagram cues."""
        hop = int(sr / 60)
        total = len(pcm)
        try:
            with sd.OutputStream(
                samplerate=sr,
                device=device_idx,
                channels=1,
                dtype="float32",
                blocksize=hop,
            ) as stream:
                pos = 0
                while pos < total and not cancel_event.is_set():
                    if not pause_gate.is_set():
                        self.emit({"type": "amplitude", "rms": 0.0})
                        pause_gate.wait()
                        if cancel_event.is_set():
                            break
                    end = min(pos + hop, total)
                    frame = pcm[pos:end]
                    rms = float(np.sqrt(np.mean(frame**2))) if len(frame) else 0.0
                    norm_rms = min(1.0, rms * 4.2)
                    elapsed_s = pos / float(sr)
                    aw = self._find_word_at_time(word_timings, elapsed_s)
                    payload: dict[str, Any] = {
                        "type": "amplitude",
                        "rms": round(norm_rms, 4),
                        "elapsed_s": round(elapsed_s, 3),
                    }
                    if aw is not None:
                        payload.update(
                            {
                                "word_index": aw["index"],
                                "word": aw["word"],
                                "norm": aw["norm"],
                                "is_greek": aw["is_greek"],
                                "diagram_cues": aw["diagram_cues"],
                                "cue_banner": aw["cue_banner"],
                            }
                        )
                    self.emit(payload)
                    stream.write(frame.reshape(-1, 1))
                    pos = end
        except Exception:
            duration = total / float(sr)
            time.sleep(min(duration, 0.2))
