"""Dry-run and 10-question MATH E-139 benchmark runner."""
from __future__ import annotations

import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

from .config import Config
from .index import build_or_update_index
from .pipeline import EuclidPipeline, TurnState
from .stt import load_audio_16k

BENCHMARK_QUESTIONS: list[tuple[str, str]] = [
    (
        "q01_prop_i23_enunciation",
        "Euclid, please state the enunciation of Book I, Proposition 23 in Greek and English.",
    ),
    (
        "q02_book1_definitions",
        "How do you define a point, a straight line, a circle, and parallel straight lines in Book I?",
    ),
    (
        "q03_postulate_5",
        "State the fifth postulate in Greek and explain when two straight lines produced indefinitely meet.",
    ),
    (
        "q04_common_notions",
        "What is the first common notion in Book I, and how does the course list of nine common notions differ from Fitzpatrick's five?",
    ),
    (
        "q05_six_parts_of_proposition",
        "What are the six canonical parts of a Euclidean proposition, and when do you end with hoper edei poiesai versus hoper edei deixai?",
    ),
    (
        "q06_prop_i1_equilateral",
        "How does Proposition I.1 construct an equilateral triangle on a given finite straight line, and what intersection assumption do modern readers note?",
    ),
    (
        "q07_prop_i5_isosceles",
        "What does Proposition I.5 prove about the base angles of isosceles triangles?",
    ),
    (
        "q08_prop_i12_perpendicular",
        "In Proposition I.12, how do you draw a perpendicular straight line to a given infinite straight line from a given point not on it?",
    ),
    (
        "q09_spherical_hyperbolic_i23",
        "Does Proposition I.23 hold in spherical geometry and in the Poincaré upper half-plane model of hyperbolic geometry from Class 5 and Class 6?",
    ),
    (
        "q10_prop_i47_pythagorean",
        "State Proposition I.47, the Pythagorean theorem, in Greek and English, and explain how the proof uses parallelograms.",
    ),
]


def ensure_question_wavs(output_dir: Path) -> list[tuple[str, str, Path]]:
    """Generate 10 representative MATH E-139 question WAVs (16 kHz mono PCM) using macOS `say` if not present."""
    output_dir.mkdir(parents=True, exist_ok=True)
    items: list[tuple[str, str, Path]] = []
    for qid, qtext in BENCHMARK_QUESTIONS:
        wav_path = output_dir / f"{qid}.wav"
        if not wav_path.exists():
            aiff_path = output_dir / f"{qid}.aiff"
            subprocess.run(
                ["say", "-v", "Samantha", "-r", "180", "-o", str(aiff_path), qtext],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(aiff_path), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path),
                ],
                check=True,
                capture_output=True,
            )
            aiff_path.unlink(missing_ok=True)
        items.append((qid, qtext, wav_path))
    return items


def run_single_dry_run(
    pipeline: EuclidPipeline,
    wav_path: Path,
    *,
    play_audio: bool = False,
    tts_backend: str | None = None,
    tts_voice: str | None = None,
    simulated_review_s: float = 1.6,
) -> TurnState:
    """Run one WAV question through STT -> Course RAG -> Gemini -> Speculative TTS -> Auto-Approve."""
    pcm_16k, duration_s = load_audio_16k(wav_path)
    t_now = time.perf_counter()
    turn = pipeline.start_turn_from_audio(
        pcm_16k,
        input_sr=16000,
        t_capture_start=t_now - duration_s,
        t_capture_end=t_now,
        capture_ms=round(duration_s * 1000.0, 1),
        question_source="wav",
        tts_backend=tts_backend,
        tts_voice=tts_voice,
        wait_for_synthesis=False,
    )

    # Simulate operator reading the control window for `simulated_review_s` while background TTS runs
    if simulated_review_s > 0:
        time.sleep(simulated_review_s)

    # Operator clicks Approve; playback starts immediately from Sentence 1 buffer (or when Sentence 1 finishes)
    pipeline.approve_current_turn(play_audio=play_audio, block=True)
    # Wait for remaining background sentence synthesis + WAV write to complete
    turn.all_ready_event.wait(timeout=30.0)
    time.sleep(0.05)
    return turn


