# Elements III.36 · Interactive 3D Area Proof & Spherical Breakdown World

Interactive Three.js 3D virtual world, scholarly Gemini 3.8 TTS narration (`Sadaltager`), acoustic highlight cue alignment, and deterministic `1920x1080` MP4 renderer (`5:53`, under the 7-minute cap) for David Wihl's MATH E-139 Group 4 presentation on **Euclid's *Elements* Book III, Proposition 36** (`coursework/projects/2026-project-iii36/proof`).

## Highlights

- **Real-Time Spoken Segment, Triangle, and Area Highlighting (`84` Acoustic Cues):**
  - Aligns spoken geometric letter sequences (`DB`, `AD`, `DC`, `AC`, `FB`, `FC`, `FD`, `EF`, `EC`, `ED`, `EB`, `DG`) and triangles (`△FBD`, `△EFC`, `△EFD`, `△EBD`) to the WAV waveform's amplitude envelope and breath pauses, illuminating named segments, triangles, vertices, and area slabs in bright gold as they are spoken.
- **Interactive Pause-and-Manipulate Checkpoints:**
  1. **Slide 1 (`~0:49` — Drag Point `A` Along Circumference Toward `B`):** Automatically pauses playback (and pauses immediately whenever `A` or the top-center slider is grabbed) so you can drag `A` directly along the circle circumference toward `B` while `C` and the blue `AD · DC` rectangle reshape live at constant area `16.00`, then click **`▶ Continue Video`** to resume.
  2. **Slide 4 (`~3:57` — Sweep Line `DF` Across the Circle):** Automatically pauses playback (and pauses on grab) so you can drag midpoint `F` / line `DF` across all chords between tangents `DB` and `DG` (watching `EF` vanish at `E`) while `AD · DC = 16.00` remains invariant, then click **`▶ Continue Video`** to resume.
- **Compact Diagram Framing & Zero Subtitles:** Scaled and framed comfortably above the bottom navigation bar (`WORLD_SCALE_2D = 0.305`) with zero subtitles and zero background distractions.
- **Why III.36 Fails in 3D Spherical Geometry:** Continuous 2D-Plane → 3D-Sphere transition (`tau` in `[0, 1]`) showing `∠EBD = 90.0°` (`III.18`) holding while a 4-right-angle geodesic "square" on `DB` splits wide open at its 4th corner and `AD × DC = 1.22` diverges from `DB² = 1.36`.

## Commands (`arm64` Homebrew Python)

```bash
PYTHONPATH=src /opt/homebrew/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world check
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world serve --port 8791
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world build --fps 24
```
