"""CLI entrypoint for `python3 -m euclid_avatar.iii36_world`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .geometry import run_all_geometry_checks
from .render import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_VIDEO_FPS,
    build_all_and_render,
    serve_interactive_world,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Elements III.36 3D Area-Proof & Spherical Breakdown World"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Run exact plane, area, and spherical failure checks")

    p_build = sub.add_parser("build", help="Render preview PNGs and 1080p MP4")
    p_build.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)
    p_build.add_argument("--skip-video", action="store_true")
    p_build.add_argument("--output-dir", type=Path, default=None)

    p_serve = sub.add_parser("serve", help="Run interactive 3D browser world server")
    p_serve.add_argument("--host", default=DEFAULT_SERVER_HOST)
    p_serve.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT)

    args = parser.parse_args()
    root_dir = Path(__file__).resolve().parents[3]

    if args.command == "check":
        res = run_all_geometry_checks()
        st1 = res["sphere_endpoint"]
        print(
            "All III.36 checks PASSED:",
            f"Plane AD*DC={res['plane']['case2']['area_rect']:.6f},",
            f"Sphere AD*DC={st1['rect_product']:.4f} vs DB^2={st1['tangent_square']:.4f},",
            f"Square gap={st1['square_corner_gap_unit']:.4f}",
        )
    elif args.command == "build":
        out = build_all_and_render(
            root_dir,
            output_dir=args.output_dir,
            fps=args.fps,
            skip_video=args.skip_video,
        )
        print(f"Output directory: {out['output_dir']}")
        if out["mp4_path"]:
            print(f"Rendered 1080p MP4: {out['mp4_path']}")
    elif args.command == "serve":
        serve_interactive_world(root_dir, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
