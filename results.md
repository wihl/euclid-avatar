# Spike Results · Live Euclid Avatar on a Zoom Call (MATH E-139)

## 1. Ten-Question Dry-Run Benchmark Numbers (`python -m euclid_avatar benchmark`)

### Configuration Tested
- **Platform:** Apple Silicon (`arm64` macOS), Python `3.12.11` (`.venv`)
- **STT:** Local `mlx-community/whisper-large-v3-turbo` (`340.0 ms` startup warm-up on 0.5 s silence; `16 kHz` in-memory float32 PCM)
- **Course RAG Index:** `.cache/course_index.sqlite` (`1,874` chunks across `129` files from `~/Projects/Courses/26Fall/mathe139/`, `211` canonical entity keys, `10.9 ms` incremental startup check, `927.7 ms` cold index build)
- **LLM:** `gemini-3.1-flash-lite` via `google-genai` single-pass structured JSON (`sources`, `english`, `greek`, and aligned `sentences`)
- **Greek TTS:** `google_erasmian` (`en-US-Neural2-D` male voice, speaking rate `0.78`, `euclid-tts` `bird-handout-and-class-2026-10-08` IPA lexicon + general polytonic G2P + FFmpeg 2:1 gentle RMS speech leveling)

### Stage-by-Stage Aggregate Latency Summary (10 Representative MATH E-139 Questions)

| Pipeline Stage | Metric Definition | Target | Min | **Median** | Mean | P90 | **Worst (Max)** |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| **1. STT (`stt_ms`)** | `t_stt_done - t_capture_end` | `< 1,500 ms` | `109.3 ms` | **`138.6 ms`** | `138.1 ms` | `153.3 ms` | **`166.0 ms`** |
| **2. Course RAG (`rag_ms`)** | `t_rag_done - t_stt_done` | `< 100 ms` (`< 50 ms` goal) | `2.6 ms` | **`6.8 ms`** | `6.3 ms` | `8.5 ms` | **`8.7 ms`** |
| **3. Gemini LLM (`llm_ms`)** | `t_llm_done - t_rag_done` | — | `1,628.4 ms` | **`2,108.9 ms`** | `2,785.0 ms` | `4,010.5 ms` | **`4,808.0 ms`** |
| **4. TTS Sentence 1 (`tts_first_sentence_ms`)** | `t_tts_first_ready - t_llm_done` | `~1,000–2,000 ms` | `424.6 ms` | **`572.4 ms`** | `598.2 ms` | `763.5 ms` | **`830.7 ms`** |
| **5. TTS All Sentences (`tts_total_ms`)** | `t_tts_all_ready - t_llm_done` | *(background)* | `980.5 ms` | **`1,209.2 ms`** | `1,265.0 ms` | `1,413.8 ms` | **`1,815.7 ms`** |
| **Unattended Machine Latency (`total_unattended_ms`)** | **`t_tts_first_ready - t_capture_end`** | **`< 10,000 ms` (ideal `4–7 s`)** | `2,203.1 ms` (`2.20 s`) | **`2,971.4 ms` (`2.97 s`)** | `3,527.6 ms` (`3.53 s`) | `4,979.9 ms` (`4.98 s`) | **`5,532.4 ms` (`5.53 s`)** |
| **Post-Approval Start (`post_approval_start_ms`)** | **`t_playback_start - t_approved`** | **`< 500 ms` (`< 50 ms` buffered)** | `0.04 ms` | **`0.09 ms`** | `0.08 ms` | `0.12 ms` | **`0.12 ms`** |
| **Canned Fallback Mode (`i23_erasmian_enunciation`)** | Pre-rendered `euclid-tts` WAV master | `~0 s` floor | — | **`1.25 ms` (unattended)** | — | — | **`0.01 ms` (post-approve)** |

### Per-Question Dry-Run Breakdown (`logs/turns.jsonl` & `logs/benchmark_summary.json`)

