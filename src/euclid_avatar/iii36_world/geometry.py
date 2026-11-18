"""Exact Euclidean, Area-Dissection, and 2D-to-3D Spherical Failure math for III.36.

Faithfully mirrors David Wihl's `iii36-proof.R` and `slides.qmd` from
`coursework/projects/2026-project-iii36/proof`, adding:
1. Exact geometric decompositions for the animated `AD · DC == DB^2` area match
   (continuous secant-to-tangent area-preserving sweep, Case 1 II.6 gnomon + I.47
   cancellation, and Case 2 `+ FE^2` Pythagorean bridge).
2. Continuous 2D-Euclidean-to-3D-Spherical deformation (`tau` in `[0, 1]`) showing
   both *why* squares break on a sphere (geodesic 4-right-angle non-closure from
   positive curvature / absence of Postulate 5) and *why* `AD * DC != DB^2`
   (`1.22` vs `1.36` at `r = 30 deg, ED = 70 deg`) while `tan(AD/2)tan(DC/2) = tan^2(DB/2)`
   holds identically.
"""

from __future__ import annotations

import math
from typing import Any

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

# Unit conversion & tolerance constants
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
RIGHT_ANGLE_DEG = 90.0
GEOMETRY_CHECK_TOL = 1e-8
SMALL_TAU_THRESHOLD = 1e-5

# Exact Euclidean construction constants from iii36-proof.R (3-4-5 right triangle EBD)
CENTRE_E: Vec2 = (0.0, 0.0)
CIRCLE_RADIUS = 3.0
POINT_B: Vec2 = (0.0, -3.0)
POINT_D: Vec2 = (-4.0, -3.0)
CASE2_OFFSET_BELOW_E = 1.5
FAN_EXPLICIT_ANGLES_DEG = (8.0, 50.0, 64.0)
EXPECTED_AREA = 16.0
EXPECTED_ED = 5.0
EXPECTED_DB = 4.0
CLOSURE_PROPOSITION_COUNT = 38

# 3D world scale (compact so the entire diagram sits well above bottom navigation)
WORLD_SCALE_2D = 0.305

# Exact spherical failure constants from iii36-proof.R (s.r = 30 deg, s.d = 70 deg)
SPHERE_RADIUS_DEG = 30.0
SPHERE_DIST_ED_DEG = 70.0
SPHERE_RADIUS_RAD = SPHERE_RADIUS_DEG * DEG_TO_RAD
SPHERE_DIST_ED_RAD = SPHERE_DIST_ED_DEG * DEG_TO_RAD
SPHERE_WORLD_RADIUS = 1.34
GLOBE_CENTER_WORLD: Vec3 = (0.16, 1.58, 0.0)

# Colour palette from iii36-proof.R
COLORS = {
    "circle": "#2BA05F",
    "tangent": "#E4471A",
    "secant": "#1B6AD1",
    "radius": "#7A3DB5",
    "perp": "#C98A00",
    "mark": "#F2B300",
    "ed_line": "#D8E2E8",
    "studio_bg": "#0b1418",
    "slate_stage": "#132227",
}


def smoothstep(t: float) -> float:
    clamped = max(0.0, min(1.0, t))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def dist2d(p: Vec2, q: Vec2) -> float:
    return math.hypot(q[0] - p[0], q[1] - p[1])


def vec3_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec3_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec3_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def vec3_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec3_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec3_norm(v: Vec3) -> float:
    return math.sqrt(vec3_dot(v, v))


def vec3_unit(v: Vec3) -> Vec3:
    n = vec3_norm(v)
    if n == 0.0:
        raise ValueError("Zero vector cannot be normalized.")
    return (v[0] / n, v[1] / n, v[2] / n)


