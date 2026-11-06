"""Dry-run and 10-question Book II Proposition 13 Professor Q&A benchmark runner."""

from __future__ import annotations

import json
from pathlib import Path
import statistics
import subprocess
import time
from typing import Any

from .config import Config
from .index import build_or_update_index
from .pipeline import EuclidPipeline, TurnState
from .stt import load_audio_16k

BENCHMARK_QUESTIONS: list[tuple[str, str]] = [
    (
        "q01_ii13_enunciation",
        "Euclid, please state the enunciation of Book II, Proposition 13 in Greek and explain how it relates to the Law of Cosines.",
    ),
    (
        "q02_ii13_three_cases",
        "In the specification of Proposition II.13, how do the nominative, genitive, and dative cases express less than and by how much?",
    ),
    (
        "q03_ii12_vs_ii13",
        "How does the Greek enunciation of Proposition II.12 for obtuse-angled triangles differ word-for-word from Proposition II.13 for acute-angled triangles?",
    ),
    (
        "q04_ii13_article_preposition",
        "How does Book II use the neuter article with the prepositions apo and hypo to name squares and rectangles, and where do the nouns drop out in II.13?",
    ),
    (
        "q05_ii13_verbs_tetmetai_echtho",
        "Can you parse the verbs tetmetai, echtho, and proskeistho in Proposition II.13 and give their principal parts?",
    ),
    (
        "q06_ii13_hypoteinousa_kathetos",
        "Explain the participle hypoteinousas and why he kathetos has a feminine article with an omicron-sigma ending.",
    ),
    (
        "q07_ii13_enclitic_accent",
        "Why does elatton esti in Proposition II.13 have two acute accents, and how does the spelling elasson in Book I Definition 12 compare?",
    ),
    (
        "q08_ii13_fitzpatrick_misprints",
        "Did you find any misprints in the Greek text of Proposition II.13 on page 65 of Fitzpatrick's edition?",
    ),
    (
        "q09_ii13_proof_ii7_i47",
        "How does the proof of Proposition II.13 use Book II Proposition 7 and the Pythagorean theorem I.47 without using subtraction or negative numbers?",
    ),
    (
        "q10_ii13_spherical_hyperbolic",
        "Does Proposition II.13 hold in spherical and hyperbolic geometry, and how do the spherical and hyperbolic laws of cosines reduce to it?",
    ),
]


