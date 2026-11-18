"""Unit tests for Elements III.36 3D Area-Proof & Spherical Breakdown World."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from euclid_avatar.iii36_world.assets import MAX_PRESENTATION_DURATION_S
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
    """Verify mathematical accuracy, no-subtitle UI rule, and <7-min duration ceiling."""

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

    def test_no_subtitles_and_slide_structure(self) -> None:
        spec = build_world_spec()
        self.assertEqual(len(spec["slides"]), 5)
        html = render_world_html(spec)
        # User requirement: subtitles completely removed
        self.assertNotIn("subtitle-banner", html)
        self.assertIn("window.setVirtualWorldTime", html)

    def test_cached_manifest_under_seven_minutes_if_present(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
