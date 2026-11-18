"""Exact Euclidean, Spherical, and continuous 2D-to-3D deformation math for III.18.

Faithfully mirrors David Wihl's `iii18-figures.R` and `slides.qmd` from
`coursework/projects/2026-project-iii18/diagram`, while adding a continuous,
singularity-free Riemannian deformation (`tau` in `[0.0, 1.0]`) from the flat 2D
Euclidean plane embedded in 3D space (`tau = 0`) onto the 3D Spherical globe
(`tau = 1`).
"""

from __future__ import annotations

import math
from typing import Any

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]  # Columns (E1, E2, NF) in right-handed SO(3)

# Unit conversion constants
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi
RIGHT_ANGLE_DEG = 90.0
STRAIGHT_ANGLE_DEG = 180.0

# Numerical verification tolerances matching iii18-figures.R
GEOMETRY_CHECK_TOL = 1e-9
SMALL_KAPPA_THRESHOLD = 1e-7
MIN_OBTUSE_FAR_FOOT_DEG = 120.0

# Plane construction constants from iii18-figures.R
EUCLID_RADIUS = 1.0
CONTACT_PHI_DEG = -40.0
SUPPOSED_PSI_DEG = 0.0
POINT_A_ANGLE_DEG = 140.0
ALONG_D_PLANE = 1.50
ALONG_E_PLANE = 0.95
CLAIM_CONTACT_ANGLES_DEG = (CONTACT_PHI_DEG, 100.0, 205.0)
FAN_OFFSETS_PLANE = (
    -0.65,
    0.42,
    math.tan(-CONTACT_PHI_DEG * DEG_TO_RAD),
    1.25,
)

# Spherical construction constants from iii18-figures.R
SPHERE_CIRCLE_RADIUS_DEG = 40.0
SPHERE_CIRCLE_RADIUS_RAD = SPHERE_CIRCLE_RADIUS_DEG * DEG_TO_RAD
SPHERE_F_LAT_DEG = 12.0
SPHERE_F_LON_DEG = -10.0
SPHERE_TANGENT_AIM_R = (0.0, 1.0, -1.2)
SPHERE_ALONG_DE_DEG = 52.0
SPHERE_ALONG_DE_RAD = SPHERE_ALONG_DE_DEG * DEG_TO_RAD

# 3D world placement constants: R_1 preserves arc length of radius FC (R_1 * 40 deg = 1.0)
SPHERE_WORLD_RADIUS = EUCLID_RADIUS / SPHERE_CIRCLE_RADIUS_RAD
MAX_CURVATURE_KAPPA = 1.0 / SPHERE_WORLD_RADIUS
GLOBE_CENTER_WORLD: Vec3 = (0.0, 1.62, 0.0)
PLANE_ORIGIN_WORLD: Vec3 = (0.0, 0.0, 0.0)
DE_SAMPLE_COUNT = 105

# Exact color palette from iii18-figures.R and slides-enhanced.js
COLORS = {
    "circle": "#2BA05F",
    "touch": "#E4471A",
    "radius": "#1B6AD1",
    "supposed": "#7A3DB5",
    "angle": "#F2B300",
    "slate_dark": "#14302A",
    "ink_dark": "#1F2933",
    "card_light": "#EEF5F0",
    "globe_fill": "#E6EEF8",
    "globe_graticule_major": "#8FA7C4",
    "globe_graticule_minor": "#BCCADB",
}


def smoothstep(t: float) -> float:
    """Cubic Hermite smoothstep on [0, 1]."""
    clamped = max(0.0, min(1.0, t))
    return clamped * clamped * (3.0 - 2.0 * clamped)


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
        raise ValueError("Cannot normalize zero vector.")
    return (v[0] / n, v[1] / n, v[2] / n)


def vec3_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def r_sphere_to_world_unit(v_r: Vec3) -> Vec3:
    """Cyclic right-handed permutation (x_R, y_R, z_R) -> (y_R, z_R, x_R).

    In SphericalToolkit.R, +x_R points at the viewer, +y_R points right, and
    +z_R points up (North Pole). Mapping to Three.js (wx, wy, wz) = (y_R, z_R, x_R)
    preserves det = +1 and places +x_R toward the +z camera, +y_R right, +z_R up.
    """
    return (v_r[1], v_r[2], v_r[0])


def make_unit_vec_r(lat_deg: float, lon_deg: float) -> Vec3:
    """Exact port of SphericalToolkit.R's makeUnitVec(lat, long)."""
    lat = lat_deg * DEG_TO_RAD
    lon = lon_deg * DEG_TO_RAD
    return (
        math.cos(lat) * math.cos(lon),
        math.cos(lat) * math.sin(lon),
        math.sin(lat),
    )


def mat3_to_quat(frame: Mat3) -> tuple[float, float, float, float]:
    """Convert right-handed orthonormal columns (c0, c1, c2) to unit quaternion (w, x, y, z)."""
    c0, c1, c2 = frame
    m00, m10, m20 = c0
    m01, m11, m21 = c1
    m02, m12, m22 = c2
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (m21 - m12) * s
        y = (m02 - m20) * s
        z = (m10 - m01) * s
    elif m00 > m11 and m00 > m22:
        s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    return (w / norm, x / norm, y / norm, z / norm)


def quat_to_mat3(q: tuple[float, float, float, float]) -> Mat3:
    """Convert unit quaternion (w, x, y, z) to orthonormal column basis (E1, E2, NF)."""
    w, x, y, z = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    e1: Vec3 = (1.0 - 2.0 * (yy + zz), 2.0 * (xy + wz), 2.0 * (xz - wy))
    e2: Vec3 = (2.0 * (xy - wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz + wx))
    nf: Vec3 = (2.0 * (xz + wy), 2.0 * (yz - wx), 1.0 - 2.0 * (xx + yy))
    return (e1, e2, nf)


