"""Unit tests for Elements III.36 3D Area-Proof & Spherical Breakdown World."""

from __future__ import annotations

import array
import json
import math
from pathlib import Path
import unittest

from euclid_avatar.iii36_world.assets import (
    AUDIO_SAMPLE_RATE_HZ,
    MAX_PRESENTATION_DURATION_S,
    extract_segment_highlight_cues,
)
from euclid_avatar.iii36_world.geometry import (
    EXPECTED_AREA,
    EXPECTED_DB,
    EXPECTED_ED,
    GEOMETRY_CHECK_TOL,
    RIGHT_ANGLE_DEG,
    build_world_spec,
    compute_plane_model,
    evaluate_spherical_state,
    run_all_geometry_checks,
)
from euclid_avatar.iii36_world.world_html import render_world_html


class TestIII36World(unittest.TestCase):
    """Verify mathematical accuracy, highlight cues, interactive controls, and UI rules."""

    def test_plane_cases_and_fan_invariance(self) -> None:
        plane = compute_plane_model()
        self.assertAlmostEqual(plane["DB"], EXPECTED_DB, places=9)
        self.assertAlmostEqual(plane["ED"], EXPECTED_ED, places=9)
        self.assertAlmostEqual(plane["case1"]["DC"], 2.0, places=9)
        self.assertAlmostEqual(plane["case1"]["DA"], 8.0, places=9)
        self.assertEqual(len(plane["fan"]), 5)
        for sec in [plane["case1"], plane["case2"], *plane["fan"]]:
            self.assertAlmostEqual(sec["area_rect"], EXPECTED_AREA, places=8)

    def test_spherical_breakdown_and_half_tangent_identity(self) -> None:
        run_all_geometry_checks()
        st0 = evaluate_spherical_state(0.0)
        self.assertAlmostEqual(st0["rect_product"], EXPECTED_AREA, places=9)
        self.assertAlmostEqual(st0["tangent_square"], EXPECTED_AREA, places=9)
        self.assertAlmostEqual(st0["square_corner_gap_unit"], 0.0, places=9)

        for step in range(1, 11):
            st = evaluate_spherical_state(step / 10.0)
            self.assertAlmostEqual(st["angle_ebd_deg"], RIGHT_ANGLE_DEG, places=5)
            self.assertGreater(st["tangent_square"], st["rect_product"])
            self.assertLess(
                abs(st["tan_half_lhs"] - st["tan_half_rhs"]), GEOMETRY_CHECK_TOL
            )
            self.assertGreater(st["square_corner_gap_unit"], 0.0)
        self.assertGreater(
            evaluate_spherical_state(1.0)["square_corner_gap_unit"], 0.5
        )

    def test_highlight_cue_extractor_detects_segments_triangles_and_squares(self) -> None:
        # Synthetic 6-second voiced waveform for unit testing cue extraction
        n_samples = 6 * AUDIO_SAMPLE_RATE_HZ
        synth = array.array(
            "h",
            (int(4000 * math.sin(2 * math.pi * 220 * i / AUDIO_SAMPLE_RATE_HZ)) for i in range(n_samples)),
        )
        text = (
            "Drop perpendicular E F to A C; in right triangle E F C, "
            "the square on D B equals A D by D C."
        )
        cues = extract_segment_highlight_cues(text, synth, AUDIO_SAMPLE_RATE_HZ, 10.0)
        all_segs = {s for c in cues for s in c["segments"]}
        all_tris = {t for c in cues for t in c["triangles"]}
        all_slabs = {sl for c in cues for sl in c["slabs"]}
        self.assertIn("EF", all_segs)
        self.assertIn("AC", all_segs)
        self.assertIn("DB", all_segs)
        self.assertIn("AD", all_segs)
        self.assertIn("DC", all_segs)
        self.assertIn("EFC", all_tris)
        self.assertIn("sqDB", all_slabs)

    def test_no_subtitles_and_interactive_checkpoints_wired(self) -> None:
        spec = build_world_spec()
        self.assertEqual(len(spec["slides"]), 5)
        interactive_modes = [
            seg.get("interactive_mode")
            for sl in spec["slides"]
            for seg in sl["segments"]
            if seg.get("interactive_mode")
        ]
        self.assertEqual(interactive_modes, ["drag_point_a", "sweep_line_df"])

        html = render_world_html(spec)
        self.assertNotIn("subtitle-banner", html)
        self.assertIn("pauseForUserManipulation", html)
        self.assertIn("applyRaycastDrag", html)
        self.assertIn("interactive-banner", html)

    def test_cached_manifest_under_seven_minutes_and_has_cues(self) -> None:
        manifest = (
            Path(__file__).resolve().parents[1]
            / ".cache"
            / "iii36_world"
            / "world_manifest.json"
        )
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            dur = float(data["timeline"]["total_duration_s"])
            self.assertLessEqual(dur, MAX_PRESENTATION_DURATION_S)
            self.assertGreater(len(data["timeline"].get("highlight_cues", [])), 50)


if __name__ == "__main__":
    unittest.main()