def cut_line(theta_rad: float) -> dict[str, Any]:
    """Exact port of iii36-proof.R's cut.line(theta) from D = (-4, -3) across circle (E, 3)."""
    ux = math.cos(theta_rad)
    uy = math.sin(theta_rad)
    dx = CENTRE_E[0] - POINT_D[0]
    dy = CENTRE_E[1] - POINT_D[1]
    fd_len = dx * ux + dy * uy
    f_pt: Vec2 = (POINT_D[0] + fd_len * ux, POINT_D[1] + fd_len * uy)
    ef_sq = max(0.0, (dx * dx + dy * dy) - fd_len * fd_len)
    ef_len = math.sqrt(ef_sq)
    half_chord = math.sqrt(max(0.0, CIRCLE_RADIUS * CIRCLE_RADIUS - ef_sq))
    dc_len = fd_len - half_chord
    da_len = fd_len + half_chord
    c_pt: Vec2 = (POINT_D[0] + dc_len * ux, POINT_D[1] + dc_len * uy)
    a_pt: Vec2 = (POINT_D[0] + da_len * ux, POINT_D[1] + da_len * uy)
    return {
        "theta_rad": theta_rad,
        "theta_deg": theta_rad * RAD_TO_DEG,
        "C": c_pt,
        "A": a_pt,
        "F": f_pt,
        "DC": dc_len,
        "DA": da_len,
        "FC": half_chord,
        "FD": fd_len,
        "EF": ef_len,
        "area_rect": da_len * dc_len,
    }


def compute_plane_model() -> dict[str, Any]:
    """Compute all exact 2D figures, lengths, areas, and dependency metadata for III.36."""
    theta_centre = math.atan2(
        CENTRE_E[1] - POINT_D[1], CENTRE_E[0] - POINT_D[0]
    )
    ed_len = dist2d(CENTRE_E, POINT_D)
    db_len = dist2d(POINT_D, POINT_B)
    theta_case2 = theta_centre - math.asin(CASE2_OFFSET_BELOW_E / ed_len)

    case1 = cut_line(theta_centre)
    case2 = cut_line(theta_case2)

    # Mirror B across line DE for second tangent point G
    u_de = ((CENTRE_E[0] - POINT_D[0]) / ed_len, (CENTRE_E[1] - POINT_D[1]) / ed_len)
    bx_rel = POINT_B[0] - POINT_D[0]
    by_rel = POINT_B[1] - POINT_D[1]
    proj = bx_rel * u_de[0] + by_rel * u_de[1]
    point_g: Vec2 = (
        POINT_D[0] + 2.0 * proj * u_de[0] - bx_rel,
        POINT_D[1] + 2.0 * proj * u_de[1] - by_rel,
    )

    fan_thetas = sorted(
        [
            FAN_EXPLICIT_ANGLES_DEG[0] * DEG_TO_RAD,
            theta_case2,
            theta_centre,
            FAN_EXPLICIT_ANGLES_DEG[1] * DEG_TO_RAD,
            FAN_EXPLICIT_ANGLES_DEG[2] * DEG_TO_RAD,
        ]
    )
    fan = [cut_line(th) for th in fan_thetas]

    # Claim figure shapes matching claim.shapes() in iii36-proof.R
    square_on_db = [
        list(POINT_D),
        list(POINT_B),
        [POINT_B[0], POINT_B[1] - db_len],
        [POINT_D[0], POINT_D[1] - db_len],
    ]
    rect_x0 = CENTRE_E[0] + CIRCLE_RADIUS + 1.4
    rect_y0 = CENTRE_E[1] + CIRCLE_RADIUS
    rectangle_ad_dc = [
        [rect_x0, rect_y0],
        [rect_x0 + case2["DC"], rect_y0],
        [rect_x0 + case2["DC"], rect_y0 - case2["DA"]],
        [rect_x0, rect_y0 - case2["DA"]],
    ]

    dependencies = {
        "closure_size": CLOSURE_PROPOSITION_COUNT,
        "curvature_safe": ["III.18", "III.3", "I.12"],
        "postulate_5_bound": ["II.6", "I.47", "I.46", "I.29", "Post. 5"],
    }

    return {
        "E": list(CENTRE_E),
        "B": list(POINT_B),
        "D": list(POINT_D),
        "G": list(point_g),
        "r": CIRCLE_RADIUS,
        "DB": db_len,
        "ED": ed_len,
        "theta_centre_rad": theta_centre,
        "theta_case2_rad": theta_case2,
        "case1": {
            k: list(v) if isinstance(v, tuple) else v for k, v in case1.items()
        },
        "case2": {
            k: list(v) if isinstance(v, tuple) else v for k, v in case2.items()
        },
        "fan": [
            {k: list(v) if isinstance(v, tuple) else v for k, v in f.items()}
            for f in fan
        ],
        "square_on_db": square_on_db,
        "rectangle_ad_dc": rectangle_ad_dc,
        "dependencies": dependencies,
    }


