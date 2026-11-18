"""Interactive 3D virtual world and video renderer for Euclid Elements III.36."""

from .geometry import (
    build_world_spec,
    evaluate_spherical_state,
    run_all_geometry_checks,
)

__all__ = [
    "build_world_spec",
    "evaluate_spherical_state",
    "run_all_geometry_checks",
]
