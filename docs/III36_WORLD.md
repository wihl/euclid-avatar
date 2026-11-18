# Elements III.36 · Interactive 3D Area Proof & Spherical Breakdown World

Interactive Three.js 3D virtual world, scholarly Gemini 3.8 TTS narration (`Sadaltager`), acoustic highlight cue alignment, and deterministic `1920x1080` MP4 renderer (`5:53`, under the 7-minute cap) for David Wihl's MATH E-139 Group 4 presentation on **Euclid's *Elements* Book III, Proposition 36** (`coursework/projects/2026-project-iii36/proof`).

---

## Monday Evening Presentation Runbook (Start & Stop Server)

### 1. Pre-Class Warm-Up (Run Once Before Class)

The first time `serve` runs in a fresh checkout, it caches `three.module.js` and synthesizes the 14 voiceover WAV segments into `.cache/iii36_world/` (~30 seconds). Once cached, subsequent startups take **`< 0.1 s`** and require **no internet or API access** during class.

From the repository root (`~/Projects/agy/euclid-avatar` once merged and updated):

```bash
cd ~/Projects/agy/euclid-avatar
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world check
```

---

### 2. Starting the Server

#### Option A · Foreground Terminal (Recommended for Live Class)

Keep a dedicated Terminal tab open so you can see the server status and stop it instantly with `Ctrl+C`:

```bash
cd ~/Projects/agy/euclid-avatar
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world serve --host 127.0.0.1 --port 8791
```

Then open **http://127.0.0.1:8791/** in Chrome (or Safari).

*(If port `8791` is already in use, either stop the existing process below or pass `--port 8792`.)*

#### Option B · Background Daemon

If you prefer running the server in the background without keeping a terminal occupied:

```bash
cd ~/Projects/agy/euclid-avatar
nohup env PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world serve --host 127.0.0.1 --port 8791 >/tmp/iii36_world.log 2>&1 &
```

Verify it is listening:

```bash
lsof -i tcp:8791
```

---

### 3. Stopping the Server

* **If running in a foreground terminal:** Press **`Ctrl+C`** in that terminal window.
* **If running in the background (or to free port `8791` from any terminal):**

```bash
lsof -ti tcp:8791 | xargs kill
```

*(Confirm it stopped — the following command should print nothing:)*

```bash
lsof -i tcp:8791
```

---

### 4. Presenting Live on Zoom (Quick Checklist)

1. **Share Browser Audio in Zoom:** When clicking **Share Screen** in Zoom, select your Chrome window showing `http://127.0.0.1:8791/` and check **"Share sound"** at the bottom-left of Zoom's share dialog so the class hears the synchronized narration directly.
2. **Start Playback (`5:53` total):** Click **`▶ Play Presentation`** in the bottom-left bar.
3. **Interactive Checkpoint 1 (`~0:49`, Slide 1):**
   * Playback automatically pauses with a cyan ring (`⇄ Drag A`) on **Point `A`**.
   * Drag **Point `A`** directly along the circle's circumference toward **`B`** (or slide the top-center slider) to show `C` moving and the blue `AD · DC` rectangle reshaping live while staying locked at area `16.00`.
   * Click **`▶ Continue Video`** (top-center pill or bottom-left button) to resume.
4. **Interactive Checkpoint 2 (`~3:57`, Slide 4):**
   * Playback automatically pauses with a cyan ring (`↕ Drag DF`) on **Point `F`**.
   * Drag **`F`** (or sweep line `DF`) across the chords between tangents `DB` and `DG` — including right through the centre `E` where `EF = 0` — showing `AD · DC = 16.00` stays invariant.
   * Click **`▶ Continue Video`** to resume into Slide 5 (the 2D Plane → 3D Sphere breakdown).
5. **Ad-Hoc Manipulation Anytime:** Grabbing `A` (on Slide 1), `F` (on Slide 4), or the **`2D ↔ 3D Sphere`** slider at any moment automatically pauses playback; click **`▶ Continue Video`** when ready, or **`🎥 Guided Cam`** if you orbited the 3D camera manually.

---

## Optional Offline Video Build (`1920x1080` MP4 Backup)

To render a standalone `1920x1080` MP4 (`output/iii36_world/iii36_virtual_world.mp4`) as an offline backup:

```bash
cd ~/Projects/agy/euclid-avatar
PYTHONPATH=src /opt/homebrew/bin/python3 -m euclid_avatar.iii36_world build --fps 24
```

## Running Unit & Geometry Tests

```bash
cd ~/Projects/agy/euclid-avatar
PYTHONPATH=src /opt/homebrew/bin/python3 -m unittest discover -s tests -v
```