def _geodesic_step_on_unit_sphere(
    p_unit: Vec3, tangent_unit: Vec3, angle_rad: float
) -> tuple[Vec3, Vec3]:
    """Advance along a unit-sphere great circle by angle_rad; return (new_pos, new_forward_tangent)."""
    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)
    next_p = vec3_add(vec3_scale(p_unit, ca), vec3_scale(tangent_unit, sa))
    next_t = vec3_sub(vec3_scale(tangent_unit, ca), vec3_scale(p_unit, sa))
    return vec3_unit(next_p), vec3_unit(next_t)


def evaluate_spherical_state(tau: float) -> dict[str, Any]:
    """Evaluate III.36 across continuous curvature parameter tau in [0, 1].

    At tau = 0: Flat Euclidean limit (AD * DC == DB^2 == 16.0, attempted square closes
    with zero corner gap).
    At tau = 1: Exact unit-sphere counterexample from iii36-proof.R (circle radius 30 deg,
    ED = 70 deg, DC = 40 deg, DA = 100 deg, DB = 66.74 deg, AD * DC = 1.2185 != DB^2 = 1.3568,
    while tan(AD/2) * tan(DC/2) == tan(DB/2)^2 == 0.433763, and an attempted 4-right-angle
    geodesic 'square' on DB visibly fails to close on the sphere).
    """
    s = smoothstep(tau)
    if s < SMALL_TAU_THRESHOLD:
        return {
            "tau": tau,
            "s": s,
            "alpha_r_rad": 0.0,
            "alpha_d_rad": 0.0,
            "DC_val": 2.0,
            "DA_val": 8.0,
            "DB_val": 4.0,
            "rect_product": EXPECTED_AREA,
            "tangent_square": EXPECTED_AREA,
            "ratio_sq_over_prod": 1.0,
            "tan_half_lhs": 0.0,
            "tan_half_rhs": 0.0,
            "square_corner_gap_unit": 0.0,
            "angle_ebd_deg": RIGHT_ANGLE_DEG,
        }

    alpha_r = s * SPHERE_RADIUS_RAD
    ratio_d_over_r = (1.0 - s) * (EXPECTED_ED / CIRCLE_RADIUS) + s * (
        SPHERE_DIST_ED_DEG / SPHERE_RADIUS_DEG
    )
    alpha_d = ratio_d_over_r * alpha_r
    alpha_dc = alpha_d - alpha_r
    alpha_da = alpha_d + alpha_r
    # Exact spherical right-triangle rule: cos(ED) = cos(EB) * cos(DB)
    cos_db = max(-1.0, min(1.0, math.cos(alpha_d) / math.cos(alpha_r)))
    alpha_db = math.acos(cos_db)

    # Scale smoothly from Euclid units (at tau -> 0: R_eff = 3 / alpha_r) to radians on unit sphere (R_eff = 1 at tau = 1)
    r_eff = (1.0 - s) * (CIRCLE_RADIUS / alpha_r) + s * 1.0
    dc_val = r_eff * alpha_dc
    da_val = r_eff * alpha_da
    db_val = r_eff * alpha_db
    rect_prod = da_val * dc_val
    tan_sq_val = db_val * db_val

    tan_lhs = math.tan(0.5 * alpha_da) * math.tan(0.5 * alpha_dc)
    tan_rhs = math.tan(0.5 * alpha_db) ** 2

    # Construct E, D, B on the unit sphere and trace a 3-right-angle geodesic path of side alpha_db
    # Place E at (+cos 18 deg, 0, ...) style front frame; in canonical unit coords:
    e_u: Vec3 = (0.0, 0.0, 1.0)
    d_u: Vec3 = (-math.sin(alpha_d), 0.0, math.cos(alpha_d))
    # B lies at distance alpha_r from E and alpha_db from D (southern tangent):
    # e_u . b_u = cos(alpha_r) => bz = cos(alpha_r)
    # d_u . b_u = -sin(alpha_d)*bx + cos(alpha_d)*cos(alpha_r) = cos(alpha_db)
    bz = math.cos(alpha_r)
    bx = (math.cos(alpha_d) * bz - math.cos(alpha_db)) / math.sin(alpha_d)
    by = -math.sqrt(max(0.0, 1.0 - bx * bx - bz * bz))
    b_u: Vec3 = vec3_unit((bx, by, bz))

    # Verify right angle EBD == 90 deg
    t_be = vec3_unit(vec3_sub(e_u, vec3_scale(b_u, vec3_dot(e_u, b_u))))
    t_bd = vec3_unit(vec3_sub(d_u, vec3_scale(b_u, vec3_dot(d_u, b_u))))
    angle_ebd_deg = math.acos(max(-1.0, min(1.0, vec3_dot(t_be, t_bd)))) * RAD_TO_DEG

    # Attempted geodesic "square" on DB:
    # Start at D->B (side 1 of arc alpha_db), turn 90 deg outward (away from E) at B -> P2,
    # turn 90 deg back toward D's meridian at P2 -> P3; compare P3 against P4 (90 deg outward from D of arc alpha_db)!
    t_db_at_d = vec3_unit(vec3_sub(b_u, vec3_scale(d_u, vec3_dot(b_u, d_u))))
    _, t_db_at_b = _geodesic_step_on_unit_sphere(d_u, t_db_at_d, alpha_db)
    # Outward normal in tangent plane at B (opposite t_be, which points inward to E!)
    out_at_b = vec3_scale(t_be, -1.0)
    p2_u, t_b_to_p2_end = _geodesic_step_on_unit_sphere(b_u, out_at_b, alpha_db)
    # Turn 90 deg toward D side at P2:
    left_at_p2 = vec3_unit(vec3_cross(p2_u, t_b_to_p2_end))
    # Ensure left_at_p2 points toward D (negative x)
    if vec3_dot(left_at_p2, d_u) < vec3_dot(vec3_scale(left_at_p2, -1.0), d_u):
        left_at_p2 = vec3_scale(left_at_p2, -1.0)
    p3_u, _ = _geodesic_step_on_unit_sphere(p2_u, left_at_p2, alpha_db)

    # Outward 90 deg at D from DB (away from circle):
    out_at_d = vec3_unit(vec3_cross(t_db_at_d, d_u))
    if out_at_d[1] > 0.0:
        out_at_d = vec3_scale(out_at_d, -1.0)
    p4_u, _ = _geodesic_step_on_unit_sphere(d_u, out_at_d, alpha_db)

    corner_gap = vec3_norm(vec3_sub(p3_u, p4_u)) / max(alpha_db, 1e-6)

    return {
        "tau": tau,
        "s": s,
        "alpha_r_rad": alpha_r,
        "alpha_d_rad": alpha_d,
        "DC_val": dc_val,
        "DA_val": da_val,
        "DB_val": db_val,
        "rect_product": rect_prod,
        "tangent_square": tan_sq_val,
        "ratio_sq_over_prod": tan_sq_val / rect_prod,
        "tan_half_lhs": tan_lhs,
        "tan_half_rhs": tan_rhs,
        "square_corner_gap_unit": corner_gap,
        "angle_ebd_deg": angle_ebd_deg,
    }


