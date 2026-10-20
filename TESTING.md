# Live Zoom Test Protocol Checklist (`TESTING.md`)

Use this step-by-step checklist to run the two-machine live Zoom verification and record the evidence for Questions 3–5 in `results.md`.

---

## Machine Roles

1. **MacBook (Euclid Host):**
   - Runs `python -m euclid_avatar serve`, OBS Studio (`OBS Virtual Camera`), `BlackHole 2ch`, and `BlackHole 16ch`.
   - Joins Zoom with Camera = `OBS Virtual Camera`, Microphone = `BlackHole 16ch`, Speaker = `Zoom + Euclid Monitor` (Multi-Output Device), **wired/USB headphones on**.
2. **Second Machine (Audience Participant):**
   - Joins the same Zoom meeting as a separate participant.
   - Views Euclid in **Speaker View** (and switches to **Gallery View** for two turns to test small-tile subtitle legibility).
   - Records its own screen and system audio using macOS Screen Recording (`⌘+Shift+5`) or OBS/QuickTime. **This recording is the primary evidence for Questions 3, 4, and 5.**

---

## Phase 1: Before Joining the Zoom Call

- [ ] **1. Install & verify virtual audio devices on the MacBook:**
  ```bash
  brew install blackhole-2ch blackhole-16ch ffmpeg
  python -m euclid_avatar devices
  ```
  Confirm both `BlackHole 2ch` and `BlackHole 16ch` show `[OK]`.
- [ ] **2. Build/verify the local MATH E-139 course index:**
  ```bash
  python -m euclid_avatar index
  ```
  Confirm `.cache/course_index.sqlite` reports `1,809` chunks across `126` files.
- [ ] **3. Configure macOS `Audio MIDI Setup` on the MacBook:**
  - Open `Audio MIDI Setup.app` and verify the Multi-Output Device **`Zoom + Euclid Monitor`** includes your **Headphones** (Primary/Master Clock, `48,000 Hz`) and **`BlackHole 2ch`** (Drift Correction checked, `48,000 Hz`).
