# Euclid in Ancient Alexandria · Genie 4 Proof of Concept (`genie4_poc`)

End-to-end Python proof of concept using Google DeepMind's **Genie 4** (`genie-4`) on the Gemini Interactions API (`v1beta`) to create a historically accurate, photorealistic interactive world of **Euclid of Alexandria (c. 300 BCE)** drawing and speaking a proposition from the *Elements* (such as **III.36**) in **Ancient Greek**.

---

## Architecture & Models Reused from `euclid-avatar`

Genie 4 (`genie-4`) is a monolithic real-time interactive world model whose `world_setup` payload accepts a text `world_prompt` and an optional 16:9 `reference_image`. Rather than replacing Genie 4's internal renderer, this POC composes `euclid-avatar`'s Gemini models around `genie-4`:

| Stage | Model | Purpose |
| --- | --- | --- |
| **1. Proposition Planning** | `gemini-3.5-flash-lite` (Interactions API JSON schema) | Reads any proposition read-only from `~/Projects/Courses/26Fall/mathe139/materials/books/Elements.pdf` and produces exact Heiberg Greek quotes + physical divider/straightedge drawing steps. *Elements* `III.36` also ships with a verified curated Heiberg plan (pp. 105–106). |
| **2. Photorealistic 16:9 Seed Frame** | `gemini-nano-banana-2.1` *(current replacement for deprecated `gemini-3.1-flash-image`; override via `--image-model`)* | Generates a 16:9 photorealistic starting frame of Euclid at a wooden sand-tray (*abax*) with a two-legged riveted bronze drafting divider (*diabētēs*, NOT magnetic) and an unmarked wooden straightedge (*kanōn*), passed to Genie 4 as `world_setup.reference_image`. |
| **3. Live Interactive World** | `genie-4` (Interactions API `v1beta`) | Streams 24 fps 16:9 video + 48 kHz stereo PCM audio over WebSockets (`record` / `run`) or WebRTC (`serve`, using ephemeral `interactions.auth_tokens.create` tokens) while accepting timed mid-session Ancient Greek drawing + speech steering prompts. |
| **4. Optional Verified Greek Narration Overlay** | `gemini-3.8-flash-tts` (`Sadaltager` / `Charon`) or `euclid_avatar.tts` (`en-AU-Chirp3-HD-Charon` Erasmian IPA, `bird-handout-and-class-2026-10-08`) | Synthesizes verified Ancient Greek audio and blends Genie 4's ambient sand-and-courtyard soundbed gently beneath it into a companion `euclid_<prop>_genie4_narrated.mp4`. |

---

## Historical Accuracy & Anti-Clutter Design

- **Instruments:** Explicitly specifies a two-legged hinged bronze drafting divider (*diabētēs* — one sharp metal pivot spike and one tapered writing/scoring leg, explicitly excluding magnetic/navigational compasses), a plain completely unmarked flat wooden straightedge (*kanōn*, zero tick marks or numbers), and a slender bronze stylus on a shallow wooden sand-tray (*abax*) filled with fine pale-ochre sand.
- **Visual realism:** Austere, natural-light 35mm documentary look in a sunlit limestone portico in Ptolemaic Alexandria (c. 300 BCE); plain undyed linen *chiton* & wool *himation*; zero museum clutter, zero neon overlays, and `"No music."`.

---

## Billing & Runtime Safety

- Genie 4 streams 24 fps video (`240` video tokens/frame = `5,760` tokens/s, approximately `~$0.10/sec` including 48 kHz stereo audio).
- `record` and `run` enforce a hard duration cap (`--duration-s <= 90`, default `24` s) and unconditionally invoke `await session.complete()` in a `finally:` block so server-side generation and billing always terminate on completion, timeout, or error.
- `serve` binds to **`127.0.0.1:8795`** (never colliding with `8787`, `8790`, or the live `iii36_world` server on `8791`), mints short-lived ephemeral auth tokens on the backend so `GEMINI_API_KEY` never reaches the browser, and sends `session.complete()` on Stop or tab unload.
- Note on wire format: Live `genie-4` WebSocket video deltas report `mime_type="video/jpeg2000"` while carrying standard JFIF JPEG bytes (`FF D8 FF`). `detect_video_frame_codec()` sniffs the real magic header bytes so FFmpeg always selects the matching decoder.

---

## Quick Start (`arm64` Homebrew Python)

Install `google-genai >= 3.2.0` in an isolated `.venv`:

```bash
uv venv --python /opt/homebrew/bin/python3 .venv
uv pip install --python .venv/bin/python -e .
```

### 1. Offline Check (No Paid API Calls)

```bash
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc check
```

### 2. Full End-to-End POC Capture (`III.36` — Seed + Live Genie 4 MP4 + Optional TTS Mix)

```bash
# Plan + 16:9 seed image + 24s live Genie 4 recording (native Greek audio):
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc run --prop III.36 --duration-s 24

# Also generate companion MP4 blended with gemini-3.8-flash-tts (Sadaltager) or Erasmian IPA:
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc run --prop III.36 --duration-s 24 --with-narration --tts-backend gemini_tts --voice Sadaltager
```

Outputs are written to `output/genie4_poc/iii36/` (gitignored):
- `seed_frame_16x9.jpg` (or `.png`, matching the image model's output format) — 16:9 photorealistic starting frame
- `prompts.md` & `prompts.json` — copy-pasteable prompt kit for `labs.google/projectgenie`
- `keyframes/` — start, per-step steering, and end frames captured from Genie 4
- `euclid_iii36_genie4.mp4` — muxed 24 fps H.264 + 48 kHz stereo AAC capture
- `session_report.json` — interaction ID, frame/audio counts, steering log, and estimated token cost

### 3. Any Other Proposition from `mathe139/materials/books/Elements.pdf`

```bash
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc run --prop II.13 --duration-s 24
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc plan --prop I.47
```

### 4. Interactive Live Browser Studio (WebRTC on Port `8795`)

```bash
PYTHONPATH=src .venv/bin/python -m euclid_avatar.genie4_poc serve --prop III.36 --port 8795
```

Open `http://127.0.0.1:8795/` in Chrome, click **Start Genie 4 World**, navigate with `W/A/S/D` + arrow keys, trigger any proof step in Ancient Greek with one click, and click **Stop & Complete** when finished.

## Unit Tests

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```