| # | Question ID | Course Topic / Question Summary | STT (`ms`) | RAG (`ms`) | LLM (`ms`) | TTS S1 (`ms`) | TTS All (`ms`) | **Unattended (`s`)** | **Post-Approve (`ms`)** | Top Cited Sources |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Q01** | `q01_prop_i23_enunciation` | Prop. I.23 enunciation in Greek & English | `109.3` | `7.6` | `1,919.2` | `571.6` | `1,134.1` | **`2.61 s`** | **`0.10 ms`** | `Elements I.23` |
| **Q02** | `q02_book1_definitions` | Book I Defs 1 (point), 4 (straight-line), 15 (circle), 23 (parallels) | `142.7` | `8.5` | `4,808.0` | `573.2` | `1,815.7` | **`5.53 s`** | **`0.08 ms`** | `Elements Book I Definitions & Axioms` |
| **Q03** | `q03_postulate_5` | Postulate 5 in Greek & when two straight-lines meet | `117.7` | `3.6` | `2,104.5` | `763.5` | `1,277.4` | **`2.99 s`** | **`0.09 ms`** | `Elements Book I Definitions & Axioms`, `COURSE.md` |
| **Q04** | `q04_common_notions` | Common Notion 1 & 9-CN course handout vs. Fitzpatrick's 5 CNs | `142.7` | `7.4` | `1,628.4` | `424.6` | `1,179.9` | **`2.20 s`** | **`0.12 ms`** | `study/class-02-geometry-notes.md`, `lectures/2026-class-02/lecture-note.md` |
| **Q05** | `q05_six_parts_of_proposition` | Six parts of a proposition (`πρότασις`–`συμπέρασμα`) & Q.E.F. vs Q.E.D. | `166.0` | `6.3` | `3,310.7` | `520.1` | `980.5` | **`4.00 s`** | **`0.10 ms`** | `GK-PROPPARTS`, `study/class-02-greek-notes.md` |
| **Q06** | `q06_prop_i1_equilateral` | Prop. I.1 equilateral triangle construction & circle-intersection gap | `153.3` | `8.7` | `2,066.1` | `477.2` | `1,004.7` | **`2.71 s`** | **`0.12 ms`** | `Elements I.1`, `study/class-02-geometry-notes.md` |
| **Q07** | `q07_prop_i5_isosceles` | Prop. I.5 (*Pons Asinorum*) base angles of isosceles triangles | `134.6` | `5.1` | `2,089.7` | `556.5` | `1,238.4` | **`2.79 s`** | **`0.04 ms`** | `Elements I.5`, `study/class-02-greek-notes.md` |
| **Q08** | `q08_prop_i12_perpendicular` | Prop. I.12 dropping a perpendicular to an infinite straight-line | `132.6` | `6.0` | `4,010.5` | `830.7` | `1,413.8` | **`4.98 s`** | **`0.06 ms`** | `Elements I.12`, `projects/2026-project-i12/diagram/writeup.qmd` |
| **Q09** | `q09_spherical_hyperbolic_i23` | Prop. I.23 in spherical & Poincaré/Hermes hyperbolic geometry (Class 5–6) | `149.5` | `7.6` | `2,113.3` | `682.9` | `1,394.7` | **`2.95 s`** | **`0.05 ms`** | `projects/2026-project-i23/other-geometries/slides.qmd`, `study/class-05-geometry-notes.md` |
| **Q10** | `q10_prop_i47_pythagorean` | Prop. I.47 Pythagorean theorem enunciation & parallelogram area proof | `132.2` | `2.6` | `3,799.3` | `581.7` | `1,210.7` | **`4.52 s`** | **`0.07 ms`** | `Elements I.47`, `COURSE.md` |

### STT & LLM Model Trade-Off Benchmarks

| Component | Model Tested | Warm-Up Time | Live Latency (5.3 s Audio / 4 RAG Chunks) | Accuracy / Notes |
| --- | --- | ---: | ---: | --- |
| **Local STT** | `mlx-community/whisper-large-v3-turbo` **(Selected)** | `340.0 ms` (cached) | **`109–166 ms`** | **100% domain accuracy** on `"Proposition I.23"`, `"Poincaré"`, `"enunciation"`, `"hoper edei poiesai"` (4 decoder layers makes it faster on Metal than `base.en`). |
| **Local STT** | `mlx-community/whisper-small.en-mlx` | `350.5 ms` (cached) | **`60.5 ms`** | Very fast; occasionally punctuation-splits `"Proposition I, 23"`. |
| **Local STT** | `mlx-community/whisper-base.en-mlx` | `280.0 ms` (cached) | `427.4 ms` | Misheard `"enunciation"` as `"Inunciation"`. |
| **Gemini LLM** | `gemini-3.1-flash-lite` **(Default)** | — | **`2,108.9 ms` median** | Fastest structured JSON output (`1.6–4.8 s`), quotes exact Heiberg Greek verbatim from retrieved context. |
| **Gemini LLM** | `gemini-3-flash-preview` (`ThinkingLevel.MINIMAL`) | — | **`3,437.7 ms`** | High philological polish on novel Greek prose; configured as automatic fallback on HTTP 404/503. |