def compute_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "p90": 0.0, "max": 0.0}
    s = sorted(values)
    p90_idx = min(len(s) - 1, int(round(0.9 * (len(s) - 1))))
    return {
        "min": round(s[0], 1),
        "median": round(statistics.median(s), 1),
        "mean": round(statistics.mean(s), 1),
        "p90": round(s[p90_idx], 1),
        "max": round(s[-1], 1),
    }


def run_benchmark_suite(
    cfg: Config,
    *,
    play_audio: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Run the 10-question MATH E-139 benchmark and TTS backend comparison."""
    print("1. Verifying SQLite FTS5 course index...")
    idx_stats = build_or_update_index(cfg, force=False)
    print(
        f"   Index ready: {idx_stats['total_chunks']} chunks across {idx_stats['total_files']} files "
        f"({idx_stats['distinct_entity_keys']} entity keys, {idx_stats['elapsed_ms']} ms)."
    )

    print("2. Initializing EuclidPipeline (warming up MLX Whisper STT, Kokoro ONNX, Google Cloud ADC)...")
    pipeline = EuclidPipeline(cfg, warmup_stt=True, preload_kokoro=True)
    print(f"   STT ({pipeline.stt.model_id}) warmup took {pipeline.stt.warmup_ms} ms.")

    wav_dir = cfg.logs_dir / "benchmark_inputs"
    questions = ensure_question_wavs(wav_dir)[:limit]

    turns_summary: list[dict[str, Any]] = []
    print(f"\n3. Running {len(questions)}-question end-to-end dry-run benchmark ({cfg.gemini_model} + {cfg.tts_backend})...")
    for idx, (qid, expected_q, wav_path) in enumerate(questions, start=1):
        turn = run_single_dry_run(
            pipeline,
            wav_path,
            play_audio=play_audio,
            simulated_review_s=1.6,
        )
        rec = {
            "q_num": idx,
            "qid": qid,
            "expected_question": expected_q,
            "transcript": turn.transcript,
            "sources": turn.sources,
            "retrieved_details": turn.retrieved_details,
            "english": turn.english,
            "greek": turn.greek,
            "sentence_count": turn.total_sentences,
            "stt_ms": round(turn.stt_ms, 1),
            "rag_ms": round(turn.rag_ms, 1),
            "llm_ms": round(turn.llm_ms, 1),
            "tts_first_sentence_ms": round(turn.tts_first_sentence_ms, 1),
            "tts_total_ms": round(turn.tts_total_ms, 1),
            "total_unattended_ms": round(turn.total_unattended_ms, 1),
            "approval_wait_ms": round(turn.approval_wait_ms, 1),
            "post_approval_start_ms": round(turn.post_approval_start_ms, 2),
            "wav_path": turn.wav_path,
        }
        turns_summary.append(rec)
        print(
            f"   [Q{idx:02d}] STT={rec['stt_ms']:5.1f}ms | RAG={rec['rag_ms']:4.1f}ms | "
            f"LLM={rec['llm_ms']:6.1f}ms | TTS_S1={rec['tts_first_sentence_ms']:5.1f}ms | "
            f"Unattended={rec['total_unattended_ms']:6.1f}ms ({rec['total_unattended_ms']/1000:.2f}s) | "
            f"PostApprove={rec['post_approval_start_ms']:4.2f}ms | Sources={rec['sources'][:2]}"
        )

    # Also test Discard, Regenerate, and Canned response so all control actions are verified in turns.jsonl
    print("\n4. Testing Canned Response (`i23_erasmian_enunciation`) for latency floor...")
    canned_turn = pipeline.play_canned_response("i23_erasmian_enunciation", play_audio=False, block=True)
    print(
        f"   [CANNED] Unattended={canned_turn.total_unattended_ms:.2f}ms | "
        f"PostApprove={canned_turn.post_approval_start_ms:.2f}ms | Voice={canned_turn.tts_voice}"
    )

    # 5. TTS Backend & Voice comparison on Proposition I.23 & Proposition I.47
    print("\n5. Benchmarking TTS Backends & Voices (Sentence 1 synthesis latency & duration)...")
    s_i23 = "Πρὸς τῇ δοθείσῃ εὐθείᾳ καὶ τῷ πρὸς αὐτῇ σημείῳ τῇ δοθείσῃ γωνίᾳ εὐθυγράμμῳ ἴσην γωνίαν εὐθύγραμμον συστήσασθαι."
    s_i47 = "Ἐν τοῖς ὀρθογωνίοις τριγώνοις τὸ ἀπὸ τῆς τὴν ὀρθὴν γωνίαν ὑποτεινούσης πλευρᾶς τετράγωνον ἴσον ἐστὶ τοῖς ἀπὸ τῶν τὴν ὀρθὴν γωνίαν περιεχουσῶν πλευρῶν τετραγώνοις."
    tts_comparison: list[dict[str, Any]] = []
    for backend, voice, label in [
        ("google_erasmian", "en-US-Neural2-D", "Google Cloud Erasmian Male (D)"),
        ("google_erasmian", "en-US-Neural2-J", "Google Cloud Erasmian Male (J)"),
        ("google_erasmian", "en-US-Neural2-H", "Google Cloud Erasmian Female (H, euclid-tts baseline)"),
        ("kokoro_erasmian", "am_adam", "Local Kokoro-82M ONNX Erasmian Male (am_adam)"),
        ("kokoro_erasmian", "af_heart", "Local Kokoro-82M ONNX Erasmian Female (af_heart)"),
        ("google_modern", "el-GR-Wavenet-B", "Google Cloud Modern Greek (el-GR-Wavenet-B)"),
        ("macos_modern", "Melina", "Local macOS say Modern Greek (Melina)"),
    ]:
        c23 = pipeline.tts.synthesize_sentence(s_i23, backend=backend, voice=voice)
        c47 = pipeline.tts.synthesize_sentence(s_i47, backend=backend, voice=voice)
        row = {
            "backend": backend,
            "voice": voice,
            "label": label,
            "i23_synth_ms": c23.synthesis_ms,
            "i23_dur_s": c23.duration_s,
            "i47_synth_ms": c47.synthesis_ms,
            "i47_dur_s": c47.duration_s,
        }
        tts_comparison.append(row)
        print(
            f"   {label:52s} | I.23: {c23.synthesis_ms:6.1f}ms ({c23.duration_s:5.2f}s) | "
            f"I.47: {c47.synthesis_ms:6.1f}ms ({c47.duration_s:5.2f}s)"
        )

    agg = {
        "stt_ms": compute_stats([r["stt_ms"] for r in turns_summary]),
        "rag_ms": compute_stats([r["rag_ms"] for r in turns_summary]),
        "llm_ms": compute_stats([r["llm_ms"] for r in turns_summary]),
        "tts_first_sentence_ms": compute_stats([r["tts_first_sentence_ms"] for r in turns_summary]),
        "tts_total_ms": compute_stats([r["tts_total_ms"] for r in turns_summary]),
        "total_unattended_ms": compute_stats([r["total_unattended_ms"] for r in turns_summary]),
        "post_approval_start_ms": compute_stats([r["post_approval_start_ms"] for r in turns_summary]),
    }

    report = {
        "model_config": {
            "stt_model": pipeline.stt.model_id,
            "stt_warmup_ms": pipeline.stt.warmup_ms,
            "gemini_model": cfg.gemini_model,
            "tts_backend": cfg.tts_backend,
            "tts_voice": cfg.active_tts_voice(),
            "tts_rate": cfg.tts_rate,
        },
        "index_stats": idx_stats,
        "aggregate_stats": agg,
        "turns": turns_summary,
        "tts_comparison": tts_comparison,
        "canned_floor": {
            "unattended_ms": canned_turn.total_unattended_ms,
            "post_approval_start_ms": canned_turn.post_approval_start_ms,
        },
    }

    summary_path = cfg.logs_dir / "benchmark_summary.json"
    summary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBenchmark complete! Saved full summary to {summary_path}")
    print(
        f"Unattended Machine Latency: Median = {agg['total_unattended_ms']['median']} ms "
        f"({agg['total_unattended_ms']['median']/1000:.2f} s), "
        f"Worst = {agg['total_unattended_ms']['max']} ms ({agg['total_unattended_ms']['max']/1000:.2f} s)"
    )
    print(
        f"Post-Approval Start Latency: Median = {agg['post_approval_start_ms']['median']} ms, "
        f"Worst = {agg['post_approval_start_ms']['max']} ms"
    )
    return report