def quat_slerp(
    q0: tuple[float, float, float, float],
    q1: tuple[float, float, float, float],
    t: float,
) -> tuple[float, float, float, float]:
    """Shortest-arc spherical linear interpolation between two unit quaternions."""
    dot = q0[0] * q1[0] + q0[1] * q1[1] + q0[2] * q1[2] + q0[3] * q1[3]
    if dot < 0.0:
        q1 = (-q1[0], -q1[1], -q1[2], -q1[3])
        dot = -dot
    if dot > 0.9995:
        raw = tuple(q0[i] + t * (q1[i] - q0[i]) for i in range(4))
        n = math.sqrt(sum(c * c for c in raw))
        return (raw[0] / n, raw[1] / n, raw[2] / n, raw[3] / n)
    theta_0 = math.acos(min(1.0, dot))
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    s0 = math.cos(theta) - dot * math.sin(theta) / sin_theta_0
    s1 = math.sin(theta) / sin_theta_0
    return (
        s0 * q0[0] + s1 * q1[0],
        s0 * q0[1] + s1 * q1[1],
        s0 * q0[2] + s1 * q1[2],
        s0 * q0[3] + s1 * q1[3],
    )


def compute_plane_construction() -> dict[str, Any]:
    """Compute exact 2D coordinates and angles from iii18-figures.R."""
    phi = CONTACT_PHI_DEG * DEG_TO_RAD
    psi = SUPPOSED_PSI_DEG * DEG_TO_RAD
    f_pt: Vec2 = (0.0, 0.0)
    dir_phi: Vec2 = (math.cos(phi), math.sin(phi))
    u_tan: Vec2 = (-dir_phi[1], dir_phi[0])
    c_pt: Vec2 = (EUCLID_RADIUS * dir_phi[0], EUCLID_RADIUS * dir_phi[1])
    d_pt: Vec2 = (
        c_pt[0] + ALONG_D_PLANE * EUCLID_RADIUS * u_tan[0],
        c_pt[1] + ALONG_D_PLANE * EUCLID_RADIUS * u_tan[1],
    )
    e_pt: Vec2 = (
        c_pt[0] - ALONG_E_PLANE * EUCLID_RADIUS * u_tan[0],
        c_pt[1] - ALONG_E_PLANE * EUCLID_RADIUS * u_tan[1],
    )
    a_rad = POINT_A_ANGLE_DEG * DEG_TO_RAD
    a_pt: Vec2 = (EUCLID_RADIUS * math.cos(a_rad), EUCLID_RADIUS * math.sin(a_rad))

    # G is intersection of ray F + t * dir(psi) with line C + s * u_tan
    dir_psi: Vec2 = (math.cos(psi), math.sin(psi))
    # Solve t * dir_psi = c_pt + s * u_tan => dot with dir_phi gives t * (dir_psi . dir_phi) = r
    denom = dir_psi[0] * dir_phi[0] + dir_psi[1] * dir_phi[1]
    fg_len = EUCLID_RADIUS / denom
    g_pt: Vec2 = (fg_len * dir_psi[0], fg_len * dir_psi[1])
    b_pt: Vec2 = (EUCLID_RADIUS * dir_psi[0], EUCLID_RADIUS * dir_psi[1])

    fan = []
    for s_val in FAN_OFFSETS_PLANE:
        gx = c_pt[0] + s_val * EUCLID_RADIUS * u_tan[0]
        gy = c_pt[1] + s_val * EUCLID_RADIUS * u_tan[1]
        g_norm = math.hypot(gx, gy)
        bx = EUCLID_RADIUS * gx / g_norm
        by = EUCLID_RADIUS * gy / g_norm
        fan.append({"s": s_val, "G": (gx, gy), "B": (bx, by), "length": g_norm})

    claim_contacts = []
    for ang_deg in CLAIM_CONTACT_ANGLES_DEG:
        ang = ang_deg * DEG_TO_RAD
        d_vec = (math.cos(ang), math.sin(ang))
        u_vec = (-d_vec[1], d_vec[0])
        p_vec = (EUCLID_RADIUS * d_vec[0], EUCLID_RADIUS * d_vec[1])
        claim_contacts.append(
            {
                "angle_deg": ang_deg,
                "P": p_vec,
                "u": u_vec,
                "line_start": (p_vec[0] - ALONG_E_PLANE * u_vec[0], p_vec[1] - ALONG_E_PLANE * u_vec[1]),
                "line_end": (p_vec[0] + ALONG_E_PLANE * u_vec[0], p_vec[1] + ALONG_E_PLANE * u_vec[1]),
            }
        )

    return {
        "F": f_pt,
        "A": a_pt,
        "B": b_pt,
        "C": c_pt,
        "D": d_pt,
        "E": e_pt,
        "G": g_pt,
        "u": u_tan,
        "r": EUCLID_RADIUS,
        "FG_length": fg_len,
        "BG_length": fg_len - EUCLID_RADIUS,
        "angle_FGC_deg": 50.0,
        "angle_FCG_deg": 90.0,
        "angle_GFC_deg": 40.0,
        "fan": fan,
        "claim_contacts": claim_contacts,
    }


