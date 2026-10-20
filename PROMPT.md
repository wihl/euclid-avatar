# Spike · Euclid avatar on a Zoom call

## Goal

Find out, with measurements, whether a live "Euclid" avatar is workable on a Zoom
call for Harvard Extension School **MATH E-139 (*Reading Euclid's Elements in Greek*)**.

In a live class session:
1. Euclid hears a question in English from the Zoom call.
2. The pipeline retrieves the relevant mathematical and Greek context from the local
   course repository (`~/Projects/Courses/26Fall/mathe139/`) and uses an LLM to
   formulate a concise, accurate answer in English paired with its Ancient Greek
   translation.
3. I review and approve the response in a local control window while speech
   synthesis runs speculatively in the background.
4. Euclid speaks the response aloud in Ancient Greek while displaying the
   synchronized English response as subtitles underneath an animated avatar.

Everything runs on my primary Apple Silicon MacBook and reaches Zoom as an
ordinary camera and microphone.

This is a spike. The deliverable is working code plus numbers and findings, not
a polished product. Prefer the simplest design that answers each question below,
and write down what you learned even when the answer is "no".

## Questions the spike must answer

1. **Latency.** Measure each stage from the end of a captured question to
   Euclid's first audible syllable:
   - audio capture finalization (`t_capture_end`),
   - speech-to-text transcription (`t_stt_done`),
   - course-material retrieval (`t_rag_done`),
   - LLM generation of English + Ancient Greek (`t_llm_done` / `t_llm_first_sentence`),
   - speech synthesis of at least the first sentence (`t_tts_first_ready` and `t_tts_all_ready`),
   - operator approval (`t_approved`), and
   - playback start (`t_playback_start`).

   Report both **unattended pipeline latency** (`t_tts_first_ready - t_capture_end`,
   measuring pure machine time to first playable audio) and **post-approval start
   latency** (`t_playback_start - t_approved`, measuring how quickly Euclid speaks
   once I click Approve). Report median and worst case over at least ten
   questions. The target for unattended machine latency is **under 10 s** (ideally
   4–7 s), and **under 0.5 s** after clicking Approve thanks to background
   pre-synthesis; report the actual numbers either way.
2. **Course grounding.** Does retrieval from `~/Projects/Courses/26Fall/mathe139/`
   find the right proposition, definition, postulate, or class note without
   blowing the latency budget (target `< 100 ms` for local retrieval)?
3. **Greek audio over Zoom.** Is the synthesized Greek intelligible as heard by
   another participant? Compare Zoom's default noise suppression against
   "Original sound for musicians", and compare Erasmian classroom pronunciation
   against normalized Modern Greek pronunciation.
4. **Subtitles.** Are the English subtitles readable in another participant's
   speaker view and gallery view?
5. **Switching.** Does an OBS scene change between my webcam ("David") and
   "Euclid" go out cleanly, with the microphone audio routing switching cleanly
   with it (no double-audio, echo, or dead air)?
6. **Control.** Can I see the transcript, cited course sources, English answer,
   and Greek translation, and approve, regenerate, edit, or discard each answer
   before Euclid speaks it?

## Fixed decisions & latency architecture

- **Platform.** macOS on Apple Silicon (`arm64`), Python 3.12+. Manage the
  environment with `uv` or `.venv`. Keys and local paths live in a gitignored
  `.env`, with variable names documented in `.env.example` (`GEMINI_API_KEY`,
  `GEMINI_MODEL`, `COURSE_REPO_PATH`, `EUCLID_TTS_PATH`, audio device names).
  Never log, print, or commit API keys.

- **Course materials grounding (`~/Projects/Courses/26Fall/mathe139/`).**
  - Read `COURSE_REPO_PATH` (default `~/Projects/Courses/26Fall/mathe139`)
    **strictly read-only**. Respect the course repository's copyright and privacy
    rules (`README.md` D014): never copy or commit course PDFs, textbook pages,
    or professor-supplied files into this repository. Keep any extracted search
    index in a gitignored `.cache/` directory.
  - **Do not parse PDFs or scan the filesystem on the live query path.** Provide
    an indexing step (`python -m euclid_avatar index`) that runs once at setup
    (and incrementally on startup if files changed) to build a fast local index
    in `.cache/course_index.sqlite` (SQLite FTS5 BM25):
    - Index Markdown, Quarto, TeX, and R notes (`coursework/COURSE.md`,
      `coursework/study/*.md`, `coursework/lectures/**/*.md`,
      `coursework/assignments/**/*.{qmd,md}`, `coursework/projects/**/*.{qmd,md}`,
      `materials/course/canvas-week-by-week-euclid-links.md`).
    - Extract text once during indexing from `materials/course/greek-resources/*.pdf`
      (Definitions, Postulates & Common Notions, Parts of a Euclidean Proposition,
      Paul's 2-page vocab list, Greek-English Lexicon, Brief intro to Greek),
      `materials/course/math-notes/*.pdf`, and proposition pages from
      `materials/books/Elements.pdf` (Fitzpatrick / Heiberg Greek-English parallel
      edition).
    - Include a fast **exact proposition / entity matcher** (e.g., `I.23`,
      `Proposition 47`, `Postulate 5`, `Common Notion 1`, `Definition 15`,
      `Class 6`, `Cayley-Klein`, `Hyperbolic`) that combines exact matches with
      top-k (`k=4`) BM25 chunks in `< 50 ms`.
    - Keep a compact pinned summary of `COURSE.md` (syllabus, class schedule,
      per-class proposition table) plus Book I Definitions, Postulates, and
      Common Notions in the base system prompt.

- **Routing.** No Zoom SDK and no bot. Zoom on the MacBook uses `OBS Virtual Camera`
  as its camera and a virtual audio device as its microphone.
  - Use **BlackHole** with two separate virtual devices installed via Homebrew so
    they coexist without custom driver compilation:
    - `brew install blackhole-2ch blackhole-16ch`
    - **Device 1 (`BlackHole 2ch`):** carries Zoom class audio into the capture
      pipeline.
    - **Device 2 (`BlackHole 16ch`):** carries audio into Zoom's microphone input.
    - Two separate devices prevent Euclid from hearing himself.
  - Monitoring goes through macOS **Audio MIDI Setup -> Multi-Output Devices**,
    so I hear both the Zoom class and Euclid on headphones.
  - Provide a CLI diagnostic (`python -m euclid_avatar devices`) that lists all
    detected CoreAudio devices and verifies the required virtual devices exist.
  - Document the exact macOS Audio MIDI Setup, Zoom audio settings, and OBS
    audio settings step-by-step in `README.md`.

- **OBS scenes & audio switching.**
  - Note that `OBS Virtual Camera` transmits **video only**; Zoom always listens
    to a single microphone input device (`BlackHole 16ch`).
  - Configure two OBS scenes, **"David"** (my webcam + my physical mic) and
    **"Euclid"** (the avatar Browser Source + Euclid's synthesized voice),
    switched by a hotkey.
  - Ensure the audio switches cleanly with the video scene via one of two
    documented mechanisms (pick the cleanest and wire it up):
    1. **Pipeline-controlled scene & mic switching via `obs-websocket`:** The
       control app triggers the OBS scene change over `obsws-python` and gates
       physical-mic pass-through vs. Euclid playback into `BlackHole 16ch`, OR
    2. **OBS Audio Monitoring to `BlackHole 16ch`:** OBS's Monitoring Device is
       set to `BlackHole 16ch`, with the physical mic set to "Monitor and Output"
       only in scene "David" and Euclid's audio active only in scene "Euclid".

- **Turn-taking & speculative pre-synthesis (key latency optimization).**
  - Turn-taking is manual. I press a hotkey (or click a button in the control UI)
    to start and stop capturing a question; there is no automatic wake-word or
    question detection. Also include a text box in the control UI so I can type
    or edit a question manually before generating.
  - **Do not serialize human review and TTS synthesis.** As soon as the LLM
    returns the answer:
    1. Immediately populate the control window with the transcript, cited course
       sources, English answer, and Ancient Greek translation, and enable the
       **Approve**, **Regenerate**, and **Discard** controls.
    2. **Immediately start synthesizing the Greek audio in a background worker**
       (beginning with Sentence 1) while I am reading the text in the control
       window.
    3. If I click **Approve** after pre-synthesis of Sentence 1 has completed,
       playback starts immediately (`< 50 ms`) from the in-memory PCM buffer. If
       I click **Approve** while Sentence 1 is still synthesizing, playback begins
       the instant Sentence 1 finishes, while Sentences 2+ synthesize behind it.
    4. If I click **Regenerate** or **Discard**, cancel/drop the in-flight TTS
       buffer.

- **Speech-to-text (STT).**
  - Run locally on Apple Silicon using `mlx-whisper` (e.g.,
    `mlx-community/whisper-large-v3-turbo` or `mlx-community/whisper-small.en`;
    benchmark and pick the best speed/accuracy trade-off) or `whisper.cpp`.
  - **Pre-load and warm up the STT model at startup** by transcribing 0.5 s of
    silence during initialization so Metal shaders and weights are resident in
    RAM before the first live question (avoiding a 4–8 s cold-start penalty).
  - Use a cloud STT service only if warmed-up local inference exceeds 1.5 s for
    a 10 s question, and record that measurement.

- **Generation (Single-pass structured LLM call).**
  - Use the `google-genai` SDK with the Gemini API. Make the model name a config
    value (`GEMINI_MODEL` in `.env`, defaulting to a fast low-latency Flash model
    such as `gemini-2.5-flash`).
  - Perform English answering and Ancient Greek translation in a **single LLM
    call** (avoiding sequential round-trips) returning strict JSON:
    ```json
    {
      "sources": ["COURSE.md", "Elements I.23"],
      "english": "Full 2-4 sentence English answer.",
      "greek": "Full polytonic Ancient Greek translation.",
      "sentences": [
        {
          "english": "Sentence 1 in English.",
          "greek": "Πρότασις αʹ ἐν τῇ Ἑλληνικῇ."
        }
      ]
    }
    ```
  - Write the Euclid persona and translation instructions in a separate editable
    file (`prompts/euclid_persona.md`). Instruct Euclid to answer in 2–4 concise
    sentences grounded in the retrieved `mathe139` context, using authentic
    Euclidean geometry terminology (Heiberg/Fitzpatrick vocabulary, e.g.,
    *εὐθεῖα*, *σημεῖον*, *γωνία εὐθύγραμμος*, *τρίγωνον*, *ὅπερ ἔδει ποιῆσαι* /
    *ὅπερ ἔδει δεῖξαι*) and quoting the original Greek from *Elements* when a
    specific proposition's enunciation or formula is requested.

- **Greek speech (`euclid-tts` integration & general Greek extension).**
  - Inspect my `euclid-tts` repository (`~/Projects/codex/euclid-tts`,
    https://github.com/wihl/euclid-tts), especially `README.md`, `EXPERIMENTS.md`,
    `config.yaml`, and `src/euclid_tts/` (`pronunciation.py`, `prosody.py`,
    `synthesize.py`, `audio.py`). Do **not** modify files inside
    `~/Projects/codex/euclid-tts`.
  - **Important technical constraint discovered in `euclid-tts`:**
    `euclid-tts`'s CLI (`python -m euclid_tts build`) is locked to Proposition
    `I.23` (`input/euclid-I23.txt`), its `erasmian()` phoneme lookup raises
    `ValueError` on any Greek word outside its hardcoded 58-word I.23 `LEXICON`
    or point labels beyond `Α–Η`, its `google_render()` restricts to `FEMALE`
    voices and makes an extra `google_voices()` HTTP call on every synthesis, and
    its CLI runs batch MP3 export and QC that take 7–17 s.
  - Therefore, build a low-latency TTS adapter in `euclid-avatar` that:
    1. **Reuses `euclid-tts`'s verified work:** imports or adapts `euclid-tts`'s
       58 reviewed I.23 word transcriptions, its audited MATH E-139 course
       pronunciation rules (`bird-handout-and-class-2026-10-08` from
       `GreekAlphabetSequence.pdf` and Class 2/3 notes: `ευ` -> `/juː/`, `υ` ->
       `/y/` or Google substitute `/uː/`, accented `ι` -> `/iː/`, `ου` -> `/uː/`,
       rough breathing -> `/h/`, etc.), its clause-pause prosody (`rate: 0.75–0.82`),
       and its gentle 2:1 speech leveling (`audio.level_speech`).
    2. **Extends coverage to arbitrary Greek text:** adds a general rule-based
       polytonic-to-IPA Erasmian grapheme-to-phoneme (G2P) fallback for words not
       in `euclid-tts`'s 58-word `LEXICON`, and expands all 24 Greek uppercase
       letter names (`Α–Ω`) for geometry point labels.
    3. **Supports configurable backends & voices:**
       - **Erasmian IPA mode:** Google Cloud TTS (`en-US-Neural2-D` or `en-US-Neural2-J`
         male voice for Euclid, plus `euclid-tts`'s accepted `en-US-Neural2-H`
         female voice for direct comparison) and local **Kokoro ONNX**
         (`onnx-community/Kokoro-82M-v1.0-ONNX`, pre-loaded once at startup).
       - **Modern Greek normalized mode:** Google Cloud TTS (`el-GR-Wavenet-B`
         or male `el-GR` voice) and local macOS `say` fallback (`Melina` / system
         Greek voice).
    4. **Optimizes synthesis latency:** caches the Google Cloud `AuthorizedSession`
       at startup (no per-turn `google_voices()` check), synthesizes
       **sentence-by-sentence** into 24 kHz mono PCM in memory so Sentence 1 is
       ready in ~1–2 s, streams playback directly via `sounddevice`, and writes
       the full WAV log file asynchronously off the critical path.

- **Avatar & Control UI.**
  - Run a single local web server (`FastAPI` / `aiohttp` + WebSocket on
    `127.0.0.1`) serving two views:
    1. **Avatar view (`/avatar`, 1920x1080 for OBS Browser Source):**
       - Stylized classical bust of Euclid (clean SVG/Canvas illustration) with
         mouth or glow animation driven at 30–60 Hz by the real-time RMS
         amplitude of the playback audio stream.
       - High-contrast English subtitles beneath the bust, synchronized
         sentence-by-sentence to the audio playback (with optional smaller
         polytonic Greek text above the English subtitle).
       - Do not attempt photorealistic lip-sync.
    2. **Operator Control view (`/control`):**
       - Live input mic level indicator, Start/Stop Capture button (plus hotkey),
         and manual question text input override.
       - Displays transcript, retrieved `mathe139` source citations, generated
         English, generated Greek, live synthesis readiness badge (`Synthesizing
         1/3...` -> `Ready`), and **Approve (Speak)**, **Regenerate**, and
         **Discard** buttons.

- **Logging.** Write one JSONL record per turn (`logs/turns.jsonl`) with stage
  timestamps and durations (`capture_ms`, `stt_ms`, `rag_ms`, `llm_ms`,
  `tts_first_sentence_ms`, `tts_total_ms`, `approval_wait_ms`,
  `post_approval_start_ms`, `total_unattended_ms`), transcript, retrieved course
  sources, Greek, English, LLM model, TTS backend/voice, decision (`approved`,
  `regenerated`, or `discarded`), and saved WAV file paths. Keep the generated
  audio files in `logs/audio/`.

## Test without Zoom first

Build a dry-run mode (`python -m euclid_avatar dry-run --wav <file.wav>` or a
batch benchmark runner `python -m euclid_avatar benchmark`) that takes WAV files
(or generates 10 representative MATH E-139 course questions as WAV files using
macOS `say` if none are supplied), runs the full STT -> Course RAG -> Gemini ->
Greek TTS pipeline in `--auto-approve` mode, plays or verifies the output audio,
and records all stage timings.

Include questions spanning the actual course material in `~/Projects/Courses/26Fall/mathe139/`
(e.g., Proposition I.23 enunciation, Book I Definitions/Postulates, Proposition
I.47 Pythagorean theorem, spherical/hyperbolic geometry comparisons from Class
4–6). Report the dry-run latencies across at least 10 questions in `results.md`
before I run the live Zoom session.

## Canned fallback mode

Include a canned mode (`canned_responses.yaml`): a curated list of prepared
MATH E-139 questions and answers with pre-rendered WAV audio (including the
accepted Proposition I.23 Erasmian and Modern WAVs from `~/Projects/codex/euclid-tts/output/`),
selectable with one click from the control window. This gives the latency floor
(`~0 s`) and a live-class fallback when generated Greek or cloud connectivity
can't be trusted.

## Out of scope

- The Zoom Meeting SDK and bots.
- Automatic wake-word or question detection.
- Photorealistic avatars and phoneme-level viseme lip-sync.
- Modifying any files inside `~/Projects/Courses/26Fall/mathe139/` or
  `~/Projects/codex/euclid-tts/`.
- Packaging, installers, and tests beyond what the spike needs.

## Live test protocol

Write this as a step-by-step checklist in `TESTING.md`. I will run it in a Zoom
room nobody uses, joining twice:

- **MacBook (Euclid).** Zoom with `OBS Virtual Camera` and `BlackHole 16ch` as
  microphone, `BlackHole 2ch` (via Multi-Output Device) as speaker, the pipeline
  running, headphones on.
- **Second machine (audience).** Joined as a separate participant, speaker view,
  recording its own screen and system audio with macOS screen recording. This
  recording is the evidence for questions 3–5.

The checklist must cover:

- **Before joining.**
  - Install and verify `blackhole-2ch` and `blackhole-16ch` and configure the
    macOS Multi-Output Device in Audio MIDI Setup.
  - Run `python -m euclid_avatar devices` and `python -m euclid_avatar index`.
  - Start OBS Virtual Camera before launching Zoom.
  - Turn off "Mirror my video" and automatic mic volume adjustment in Zoom on
    the MacBook.
  - Note how to join the same Zoom meeting from two machines (using a signed-out
    guest browser window or second account on the audience machine so Zoom does
    not kick the host session).
  - Prevent acoustic feedback between two machines in one room: headphones on
    both, or the second machine's speakers muted while it records system audio.
- **Sequence.** Ten or more questions asked from the second machine.
  - Run at least three with Zoom noise suppression on "Auto" and three with
    "Original sound for musicians" enabled.
  - Compare at least two turns with Erasmian TTS and two with Modern Greek TTS.
  - Do at least two OBS scene switches ("David" <-> "Euclid") in each direction.
  - Include at least one discard, one regenerate, and one canned response.
- **After.** Fill in `results.md` from `logs/turns.jsonl` and the audience screen
  recording.

## Deliverables

- Working code in this repository, with a `README.md` covering setup, `.env`
  configuration, exact BlackHole / Multi-Output / OBS / Zoom routing, and how to
  run indexing, dry-run benchmark mode, and live mode.
- `prompts/euclid_persona.md` and `canned_responses.yaml`.
- `TESTING.md`.
- `results.md`:
  - the 10-question dry-run benchmark numbers (stage-by-stage median and worst
    case, plus TTS backend comparisons);
  - a ready-to-fill table for the live Zoom numbers;
  - technical findings (including `euclid-tts` adaptation details and course
    retrieval accuracy);
  - a one-paragraph go/no-go recommendation with the main risks.

Commit to a feature branch and open a PR (or leave clean commits ready on the
branch if no remote is configured yet); I will review and merge.
