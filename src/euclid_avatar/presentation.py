"""5-Minute Book II Proposition 13 Greek Presentation loader, pre-builder, and state manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any

import numpy as np
import yaml

from .config import Config
from .tts import (
    SAMPLE_RATE,
    GreekTTSAdapter,
    SentenceAudioChunk,
    read_wav_mono24k,
    write_wav_mono24k,
)

INTER_SEGMENT_PAUSE_S = 0.45
INTER_SLIDE_PAUSE_S = 0.85


@dataclass
class PresentationSegment:
    """Single spoken segment within a slide of the II.13 presentation."""

    id: str
    slide_number: int
    slide_title: str
    segment_index_in_slide: int
    global_index: int
    rate: float
    greek: str
    english: str
    spoken: str
    duration_s: float = 0.0
    cached: bool = False
    wav_path: str = ""


@dataclass
class PresentationSlide:
    """Slide specification matching coursework/projects/2026-project-ii13/greek/slides.qmd."""

    slide_number: int
    id: str
    title: str
    layout: str
    header: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    segments: list[PresentationSegment] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        if not self.segments:
            return 0.0
        seg_sum = sum(s.duration_s for s in self.segments)
        pauses = max(0, len(self.segments) - 1) * INTER_SEGMENT_PAUSE_S
        return round(seg_sum + pauses, 2)

    def to_ui_dict(self) -> dict[str, Any]:
        return {
            "slide_number": self.slide_number,
            "id": self.id,
            "title": self.title,
            "layout": self.layout,
            "header": self.header,
            "headers": self.headers,
            "rows": self.rows,
            "duration_s": self.duration_s,
            "segments": [
                {
                    "id": s.id,
                    "slide_number": s.slide_number,
                    "slide_title": s.slide_title,
                    "segment_index_in_slide": s.segment_index_in_slide,
                    "global_index": s.global_index,
                    "rate": s.rate,
                    "greek": s.greek,
                    "english": s.english,
                    "spoken": s.spoken,
                    "duration_s": round(s.duration_s, 2),
                    "cached": s.cached,
                    "wav_path": s.wav_path,
                }
                for s in self.segments
            ],
        }


@dataclass
class PresentationDeck:
    """Full 5-slide II.13 Greek presentation deck."""

    id: str
    title: str
    subtitle: str
    target_duration_seconds: float
    voice: str
    slides: list[PresentationSlide]

    @property
    def total_segments(self) -> int:
        return sum(len(s.segments) for s in self.slides)

    @property
    def total_duration_s(self) -> float:
        if not self.slides:
            return 0.0
        slide_sum = sum(s.duration_s for s in self.slides)
        slide_pauses = max(0, len(self.slides) - 1) * INTER_SLIDE_PAUSE_S
        return round(slide_sum + slide_pauses, 2)

    def flat_segments(self) -> list[PresentationSegment]:
        out: list[PresentationSegment] = []
        for s in self.slides:
            out.extend(s.segments)
        return out

    def to_ui_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "target_duration_seconds": self.target_duration_seconds,
            "voice": self.voice,
            "total_slides": len(self.slides),
            "total_segments": self.total_segments,
            "total_duration_s": self.total_duration_s,
            "slides": [s.to_ui_dict() for s in self.slides],
        }


def segment_cache_wav_path(cfg: Config, seg_id: str, voice: str) -> Path:
    safe_voice = voice.replace("/", "_")
    return cfg.presentation_cache_dir / f"{seg_id}_{safe_voice}.wav"


def load_presentation_deck(
    cfg: Config, voice: str | None = None
) -> PresentationDeck:
    """Load presentation_ii13.yaml and populate cached segment durations if pre-rendered."""
    pres_path = cfg.presentation_file
    if not pres_path.exists():
        raise FileNotFoundError(
            f"Presentation file not found at {pres_path}"
        )
    raw = yaml.safe_load(pres_path.read_text(encoding="utf-8")) or {}
    pres = raw.get("presentation", {})
    active_voice = (
        voice
        or cfg.tts_voice_english
        or str(pres.get("voice_english", "en-AU-Neural2-D"))
    )

    slides: list[PresentationSlide] = []
    global_idx = 0
    for s_raw in pres.get("slides", []):
        s_num = int(s_raw.get("slide_number", len(slides) + 1))
        s_title = str(s_raw.get("title", f"Slide {s_num}"))
        segs: list[PresentationSegment] = []
        for seg_idx, seg_raw in enumerate(s_raw.get("segments", [])):
            seg_id = str(seg_raw["id"])
            wav_file = segment_cache_wav_path(cfg, seg_id, active_voice)
            dur_s = 0.0
            is_cached = wav_file.exists()
            if is_cached:
                try:
                    pcm, sr = read_wav_mono24k(wav_file)
                    dur_s = round(len(pcm) / float(sr), 2)
                except Exception:
                    is_cached = False
            segs.append(
                PresentationSegment(
                    id=seg_id,
                    slide_number=s_num,
                    slide_title=s_title,
                    segment_index_in_slide=seg_idx,
                    global_index=global_idx,
                    rate=float(seg_raw.get("rate", cfg.tts_rate_english)),
                    greek=str(seg_raw.get("greek", "")).strip(),
                    english=str(seg_raw.get("english", "")).strip(),
                    spoken=" ".join(str(seg_raw.get("spoken", "")).split()),
                    duration_s=dur_s,
                    cached=is_cached,
                    wav_path=str(wav_file) if is_cached else "",
                )
            )
            global_idx += 1

        slides.append(
            PresentationSlide(
                slide_number=s_num,
                id=str(s_raw.get("id", f"slide_{s_num}")),
                title=s_title,
                layout=str(s_raw.get("layout", "bullets")),
                header=str(s_raw.get("header", "")),
                headers=[str(h) for h in s_raw.get("headers", [])],
                rows=[
                    {
                        "greek": str(r.get("greek", "")),
                        "english": str(r.get("english", "")),
                    }
                    for r in s_raw.get("rows", [])
                ],
                segments=segs,
            )
        )

    return PresentationDeck(
        id=str(pres.get("id", "ii13_greek_presentation")),
        title=str(pres.get("title", "Euclid, Elements II.13: The Greek")),
        subtitle=str(pres.get("subtitle", "")),
        target_duration_seconds=float(
            pres.get("target_duration_seconds", 300.0)
        ),
        voice=active_voice,
        slides=slides,
    )


def synthesize_or_load_segment(
    cfg: Config,
    tts: GreekTTSAdapter,
    seg: PresentationSegment,
    *,
    voice: str | None = None,
    force: bool = False,
) -> SentenceAudioChunk:
    """Load pre-synthesized WAV from cache or synthesize and cache on demand."""
    active_voice = voice or cfg.tts_voice_english
    wav_file = segment_cache_wav_path(cfg, seg.id, active_voice)
    if wav_file.exists() and not force:
        t0 = time.perf_counter()
        pcm, _ = read_wav_mono24k(wav_file)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        dur_s = round(len(pcm) / float(SAMPLE_RATE), 3)
        seg.duration_s = dur_s
        seg.cached = True
        seg.wav_path = str(wav_file)
        return SentenceAudioChunk(
            index=seg.global_index,
            english=seg.english,
            greek=seg.greek,
            pcm=pcm,
            duration_s=dur_s,
            synthesis_ms=round(elapsed_ms, 2),
            backend="google_au_bilingual_cached",
            voice=active_voice,
        )

    chunk = tts.synthesize_bilingual_segment(
        seg.spoken,
        english_display=seg.english,
        greek_display=seg.greek,
        index=seg.global_index,
        voice=active_voice,
        rate=seg.rate,
    )
    write_wav_mono24k(wav_file, chunk.pcm, SAMPLE_RATE)
    seg.duration_s = chunk.duration_s
    seg.cached = True
    seg.wav_path = str(wav_file)
    return chunk


def prebuild_presentation(
    cfg: Config,
    tts: GreekTTSAdapter,
    *,
    voice: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Pre-synthesize all 5 slides of the II.13 presentation and write a combined WAV file."""
    t0 = time.perf_counter()
    active_voice = voice or cfg.tts_voice_english
    deck = load_presentation_deck(cfg, voice=active_voice)

    seg_Pause = np.zeros(
        int(INTER_SEGMENT_PAUSE_S * SAMPLE_RATE), dtype=np.float32
    )
    slide_pause = np.zeros(
        int(INTER_SLIDE_PAUSE_S * SAMPLE_RATE), dtype=np.float32
    )
    all_pcm_parts: list[np.ndarray] = []
    synthesized_count = 0
    cached_count = 0

    for s_idx, slide in enumerate(deck.slides):
        for seg_idx, seg in enumerate(slide.segments):
            was_cached = seg.cached and not force
            chunk = synthesize_or_load_segment(
                cfg, tts, seg, voice=active_voice, force=force
            )
            if was_cached:
                cached_count += 1
            else:
                synthesized_count += 1
            all_pcm_parts.append(chunk.pcm)
            if seg_idx < len(slide.segments) - 1:
                all_pcm_parts.append(seg_Pause)
        if s_idx < len(deck.slides) - 1:
            all_pcm_parts.append(slide_pause)

    full_pcm = (
        np.concatenate(all_pcm_parts)
        if all_pcm_parts
        else np.zeros(SAMPLE_RATE, dtype=np.float32)
    )
    safe_voice = active_voice.replace("/", "_")
    full_wav_path = (
        cfg.audio_log_dir / f"presentation_ii13_full_{safe_voice}.wav"
    )
    write_wav_mono24k(full_wav_path, full_pcm, SAMPLE_RATE)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "voice": active_voice,
        "total_slides": len(deck.slides),
        "total_segments": deck.total_segments,
        "synthesized_segments": synthesized_count,
        "loaded_from_cache": cached_count,
        "total_duration_s": deck.total_duration_s,
        "total_duration_min": round(deck.total_duration_s / 60.0, 2),
        "full_wav_path": str(full_wav_path),
        "elapsed_ms": round(elapsed_ms, 1),
        "slides": [
            {
                "slide_number": s.slide_number,
                "title": s.title,
                "segments": len(s.segments),
                "duration_s": s.duration_s,
            }
            for s in deck.slides
        ],
    }