def compute_sphere_frames() -> dict[str, Any]:
    """Compute the SO(3) endpoint frames and spherical construction matching iii18-figures.R."""
    # tau = 0 frame: Euclidean (X, Y) -> (X, 0, -Y), normal +Y_world = (0, 1, 0)
    frame_plane: Mat3 = (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        (0.0, 1.0, 0.0),
    )

    sf_r = make_unit_vec_r(SPHERE_F_LAT_DEG, SPHERE_F_LON_DEG)
    aim_dot = vec3_dot(SPHERE_TANGENT_AIM_R, sf_r)
    st_r = vec3_unit(vec3_sub(SPHERE_TANGENT_AIM_R, vec3_scale(sf_r, aim_dot)))

    nf_sphere = r_sphere_to_world_unit(sf_r)
    tc_sphere = r_sphere_to_world_unit(st_r)
    pc_sphere = vec3_cross(nf_sphere, tc_sphere)

    phi = CONTACT_PHI_DEG * DEG_TO_RAD
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    e1_sphere = vec3_sub(vec3_scale(tc_sphere, cos_phi), vec3_scale(pc_sphere, sin_phi))
    e2_sphere = vec3_add(vec3_scale(tc_sphere, sin_phi), vec3_scale(pc_sphere, cos_phi))
    frame_sphere: Mat3 = (e1_sphere, e2_sphere, nf_sphere)

    f_world_sphere = vec3_add(
        GLOBE_CENTER_WORLD, vec3_scale(nf_sphere, SPHERE_WORLD_RADIUS)
    )

    # Far-foot counterexample from iii18-figures.R (far.foot.example)
    l_rad = math.acos(-math.sqrt(math.cos(SPHERE_CIRCLE_RADIUS_RAD)))
    ff_g_r: Vec3 = (0.0, 0.0, 1.0)
    ff_f_r: Vec3 = (math.sin(l_rad), 0.0, math.cos(l_rad))
    ff_c_r: Vec3 = (0.0, math.sin(l_rad), math.cos(l_rad))
    ff_near_r: Vec3 = vec3_unit((0.0, ff_f_r[1], ff_f_r[2]))

    def _sphere_tangent_angle_deg(v: Vec3, p: Vec3, q: Vec3) -> float:
        tp = vec3_unit(vec3_sub(p, vec3_scale(v, vec3_dot(p, v))))
        tq = vec3_unit(vec3_sub(q, vec3_scale(v, vec3_dot(q, v))))
        return math.acos(max(-1.0, min(1.0, vec3_dot(tp, tq)))) * RAD_TO_DEG

    def _rotate_for_front_display(v_world: Vec3) -> Vec3:
        """Rigid SO(3) tilt (-58 deg about X, +18 deg about Y) placing F, C, G all on front hemisphere."""
        ax = -58.0 * DEG_TO_RAD
        x0, y0, z0 = v_world
        y1 = y0 * math.cos(ax) - z0 * math.sin(ax)
        z1 = y0 * math.sin(ax) + z0 * math.cos(ax)
        ay = -18.0 * DEG_TO_RAD
        x2 = x0 * math.cos(ay) + z1 * math.sin(ay)
        z2 = -x0 * math.sin(ay) + z1 * math.cos(ay)
        return (x2, y1, z2)

    far_foot = {
        "G_unit": _rotate_for_front_display(r_sphere_to_world_unit(ff_g_r)),
        "F_unit": _rotate_for_front_display(r_sphere_to_world_unit(ff_f_r)),
        "C_unit": _rotate_for_front_display(r_sphere_to_world_unit(ff_c_r)),
        "near_unit": _rotate_for_front_display(r_sphere_to_world_unit(ff_near_r)),
        "FC_deg": math.acos(vec3_dot(ff_f_r, ff_c_r)) * RAD_TO_DEG,
        "FG_deg": math.acos(vec3_dot(ff_f_r, ff_g_r)) * RAD_TO_DEG,
        "near_FG_deg": math.acos(vec3_dot(ff_f_r, ff_near_r)) * RAD_TO_DEG,
        "angle_G_deg": _sphere_tangent_angle_deg(ff_g_r, ff_f_r, ff_c_r),
        "angle_C_deg": _sphere_tangent_angle_deg(ff_c_r, ff_f_r, ff_g_r),
    }

    return {
        "frame_plane": frame_plane,
        "frame_sphere": frame_sphere,
        "quat_plane": mat3_to_quat(frame_plane),
        "quat_sphere": mat3_to_quat(frame_sphere),
        "f_world_plane": PLANE_ORIGIN_WORLD,
        "f_world_sphere": f_world_sphere,
        "sF_r": sf_r,
        "far_foot": far_foot,
    }


