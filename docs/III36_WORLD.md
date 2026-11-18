# Elements III.36 · Animated 3D Area Proof & Spherical Breakdown World

Interactive Three.js 3D virtual world, scholarly Gemini 3.8 TTS narration (`Sadaltager`), and deterministic `1920x1080` MP4 renderer (`5:53`, under the 7-minute cap) for David Wihl's MATH E-139 Group 4 presentation on **Euclid's *Elements* Book III, Proposition 36** (`coursework/projects/2026-project-iii36/proof`).

## Highlights

- **Zero Subtitles & Zero Background Clutter:** Clean dark-slate studio stage (`#0b1418`) keeping 100% of visual focus on the geometric figures and animated 3D area slabs.
- **Animated Area Equivalence (`AD · DC == DB² == 16.00`):**
  1. **Slide 1 (`The Claim`):** Unit-grid `4 × 4` square on `DB` (`16.00`) beside the `7.37 × 2.17` rectangle `AD · DC` (`16.00`), followed by a continuous secant-to-tangent sweep that reshapes the blue rectangle at constant area `16.00` into `4 × 4` and slides it flush onto `DB²`.
  2. **Slide 2 (`Case 1`):** Animated 3D `II.6` gnomon (`8 × 2` folds around `FC² = 9` into `FD² = 25`), matched against `FB² (9) + DB² (16)` (`I.47` on `3-4-5` `△FBD`), lifting away `FC² = FB² = 9`.
  3. **Slide 3 (`Case 2`):** Animated `+ FE² (2.25)` addition on both sides, fusing `FC² + FE² → EC² (9)` (`△EFC`) and `FD² + FE² → ED² (25)` (`△EFD`), then cancelling `EB² (9)`.
  4. **Slide 4 (`Why F Drops Out`):** Live sweeping secant across all 5 cutting lines between tangents `DB = DG = 4`, keeping `AD · DC = ED² − r² = 16.00` invariant.
- **Why III.36 Fails in 3D Spherical Geometry (Replaces Static Dependency Slide):**
  - Continuous 2D-Plane → 3D-Sphere transition (`tau` in `[0, 1]`) separating `III.36`'s `38`-proposition closure into **Postulate-5-free** circle steps (`III.18`, `III.3`, `I.12` — `∠EBD = 90.0°` holds on the globe) vs. **Postulate-5-dependent** square steps (`Post. 5 → I.29 → I.46 → II.6, I.47`):
    1. **No Squares on a Sphere:** Laying off four equal `66.7°` geodesic sides with `90°` turns on the sphere bends inward under positive curvature so the 4th corner splits wide open.
    2. **Pythagorean Breakdown:** At `r = 30°, ED = 70°`, `cos ED = cos EB · cos DB` makes `AD × DC = 1.22` vs. `DB² = 1.36` (while `tan(AD/2)·tan(DC/2) = tan²(DB/2) = 0.434` holds).

## Commands (`arm64` Homebrew Python)

```bash
PYTHONPATH=src /opt/homebrew/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world check
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world serve --port 8791
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world build --fps 24
```
