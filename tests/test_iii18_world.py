"""Unit tests for the Proposition III.18 3D Euclidean-to-Spherical Virtual World."""

from __future__ import annotations

import math
import unittest

from euclid_avatar.iii18_world.geometry import (
    DEG_TO_RAD,
    EUCLID_RADIUS,
    GEOMETRY_CHECK_TOL,
    GLOBE_CENTER_WORLD,
    MIN_OBTUSE_FAR_FOOT_DEG,
    RIGHT_ANGLE_DEG,
    SPHERE_CIRCLE_RADIUS_DEG,
    build_world_spec,
    compute_plane_construction,
    evaluate_deformed_state,
    run_all_geometry_checks,
    vec3_dot,
    vec3_norm,
    vec3_scale,
    vec3_sub,
)
from euclid_avatar.iii18_world.world_html import render_world_html


class TestIII18WorldGeometry(unittest.TestCase):
    """Verify mathematical accuracy of plane, spherical, and continuous morph states."""

    def test_plane_construction_matches_fitzpatrick_and_r_checks(self) -> None:
        plane = compute_plane_construction()
        self.assertAlmostEqual(plane["angle_FGC_deg"], 50.0, places=9)
        self.assertAlmostEqual(plane["angle_FCG_deg"], RIGHT_ANGLE_DEG, places=9)
        expected_fg = EUCLID_RADIUS / math.cos(40.0 * DEG_TO_RAD)
        self.assertAlmostEqual(plane["FG_length"], expected_fg, places=9)
        self.assertGreater(plane["BG_length"], 0.2)
        self.assertEqual(len(plane["claim_contacts"]), 3)
        self.assertEqual(len(plane["fan"]), 4)
        for ray in plane["fan"]:
            self.assertGreater(ray["length"], EUCLID_RADIUS + 0.05)

    def test_continuous_deformation_preserves_right_angle_and_tangency(self) -> None:
        for step in range(11):
            tau = step / 10.0
            state = evaluate_deformed_state(tau)
            self.assertLess(
                abs(state["angle_fcd_deg"] - RIGHT_ANGLE_DEG),
                GEOMETRY_CHECK_TOL,
                msg=f"Angle FCD drifted from 90 deg at tau={tau}",
            )
            if state["sphere_center"] is not None and state["sphere_radius"] is not None:
                ctr = state["sphere_center"]
                rad = state["sphere_radius"]
                nf = vec3_scale(vec3_sub(state["F"], ctr), 1.0 / rad)
                nc = vec3_scale(vec3_sub(state["C"], ctr), 1.0 / rad)
                alpha = math.acos(max(-1.0, min(1.0, vec3_dot(nf, nc))))
                self.assertAlmostEqual(rad * alpha, EUCLID_RADIUS, places=9)

    def test_sphere_endpoint_and_far_foot_counterexample(self) -> None:
        checks = run_all_geometry_checks()
        state_1 = evaluate_deformed_state(1.0)
        self.assertIsNotNone(state_1["sphere_center"])
        self.assertLess(
            vec3_norm(vec3_sub(state_1["sphere_center"], GLOBE_CENTER_WORLD)),
            GEOMETRY_CHECK_TOL,
        )
        ff = checks["far_foot"]
        self.assertAlmostEqual(ff["FC_deg"], SPHERE_CIRCLE_RADIUS_DEG, places=9)
        self.assertAlmostEqual(ff["angle_G_deg"], RIGHT_ANGLE_DEG, places=9)
        self.assertGreater(ff["angle_C_deg"], MIN_OBTUSE_FAR_FOOT_DEG)
        self.assertGreater(ff["FG_deg"], RIGHT_ANGLE_DEG)
        self.assertLess(ff["near_FG_deg"], RIGHT_ANGLE_DEG)

    def test_slides_and_world_html_completeness(self) -> None:
        spec = build_world_spec()
        slides = spec["slides"]
        self.assertEqual(len(slides), 6)
        total_segs = sum(len(s["segments"]) for s in slides)
        self.assertEqual(total_segs, 18)
        # Ensure Slide 6 executes the 0 -> 1 2D-to-Sphere morph
        morph_segs = [
            seg
            for s in slides
            for seg in s["segments"]
            if seg["tau_start"] == 0.0 and seg["tau_end"] == 1.0
        ]
        self.assertEqual(len(morph_segs), 1)

        html = render_world_html(spec)
        self.assertIn("window.setVirtualWorldTime", html)
        self.assertIn("evaluateDeformed", html)
        self.assertIn("On the sphere", html)


if __name__ == "__main__":
    unittest.main()