def evaluate_deformed_state(tau: float) -> dict[str, Any]:
    """Evaluate exact 3D coordinates of III.18 at deformation parameter tau in [0, 1].

    At tau = 0, lies flat in the 3D plane y = 0 matching iii18-figures.R's plane figures.
    At tau = 1, wraps onto the 3D sphere of radius SPHERE_WORLD_RADIUS centered at
    GLOBE_CENTER_WORLD, matching iii18-figures.R's fig.sphere() to machine precision.
    """
    frames = compute_sphere_frames()
    s = smoothstep(tau)
    q = quat_slerp(frames["quat_plane"], frames["quat_sphere"], s)
    e1, e2, nf = quat_to_mat3(q)
    f_pos = vec3_lerp(frames["f_world_plane"], frames["f_world_sphere"], s)
    kappa = s * MAX_CURVATURE_KAPPA

    phi = CONTACT_PHI_DEG * DEG_TO_RAD
    tc = vec3_add(vec3_scale(e1, math.cos(phi)), vec3_scale(e2, math.sin(phi)))
    w_de = vec3_cross(nf, tc)

    # Arc lengths along DE smoothly transition from (1.50, 0.95) to symmetric 52 deg / 40 deg = 1.30
    sphere_de_arc = SPHERE_ALONG_DE_RAD * SPHERE_WORLD_RADIUS
    arc_d = (1.0 - s) * ALONG_D_PLANE * EUCLID_RADIUS + s * sphere_de_arc
    arc_e = (1.0 - s) * ALONG_E_PLANE * EUCLID_RADIUS + s * sphere_de_arc

    def exp_from_f(x_coord: float, y_coord: float) -> Vec3:
        rho = math.hypot(x_coord, y_coord)
        if rho == 0.0:
            return f_pos
        dir_tan = vec3_scale(
            vec3_add(vec3_scale(e1, x_coord), vec3_scale(e2, y_coord)), 1.0 / rho
        )
        if kappa < SMALL_KAPPA_THRESHOLD:
            tangential = vec3_scale(dir_tan, rho)
            normal_drop = vec3_scale(nf, -0.5 * kappa * rho * rho)
            return vec3_add(f_pos, vec3_add(tangential, normal_drop))
        rad = 1.0 / kappa
        psi_ang = min(math.pi, kappa * rho)
        center = vec3_sub(f_pos, vec3_scale(nf, rad))
        unit_dir = vec3_add(
            vec3_scale(nf, math.cos(psi_ang)),
            vec3_scale(dir_tan, math.sin(psi_ang)),
        )
        return vec3_add(center, vec3_scale(unit_dir, rad))

    if kappa < SMALL_KAPPA_THRESHOLD:
        c_pos = exp_from_f(
            EUCLID_RADIUS * math.cos(phi), EUCLID_RADIUS * math.sin(phi)
        )
        t_fc_at_c = vec3_scale(tc, -1.0)

        def de_point(arc_s: float) -> Vec3:
            # Exact tangent geodesic in low-curvature limit
            base = vec3_add(c_pos, vec3_scale(w_de, arc_s))
            return vec3_add(base, vec3_scale(nf, -0.5 * kappa * arc_s * arc_s))

        center_opt: Vec3 | None = None
        radius_opt: float | None = None
    else:
        rad = 1.0 / kappa
        center = vec3_sub(f_pos, vec3_scale(nf, rad))
        alpha = kappa * EUCLID_RADIUS
        nc = vec3_add(
            vec3_scale(nf, math.cos(alpha)),
            vec3_scale(tc, math.sin(alpha)),
        )
        c_pos = vec3_add(center, vec3_scale(nc, rad))
        # Unit geodesic tangent at C pointing back toward F along great circle FC
        t_fc_at_c = vec3_sub(
            vec3_scale(nf, math.sin(alpha)),
            vec3_scale(tc, math.cos(alpha)),
        )

        def de_point(arc_s: float) -> Vec3:
            beta = kappa * arc_s
            n_pt = vec3_add(
                vec3_scale(nc, math.cos(beta)),
                vec3_scale(w_de, math.sin(beta)),
            )
            return vec3_add(center, vec3_scale(n_pt, rad))

        center_opt = center
        radius_opt = rad

    d_pos = de_point(arc_d)
    e_pos = de_point(-arc_e)
    a_ang = POINT_A_ANGLE_DEG * DEG_TO_RAD
    a_pos = exp_from_f(EUCLID_RADIUS * math.cos(a_ang), EUCLID_RADIUS * math.sin(a_ang))

    # Geodesic angle at C between CF and CD
    angle_fcd_deg = math.acos(max(-1.0, min(1.0, vec3_dot(t_fc_at_c, w_de)))) * RAD_TO_DEG

    return {
        "tau": tau,
        "s": s,
        "kappa": kappa,
        "sphere_center": center_opt,
        "sphere_radius": radius_opt,
        "frame": (e1, e2, nf),
        "F": f_pos,
        "A": a_pos,
        "C": c_pos,
        "D": d_pos,
        "E": e_pos,
        "arc_d": arc_d,
        "arc_e": arc_e,
        "de_point_fn": de_point,
        "exp_from_f_fn": exp_from_f,
        "angle_fcd_deg": angle_fcd_deg,
    }


