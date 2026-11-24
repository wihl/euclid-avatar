"""Deterministic, mathematically exact Euclidean construction data for the Genie 4 studio.

Mirrors the verified 3-4-5 Euclidean plane geometry from
``euclid_avatar.iii36_world.geometry`` using J. L. Heiberg's Greek lettering
(``Α, Β, Γ, Δ, Ε, Ζ``) from *Elements* Book III, Proposition 36 (pp. 105-106).
"""

from __future__ import annotations

import math
from typing import Any

from euclid_avatar.iii36_world.geometry import (
    CIRCLE_RADIUS,
    EXPECTED_AREA,
    EXPECTED_DB,
    EXPECTED_ED,
    compute_plane_model,
)
from .propositions import PropositionPlan

# Coordinate bounds for the deterministic SVG/Canvas viewport (math space -> viewBox)
VIEWBOX_WIDTH = 640.0
VIEWBOX_HEIGHT = 480.0
MATH_X_MIN = -5.4
MATH_X_MAX = 4.6
MATH_Y_MIN = -4.2
MATH_Y_MAX = 3.8


def build_iii36_diagram_spec() -> dict[str, Any]:
    """Build exact Heiberg-lettered geometric scenes for every step of *Elements* III.36."""
    plane = compute_plane_model()
    e_pt = tuple(plane["E"])
    b_pt = tuple(plane["B"])
    d_pt = tuple(plane["D"])
    c1 = plane["case1"]
    c2 = plane["case2"]

    c1_a = tuple(c1["A"])
    c1_c = tuple(c1["C"])
    c1_z = tuple(c1["F"])  # Heiberg Case 1 center Ζ (= E)

    c2_a = tuple(c2["A"])
    c2_c = tuple(c2["C"])
    c2_z = tuple(c2["F"])  # Heiberg Case 2 perpendicular foot Ζ

    # Keep isotropic scaling by computing uniform pixel scale centered in viewBox
    px_scale = min(
        VIEWBOX_WIDTH / (MATH_X_MAX - MATH_X_MIN),
        VIEWBOX_HEIGHT / (MATH_Y_MAX - MATH_Y_MIN),
    )
    x_mid = 0.5 * (MATH_X_MIN + MATH_X_MAX)
    y_mid = 0.5 * (MATH_Y_MIN + MATH_Y_MAX)

    def iso(pt: tuple[float, float]) -> list[float]:
        cx = VIEWBOX_WIDTH * 0.5 + (pt[0] - x_mid) * px_scale
        cy = VIEWBOX_HEIGHT * 0.5 - (pt[1] - y_mid) * px_scale
        return [round(cx, 2), round(cy, 2)]

    def iso_right_angle(
        v: tuple[float, float],
        t1: tuple[float, float],
        t2: tuple[float, float],
        size: float = 0.42,
    ) -> list[list[float]]:
        u1x, u1y = t1[0] - v[0], t1[1] - v[1]
        u2x, u2y = t2[0] - v[0], t2[1] - v[1]
        n1 = math.hypot(u1x, u1y) or 1.0
        n2 = math.hypot(u2x, u2y) or 1.0
        u1 = (u1x / n1 * size, u1y / n1 * size)
        u2 = (u2x / n2 * size, u2y / n2 * size)
        return [
            iso((v[0] + u1[0], v[1] + u1[1])),
            iso((v[0] + u1[0] + u2[0], v[1] + u1[1] + u2[1])),
            iso((v[0] + u2[0], v[1] + u2[1])),
        ]

    circle_center = iso(e_pt)
    circle_r_px = round(CIRCLE_RADIUS * px_scale, 2)

    # Exact verification of Case 1 & Case 2 invariants
    assert abs(c1["DA"] * c1["DC"] - EXPECTED_AREA) < 1e-8
    assert abs(c2["DA"] * c2["DC"] - EXPECTED_AREA) < 1e-8

    scenes = {
        "step_0_enunciation": {
            "case_title": "Πρότασις λςʹ · Enunciation (Secant & Tangent)",
            "formula_greek": "τὸ ὑπὸ ὅλης τῆς τεμνούσης καὶ τῆς ἐκτὸς = τὸ ἀπὸ τῆς ἐφαπτομένης",
            "formula_numeric": f"ΑΔ · ΔΓ = {c2['DA']:.2f} × {c2['DC']:.2f} = {EXPECTED_AREA:.2f} = ΔΒ² ({EXPECTED_DB:.0f}²)",
            "citation_badges": ["Book III Def. 2 (Tangent)", "Post. 1 & 3 (Straightedge & Divider)"],
            "circle": {"cx": circle_center[0], "cy": circle_center[1], "r": circle_r_px},
            "points": [
                {"id": "Α", "xy": iso(c2_a), "offset": [12, -10], "role": "secant"},
                {"id": "Γ", "xy": iso(c2_c), "offset": [-10, -14], "role": "secant"},
                {"id": "Β", "xy": iso(b_pt), "offset": [2, 22], "role": "tangent"},
                {"id": "Δ", "xy": iso(d_pt), "offset": [-18, 16], "role": "external"},
            ],
            "segments": [
                {"id": "ΔΓΑ", "p1": iso(d_pt), "p2": iso(c2_a), "style": "secant", "tool": "straightedge"},
                {"id": "ΔΓ", "p1": iso(d_pt), "p2": iso(c2_c), "style": "secant_outer", "tool": "straightedge"},
                {"id": "ΔΒ", "p1": iso(d_pt), "p2": iso(b_pt), "style": "tangent", "tool": "straightedge"},
            ],
            "triangles": [],
            "right_angles": [],
            "ticks": [],
        },
        "step_1_ekthesis": {
            "case_title": "Ἔκθεσις & Διορισμός · Setting-Out & Claim",
            "formula_greek": "λέγω, ὅτι τὸ ὑπὸ τῶν ΑΔ, ΔΓ ὀρθογώνιον ἴσον ἐστὶ τῷ ἀπὸ τῆς ΔΒ τετραγώνῳ",
            "formula_numeric": f"ΑΔ = {c2['DA']:.2f}, ΔΓ = {c2['DC']:.2f} → rect(ΑΔ, ΔΓ) = 16.00 = sq(ΔΒ)",
            "citation_badges": ["Circle ΑΒΓ", "Secant ΔΓΑ", "Tangent ΔΒ"],
            "circle": {"cx": circle_center[0], "cy": circle_center[1], "r": circle_r_px},
            "points": [
                {"id": "Α", "xy": iso(c2_a), "offset": [12, -10], "role": "highlight"},
                {"id": "Γ", "xy": iso(c2_c), "offset": [-10, -14], "role": "highlight"},
                {"id": "Β", "xy": iso(b_pt), "offset": [2, 22], "role": "highlight"},
                {"id": "Δ", "xy": iso(d_pt), "offset": [-18, 16], "role": "highlight"},
            ],
            "segments": [
                {"id": "ΔΓΑ", "p1": iso(d_pt), "p2": iso(c2_a), "style": "secant", "tool": "straightedge"},
                {"id": "ΔΓ", "p1": iso(d_pt), "p2": iso(c2_c), "style": "secant_outer", "tool": "straightedge"},
                {"id": "ΔΒ", "p1": iso(d_pt), "p2": iso(b_pt), "style": "tangent", "tool": "straightedge"},
            ],
            "triangles": [],
            "right_angles": [],
            "ticks": [],
        },
        "step_2_case1": {
            "case_title": "Case 1 · ΔΓΑ Through Center Ζ (Heiberg Fig. 1)",
            "formula_greek": "ΑΔ·ΔΓ + ΖΓ² = ΖΔ² (II.6) · ΖΓ = ΖΒ · ΖΔ² = ΖΒ² + ΔΒ² (I.47) ⇒ ΑΔ·ΔΓ = ΔΒ²",
            "formula_numeric": (
                f"ΑΔ·ΔΓ ({c1['DA']:.0f}×{c1['DC']:.0f}=16) + ΖΓ² (9) = ΖΔ² (25) = ΖΒ² (9) + ΔΒ² (16)"
            ),
            "citation_badges": ["III.18 (∠ΖΒΔ = 90°)", "II.6 (ΑΓ halved at Ζ)", "I.47 (△ΖΒΔ)"],
            "circle": {"cx": circle_center[0], "cy": circle_center[1], "r": circle_r_px},
            "points": [
                {"id": "Α", "xy": iso(c1_a), "offset": [12, -10], "role": "secant"},
                {"id": "Γ", "xy": iso(c1_c), "offset": [-16, -12], "role": "secant"},
                {"id": "Ζ", "xy": iso(c1_z), "offset": [-14, -14], "role": "center"},
                {"id": "Β", "xy": iso(b_pt), "offset": [2, 22], "role": "tangent"},
                {"id": "Δ", "xy": iso(d_pt), "offset": [-18, 16], "role": "external"},
            ],
            "segments": [
                {"id": "ΔΓΑ", "p1": iso(d_pt), "p2": iso(c1_a), "style": "secant", "tool": "straightedge"},
                {"id": "ΔΓ", "p1": iso(d_pt), "p2": iso(c1_c), "style": "secant_outer", "tool": "straightedge"},
                {"id": "ΔΒ", "p1": iso(d_pt), "p2": iso(b_pt), "style": "tangent", "tool": "straightedge"},
                {"id": "ΖΒ", "p1": iso(c1_z), "p2": iso(b_pt), "style": "radius", "tool": "straightedge"},
            ],
            "triangles": [
                {"id": "△ΖΒΔ", "pts": [iso(c1_z), iso(b_pt), iso(d_pt)]},
            ],
            "right_angles": [
                {"pts": iso_right_angle(b_pt, c1_z, d_pt), "label": "∠ΖΒΔ = 90°"},
            ],
            "ticks": [
                {"p1": iso(c1_z), "p2": iso(b_pt), "count": 1},
                {"p1": iso(c1_z), "p2": iso(c1_c), "count": 1},
            ],
        },
        "step_3_case2": {
            "case_title": "Case 2 · ΔΓΑ Not Through Center Ε (Heiberg Fig. 2)",
            "formula_greek": "ΑΔ·ΔΓ + ΓΖ² + ΖΕ² = ΖΔ² + ΖΕ² ⇒ ΑΔ·ΔΓ + ΕΓ² = ΕΔ² = ΕΒ² + ΔΒ² ⇒ ΑΔ·ΔΓ = ΔΒ²",
            "formula_numeric": (
                f"16.00 + ΓΖ² ({c2['FC']**2:.2f}) + ΖΕ² ({c2['EF']**2:.2f}) = "
                f"ΕΔ² ({EXPECTED_ED**2:.0f}) = ΕΒ² (9) + ΔΒ² (16)"
            ),
            "citation_badges": ["I.12 (ΕΖ ⟂ ΑΓ)", "III.3 (ΑΖ = ΖΓ)", "II.6 (+ ΖΕ²)", "3 × I.47", "III.18"],
            "circle": {"cx": circle_center[0], "cy": circle_center[1], "r": circle_r_px},
            "points": [
                {"id": "Α", "xy": iso(c2_a), "offset": [12, -10], "role": "secant"},
                {"id": "Γ", "xy": iso(c2_c), "offset": [-14, -14], "role": "secant"},
                {"id": "Ζ", "xy": iso(c2_z), "offset": [10, 18], "role": "perp"},
                {"id": "Ε", "xy": iso(e_pt), "offset": [-14, -14], "role": "center"},
                {"id": "Β", "xy": iso(b_pt), "offset": [2, 22], "role": "tangent"},
                {"id": "Δ", "xy": iso(d_pt), "offset": [-18, 16], "role": "external"},
            ],
            "segments": [
                {"id": "ΔΓΑ", "p1": iso(d_pt), "p2": iso(c2_a), "style": "secant", "tool": "straightedge"},
                {"id": "ΔΓ", "p1": iso(d_pt), "p2": iso(c2_c), "style": "secant_outer", "tool": "straightedge"},
                {"id": "ΔΒ", "p1": iso(d_pt), "p2": iso(b_pt), "style": "tangent", "tool": "straightedge"},
                {"id": "ΕΖ", "p1": iso(e_pt), "p2": iso(c2_z), "style": "perp", "tool": "straightedge"},
                {"id": "ΕΒ", "p1": iso(e_pt), "p2": iso(b_pt), "style": "radius", "tool": "straightedge"},
                {"id": "ΕΓ", "p1": iso(e_pt), "p2": iso(c2_c), "style": "radius", "tool": "straightedge"},
                {"id": "ΕΔ", "p1": iso(e_pt), "p2": iso(d_pt), "style": "hypotenuse", "tool": "straightedge"},
            ],
            "triangles": [
                {"id": "△ΕΖΓ", "pts": [iso(e_pt), iso(c2_z), iso(c2_c)]},
                {"id": "△ΕΒΔ", "pts": [iso(e_pt), iso(b_pt), iso(d_pt)]},
            ],
            "right_angles": [
                {"pts": iso_right_angle(b_pt, e_pt, d_pt), "label": "∠ΕΒΔ = 90°"},
                {"pts": iso_right_angle(c2_z, e_pt, c2_c, size=0.34), "label": "∠ΕΖΓ = 90°"},
            ],
            "ticks": [
                {"p1": iso(e_pt), "p2": iso(b_pt), "count": 1},
                {"p1": iso(e_pt), "p2": iso(c2_c), "count": 1},
                {"p1": iso(c2_a), "p2": iso(c2_z), "count": 2},
                {"p1": iso(c2_z), "p2": iso(c2_c), "count": 2},
            ],
        },
        "step_4_conclusion": {
            "case_title": "Συμπέρασμα · Conclusion (ὅπερ ἔδει δεῖξαι)",
            "formula_greek": "τὸ ὑπὸ τῶν ΑΔ, ΔΓ ἴσον ἐστὶ τῷ ἀπὸ τῆς ΔΒ τετραγώνῳ · ὅπερ ἔδει δεῖξαι",
            "formula_numeric": f"Every secant ΔΓΑ from Δ gives ΑΔ · ΔΓ = ΕΔ² − r² = {EXPECTED_AREA:.2f} = ΔΒ²",
            "citation_badges": ["Case 1 (Through Ζ)", "Case 2 (Off-Center Ε)", "ὅπερ ἔδει δεῖξαι"],
            "circle": {"cx": circle_center[0], "cy": circle_center[1], "r": circle_r_px},
            "points": [
                {"id": "Α", "xy": iso(c2_a), "offset": [12, -10], "role": "highlight"},
                {"id": "Γ", "xy": iso(c2_c), "offset": [-14, -14], "role": "highlight"},
                {"id": "Ε", "xy": iso(e_pt), "offset": [-14, -14], "role": "center"},
                {"id": "Β", "xy": iso(b_pt), "offset": [2, 22], "role": "highlight"},
                {"id": "Δ", "xy": iso(d_pt), "offset": [-18, 16], "role": "highlight"},
            ],
            "segments": [
                {"id": "ΔΓΑ", "p1": iso(d_pt), "p2": iso(c2_a), "style": "secant", "tool": "straightedge"},
                {"id": "ΔΓ", "p1": iso(d_pt), "p2": iso(c2_c), "style": "secant_outer", "tool": "straightedge"},
                {"id": "ΔΒ", "p1": iso(d_pt), "p2": iso(b_pt), "style": "tangent", "tool": "straightedge"},
                {"id": "ΕΒ", "p1": iso(e_pt), "p2": iso(b_pt), "style": "radius", "tool": "straightedge"},
            ],
            "triangles": [],
            "right_angles": [
                {"pts": iso_right_angle(b_pt, e_pt, d_pt), "label": "∠ΕΒΔ = 90°"},
            ],
            "ticks": [],
        },
    }

    return {
        "has_exact_geometry": True,
        "proposition_id": "III.36",
        "viewbox": [VIEWBOX_WIDTH, VIEWBOX_HEIGHT],
        "default_step_id": "step_0_enunciation",
        "scenes": scenes,
    }