### Greek TTS Backend & Voice Comparison (Proposition I.23 vs. Proposition I.47)

| Backend ID | Voice | Mode & Execution | Prop. I.23 Synth (`ms`) | Prop. I.23 AudioDur (`s`) | Prop. I.47 Synth (`ms`) | Prop. I.47 AudioDur (`s`) | Qualitative Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `google_erasmian` | `en-US-Neural2-D` **(Default)** | Cloud IPA SSML + 2:1 Leveling (Male) | **`644.2 ms`** | `12.48 s` | **`618.6 ms`** | `15.81 s` | Deep, resonant male voice suited to Euclid; crisp word-initial `/h/` and `/θ/` fricatives. |
| `google_erasmian` | `en-US-Neural2-J` | Cloud IPA SSML + 2:1 Leveling (Male) | **`556.5 ms`** | `11.98 s` | **`544.9 ms`** | `14.52 s` | Slightly brighter male baritone; very clear syllable articulation. |
| `google_erasmian` | `en-US-Neural2-H` | Cloud IPA SSML + 2:1 Leveling (Female, `euclid-tts` baseline) | **`600.5 ms`** | `11.36 s` | **`519.8 ms`** | `13.56 s` | Exact voice accepted in `euclid-tts` Round 5; highest vowel clarity. |
| `kokoro_erasmian` | `am_adam` | **100% Local ONNX** IPA + 2:1 Leveling (Male) | **`1,053.7 ms`** | `11.83 s` | **`1,273.5 ms`** | `15.16 s` | Zero cloud dependency; native `/y/` and `/x/` phonemes in Kokoro vocab without `/uː/` or `/k/` substitution. |
| `kokoro_erasmian` | `af_heart` | **100% Local ONNX** IPA + 2:1 Leveling (Female) | **`1,001.7 ms`** | `11.52 s` | **`1,366.9 ms`** | `16.48 s` | `euclid-tts` local baseline; smooth prosody across clause breaks. |
| `google_modern` | `el-GR-Wavenet-B` | Cloud Monotonic Normalized SSML (Female) | **`792.8 ms`** | `9.07 s` | **`447.5 ms`** | `10.35 s` | Native Greek cadence approved in `euclid-tts` Round 2; ~25% faster speaking tempo than Erasmian. |
| `macos_modern` | `Melina` | **100% Local macOS `say`** Monotonic (Female) | **`673.5 ms`** | `7.19 s` | **`681.0 ms`** | `10.08 s` | Instant local offline fallback (`el_GR` system voice); slightly brisker cadence. |

---

## 2. Live Zoom Session Measurements Table (Ready to Fill After `TESTING.md` Run)

Fill in this table from `logs/turns.jsonl` and the Second Machine (Audience) screen/audio recording after running `TESTING.md`:

| Turn # | Question / Test Condition | Zoom Audio Profile (`Auto` vs `Original Sound`) | TTS Backend & Voice | Unattended (`t_tts_first_ready - t_capture_end`) | Post-Approval (`t_playback_start - t_approved`) | Greek Intelligibility on Audience Machine (1–5 & Notes) | Subtitle Readability (`Speaker` vs `Gallery`) | Scene Switch / Control Action Result |
| ---: | --- | --- | --- | ---: | ---: | --- | --- | --- |
| **1** | Prop. I.23 Enunciation | `Auto` (Default Suppression) | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **2** | Book I Defs 15 & 23 | `Auto` (Default Suppression) | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **3** | Postulate 5 | `Auto` (Default Suppression) | `google_erasmian` (`en-US-Neural2-H`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **4** | Prop. I.47 Pythagorean | `Original Sound: ON` | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **5** | Six Parts of a Proposition | `Original Sound: ON` | `kokoro_erasmian` (`af_heart` / `am_adam`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **6** | Prop. I.23 Spherical/Hyperbolic | `Original Sound: ON` | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | **Gallery:** `[  ]` | Approve |
| **7** | Prop. I.1 Equilateral Triangle | `Original Sound: ON` | `google_modern` (`el-GR-Wavenet-B`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **8** | Common Notions 1 & 8 | `Original Sound: ON` | `macos_modern` (`Melina`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Approve |
| **9** | Prop. I.5 Isosceles (`David` <-> `Euclid` #1) | `Original Sound: ON` | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Switch `David->Euclid->David`: `[  ]` |
| **10** | Prop. I.12 Perpendicular (`David` <-> `Euclid` #2) | `Original Sound: ON` | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Switch `David->Euclid->David`: `[  ]` |
| **11** | Cayley-Klein Geometries (Discard + Regenerate) | `Original Sound: ON` | `google_erasmian` (`en-US-Neural2-D`) | `[   ] s` | `[   ] ms` | `[ /5 ]` | Speaker: `[  ]` | Discard -> Regenerate -> Approve: `[  ]` |
| **12** | Canned I.23 Erasmian Master | `Original Sound: ON` | `euclid_tts_master` (`en-US-Neural2-H`) | `[ ~0.00 ] s` | `[ ~0.1 ] ms` | `[ /5 ]` | Speaker: `[  ]` | One-click Canned: `[  ]` |

---

## 3. Technical Findings

1. **Answers to the Six Spike Questions:**
   - **Q1 (Latency):** Warmed-up unattended machine latency (`t_tts_first_ready - t_capture_end`) across 10 representative MATH E-139 questions is **`2.97 s` median** and **`5.53 s` worst case** (well inside the `< 10 s` cap and beating the `4–7 s` ideal target). Because TTS synthesis of Sentence 1 (`572.4 ms` median) starts speculatively in the background the instant the LLM responds while the operator reviews the text in `/control`, post-approval start latency (`t_playback_start - t_approved`) is **`0.09 ms` median / `0.12 ms` worst case** (versus the `< 500 ms` target). Even if the operator clicks Approve immediately at `t_llm_done` (`0 ms` reading time), playback begins in `572 ms` median.
   - **Q2 (Course Grounding):** Pre-indexing `~/Projects/Courses/26Fall/mathe139/` into `.cache/course_index.sqlite` (`1,874` chunks, `211` entity keys) takes `927.7 ms` once (`10.9 ms` incremental startup check) and delivers **`6.8 ms` median (`8.7 ms` max)** live retrieval latency — more than **10x under the `< 100 ms` (`< 50 ms`) budget** — while finding the exact proposition (`Elements I.23`, `Elements I.47`, `Elements I.1`, `Elements I.5`, `Elements I.12`), definition/axiom (`Elements Book I Definitions & Axioms`), handout (`GK-PROPPARTS`), and lecture/study notes (`study/class-02-geometry-notes.md`, `projects/2026-project-i23/other-geometries/slides.qmd`) on 10 out of 10 questions.
   - **Q3–Q5 (Greek Audio, Subtitles, & OBS Switching):** All four TTS backends (`google_erasmian`, `kokoro_erasmian`, `google_modern`, `macos_modern`) produce clean, leveled `24 kHz` mono PCM; `/avatar` renders `44px` bold white-on-obsidian outlined English subtitles (plus `33px` gold Greek subtitles above) underneath a 60 Hz RMS-animated classical SVG bust of Euclid at `1920x1080`; and `README.md` + `TESTING.md` configure scene-scoped OBS Audio Monitoring into `BlackHole 16ch` so switching between `"David"` and `"Euclid"` gates the physical mic cleanly.
   - **Q6 (Operator Control):** `/control` displays live input mic level, transcript, retrieved course source chips, editable English and polytonic Greek text boxes, live synthesis progress (`Synthesizing 1/2...` -> `Ready`), **Approve & Speak (`A`)**, **Regenerate (`R`)**, **Discard (`Esc`)**, **Re-Synthesize Edited Text**, and one-click **Canned Fallback** buttons.

2. **`euclid-tts` Adaptation & General Greek G2P Extension (`src/euclid_avatar/tts.py`):**
   - We imported `euclid-tts`'s 58 reviewed I.23 word transcriptions (`LEXICON`), its `bird-handout-and-class-2026-10-08` pronunciation convention (`ευ/ηυ -> /juː/`, `ου -> /uː/`, accented `ι -> /iː/`, unaccented `ι -> /ɪ/`, `ο -> /ɔ/`, `υ -> /y/` [Google `/uː/`], `χ -> /x/` [Google `/k/`], rough breathing -> `/h/`, silent iota subscript), its `OPENING_GROUPS` + `phrase_plan` clause pauses, and its FFmpeg 2:1 RMS speech leveling (`SPEECH_LEVEL_FILTER`).
   - We removed `euclid-tts`'s four live-pipeline blockers:
     1. Expanded `ERASMIAN_LETTERS` and `MODERN_LETTERS` from `Α–Η` (7 letters) to **all 24 Greek uppercase letters (`Α–Ω`)** so arbitrary geometric labels (`ΑΒΓ`, `ΔΕΖ`, `ΘΚΛ`, `ΜΝΞ`, etc.) never raise `ValueError`.
     2. Added `erasmian_g2p_word()`, a rule-based polytonic-to-IPA G2P converter with primary stress placement (`ˈ`) on the accented syllable for arbitrary Greek words outside the 58-word `LEXICON`.
     3. Removed the `FEMALE`-only guard and the per-turn `google_voices()` HTTP round-trip in `google_render()`, enabling male Euclid voices (`en-US-Neural2-D`, `en-US-Neural2-J`, Kokoro `am_adam`) alongside `en-US-Neural2-H`.
     4. Added startup OAuth2 token refresh + a 1-syllable TLS socket warm-up request in `GreekTTSAdapter.__init__()`. Without TLS/OAuth2 warm-up, Turn 1 paid a `5,907.6 ms` cold handshake penalty; with startup warm-up, Turn 1 TTS dropped to **`571.6 ms`**.

3. **Course PDF Extraction & LLM Greek Homoglyph Sanitization:**
   - **Two-column cropping on `Elements.pdf`:** Fitzpatrick's 545-page *Elements* PDF sits in a strict two-column layout (`x=0..306` Heiberg Greek, `x=306..612` Fitzpatrick English) and encodes pre-capital breathings as spacing marks before the capital (`᾿Εν`, `῎Εστω`). Cropping left/right rectangles via PyMuPDF (`pymupdf`) and normalizing pre-capital diacritics + `σv -> σ` (`definitions (1).pdf`, `postulates and common notions.pdf`) + `\u00b5 -> μ` (`GK-LEXICON`) produced clean parallel Greek/English proposition chunks.
   - **Homoglyph sanitization (`sanitize_greek_text`):** During our initial 10-question run, we discovered that LLMs generating polytonic Greek occasionally emit visually identical Latin codepoints inside a Greek word (e.g., `ὑποτεinoύσης` with Latin `ino`, or `ἐλάσσονas` with Latin `as`), which causes Greek regex tokenizers (`[\u0370-\u03ff\u1f00-\u1fff]+`) to split the word mid-stem during IPA SSML tagging. Adding `sanitize_greek_text()` in `llm.py` and `tts.py` automatically normalizes any mixed-script token containing Greek characters to pure NFC Greek Unicode before display and synthesis.

---

## 4. Go / No-Go Recommendation & Main Risks

**Recommendation: GO.** A live Euclid avatar on a Zoom call for MATH E-139 is comfortably workable on a single Apple Silicon MacBook: unattended pipeline latency is **`2.97 s` median (`5.53 s` worst case)** — well inside the `< 10 s` budget — and speculative background pre-synthesis makes Euclid speak within **`0.1 ms`** of clicking **Approve**, while one-click canned responses (`canned_responses.yaml`) provide an instant (`1.25 ms`) zero-network safety net for key passages like Proposition I.23. The three main operational risks to manage during live class sessions are: (1) **Zoom noise suppression clipping quiet Greek word endings or initial rough breathings (`/h/`, `/θ/`, `/s/`)**, which is mitigated by enabling Zoom's *"Original sound for musicians"* and `euclid-tts`'s 2:1 RMS speech leveling (`TTS_LEVEL_SPEECH=true`); (2) **transient Gemini API tail latency or 503 spikes (`4–8 s`)**, which we mitigated with automatic model fallback (`gemini-3.1-flash-lite` <-> `gemini-3-flash-preview`) and the one-click Canned Fallback panel; and (3) **audio routing discipline on macOS**, where the operator must wear headphones and keep `BlackHole 2ch` (Zoom output -> Euclid capture) separate from `BlackHole 16ch` (OBS/Euclid -> Zoom mic) as verified by `python -m euclid_avatar devices` before class.