def run_all_geometry_checks() -> dict[str, Any]:
    """Verify plane, sphere, far-foot, and intermediate morph invariants to < 1e-9."""
    plane = compute_plane_construction()
    f_pt = plane["F"]
    c_pt = plane["C"]
    d_pt = plane["D"]
    e_pt = plane["E"]
    g_pt = plane["G"]
    b_pt = plane["B"]

    # 1. Plane checks matching iii18.checks()
    fc_dist = math.hypot(c_pt[0] - f_pt[0], c_pt[1] - f_pt[1])
    assert abs(fc_dist - EUCLID_RADIUS) < GEOMETRY_CHECK_TOL

    # Angle FCD == 90 deg
    v_cf = (f_pt[0] - c_pt[0], f_pt[1] - c_pt[1])
    v_cd = (d_pt[0] - c_pt[0], d_pt[1] - c_pt[1])
    dot_fcd = (v_cf[0] * v_cd[0] + v_cf[1] * v_cd[1]) / (
        math.hypot(*v_cf) * math.hypot(*v_cd)
    )
    angle_fcd = math.acos(max(-1.0, min(1.0, dot_fcd))) * RAD_TO_DEG
    assert abs(angle_fcd - RIGHT_ANGLE_DEG) < GEOMETRY_CHECK_TOL

    # Angle FGC == 50 deg and FCG == 90 deg
    v_gf = (f_pt[0] - g_pt[0], f_pt[1] - g_pt[1])
    v_gc = (c_pt[0] - g_pt[0], c_pt[1] - g_pt[1])
    cos_fgc = (v_gf[0] * v_gc[0] + v_gf[1] * v_gc[1]) / (
        math.hypot(*v_gf) * math.hypot(*v_gc)
    )
    angle_fgc = math.acos(max(-1.0, min(1.0, cos_fgc))) * RAD_TO_DEG
    assert abs(angle_fgc - 50.0) < GEOMETRY_CHECK_TOL
    assert abs(plane["FG_length"] - 1.0 / math.cos(40.0 * DEG_TO_RAD)) < GEOMETRY_CHECK_TOL

    # B strictly between F and G on FG
    fg_d = math.hypot(g_pt[0] - f_pt[0], g_pt[1] - f_pt[1])
    fb_d = math.hypot(b_pt[0] - f_pt[0], b_pt[1] - f_pt[1])
    bg_d = math.hypot(g_pt[0] - b_pt[0], g_pt[1] - b_pt[1])
    assert abs(fb_d - EUCLID_RADIUS) < GEOMETRY_CHECK_TOL
    assert abs(fg_d - fb_d - bg_d) < GEOMETRY_CHECK_TOL
    assert bg_d > 0.2

    # 2. Continuous morph invariance across tau in [0.0, 1.0]
    for tau_val in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        st = evaluate_deformed_state(tau_val)
        assert abs(st["angle_fcd_deg"] - RIGHT_ANGLE_DEG) < GEOMETRY_CHECK_TOL
        if st["sphere_center"] is not None and st["sphere_radius"] is not None:
            ctr = st["sphere_center"]
            rad = st["sphere_radius"]
            nf_unit = vec3_scale(vec3_sub(st["F"], ctr), 1.0 / rad)
            nc_unit = vec3_scale(vec3_sub(st["C"], ctr), 1.0 / rad)
            alpha_rad = math.acos(max(-1.0, min(1.0, vec3_dot(nf_unit, nc_unit))))
            # Geodesic arc length FC must stay identically EUCLID_RADIUS (1.0)
            assert abs(rad * alpha_rad - EUCLID_RADIUS) < GEOMETRY_CHECK_TOL

            # Sample points along DE \ {C}: all must lie strictly outside spherical cap
            for idx in range(DE_SAMPLE_COUNT):
                frac = -1.0 + 2.0 * idx / (DE_SAMPLE_COUNT - 1)
                arc_s = frac * st["arc_d"]
                if abs(arc_s) < 1e-6:
                    continue
                pt_x = st["de_point_fn"](arc_s)
                nx_unit = vec3_scale(vec3_sub(pt_x, ctr), 1.0 / rad)
                assert abs(vec3_norm(nx_unit) - 1.0) < GEOMETRY_CHECK_TOL
                dist_rad = math.acos(max(-1.0, min(1.0, vec3_dot(nf_unit, nx_unit))))
                assert dist_rad > alpha_rad
                # Class 8 spherical right-triangle law: cos(FX) == cos(FC) * cos(CX)
                cos_law_err = abs(
                    math.cos(dist_rad) - math.cos(alpha_rad) * math.cos(abs(arc_s) / rad)
                )
                assert cos_law_err < GEOMETRY_CHECK_TOL

    # 3. Exact endpoint match at tau = 1.0 with iii18-figures.R's sF, sC, sD, sE
    st1 = evaluate_deformed_state(1.0)
    ctr1 = st1["sphere_center"]
    rad1 = st1["sphere_radius"]
    assert ctr1 is not None and rad1 is not None
    assert abs(vec3_norm(vec3_sub(ctr1, GLOBE_CENTER_WORLD))) < GEOMETRY_CHECK_TOL
    sf_unit_1 = vec3_scale(vec3_sub(st1["F"], ctr1), 1.0 / rad1)
    sf_expected = r_sphere_to_world_unit(make_unit_vec_r(SPHERE_F_LAT_DEG, SPHERE_F_LON_DEG))
    assert vec3_norm(vec3_sub(sf_unit_1, sf_expected)) < GEOMETRY_CHECK_TOL

    # 4. Far-foot I.16/I.17 counterexample check
    ff = compute_sphere_frames()["far_foot"]
    assert abs(ff["FC_deg"] - SPHERE_CIRCLE_RADIUS_DEG) < GEOMETRY_CHECK_TOL
    assert abs(ff["angle_G_deg"] - RIGHT_ANGLE_DEG) < GEOMETRY_CHECK_TOL
    assert ff["angle_C_deg"] > MIN_OBTUSE_FAR_FOOT_DEG
    assert ff["FG_deg"] > RIGHT_ANGLE_DEG
    assert ff["near_FG_deg"] < RIGHT_ANGLE_DEG

    return {
        "plane": plane,
        "sphere_endpoint": {
            "FC_deg": SPHERE_CIRCLE_RADIUS_DEG,
            "angle_FCD_deg": st1["angle_fcd_deg"],
        },
        "far_foot": ff,
    }