def build_diagram_spec_for_plan(plan: PropositionPlan) -> dict[str, Any]:
    """Return the exact deterministic diagram specification for ``plan``.

    Uses exact verified 3-4-5 Heiberg Euclidean geometry for ``III.36``, and a
    graceful text-anchored step card specification for arbitrary dynamically
    planned propositions.
    """
    if plan.proposition_id == "III.36":
        return build_iii36_diagram_spec()

    fallback_scenes: dict[str, Any] = {
        "step_0_enunciation": {
            "case_title": f"Elements {plan.proposition_id} · Enunciation (Πρότασις)",
            "formula_greek": plan.enunciation_greek,
            "formula_numeric": f"Heiberg letters: {', '.join(plan.greek_letters)}",
            "citation_badges": [plan.proposition_id, "Heiberg Greek"],
        }
    }
    for step in plan.steps:
        fallback_scenes[step.id] = {
            "case_title": step.label,
            "formula_greek": step.greek_text,
            "formula_numeric": step.english_summary,
            "citation_badges": [plan.proposition_id, *plan.greek_letters[:4]],
        }
    return {
        "has_exact_geometry": False,
        "proposition_id": plan.proposition_id,
        "viewbox": [VIEWBOX_WIDTH, VIEWBOX_HEIGHT],
        "default_step_id": "step_0_enunciation",
        "scenes": fallback_scenes,
    }
