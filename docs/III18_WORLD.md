# Elements III.18 · 3D Euclidean-to-Spherical Virtual World

Interactive Three.js 3D virtual world, Gemini 3.8 TTS voiceover pipeline, Genie 4 seed exporter, and deterministic `1920x1080` MP4 renderer for David Wihl's MATH E-139 Group 4 presentation on **Euclid's *Elements* Book III, Proposition 18** (`coursework/projects/2026-project-iii18/diagram`).

## Features

- **Exact Mathematical Fidelity (`< 1e-9`):** Mirrors `iii18-figures.R` and `slides.qmd` across all 6 slides (`Claim`, `Steps 1–4`, and `On the sphere`), verified by `run_all_geometry_checks()` and `tests/test_iii18_world.py`.
- **Continuous 2D Plane → 3D Sphere Deformation (`tau` in `[0, 1]`):** Uses an isometric Riemannian exponential map + `SO(3)` quaternion slerp so the flat 2D Euclidean plane (`z = 0`) continuously bends into the 3D globe of radius `FC = 40°`, curving straight tangent `DE` into a great circle while preserving geodesic `∠FCD = 90.0°` at every intermediate curvature.
- **`I.16` / `I.17` Far-Foot Counterexample:** Interactive 3D visualization on the sphere showing the farther perpendicular foot `G` (`FG = 151.1°`, `∠G = 90.0°`, `FC = 40°`) where `∠FCG = 131.2°` is obtuse.
- **Synchronized Voiceover & Architectural Gallery:** Synthesizes all 18 spoken paragraphs from `slides.qmd` via `gemini-3.8-flash-tts` (`Charon`), paired with 6 illuminated slide monoliths inside a 3D Alexandrian rotunda with a 360° skybox (`gemini-3.1-flash-image`).
- **Project Genie (`Genie 4`) Seed Kit:** Exports clean `1920x1080` HUD-free seed keyframes (`output/iii18_world/genie_seeds/`) plus standalone `.wav`/`.mp3` narration for side-by-side comparison in `labs.google/projectgenie`.

## Commands (`arm64` Homebrew Python)

```bash
# 1. Verify plane, spherical, and continuous morph invariants (< 1e-9)
PYTHONPATH=src /opt/homebrew/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii18_world check

# 2. Launch the interactive 3D browser world at http://127.0.0.1:8790/
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii18_world serve --port 8790

# 3. Synthesize voiceover, export Genie 4 seed keyframes, and render 1080p MP4
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii18_world build --fps 24
```