def ensure_question_wavs(output_dir: Path) -> list[tuple[str, str, Path]]:
    """Generate 10 representative II.13 Professor Q&A WAVs (16 kHz mono PCM) using macOS `say` if not present."""
    output_dir.mkdir(parents=True, exist_ok=True)
    items: list[tuple[str, str, Path]] = []
    for qid, qtext in BENCHMARK_QUESTIONS:
        wav_path = output_dir / f"{qid}.wav"
        if not wav_path.exists():
            aiff_path = output_dir / f"{qid}.aiff"
            subprocess.run(
                [
                    "say",
                    "-v",
                    "Samantha",
                    "-r",
                    "180",
                    "-o",
                    str(aiff_path),
                    qtext,
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(aiff_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav_path),
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

    if simulated_review_s > 0:
        time.sleep(simulated_review_s)

    pipeline.approve_current_turn(play_audio=play_audio, block=True)
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
    """Run the 10-question Book II Proposition 13 Professor Q&A benchmark and TTS model comparison."""
    print("1. Verifying SQLite FTS5 course index...")
    idx_stats = build_or_update_index(cfg, force=False)
    print(
        f"   Index ready: {idx_stats['total_chunks']} chunks across {idx_stats['total_files']} files "
        f"({idx_stats['distinct_entity_keys']} entity keys, {idx_stats['elapsed_ms']} ms)."
    )

    print(
        "2. Initializing EuclidPipeline (warming up MLX Whisper STT, Kokoro ONNX, Google Cloud ADC)..."
    )
    pipeline = EuclidPipeline(cfg, warmup_stt=True, preload_kokoro=True)
    print(
        f"   STT ({pipeline.stt.model_id}) warmup took {pipeline.stt.warmup_ms} ms."
    )

    wav_dir = cfg.logs_dir / "benchmark_inputs"
    questions = ensure_question_wavs(wav_dir)[:limit]

    turns_summary: list[dict[str, Any]] = []
    print(
        f"\n3. Running {len(questions)}-question II.13 Professor Q&A benchmark "
        f"({cfg.gemini_model} + {cfg.tts_backend}/{cfg.active_tts_voice()})..."
    )
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

    print(
        "\n4. Testing Canned II.13 Response (`ii13_verbs`) for latency floor..."
    )
    canned_turn = pipeline.play_canned_response(
        "ii13_verbs", play_audio=False, block=True
    )
    print(
        f"   [CANNED] Unattended={canned_turn.total_unattended_ms:.2f}ms | "
        f"PostApprove={canned_turn.post_approval_start_ms:.2f}ms | Voice={canned_turn.tts_voice}"
    )

    print(
        "\n5. Benchmarking Latest TTS Models & Voices on II.13 Bilingual & Pure Erasmian Greek..."
    )
    s_bilingual = (
        "In acute-angled triangles, the two words in bold, ἔλαττόν ἐστι, "
        "mean 'is less', and the square τὸ ἀπὸ τῆς ΑΓ τετράγωνον is the nominative subject."
    )
    s_ii13_spec = (
        "λέγω, ὅτι τὸ ἀπὸ τῆς ΑΓ τετράγωνον ἔλαττόν ἐστι τῶν ἀπὸ τῶν ΓΒ, ΒΑ τετραγώνων "
        "τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ περιεχομένῳ ὀρθογωνίῳ."
    )
    tts_comparison: list[dict[str, Any]] = []
    for backend, voice, label in [
        (
            "google_au_bilingual",
            "en-AU-Neural2-D",
            "Google Cloud en-AU Male Neural2-D (Bilingual AU + Erasmian IPA)",
        ),
        (
            "google_au_bilingual",
            "en-AU-News-G",
            "Google Cloud en-AU Male News-G (Bilingual AU + Erasmian IPA)",
        ),
        (
            "google_au_bilingual",
            "en-AU-Polyglot-1",
            "Google Cloud en-AU Male Polyglot-1 (Bilingual AU + Erasmian IPA)",
        ),
        (
            "google_au_bilingual",
            "en-AU-Chirp3-HD-Charon",
            "Google Cloud en-AU Male Chirp3-HD-Charon (Generative HD)",
        ),
        (
            "google_au_bilingual",
            "en-AU-Chirp3-HD-Orus",
            "Google Cloud en-AU Male Chirp3-HD-Orus (Generative HD)",
        ),
        (
            "google_erasmian",
            "en-AU-Neural2-D",
            "Google Cloud en-AU Male Neural2-D (Pure Erasmian Greek)",
        ),
        (
            "google_erasmian",
            "en-US-Chirp3-HD-Charon",
            "Google Cloud en-US Male Chirp3-HD-Charon (Pure Erasmian Greek)",
        ),
        (
            "google_erasmian",
            "en-US-Studio-Q",
            "Google Cloud en-US Male Studio-Q (Pure Erasmian Greek)",
        ),
        (
            "kokoro_erasmian",
            "bm_george",
            "Local Kokoro-82M ONNX Male (bm_george, Offline Fallback)",
        ),
    ]:
        c_bi = pipeline.tts.synthesize_sentence(
            s_ii13_spec,
            english_sentence=s_bilingual,
            backend=backend,
            voice=voice,
        )
        c_gr = pipeline.tts.synthesize_sentence(
            s_ii13_spec,
            backend=(
                "google_erasmian" if backend == "google_au_bilingual" else backend
            ),
            voice=voice,
        )
        row = {
            "backend": backend,
            "voice": voice,
            "label": label,
            "bilingual_synth_ms": c_bi.synthesis_ms,
            "bilingual_dur_s": c_bi.duration_s,
            "ii13_spec_synth_ms": c_gr.synthesis_ms,
            "ii13_spec_dur_s": c_gr.duration_s,
        }
        tts_comparison.append(row)
        print(
            f"   {label:64s} | Bilingual: {c_bi.synthesis_ms:6.1f}ms ({c_bi.duration_s:5.2f}s) | "
            f"II.13 Spec: {c_gr.synthesis_ms:6.1f}ms ({c_gr.duration_s:5.2f}s)"
        )

    agg = {
        "stt_ms": compute_stats([r["stt_ms"] for r in turns_summary]),
        "rag_ms": compute_stats([r["rag_ms"] for r in turns_summary]),
        "llm_ms": compute_stats([r["llm_ms"] for r in turns_summary]),
        "tts_first_sentence_ms": compute_stats(
            [r["tts_first_sentence_ms"] for r in turns_summary]
        ),
        "tts_total_ms": compute_stats(
            [r["tts_total_ms"] for r in turns_summary]
        ),
        "total_unattended_ms": compute_stats(
            [r["total_unattended_ms"] for r in turns_summary]
        ),
        "post_approval_start_ms": compute_stats(
            [r["post_approval_start_ms"] for r in turns_summary]
        ),
    }

    report = {
        "model_config": {
            "stt_model": pipeline.stt.model_id,
            "stt_warmup_ms": pipeline.stt.warmup_ms,
            "gemini_model": cfg.gemini_model,
            "tts_backend": cfg.tts_backend,
            "tts_voice": cfg.active_tts_voice(),
            "tts_rate_english": cfg.tts_rate_english,
            "tts_rate_greek": cfg.tts_rate,
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
    summary_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
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