def run_all_geometry_checks() -> dict[str, Any]:
    """Run exhaustive plane, area, dependency, and spherical failure checks (< 1e-8)."""
    model = compute_plane_model()
    assert abs(model["DB"] - EXPECTED_DB) < GEOMETRY_CHECK_TOL
    assert abs(model["ED"] - EXPECTED_ED) < GEOMETRY_CHECK_TOL

    # Check Case 1, Case 2, and all 5 fan secants
    c1 = model["case1"]
    c2 = model["case2"]
    assert abs(c1["DC"] - 2.0) < GEOMETRY_CHECK_TOL
    assert abs(c1["DA"] - 8.0) < GEOMETRY_CHECK_TOL
    assert abs(c1["EF"]) < GEOMETRY_CHECK_TOL
    assert abs(c2["EF"] - CASE2_OFFSET_BELOW_E) < GEOMETRY_CHECK_TOL

    for sec in [c1, c2, *model["fan"]]:
        # III.3 midpoint check, II.6 check, I.47 checks, and III.36 area equality
        assert abs(dist2d(tuple(sec["A"]), tuple(sec["F"])) - sec["FC"]) < GEOMETRY_CHECK_TOL
        assert abs(sec["DA"] * sec["DC"] + sec["FC"] ** 2 - sec["FD"] ** 2) < GEOMETRY_CHECK_TOL
        assert abs(sec["FC"] ** 2 + sec["EF"] ** 2 - CIRCLE_RADIUS ** 2) < GEOMETRY_CHECK_TOL
        assert abs(sec["FD"] ** 2 + sec["EF"] ** 2 - EXPECTED_ED ** 2) < GEOMETRY_CHECK_TOL
        assert abs(sec["area_rect"] - EXPECTED_AREA) < GEOMETRY_CHECK_TOL

    # Check continuous 2D -> 3D spherical transition
    st0 = evaluate_spherical_state(0.0)
    assert abs(st0["rect_product"] - st0["tangent_square"]) < GEOMETRY_CHECK_TOL
    assert abs(st0["square_corner_gap_unit"]) < GEOMETRY_CHECK_TOL

    for tau_val in (0.2, 0.5, 0.8, 1.0):
        st = evaluate_spherical_state(tau_val)
        # III.18 (tangent perpendicular to radius) STILL holds at every curvature!
        assert abs(st["angle_ebd_deg"] - RIGHT_ANGLE_DEG) < 1e-6
        # Plain length product STRICTLY fails (DB^2 > AD * DC) at every positive curvature!
        assert st["tangent_square"] > st["rect_product"]
        # Half-tangent spherical law holds identically!
        assert abs(st["tan_half_lhs"] - st["tan_half_rhs"]) < GEOMETRY_CHECK_TOL
        # Geodesic 4-right-angle "square" fails to close on curved sphere!
        assert st["square_corner_gap_unit"] > 1e-3

    st1 = evaluate_spherical_state(1.0)
    assert abs(st1["DC_val"] - 40.0 * DEG_TO_RAD) < GEOMETRY_CHECK_TOL
    assert abs(st1["DA_val"] - 100.0 * DEG_TO_RAD) < GEOMETRY_CHECK_TOL
    assert st1["tangent_square"] - st1["rect_product"] > 0.13
    assert st1["square_corner_gap_unit"] > 0.5

    return {"plane": model, "sphere_endpoint": st1}


