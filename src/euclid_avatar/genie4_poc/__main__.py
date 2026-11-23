"""CLI entrypoint for ``python -m euclid_avatar.genie4_poc``."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import shutil

from . import (
    DEFAULT_DURATION_S,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    GENIE_MODEL,
    MAX_SESSION_DURATION_S,
)
from .genie_client import build_steering_schedule, record_genie4_session
from .media import (
    DEFAULT_SEED_ASPECT_RATIO,
    DEFAULT_SEED_IMAGE_SIZE,
    detect_video_frame_codec,
    discover_gemini_api_key,
    generate_seed_image,
    mux_video_with_narration_mp4,
    synthesize_ancient_greek_narration,
)
from .prompts import build_prompt_bundle, export_prompt_kit
from .propositions import (
    DEFAULT_COURSE_REPO,
    build_curated_iii36_plan,
    load_or_build_proposition_plan,
    parse_proposition_id,
)
from .server import serve_genie4_studio


def _find_existing_seed_image(out_dir: Path) -> Path | None:
    for ext in (".jpg", ".png", ".webp"):
        candidate = out_dir / f"seed_frame_16x9{ext}"
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def _default_output_dir(root_dir: Path, slug: str) -> Path:
    return root_dir / "output" / "genie4_poc" / slug


def _default_cache_dir(root_dir: Path, slug: str) -> Path:
    return root_dir / ".cache" / "genie4_poc" / slug


def _run_offline_check(root_dir: Path, course_repo: Path) -> None:
    plan = build_curated_iii36_plan()
    bundle = build_prompt_bundle(plan)
    assert "NOT a magnetic" in bundle["world_setup_prompt"]
    assert "unmarked" in bundle["world_setup_prompt"]
    assert "No music." in bundle["world_setup_prompt"]
    assert "ὅπερ ἔδει δεῖξαι" in plan.steps[-1].greek_text
    assert detect_video_frame_codec(b"\xff\xd8\xff\xe0\x00\x10JFIF")[0] == "mjpeg"
    sched = build_steering_schedule(plan, int(DEFAULT_DURATION_S * 24))
    assert len(sched) == len(plan.steps)

    has_key = bool(discover_gemini_api_key(root_dir, course_repo_path=course_repo))
    has_pdf = (course_repo / "materials/books/Elements.pdf").exists()
    has_ffmpeg = shutil.which("ffmpeg") is not None
    print(
        f"Genie 4 POC offline check PASSED · prop={plan.proposition_id} "
        f"steps={len(plan.steps)} api_key={'found' if has_key else 'missing'} "
        f"elements_pdf={'found' if has_pdf else 'missing'} "
        f"ffmpeg={'found' if has_ffmpeg else 'missing'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Historically accurate Euclid in Ancient Greek — Genie 4 POC"
    )
    parser.add_argument(
        "--course-repo",
        type=Path,
        default=DEFAULT_COURSE_REPO,
        help="Read-only path to ~/Projects/Courses/26Fall/mathe139",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Run offline prompt, Greek text, and environment checks")

    def _add_common_prop_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--prop", default="III.36", help="Elements proposition (e.g. III.36, II.13, I.47)")
        p.add_argument("--use-llm", action="store_true", help="Plan via gemini-3.5-flash-lite even for III.36")
        p.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
        p.add_argument("--ambient-only", action="store_true", help="Prompt Genie 4 for ambient sound only")
        p.add_argument("--output-dir", type=Path, default=None)

    p_plan = sub.add_parser("plan", help="Build and export the Genie 4 prompt kit")
    _add_common_prop_args(p_plan)

    p_seed = sub.add_parser("seed", help="Generate the 16:9 photorealistic starting seed image")
    _add_common_prop_args(p_seed)
    p_seed.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    p_seed.add_argument("--image-size", default=DEFAULT_SEED_IMAGE_SIZE)
    p_seed.add_argument("--force", action="store_true")

    p_narr = sub.add_parser("narrate", help="Synthesize Ancient Greek audio with euclid-avatar TTS models")
    _add_common_prop_args(p_narr)
    p_narr.add_argument("--tts-backend", choices=("gemini_tts", "erasmian_ipa"), default="gemini_tts")
    p_narr.add_argument("--tts-model", default=DEFAULT_TTS_MODEL)
    p_narr.add_argument("--voice", default=DEFAULT_TTS_VOICE)
    p_narr.add_argument("--force", action="store_true")

    p_rec = sub.add_parser("record", help="Run a live Genie 4 WebSocket capture and mux to MP4")
    _add_common_prop_args(p_rec)
    p_rec.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    p_rec.add_argument("--seed-image", type=Path, default=None)
    p_rec.add_argument("--no-seed", action="store_true")

    p_run = sub.add_parser("run", help="Full end-to-end POC: plan -> seed -> Genie 4 record -> optional TTS mux")
    _add_common_prop_args(p_run)
    p_run.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    p_run.add_argument("--image-size", default=DEFAULT_SEED_IMAGE_SIZE)
    p_run.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    p_run.add_argument("--with-narration", action="store_true", help="Also synthesize & mix Ancient Greek TTS")
    p_run.add_argument("--tts-backend", choices=("gemini_tts", "erasmian_ipa"), default="gemini_tts")
    p_run.add_argument("--tts-model", default=DEFAULT_TTS_MODEL)
    p_run.add_argument("--voice", default=DEFAULT_TTS_VOICE)
    p_run.add_argument("--force", action="store_true")

    p_srv = sub.add_parser("serve", help="Run local interactive WebRTC Genie 4 studio (port 8795)")
    _add_common_prop_args(p_srv)
    p_srv.add_argument("--host", default=DEFAULT_SERVER_HOST)
    p_srv.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT)
    p_srv.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    p_srv.add_argument("--image-size", default=DEFAULT_SEED_IMAGE_SIZE)
    p_srv.add_argument("--no-seed", action="store_true")

    args = parser.parse_args()
    root_dir = Path(__file__).resolve().parents[3]

    if args.command == "check":
        _run_offline_check(root_dir, args.course_repo)
        return

    api_key = discover_gemini_api_key(root_dir, course_repo_path=args.course_repo)
    _, _, canonical = parse_proposition_id(args.prop)
    slug = canonical.lower().replace(".", "")
    out_dir = args.output_dir or _default_output_dir(root_dir, slug)
    cache_dir = _default_cache_dir(root_dir, slug)

    plan = load_or_build_proposition_plan(
        canonical,
        api_key=api_key,
        course_repo_path=args.course_repo,
        llm_model=args.llm_model,
        use_llm=args.use_llm,
        cache_path=cache_dir / "lesson_plan.json",
    )
    kit = export_prompt_kit(plan, out_dir, ambient_only_audio=args.ambient_only)
    bundle = build_prompt_bundle(plan, ambient_only_audio=args.ambient_only)

    if args.command == "plan":
        print(f"Exported prompt kit for Elements {plan.proposition_id}:")
        for key, path in kit.items():
            print(f"  {key}: {path}")
        return

    if args.command == "seed":
        info = generate_seed_image(
            bundle["seed_image_prompt"],
            out_dir / "seed_frame_16x9.jpg",
            api_key,
            model=args.image_model,
            aspect_ratio=DEFAULT_SEED_ASPECT_RATIO,
            image_size=args.image_size,
            cache_dir=cache_dir / "seeds",
            force=args.force,
        )
        print(
            f"Seed image ready ({info['model']}, cached={info['cached']}, "
            f"{info['bytes']} bytes): {info['path']}"
        )
        return

    if args.command == "narrate":
        manifest = synthesize_ancient_greek_narration(
            plan,
            out_dir / "audio",
            api_key,
            backend=args.tts_backend,
            tts_model=args.tts_model,
            voice=args.voice,
            force=args.force,
        )
        print(
            f"Narration ready ({manifest['tts_model']} / {manifest['voice']}, "
            f"{manifest['total_duration_s']:.1f}s): {manifest['master_wav']}"
        )
        return

    if args.command == "record":
        if args.duration_s > MAX_SESSION_DURATION_S:
            raise SystemExit(
                f"--duration-s={args.duration_s} exceeds {MAX_SESSION_DURATION_S:.0f}s safety cap."
            )
        seed_path = (
            None
            if args.no_seed
            else (args.seed_image or _find_existing_seed_image(out_dir))
        )
        if not args.no_seed and (seed_path is None or not seed_path.exists()):
            raise SystemExit(
                f"Seed image not found in {out_dir}. Run `seed` first or pass --no-seed."
            )
        report = asyncio.run(
            record_genie4_session(
                plan,
                api_key,
                out_dir,
                seed_image_path=seed_path,
                duration_s=args.duration_s,
                ambient_only_audio=args.ambient_only,
                model=GENIE_MODEL,
            )
        )
        print(
            f"Genie 4 MP4 ready: {report.output_mp4_path} "
            f"({report.video_frames} frames, {report.actual_duration_s:.2f}s, "
            f"~${report.estimated_video_cost_usd:.3f}, completed={report.completed_cleanly})"
        )
        return

    if args.command == "run":
        seed_info = generate_seed_image(
            bundle["seed_image_prompt"],
            out_dir / "seed_frame_16x9.jpg",
            api_key,
            model=args.image_model,
            aspect_ratio=DEFAULT_SEED_ASPECT_RATIO,
            image_size=args.image_size,
            cache_dir=cache_dir / "seeds",
            force=args.force,
        )
        seed_path = seed_info["path"]
        print(
            f"[1/3] Seed frame ({seed_info['model']}, cached={seed_info['cached']}): "
            f"{seed_path}"
        )

        report = asyncio.run(
            record_genie4_session(
                plan,
                api_key,
                out_dir,
                seed_image_path=seed_path,
                duration_s=args.duration_s,
                ambient_only_audio=args.ambient_only,
                model=GENIE_MODEL,
            )
        )
        print(
            f"[2/3] Genie 4 capture: {report.output_mp4_path} "
            f"({report.video_frames} frames, {report.actual_duration_s:.2f}s, "
            f"codec={report.detected_video_codec}, audio={report.audio_bytes} B, "
            f"~${report.estimated_video_cost_usd:.3f})"
        )

        if args.with_narration:
            manifest = synthesize_ancient_greek_narration(
                plan,
                out_dir / "audio",
                api_key,
                backend=args.tts_backend,
                tts_model=args.tts_model,
                voice=args.voice,
                force=args.force,
            )
            narrated_mp4 = out_dir / f"euclid_{plan.slug}_genie4_narrated.mp4"
            mux_video_with_narration_mp4(
                Path(report.output_mp4_path),
                Path(manifest["master_wav"]),
                narrated_mp4,
            )
            print(
                f"[3/3] Narrated companion MP4 ({manifest['tts_model']} / {manifest['voice']}): "
                f"{narrated_mp4}"
            )
        else:
            print("[3/3] Skipped external TTS overlay (pass --with-narration to add).")
        return

    if args.command == "serve":
        seed_path: Path | None = None
        if not args.no_seed:
            seed_path = _find_existing_seed_image(out_dir)
            if seed_path is None:
                seed_info = generate_seed_image(
                    bundle["seed_image_prompt"],
                    out_dir / "seed_frame_16x9.jpg",
                    api_key,
                    model=args.image_model,
                    aspect_ratio=DEFAULT_SEED_ASPECT_RATIO,
                    image_size=args.image_size,
                    cache_dir=cache_dir / "seeds",
                )
                seed_path = seed_info["path"]
        serve_genie4_studio(
            plan,
            seed_path,
            api_key,
            host=args.host,
            port=args.port,
            ambient_only_audio=args.ambient_only,
        )


if __name__ == "__main__":
    main()