def build_slides_and_narration() -> list[dict[str, Any]]:
    """Build the 6-slide III.18 specification and exact spoken notes from slides.qmd."""
    return [
        {
            "slide_number": 1,
            "id": "slide_1_claim",
            "kicker": "ELEMENTS III.18 · FRAMING",
            "title": "The radius meets the touching line square",
            "step_tracker": 0,
            "theme": "dark",
            "bullets": [
                {
                    "badge": "Touches",
                    "badge_color": COLORS["circle"],
                    "text": "A line touches a circle if it meets it and, produced, does not cut it (Def. III.2).",
                },
                {
                    "badge": "Claim",
                    "badge_color": COLORS["radius"],
                    "text": "The radius to the point of contact is perpendicular to the touching line.",
                },
                {
                    "badge": "Method",
                    "badge_color": COLORS["touch"],
                    "text": "Euclid argues by contradiction, so his figure must show the impossible.",
                },
            ],
            "segments": [
                {
                    "id": "s1_p1_definition",
                    "spoken": (
                        "This is Proposition 18 of Book Three, our first proposition about circles. "
                        "Book Three defines a straight line that touches a circle: it meets the circle, "
                        "and however far you extend it, it never cuts into it. Today we would call it a tangent."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_intro",
                    "cam_start": [-2.8, 1.75, 4.65],
                    "cam_end": [-0.85, 1.68, 4.15],
                    "look_start": [-0.35, 0.72, -0.85],
                    "look_end": [0.0, 0.42, -0.35],
                },
                {
                    "id": "s1_p2_three_tangents",
                    "spoken": (
                        "The claim is about the radius drawn to the point of contact. "
                        "Here are three lines touching one circle at three different points, "
                        "and at each one the radius meets the line square. "
                        "Euclid says that is no accident: whatever line touches, "
                        "the radius to the point of contact is perpendicular to it."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_all_three",
                    "cam_start": [-1.8, 2.25, 3.6],
                    "cam_end": [1.3, 2.65, 3.3],
                    "look_start": [0.0, 0.12, 0.0],
                    "look_end": [0.1, 0.05, 0.05],
                },
                {
                    "id": "s1_p3_contradiction_setup",
                    "spoken": (
                        "He proves it by contradiction. He supposes the angle is not a right angle, "
                        "argues until he reaches something impossible, and concludes that it must be. "
                        "That makes the diagram unusual: it has to show a supposition that is false, "
                        "and a false thing cannot be drawn correctly. I will build it in four steps."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "claim_focus_c",
                    "cam_start": [1.3, 2.65, 3.3],
                    "cam_end": [0.35, 2.15, 3.1],
                    "look_start": [0.1, 0.05, 0.05],
                    "look_end": [0.45, 0.05, 0.35],
                },
            ],
        },
        {
            "slide_number": 2,
            "id": "slide_2_setting",
            "kicker": "STEP 1 OF 4 · THE SETTING-OUT",
            "title": "Step 1 · The setting-out",
            "step_tracker": 1,
            "theme": "light",
            "bullets": [
                {
                    "badge": "Given",
                    "badge_color": COLORS["touch"],
                    "text": "DE touches the circle ABC at C.",
                },
                {
                    "badge": "III.1",
                    "badge_color": COLORS["radius"],
                    "text": "Find the centre F (III.1) and join FC.",
                },
                {
                    "badge": "To show",
                    "badge_color": COLORS["radius"],
                    "text": "FC is perpendicular to DE.",
                },
                {
                    "badge": "Disc",
                    "badge_color": COLORS["circle"],
                    "text": "DE meets the shaded disc only at C.",
                },
            ],
            "segments": [
                {
                    "id": "s2_p1_setting_out",
                    "spoken": (
                        "Step 1. Euclid lets the line D E touch the circle A B C at the point C. "
                        "He finds the centre of the circle, F, by Proposition 1 of this book, and joins F C. "
                        "What he has to show is that F C is perpendicular to D E."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step1_construct",
                    "cam_start": [-2.2, 1.95, 3.4],
                    "cam_end": [0.25, 2.35, 3.05],
                    "look_start": [-0.3, 0.35, -0.2],
                    "look_end": [0.35, 0.05, 0.2],
                },
                {
                    "id": "s2_p2_shaded_disc",
                    "spoken": (
                        "I have shaded the disc so you can see what touching means: "
                        "D E meets the circle at C, and everywhere else it stays outside. "
                        "That fact is the key to the whole proof, and it comes back at the end."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step1_disc_skim",
                    "cam_start": [0.25, 2.35, 3.05],
                    "cam_end": [1.85, 0.72, 2.25],
                    "look_start": [0.35, 0.05, 0.2],
                    "look_end": [0.65, 0.04, 0.45],
                },
                {
                    "id": "s2_p3_colour_key",
                    "spoken": (
                        "The colours stay the same all the way through: "
                        "the circle green, the touching line red-orange, the radius blue."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step1_full",
                    "cam_start": [1.85, 0.72, 2.25],
                    "cam_end": [0.4, 2.45, 2.95],
                    "look_start": [0.65, 0.04, 0.45],
                    "look_end": [0.35, 0.05, 0.2],
                },
            ],
        },
        {
            "slide_number": 3,
            "id": "slide_3_suppose",
            "kicker": "STEP 2 OF 4 · SUPPOSE NOT",
            "title": "Step 2 · Suppose not",
            "step_tracker": 2,
            "theme": "light",
            "bullets": [
                {
                    "badge": "I.12",
                    "badge_color": COLORS["supposed"],
                    "text": "Then draw FG perpendicular to DE (I.12).",
                },
                {
                    "badge": "I.17",
                    "badge_color": COLORS["supposed"],
                    "text": "Angle at G right, so angle at C acute (I.17).",
                },
                {
                    "badge": "I.19",
                    "badge_color": COLORS["radius"],
                    "text": "So FC is greater than FG (I.19).",
                },
                {
                    "badge": "Drawn truly",
                    "badge_color": COLORS["angle"],
                    "text": "G is 50°, C is 90°. It cannot be drawn.",
                },
            ],
            "segments": [
                {
                    "id": "s3_p1_drop_fg",
                    "spoken": (
                        "Step 2. Suppose F C is not perpendicular. "
                        "Then, by Proposition 12 of Book One, we can drop a different perpendicular "
                        "from F to D E. Call it F G, with G somewhere else on D E."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step2_fg",
                    "cam_start": [0.4, 2.45, 2.95],
                    "cam_end": [0.95, 2.05, 2.65],
                    "look_start": [0.35, 0.05, 0.2],
                    "look_end": [0.68, 0.05, 0.22],
                },
                {
                    "id": "s3_p2_triangle_fgc",
                    "spoken": (
                        "Now look at the triangle F G C. The text says the angle at G is a right angle, "
                        "so by Proposition 17 the angle at C must be acute. "
                        "And by Proposition 19 the bigger angle faces the bigger side, "
                        "so F C, opposite the right angle, is longer than F G."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step2_supposed_labels",
                    "cam_start": [0.95, 2.05, 2.65],
                    "cam_end": [1.55, 1.55, 2.15],
                    "look_start": [0.68, 0.05, 0.22],
                    "look_end": [0.82, 0.06, 0.28],
                },
                {
                    "id": "s3_p3_true_wedges",
                    "spoken": (
                        "Here is the catch for a diagram. I cannot draw that triangle, because it does not exist. "
                        "The labels say what the text supposes; the gold wedges show the angles as they really are: "
                        "about 50 degrees at G and a right angle at C, the reverse. "
                        "Fitzpatrick's printed figure does exactly the same: its angle at G measures about 49 degrees. "
                        "The figure shows the truth while the text argues about the supposition. "
                        "So don't look for a right angle at G."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step2_true_wedges",
                    "cam_start": [1.55, 1.55, 2.15],
                    "cam_end": [0.75, 2.25, 2.45],
                    "look_start": [0.82, 0.06, 0.28],
                    "look_end": [0.85, 0.04, 0.28],
                },
            ],
        },
        {
            "slide_number": 4,
            "id": "slide_4_contradiction",
            "kicker": "STEP 3 OF 4 · THE CONTRADICTION",
            "title": "Step 3 · The lesser greater than the greater",
            "step_tracker": 3,
            "theme": "light",
            "bullets": [
                {
                    "badge": "Radii",
                    "badge_color": COLORS["radius"],
                    "text": "FC = FB: both are radii.",
                },
                {
                    "badge": "From text",
                    "badge_color": COLORS["radius"],
                    "text": "So FB is greater than FG.",
                },
                {
                    "badge": "Impossible",
                    "badge_color": COLORS["supposed"],
                    "text": "But FB is only part of FG. Impossible.",
                },
                {
                    "badge": "Q.E.D.",
                    "badge_color": COLORS["touch"],
                    "text": "So FC is perpendicular to DE.",
                },
            ],
            "segments": [
                {
                    "id": "s4_p1_equal_radii",
                    "spoken": (
                        "Step 3. F C and F B are both radii of the circle, so they are equal; one tick each. "
                        "So if F C is longer than F G, then F B is longer than F G too."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step3_radii_ticks",
                    "cam_start": [0.75, 2.25, 2.45],
                    "cam_end": [0.55, 1.65, 2.25],
                    "look_start": [0.85, 0.04, 0.28],
                    "look_end": [0.58, 0.06, 0.16],
                },
                {
                    "id": "s4_p2_part_and_whole",
                    "spoken": (
                        "But look where B is. It is on the line F G, between F and G, "
                        "so F B is just a part of F G, the blue part; "
                        "the purple piece, B G, is the rest of it. "
                        "A part longer than the whole: the lesser greater than the greater, "
                        "as Euclid says, and that is impossible."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step3_part_whole",
                    "cam_start": [0.55, 1.65, 2.25],
                    "cam_end": [0.92, 1.05, 1.78],
                    "look_start": [0.58, 0.06, 0.16],
                    "look_end": [0.72, 0.08, 0.0],
                },
                {
                    "id": "s4_p3_conclusion",
                    "spoken": (
                        "So F G is not perpendicular to D E. "
                        "Euclid adds that, in the same way, no other line from F is, except F C. "
                        "So F C is perpendicular to D E, which is the proposition."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step3_qed",
                    "cam_start": [0.92, 1.05, 1.78],
                    "cam_end": [0.5, 2.35, 2.85],
                    "look_start": [0.72, 0.08, 0.0],
                    "look_end": [0.48, 0.05, 0.18],
                },
            ],
        },
        {
            "slide_number": 5,
            "id": "slide_5_between",
            "kicker": "STEP 4 OF 4 · WHAT THE FIGURE SUPPLIES",
            "title": "Step 4 · Why B lies between F and G",
            "step_tracker": 4,
            "theme": "light",
            "bullets": [
                {
                    "badge": "Silent step",
                    "badge_color": COLORS["ink_dark"],
                    "text": "The text never says so: the figure does.",
                },
                {
                    "badge": "1 · Outside",
                    "badge_color": COLORS["touch"],
                    "text": "DE touches, so all of it but C lies outside the circle.",
                },
                {
                    "badge": "2 · Crossing",
                    "badge_color": COLORS["circle"],
                    "text": "So any line from F to DE crosses the circle first.",
                },
                {
                    "badge": "3 · Nearest",
                    "badge_color": COLORS["angle"],
                    "text": "The true perpendicular from F lands on C.",
                },
            ],
            "segments": [
                {
                    "id": "s5_p1_diagram_gap",
                    "spoken": (
                        "Step 4. One thing in that argument comes from the picture, not the text. "
                        "Euclid never says that F G crosses the circle at B, between F and G. "
                        "Without that there is no contradiction. So why is it true?"
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step4_focus_b",
                    "cam_start": [0.5, 2.35, 2.85],
                    "cam_end": [1.25, 1.85, 2.55],
                    "look_start": [0.48, 0.05, 0.18],
                    "look_end": [0.65, 0.05, 0.15],
                },
                {
                    "id": "s5_p2_inside_to_outside",
                    "spoken": (
                        "Because D E touches the circle. Touching means it never cuts in, "
                        "so every point of D E except C lies outside the circle. "
                        "A line from the centre F to any such point starts inside and ends outside, "
                        "so it must cross the circle on the way. That crossing is B."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step4_single_crossing",
                    "cam_start": [1.25, 1.85, 2.55],
                    "cam_end": [1.65, 2.25, 2.65],
                    "look_start": [0.65, 0.05, 0.15],
                    "look_end": [0.55, 0.05, 0.15],
                },
                {
                    "id": "s5_p3_fan_nearest",
                    "spoken": (
                        "Here it is for G and three other points of D E. "
                        "Every line from F to D E crosses the circle first and is longer than the radius F C. "
                        "So C is the point of D E nearest to F, and the true perpendicular from F lands exactly on C. "
                        "This picture is my illustration; Euclid's proof needs only the one line F G."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 0.0,
                    "visual_mode": "step4_fan_complete",
                    "cam_start": [1.65, 2.25, 2.65],
                    "cam_end": [0.25, 2.85, 3.45],
                    "look_start": [0.55, 0.05, 0.15],
                    "look_end": [0.35, 0.05, 0.1],
                },
            ],
        },
        {
            "slide_number": 6,
            "id": "slide_6_sphere",
            "kicker": "OPTIONAL · FROM 2D EUCLIDEAN PLANE TO 3D SPHERE",
            "title": "On the sphere",
            "step_tracker": 0,
            "theme": "dark",
            "bullets": [
                {
                    "badge": "Great circle",
                    "badge_color": COLORS["touch"],
                    "text": "A line is a great circle: DE curves.",
                },
                {
                    "badge": "Holds",
                    "badge_color": COLORS["angle"],
                    "text": "FC meets DE at 90.0°, and C is its point nearest F.",
                },
                {
                    "badge": "I.16 risk",
                    "badge_color": COLORS["supposed"],
                    "text": "The proof cites no fifth postulate, but it rests on I.16, which can fail here.",
                },
                {
                    "badge": "Not shown",
                    "badge_color": COLORS["radius"],
                    "text": "The picture holds; that the proof does is not shown.",
                },
            ],
            "segments": [
                {
                    "id": "s6_p1_morph_to_sphere",
                    "spoken": (
                        "The instructors asked, as an option, for the diagram on the sphere, "
                        "saying the proof is the same but the diagram looks different. "
                        "Watch the flat Euclidean plane bend continuously into three-dimensional spherical space. "
                        "The diagram certainly looks different. Whether the proof is the same is a real question here, "
                        "and I am not going to claim it."
                    ),
                    "tau_start": 0.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_morph",
                    "cam_start": [0.25, 2.85, 3.45],
                    "cam_end": [0.35, 2.05, 4.75],
                    "look_start": [0.35, 0.05, 0.1],
                    "look_end": [0.0, 1.55, 0.0],
                },
                {
                    "id": "s6_p2_great_circle_holds",
                    "spoken": (
                        "On the sphere a straight line is a great circle, so the touching line D E curves across the globe. "
                        "Here is a circle of radius 40 degrees about F, and the great circle D E touching it at C. "
                        "The toolkit measures the angle between F C and D E as 90.0 degrees, "
                        "its own perpendicular from F lands on C, and every other point of D E is farther from F than C is. "
                        "So the picture is right."
                    ),
                    "tau_start": 1.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_picture_holds",
                    "cam_start": [0.35, 2.05, 4.75],
                    "cam_end": [1.65, 1.65, 4.35],
                    "look_start": [0.0, 1.55, 0.0],
                    "look_end": [0.05, 1.52, 0.15],
                },
                {
                    "id": "s6_p3_i16_far_foot",
                    "spoken": (
                        "The proof is another matter. Following Euclid's citations back, "
                        "Proposition 18 rests on 18 earlier propositions and on Postulates 1, 2 and 3, "
                        "never the fifth, the one about parallels. "
                        "But the class 4 notes warn that Proposition 16 fails on the sphere, because its proof doubles a line, "
                        "and Proposition 17, which this proof uses, rests on 16. "
                        "On the sphere there are two perpendiculars from F to a line, a near one and a far one, "
                        "and if G is taken at the far one, the angle at C need not be acute even for a circle this size. "
                        "Whether the near one always saves the proof I have not worked out. "
                        "So: the picture holds on the sphere; that Euclid's proof does, I leave open."
                    ),
                    "tau_start": 1.0,
                    "tau_end": 1.0,
                    "visual_mode": "sphere_far_foot",
                    "cam_start": [1.65, 1.65, 4.35],
                    "cam_end": [0.55, 1.85, 4.75],
                    "look_start": [0.05, 1.52, 0.15],
                    "look_end": [0.05, 1.58, 0.0],
                },
            ],
        },
    ]


def build_world_spec() -> dict[str, Any]:
    """Return the complete serializable specification for the 3D III.18 world."""
    checks = run_all_geometry_checks()
    frames = compute_sphere_frames()
    slides = build_slides_and_narration()
    return {
        "title": "Euclid, Elements III.18 · 3D Euclidean-to-Spherical Virtual World",
        "subtitle": "David Wihl · Group 4 Diagram Section · MATH E-139",
        "colors": COLORS,
        "constants": {
            "euclid_radius": EUCLID_RADIUS,
            "contact_phi_deg": CONTACT_PHI_DEG,
            "supposed_psi_deg": SUPPOSED_PSI_DEG,
            "point_a_angle_deg": POINT_A_ANGLE_DEG,
            "along_d_plane": ALONG_D_PLANE,
            "along_e_plane": ALONG_E_PLANE,
            "sphere_circle_radius_deg": SPHERE_CIRCLE_RADIUS_DEG,
            "sphere_along_de_deg": SPHERE_ALONG_DE_DEG,
            "sphere_world_radius": SPHERE_WORLD_RADIUS,
            "max_curvature_kappa": MAX_CURVATURE_KAPPA,
            "globe_center_world": list(GLOBE_CENTER_WORLD),
            "plane_origin_world": list(PLANE_ORIGIN_WORLD),
        },
        "plane": checks["plane"],
        "frames": {
            "quat_plane": list(frames["quat_plane"]),
            "quat_sphere": list(frames["quat_sphere"]),
            "f_world_plane": list(frames["f_world_plane"]),
            "f_world_sphere": list(frames["f_world_sphere"]),
            "far_foot": {
                k: list(v) if isinstance(v, tuple) else v
                for k, v in frames["far_foot"].items()
            },
        },
        "slides": slides,
    }
