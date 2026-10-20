"""Command-line interface for `euclid-avatar`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from .benchmark import run_benchmark_suite, run_single_dry_run
from .config import load_config
from .devices import format_devices_report
from .index import build_or_update_index
from .pipeline import EuclidPipeline
from .server import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="euclid_avatar",
        description="Live Euclid avatar spike for Harvard Extension School MATH E-139 on Zoom",
    )
    sub = parser.add_subparsers(dest="command")

    # 1. devices
    sub.add_parser("devices", help="List detected CoreAudio devices and verify BlackHole virtual routing")

    # 2. index
    idx_p = sub.add_parser("index", help="Build or update local SQLite FTS5 course index in .cache/course_index.sqlite")
    idx_p.add_argument("--force", action="store_true", help="Force full rebuild of the index")

    # 3. dry-run
    dry_p = sub.add_parser("dry-run", help="Run a single WAV file through STT -> RAG -> Gemini -> Greek TTS")
    dry_p.add_argument("--wav", type=str, required=True, help="Path to input WAV question file")
    dry_p.add_argument("--auto-approve", action="store_true", default=True, help="Automatically approve and record timings")
    dry_p.add_argument("--play", action="store_true", help="Play synthesized Greek audio out loud during dry-run")
    dry_p.add_argument("--backend", type=str, default=None, help="Override TTS backend")
    dry_p.add_argument("--voice", type=str, default=None, help="Override TTS voice")

    # 4. benchmark
    bench_p = sub.add_parser("benchmark", help="Run the 10-question MATH E-139 dry-run benchmark suite")
    bench_p.add_argument("--limit", type=int, default=10, help="Number of benchmark questions to run (default: 10)")
    bench_p.add_argument("--play", action="store_true", help="Play synthesized Greek audio out loud")
    bench_p.add_argument("--model", type=str, default=None, help="Override GEMINI_MODEL")
    bench_p.add_argument("--backend", type=str, default=None, help="Override TTS_BACKEND")

    # 5. serve (default)
    serve_p = sub.add_parser("serve", help="Run local web server serving /avatar and /control")
    serve_p.add_argument("--host", type=str, default=None, help="Bind host (default 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=None, help="Bind port (default 8765)")

    args = parser.parse_args(argv)
    cfg = load_config()

    cmd = args.command or "serve"

    if cmd == "devices":
        print(format_devices_report(cfg))
        return 0

    if cmd == "index":
        stats = build_or_update_index(cfg, force=getattr(args, "force", False))
        print(f"Course index ready at {stats['db_path']}")
        print(
            f"  Indexed files: {stats['total_files']} (updated: {stats['updated_files']})\n"
            f"  Total chunks:  {stats['total_chunks']}\n"
            f"  Entity keys:   {stats['distinct_entity_keys']}\n"
            f"  Elapsed time:  {stats['elapsed_ms']} ms"
        )
        return 0

    if cmd == "dry-run":
        wav_path = Path(args.wav).expanduser().resolve()
        if not wav_path.exists():
            print(f"Error: WAV file not found: {wav_path}", file=sys.stderr)
            return 1
        build_or_update_index(cfg, force=False)
        pipeline = EuclidPipeline(cfg, warmup_stt=True, preload_kokoro=True)
        turn = run_single_dry_run(
            pipeline,
            wav_path,
            play_audio=args.play,
            tts_backend=args.backend,
            tts_voice=args.voice,
        )
        print("\n=== Dry-Run Turn Summary ===")
        print(f"Transcript:           {turn.transcript}")
        print(f"Cited Sources:        {', '.join(turn.sources)}")
        print(f"English:              {turn.english}")
        print(f"Ancient Greek:        {turn.greek}")
        print(f"Saved WAV:            {turn.wav_path}")
        print(f"STT Latency:          {turn.stt_ms:.1f} ms")
        print(f"Course RAG Latency:   {turn.rag_ms:.1f} ms")
        print(f"Gemini LLM Latency:   {turn.llm_ms:.1f} ms ({turn.llm_model})")
        print(f"TTS Sent 1 Latency:   {turn.tts_first_sentence_ms:.1f} ms ({turn.tts_backend} / {turn.tts_voice})")
        print(f"TTS Total Latency:    {turn.tts_total_ms:.1f} ms")
        print(f"Unattended Latency:   {turn.total_unattended_ms:.1f} ms ({turn.total_unattended_ms/1000:.2f} s)")
        print(f"Post-Approval Start:  {turn.post_approval_start_ms:.2f} ms")
        return 0

    if cmd == "benchmark":
        if args.model:
            cfg.gemini_model = args.model
        if args.backend:
            cfg.tts_backend = args.backend
        run_benchmark_suite(cfg, play_audio=args.play, limit=args.limit)
        return 0

    if cmd == "serve":
        host = getattr(args, "host", None) or cfg.host
        port = getattr(args, "port", None) or cfg.port
        print("1. Checking course index (.cache/course_index.sqlite)...")
        stats = build_or_update_index(cfg, force=False)
        print(f"   Course index ready ({stats['total_chunks']} chunks, {stats['elapsed_ms']} ms).")
        print("2. Warming up MLX Whisper STT & pre-loading TTS engines...")
        pipeline = EuclidPipeline(cfg, warmup_stt=True, preload_kokoro=True)
        print(f"   STT warmup completed in {pipeline.stt.warmup_ms} ms.")
        print(f"3. Starting server on http://{host}:{port}")
        print(f"   -> Operator Control UI: http://{host}:{port}/control")
        print(f"   -> OBS Browser Source:  http://{host}:{port}/avatar (1920x1080)")
        app = create_app(cfg, pipeline)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