def build_slides_and_narration() -> list[dict[str, Any]]:
    """Build the 5-slide III.36 specification and concise scholarly script (< 7 min)."""
    return [
        {
            "slide_number": 1,
            "id": "slide_1_claim",
            "kicker": "ELEMENTS III.36 · THE CLAIM",
            "title": "III.36 · A rectangle equal to a square",
            "bullets": [
                {
                    "badge": "Setup",
                    "badge_color": COLORS["circle"],
                    "text": "From D outside the circle, DB touches it and DCA cuts it.",
                },
                {
                    "badge": "Claim",
                    "badge_color": COLORS["tangent"],
                    "text": "The rectangle contained by AD and DC equals the square on DB.",
                },
                {
                    "badge": "Areas",
                    "badge_color": COLORS["secant"],
                    "text": "Shorthand: AD·DC and DB² are geometric areas (both 16 here).",
                },
            ],
            "segments": [
                {
                    "id": "s1_p1_enunciation",
                    "spoken": (
                        "This is Proposition 36 of Book Three, and my part is why it is true. "
                        "Take a point D outside a circle, and draw two straight lines from it. "
                        "One, D B, touches the circle at B; it is a tangent, as in Proposition 18. "
                        "The other cuts the circle, first at C and then at A. "
                        "Euclid's claim is that the rectangle contained by the whole line A D "
                        "and its outside piece D C equals the square on the tangent D B."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_setup",
                    "cam_start": [0.25, 4.35, 5.45],
                    "cam_end": [0.38, 4.15, 5.20],
                    "look_start": [0.30, 0.0, 0.85],
                    "look_end": [0.36, 0.0, 0.88],
                },
                {
                    "id": "s1_p2_scale_areas",
                    "spoken": (
                        "Here are both figures drawn to the exact same unit grid: "
                        "the red-orange square built on D B, of side 4 and area 16, "
                        "and the blue rectangle beside the circle, with long side A D about 7.37 "
                        "and short side D C about 2.17 — again an area of 16."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_grid_compare",
                    "cam_start": [0.38, 4.15, 5.20],
                    "cam_end": [0.65, 4.05, 5.10],
                    "look_start": [0.36, 0.0, 0.88],
                    "look_end": [0.44, 0.0, 0.90],
                },
                {
                    "id": "s1_p3_area_morph",
                    "spoken": (
                        "Watch how their areas match: as the cutting line swings down toward the tangent, "
                        "A D shortens while D C widens at constant area 16, reshaping the blue rectangle "
                        "into a 4-by-4 square that lands flush on the square on D B. "
                        "Euclid never multiplies lengths — he adds and subtracts areas across two cases: "
                        "first a line through the centre, then any other."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_morph_overlay",
                    "interactive_mode": "drag_point_a",
                    "cam_start": [0.65, 4.05, 5.10],
                    "cam_end": [0.15, 4.10, 5.15],
                    "look_start": [0.44, 0.0, 0.90],
                    "look_end": [0.12, 0.0, 0.88],
                },
            ],
        },
        {
            "slide_number": 2,
            "id": "slide_2_case1",
            "kicker": "CASE 1 OF 2 · THROUGH THE CENTRE",
            "title": "Case 1 · The line through the centre",
            "bullets": [
                {
                    "badge": "III.18",
                    "badge_color": COLORS["mark"],
                    "text": "F is the centre, so FB meets DB at right angles (III.18).",
                },
                {
                    "badge": "II.6",
                    "badge_color": COLORS["secant"],
                    "text": "AC is halved at F and CD added, so AD·DC + FC² = FD² (II.6).",
                },
                {
                    "badge": "I.47",
                    "badge_color": COLORS["radius"],
                    "text": "FC = FB, and FD² = FB² + DB² (I.47). Subtract FB²: AD·DC = DB².",
                },
            ],
            "segments": [
                {
                    "id": "s2_p1_right_triangle",
                    "spoken": (
                        "First the simpler case, where the cutting line passes straight through the centre, F. "
                        "Join F B to the point of contact. By Proposition 18, the radius F B meets the tangent D B "
                        "at right angles, forming the shaded 3-4-5 right triangle F B D."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case1_triangle",
                    "cam_start": [0.15, 4.00, 5.10],
                    "cam_end": [-0.10, 3.65, 4.65],
                    "look_start": [0.15, 0.0, 0.72],
                    "look_end": [0.22, 0.0, 0.55],
                },
                {
                    "id": "s2_p2_ii6_gnomon",
                    "spoken": (
                        "The engine of the proof is Book Two, Proposition 6. "
                        "The diameter A C is halved at F, and D C is added in a straight line. "
                        "Watch the 8-by-2 blue rectangle fold into an L-shaped gnomon of area 16 "
                        "around the purple 3-by-3 square on F C, completing the 5-by-5 square on F D, of area 25."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case1_gnomon",
                    "cam_start": [-0.10, 3.65, 4.65],
                    "cam_end": [0.65, 3.85, 4.85],
                    "look_start": [0.22, 0.0, 0.55],
                    "look_end": [0.46, 0.0, 0.58],
                },
                {
                    "id": "s2_p3_i47_cancel",
                    "spoken": (
                        "Now compare the two decompositions of that 25-unit square on F D. "
                        "F C equals F B, both radii of length 3. By Pythagoras in triangle F B D, "
                        "the square on F D also equals the purple radius square on F B plus the red-orange square on D B. "
                        "Lift away the equal radius squares of area 9 from both sides, "
                        "and the blue rectangle equals the square on the tangent."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case1_cancel",
                    "cam_start": [0.65, 3.85, 4.85],
                    "cam_end": [0.45, 3.95, 5.00],
                    "look_start": [0.46, 0.0, 0.58],
                    "look_end": [0.44, 0.0, 0.65],
                },
            ],
        },
        {
            "slide_number": 3,
            "id": "slide_3_case2",
            "kicker": "CASE 2 OF 2 · GENERAL CUTTING LINE",
            "title": "Case 2 · A line not through the centre",
            "bullets": [
                {
                    "badge": "III.3",
                    "badge_color": COLORS["perp"],
                    "text": "Centre E: drop EF ⊥ AC (I.12); it halves chord AC at F (III.3).",
                },
                {
                    "badge": "+ FE²",
                    "badge_color": COLORS["perp"],
                    "text": "Start from AD·DC + FC² = FD² (II.6) and add FE² to both sides.",
                },
                {
                    "badge": "3 × I.47",
                    "badge_color": COLORS["radius"],
                    "text": "By I.47 twice, AD·DC + EC² = ED² = EB² + DB². Subtract EB².",
                },
            ],
            "segments": [
                {
                    "id": "s3_p1_drop_ef",
                    "spoken": (
                        "Now the general case, where the centre is E and the cutting line passes below it. "
                        "Drop the gold perpendicular E F to the chord by Book One, Proposition 12. "
                        "By Book Three, Proposition 3, a perpendicular from the centre bisects the chord, "
                        "so F is again the midpoint of A C. Proposition 6 of Book Two applies just as before: "
                        "the rectangle A D by D C, plus the square on F C, equals the square on F D."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case2_drop_perp",
                    "cam_start": [0.45, 3.95, 5.00],
                    "cam_end": [0.18, 3.60, 4.55],
                    "look_start": [0.44, 0.0, 0.65],
                    "look_end": [0.22, 0.0, 0.52],
                },
                {
                    "id": "s3_p2_add_fe2",
                    "spoken": (
                        "Here is the one new move: add the gold square on F E to both sides. "
                        "On the left, the squares on F C and F E fuse by Pythagoras in right triangle E F C "
                        "into the purple radius square on E C, of area 9. "
                        "On the right, the squares on F D and F E fuse by Pythagoras in triangle E F D "
                        "into the 25-unit square on the dashed line E D."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case2_add_fe2",
                    "cam_start": [0.18, 3.60, 4.55],
                    "cam_end": [0.78, 3.85, 4.85],
                    "look_start": [0.22, 0.0, 0.52],
                    "look_end": [0.52, 0.0, 0.58],
                },
                {
                    "id": "s3_p3_finish_case2",
                    "spoken": (
                        "From there it is Case 1 again. E C equals E B, both radii, "
                        "and the angle at B is right by Proposition 18, so the square on E D equals "
                        "the square on E B plus the square on D B. "
                        "Remove the equal purple radius squares from both sides, "
                        "and once again the blue rectangle A D by D C equals the square on D B."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "case2_cancel",
                    "cam_start": [0.78, 3.85, 4.85],
                    "cam_end": [0.45, 3.95, 5.05],
                    "look_start": [0.52, 0.0, 0.58],
                    "look_end": [0.36, 0.0, 0.72],
                },
            ],
        },
        {
            "slide_number": 4,
            "id": "slide_4_fan",
            "kicker": "INVARIANCE · POWER OF THE POINT D",
            "title": "Why it works · F drops out",
            "bullets": [
                {
                    "badge": "Invariant",
                    "badge_color": COLORS["secant"],
                    "text": "Every cutting line gives AD·DC + r² = ED² = DB² + r².",
                },
                {
                    "badge": "5 Secants",
                    "badge_color": COLORS["perp"],
                    "text": "Adding FE² eliminates the moving foot F; both tangents DB and DG are equal.",
                },
                {
                    "badge": "Two cases",
                    "badge_color": COLORS["radius"],
                    "text": "Through E there is no perpendicular to drop (I.12): Euclid has no zero length.",
                },
            ],
            "segments": [
                {
                    "id": "s4_p1_invariant",
                    "spoken": (
                        "Step back and look at why both cases worked. "
                        "Adding the square on F E replaced distances from the moving foot F "
                        "with distances from the fixed centre E. "
                        "Every cutting line satisfies the same balance: the rectangle plus a radius squared "
                        "equals E D squared — and so does the tangent square plus a radius squared."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "fan_overview",
                    "cam_start": [0.45, 3.95, 5.05],
                    "cam_end": [0.28, 4.10, 5.20],
                    "look_start": [0.36, 0.0, 0.78],
                    "look_end": [0.32, 0.0, 0.78],
                },
                {
                    "id": "s4_p2_sweep",
                    "spoken": (
                        "Watch five cutting lines sweep between the two tangents D B and D G. "
                        "Each chord has a different midpoint F, and the blue rectangle beside the circle "
                        "stretches and widens, yet its area stays locked at 16 every single time — "
                        "while symmetry gives D G equal to D B. "
                        "And why did Euclid need two cases? Because Proposition 12 only drops a perpendicular "
                        "from a point not on the line; through E there is no segment F E of length zero."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "fan_sweep",
                    "interactive_mode": "sweep_line_df",
                    "cam_start": [0.28, 4.10, 5.20],
                    "cam_end": [0.40, 4.15, 5.25],
                    "look_start": [0.32, 0.0, 0.78],
                    "look_end": [0.32, 0.0, 0.78],
                },
            ],
        },
        {
            "slide_number": 5,
            "id": "slide_5_sphere_failure",
            "kicker": "2D PLANE → 3D SPHERE · WHY III.36 BREAKS",
            "title": "Why III.36 fails in 3D spherical geometry",
            "bullets": [
                {
                    "badge": "Holds (Green)",
                    "badge_color": COLORS["circle"],
                    "text": "III.18, III.3, and I.12 need no Postulate 5: ∠EBD = 90° still holds.",
                },
                {
                    "badge": "No Squares",
                    "badge_color": COLORS["tangent"],
                    "text": "Postulate 5 enters via I.29 → I.46: a 4-right-angle 'square' splits open on a sphere.",
                },
                {
                    "badge": "I.47 Fails",
                    "badge_color": COLORS["secant"],
                    "text": "At r = 30°, ED = 70°: AD×DC = 1.22 ≠ DB² = 1.36 (becomes tan ½AD · tan ½DC = tan² ½DB).",
                },
            ],
            "segments": [
                {
                    "id": "s5_p1_morph_and_post5",
                    "spoken": (
                        "Finally, what happens if we bend the flat Euclidean plane into three-dimensional "
                        "spherical space, as we did for Proposition 18? This time, the proposition breaks — "
                        "and tracing Euclid's 38 underlying propositions shows exactly why. "
                        "The circle and perpendicular steps — Propositions 18, 3, and I.12 — never touch "
                        "the Parallel Postulate, so on the globe the radius E B still meets the tangent great circle D B "
                        "at an exact right angle."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_morph_fracture",
                    "cam_start": [0.40, 4.15, 5.25],
                    "cam_end": [0.35, 2.25, 5.05],
                    "look_start": [0.32, 0.0, 0.78],
                    "look_end": [0.18, 1.36, 0.0],
                },
                {
                    "id": "s5_p2_broken_square",
                    "spoken": (
                        "Postulate 5 enters exclusively through Book Two, Proposition 6 and Pythagoras — "
                        "because both construct Euclidean squares via Proposition 46 of Book One. "
                        "Watch what happens when we lay off four equal geodesic sides with 90-degree turns on the sphere: "
                        "positive curvature bends the sides inward so the fourth corner splits wide open. "
                        "Because every spherical triangle's angles exceed 180 degrees, a four-right-angle square cannot exist."
                    ),
                    "tau_start": 1.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_broken_square",
                    "cam_start": [0.35, 2.25, 5.05],
                    "cam_end": [-0.85, 1.55, 4.85],
                    "look_start": [0.18, 1.36, 0.0],
                    "look_end": [0.08, 1.28, 0.15],
                },
                {
                    "id": "s5_p3_numbers_diverge",
                    "spoken": (
                        "Even if we replace areas by multiplied arc lengths, Pythagoras fails on the sphere: "
                        "a right triangle obeys cosine E D equals cosine E B times cosine D B. "
                        "For a 30-degree circle with D 70 degrees from the centre, A D times D C is 1.22, "
                        "whereas D B squared is 1.36 — a clear mismatch shown on the right. "
                        "Only a curved half-tangent formula survives, proving Proposition 36 is Euclidean to its core."
                    ),
                    "tau_start": 1.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_product_mismatch",
                    "cam_start": [-0.85, 1.55, 4.85],
                    "cam_end": [0.50, 2.05, 4.95],
                    "look_start": [0.08, 1.28, 0.15],
                    "look_end": [0.22, 1.36, 0.0],
                },
            ],
        },
    ]


def build_world_spec() -> dict[str, Any]:
    """Return complete JSON-serializable world specification for Elements III.36."""
    checks = run_all_geometry_checks()
    return {
        "title": "Euclid, Elements III.36 · Animated Area Proof & 3D Spherical Breakdown",
        "subtitle": "David Wihl · Group 4 Proof & Logic Section · MATH E-139",
        "colors": COLORS,
        "constants": {
            "world_scale_2d": WORLD_SCALE_2D,
            "circle_radius": CIRCLE_RADIUS,
            "expected_db": EXPECTED_DB,
            "expected_ed": EXPECTED_ED,
            "expected_area": EXPECTED_AREA,
            "sphere_radius_deg": SPHERE_RADIUS_DEG,
            "sphere_dist_ed_deg": SPHERE_DIST_ED_DEG,
            "sphere_world_radius": SPHERE_WORLD_RADIUS,
            "globe_center_world": list(GLOBE_CENTER_WORLD),
        },
        "plane": checks["plane"],
        "sphere_endpoint": checks["sphere_endpoint"],
        "slides": build_slides_and_narration(),
    }
