"""Command-line interface for `euclid-avatar` (II.13 Presentation & Live Q&A)."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

import uvicorn

from .benchmark import run_benchmark_suite, run_single_dry_run
from .config import DEFAULT_PORT, load_config
from .devices import format_devices_report
from .index import build_or_update_index
from .pipeline import EuclidPipeline
from .server import create_app
from .video import DEFAULT_TARGET_DURATION_S, render_presentation_videos

MAX_PORT_PROBE_ATTEMPTS = 20


def _is_port_available(host: str, port: int) -> bool:
    """Return True if (host, port) can be bound without conflict."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _select_available_port(host: str, preferred_port: int) -> int:
    """Return preferred_port if free, or the next available port starting at DEFAULT_PORT."""
    if _is_port_available(host, preferred_port):
        return preferred_port
    candidates = [DEFAULT_PORT] + [
        DEFAULT_PORT + offset for offset in range(1, MAX_PORT_PROBE_ATTEMPTS)
    ]
    for candidate in candidates:
        if candidate != preferred_port and _is_port_available(host, candidate):
            return candidate
    raise RuntimeError(
        f"Could not find an available local TCP port near {preferred_port}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="euclid_avatar",
        description="Euclid Avatar for MATH E-139 Book II Proposition 13 Presentation & Professor Q&A",
    )
    sub = parser.add_subparsers(dest="command")

    # 1. devices
    sub.add_parser(
        "devices",
        help="List detected CoreAudio devices and verify BlackHole virtual routing",
    )

    # 2. index
    idx_p = sub.add_parser(
        "index",
        help="Build or update local SQLite FTS5 course index in .cache/course_index.sqlite",
    )
    idx_p.add_argument(
        "--force", action="store_true", help="Force full rebuild of the index"
    )

    # 3. prebuild-presentation
    pres_p = sub.add_parser(
        "prebuild-presentation",
        help="Pre-render all 5 slides of the II.13 Greek presentation (Australian English + Erasmian Greek)",
    )
    pres_p.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Override TTS voice (e.g. en-AU-Neural2-D or en-AU-Chirp3-HD-Charon)",
    )
    pres_p.add_argument(
        "--force",
        action="store_true",
        help="Force re-synthesis of all segments even if cached",
    )
    pres_p.add_argument(
        "--play",
        action="store_true",
        help="Play the presentation out loud after building",
    )

    # 3b. render-video
    vid_p = sub.add_parser(
        "render-video",
        help="Render the full 5-minute 16:9 (1920x1080) MP4 presentation video for Google Slides",
    )
    vid_p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/videos"),
        help="Output directory for generated MP4 files (default: output/videos)",
    )
    vid_p.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Override TTS voice identifier (default: en-AU-Chirp3-HD-Charon)",
    )
    vid_p.add_argument(
        "--target-duration",
        type=float,
        default=DEFAULT_TARGET_DURATION_S,
        help="Target duration in seconds (default: 300.0 for 5 minutes; <= 0 for unabridged)",
    )
    vid_p.add_argument(
        "--also-unabridged",
        action="store_true",
        help="Also render the 1.0x unabridged presentation MP4",
    )

    # 4. dry-run
    dry_p = sub.add_parser(
        "dry-run",
        help="Run a single WAV file through STT -> RAG -> Gemini -> Bilingual/Erasmian TTS",
    )
    dry_p.add_argument(
        "--wav", type=str, required=True, help="Path to input WAV question file"
    )
    dry_p.add_argument(
        "--auto-approve",
        action="store_true",
        default=True,
        help="Automatically approve and record timings",
    )
    dry_p.add_argument(
        "--play",
        action="store_true",
        help="Play synthesized audio out loud during dry-run",
    )
    dry_p.add_argument(
        "--backend", type=str, default=None, help="Override TTS backend"
    )
    dry_p.add_argument(
        "--voice", type=str, default=None, help="Override TTS voice"
    )

    # 5. benchmark
    bench_p = sub.add_parser(
        "benchmark",
        help="Run the 10-question Book II Proposition 13 Professor Q&A benchmark suite",
    )
    bench_p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of benchmark questions to run (default: 10)",
    )
    bench_p.add_argument(
        "--play",
        action="store_true",
        help="Play synthesized audio out loud",
    )
    bench_p.add_argument(
        "--model", type=str, default=None, help="Override GEMINI_MODEL"
    )
    bench_p.add_argument(
        "--backend", type=str, default=None, help="Override TTS_BACKEND"
    )

    # 6. serve (default)
    serve_p = sub.add_parser(
        "serve", help="Run local web server serving /avatar and /control"
    )
    serve_p.add_argument(
        "--host", type=str, default=None, help="Bind host (default 127.0.0.1)"
    )
    serve_p.add_argument(
        "--port", type=int, default=None, help="Bind port (default 8765)"
    )

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

    if cmd == "prebuild-presentation":
        pipeline = EuclidPipeline(cfg, warmup_stt=False, preload_kokoro=False)
        summary = pipeline.prebuild_presentation_deck(
            voice=args.voice, force=args.force
        )
        print("\n=== II.13 Greek Presentation Pre-Build Summary ===")
        print(f"Voice Model:          {summary['voice']}")
        print(
            f"Slides / Segments:    {summary['total_slides']} slides / {summary['total_segments']} segments "
            f"(synthesized: {summary['synthesized_segments']}, cached: {summary['loaded_from_cache']})"
        )
        for s in summary["slides"]:
            print(
                f"  Slide {s['slide_number']}: {s['title']:36s} | "
                f"{s['segments']} segs | {s['duration_s']:5.1f} s"
            )
        print(
            f"Total Duration:       {summary['total_duration_s']:.1f} s ({summary['total_duration_min']:.2f} min)"
        )
        print(f"Combined Master WAV:  {summary['full_wav_path']}")
        print(f"Build Time:           {summary['elapsed_ms']:.1f} ms")
        if args.play:
            print("\nPlaying full 5-minute presentation...")
            pipeline.play_presentation(
                start_slide=1,
                voice=args.voice,
                play_audio=True,
                block=True,
            )
        return 0

    if cmd == "render-video":
        voice = args.voice or cfg.active_tts_voice()
        target_dur = (
            args.target_duration
            if args.target_duration and args.target_duration > 0
            else None
        )
        out_dir = Path(args.output_dir).expanduser().resolve()
        summary = render_presentation_videos(
            cfg.project_root / "presentation_ii13.yaml",
            cfg.cache_dir / "presentation_ii13",
            out_dir,
            voice=voice,
            target_duration_s=target_dur,
            render_per_slide=True,
        )
        print("\n=== II.13 16:9 Presentation Video Render Summary ===")
        print(
            f"Full Video:           {summary['full_video']['path']} "
            f"({summary['full_video']['duration_s']} s / {summary['full_video']['duration_min']} min, "
            f"{summary['full_video']['size_mb']} MB, {summary['full_video']['resolution']})"
        )
        for sv in summary.get("slide_videos", []):
            print(
                f"  Slide {sv['slide_number']} Video:      {sv['path']} "
                f"({sv['duration_s']} s, {sv['size_mb']} MB)"
            )
        if args.also_unabridged and target_dur is not None:
            unab = render_presentation_videos(
                cfg.project_root / "presentation_ii13.yaml",
                cfg.cache_dir / "presentation_ii13",
                out_dir,
                voice=voice,
                target_duration_s=None,
                render_per_slide=False,
            )
            print(
                f"Unabridged Video:     {unab['full_video']['path']} "
                f"({unab['full_video']['duration_s']} s / {unab['full_video']['duration_min']} min, "
                f"{unab['full_video']['size_mb']} MB)"
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
        print(f"Spoken Answer:        {turn.english}")
        print(f"Greek Quotation:      {turn.greek}")
        print(f"Saved WAV:            {turn.wav_path}")
        print(f"STT Latency:          {turn.stt_ms:.1f} ms")
        print(f"Course RAG Latency:   {turn.rag_ms:.1f} ms")
        print(
            f"Gemini LLM Latency:   {turn.llm_ms:.1f} ms ({turn.llm_model})"
        )
        print(
            f"TTS Sent 1 Latency:   {turn.tts_first_sentence_ms:.1f} ms ({turn.tts_backend} / {turn.tts_voice})"
        )
        print(f"TTS Total Latency:    {turn.tts_total_ms:.1f} ms")
        print(
            f"Unattended Latency:   {turn.total_unattended_ms:.1f} ms ({turn.total_unattended_ms/1000:.2f} s)"
        )
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
        requested_port = getattr(args, "port", None) or cfg.port
        port = _select_available_port(host, requested_port)
        if port != requested_port:
            print(
                f"   [Note] Port {requested_port} is already in use by another process; "
                f"binding to {host}:{port} instead."
            )
        cfg.host = host
        cfg.port = port
        print("1. Checking course index (.cache/course_index.sqlite)...")
        stats = build_or_update_index(cfg, force=False)
        print(
            f"   Course index ready ({stats['total_chunks']} chunks, {stats['elapsed_ms']} ms)."
        )
        print("2. Warming up MLX Whisper STT & pre-loading TTS engines...")
        pipeline = EuclidPipeline(cfg, warmup_stt=True, preload_kokoro=True)
        print(f"   STT warmup completed in {pipeline.stt.warmup_ms} ms.")
        print(
            "3. Ensuring 5-minute II.13 Greek presentation segments are pre-cached..."
        )
        pres_summary = pipeline.prebuild_presentation_deck(force=False)
        print(
            f"   Presentation ready ({pres_summary['total_slides']} slides, "
            f"{pres_summary['total_duration_s']:.1f} s / {pres_summary['total_duration_min']:.2f} min)."
        )
        print(f"4. Starting server on http://{host}:{port}")
        print(f"   -> Operator Control UI: http://{host}:{port}/control")
        print(
            f"   -> OBS Browser Source:  http://{host}:{port}/avatar (1920x1080)"
        )
        app = create_app(cfg, pipeline)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