- [ ] **4. Start the Euclid Avatar server on the MacBook:**
  ```bash
  python -m euclid_avatar serve
  ```
  - Open [`http://127.0.0.1:8765/control`](http://127.0.0.1:8765/control) in your browser on the MacBook.
  - Verify the status badge reads `Idle` and the **⚡ One-Click Canned Fallback** panel lists the 6 curated MATH E-139 responses.
- [ ] **5. Start OBS Studio & Virtual Camera BEFORE launching Zoom:**
  - Verify `OBS -> Settings -> Audio -> Advanced -> Monitoring Device` is set to **`BlackHole 16ch`**.
  - Verify Scene **`David`** contains your Webcam + Physical Mic (`Monitor and Output`).
  - Verify Scene **`Euclid`** contains the Browser Source (`http://127.0.0.1:8765/avatar`, `1920x1080`, `60 FPS`) and **no** physical mic source.
  - Click **Start Virtual Camera** in OBS.
- [ ] **6. Launch Zoom on the MacBook & verify audio/video settings:**
  - **Video:** Camera = `OBS Virtual Camera`; **uncheck** *"Mirror my video"*; **check** *"HD"* and *"Original ratio"*.
  - **Audio:** Speaker = `Zoom + Euclid Monitor`; Microphone = `BlackHole 16ch`; **uncheck** *"Automatically adjust microphone volume"*.
  - Enable *"Original sound for musicians"* in Zoom Audio Settings so the in-meeting toggle button appears in the top-left corner of the meeting window.
- [ ] **7. Join the same Zoom meeting from the Second Machine (Audience) without kicking the Host:**
  - **Important Zoom gotcha:** If you sign into the exact same Zoom account on two desktop Zoom clients, Zoom will sign out or kick the first session.
  - **Solution:** On the Second Machine, either:
    1. Open an **Incognito / Private browser window**, paste the meeting invite link, and join via the **Zoom Web Client (`Join from your browser`)** as a guest participant named `"Audience Test"`, **OR**
    2. Sign in with a second/personal Zoom account.
- [ ] **8. Prevent acoustic feedback between the two machines in one room:**
  - Put **headphones on the MacBook**.
  - On the Second Machine (Audience), **mute its physical speakers** while capturing system audio (e.g., via macOS Screen Recording `⌘+Shift+5` with system audio capture / BlackHole / headphones plugged in) and only unmute the Second Machine's microphone while asking each question.
- [ ] **9. Start Screen & System Audio Recording on the Second Machine:**
  - Confirm the Second Machine is pinned to **Speaker View** on the MacBook ("Euclid") tile and start recording.

---

## Phase 2: Live Test Sequence (12 Turns)

Ask the following 10+ questions from the Second Machine (or via the capture pipeline) and log observations:

### Block A — Zoom Noise Suppression on "Auto" + Erasmian TTS (Turns 1–3)
*Ensure "Original sound for musicians" is **OFF** (Zoom default "Auto" noise suppression active). In `/control`, select `Erasmian IPA · Google Male (en-US-Neural2-D)`.*

- [ ] **Turn 1 (Prop. I.23 Enunciation):**
  - Ask from Second Machine: *"Euclid, please state the enunciation of Book I, Proposition 23 in Greek and English."*
  - Capture (`Space`), wait for `/control` to populate and pre-synthesize Sentence 1, and click **✅ Approve & Speak (`A`)**.
- [ ] **Turn 2 (Book I Definitions — Circle & Parallel Lines):**
  - Ask: *"How do you define a circle in Definition 15 and parallel straight lines in Definition 23?"*
  - Approve and observe subtitle transitions between sentences in Speaker View.
- [ ] **Turn 3 (Postulate 5 — Parallel Postulate):**
  - Switch `/control` TTS mode to `Erasmian IPA · euclid-tts Baseline (en-US-Neural2-H)`.
  - Ask: *"State the fifth postulate in Greek and explain when two straight lines meet."*
  - Approve and compare `en-US-Neural2-H` vs `en-US-Neural2-D` under Zoom "Auto" suppression.

### Block B — Zoom "Original Sound for Musicians" ON + Erasmian & Kokoro TTS (Turns 4–6)
*Click **"Original Sound for Musicians: ON"** in the top-left of the MacBook's Zoom window.*

- [ ] **Turn 4 (Prop. I.47 Pythagorean Theorem — Erasmian with Original Sound ON):**
  - Select `Erasmian IPA · Google Male (en-US-Neural2-D)`.
  - Ask: *"State Proposition I.47, the Pythagorean theorem, in Greek and English."*
  - Note whether word-final fricatives (`/s/`, `/θ/` in `συστήσασθαι`, `ὑποτεινούσης`) are clearer with Original Sound ON vs Auto.
- [ ] **Turn 5 (Six Canonical Parts of a Proposition — Local Kokoro ONNX Erasmian):**
  - Select `Erasmian IPA · Local Kokoro Female (af_heart)` (or `am_adam`).
  - Ask: *"What are the six parts of a Euclidean proposition, and when do you end with hoper edei poiesai versus hoper edei deixai?"*
- [ ] **Turn 6 (Spherical & Hyperbolic Geometry — Gallery View Subtitle Check):**
  - On the Second Machine, switch Zoom from **Speaker View** to **Gallery View**.
  - Ask: *"Does Proposition I.23 hold in spherical geometry and in the Poincaré upper half-plane model of hyperbolic geometry from Class 5?"*
  - Verify whether the `44px` high-contrast English subtitle remains legible in Gallery View, then switch back to **Speaker View**.

### Block C — Modern Greek Pronunciation Comparison (Turns 7–8)
- [ ] **Turn 7 (Google Cloud Modern Greek `el-GR-Wavenet-B`):**
  - Select `Modern Greek · Google Wavenet (el-GR-Wavenet-B)` in `/control`.
  - Ask: *"How does Proposition I.1 construct an equilateral triangle on a given finite straight line?"*
  - Approve and compare cadence/intelligibility against Erasmian mode.
- [ ] **Turn 8 (Local macOS `Melina` Modern Greek):**
  - Select `Modern Greek · Local macOS (Melina)` in `/control`.
  - Ask: *"What is the first common notion in Book I, and what does Common Notion 8 state about the whole and the part?"*

### Block D — OBS Scene Switching ("David" <-> "Euclid") (Turns 9–10)
- [ ] **Turn 9 (Scene Switch `David` -> `Euclid` -> `David` #1):**
  - Start in OBS Scene **`David`** and speak in English for 5 seconds ("Testing David webcam and physical mic before handing over to Euclid").
  - Switch OBS to Scene **`Euclid`**, ask *"What does Proposition I.5 prove about isosceles triangles?"*, and click **Approve**.
  - When Euclid finishes speaking, switch OBS back to Scene **`David`** and speak in English.
  - Check Audience recording for: clean video cut, zero double-audio, zero echo, zero dead air.
- [ ] **Turn 10 (Scene Switch `David` -> `Euclid` -> `David` #2):**
  - Repeat the `David` -> `Euclid` -> `David` transition while asking: *"In Proposition I.12, how do you drop a perpendicular to an infinite straight line from a point not on it?"*

### Block E — Operator Controls: Discard, Regenerate, Edit, & Canned Fallback (Turns 11–12)
- [ ] **Turn 11 (Discard + Regenerate + Edit):**
  - Ask: *"Explain the nine Cayley-Klein plane geometries from Class 3."*
  - When the response appears in `/control`, click **🗑️ Discard (`Esc`)** and verify Euclid stays silent and `logs/turns.jsonl` records `"decision": "discarded"`.
  - Ask the question again, click **🔄 Regenerate (`R`)**, verify a fresh response is generated and pre-synthesized, optionally edit a word in the English box (`✏️ Re-Synthesize Edited Text`), and click **✅ Approve & Speak**.
- [ ] **Turn 12 (One-Click Canned Response Fallback):**
  - In `/control`, click **▶ Speak** next to **`Prop. I.23 Enunciation (Erasmian Master)`** in the Canned Fallback panel.
  - Verify instant (`< 10 ms`) playback of the accepted `euclid-tts` WAV master (`output/euclid-I23-erasmian.wav`) with synchronized subtitles.

---

## Phase 3: Post-Session Data Collection

1. Stop the screen recording on the Second Machine and save the `.mov` / `.mp4` file.
2. Inspect `logs/turns.jsonl` for the exact stage timings of the live turns:
   ```bash
   tail -n 20 logs/turns.jsonl | jq '{turn_id, decision, stt_ms, rag_ms, llm_ms, tts_first_sentence_ms, total_unattended_ms, post_approval_start_ms, sources}'
   ```
3. Fill in the **Live Zoom Session Measurements** table in `results.md`.
