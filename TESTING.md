# Live Zoom Test Protocol Checklist (`TESTING.md`) · Group 4 Presentation on *Elements* Book II, Proposition 13

Use this step-by-step checklist to verify the **5-Minute Prepared Greek Presentation (`2026-project-ii13`)** and **Live Professor Q&A (Paul Bamberg & Graeme Bird)** on a two-machine Zoom call.

---

## Machine Roles

1. **MacBook (Euclid Host):**
   - Runs `.venv/bin/python -m euclid_avatar serve`, OBS Studio (`OBS Virtual Camera`), `BlackHole 2ch`, and `BlackHole 16ch`.
   - Joins Zoom with Camera = `OBS Virtual Camera`, Microphone = `BlackHole 16ch`, Speaker = `Zoom + Euclid Monitor` (Multi-Output Device), **wired/USB headphones on**.
2. **Second Machine (Audience / Professor Simulator):**
   - Joins the same Zoom meeting as a separate participant.
   - Views Euclid in **Speaker View** (and switches to **Gallery View** for two turns to test small-tile slide and subtitle legibility).
   - Records its own screen and system audio using macOS Screen Recording (`⌘+Shift+5`) or OBS/QuickTime.

---

## Phase 1: Before Joining the Zoom Call

- [ ] **1. Verify virtual audio devices on the MacBook:**
  ```bash
  .venv/bin/python -m euclid_avatar devices
  ```
  Confirm both `BlackHole 2ch` and `BlackHole 16ch` show `[OK]`.
- [ ] **2. Verify the local MATH E-139 course index & pre-rendered II.13 presentation deck:**
  ```bash
  .venv/bin/python -m euclid_avatar index
  .venv/bin/python -m euclid_avatar prebuild-presentation
  ```
  Confirm `.cache/course_index.sqlite` reports `3,195` chunks across `381` files (`214` entity keys) and `.cache/presentation_ii13/` has all 13 segments (`309.1 s` / `5.15 min` total for `en-AU-Neural2-D`).
- [ ] **3. Configure macOS `Audio MIDI Setup` on the MacBook:**
  - Open `Audio MIDI Setup.app` and verify the Multi-Output Device **`Zoom + Euclid Monitor`** includes your **Headphones** (Primary/Master Clock, `48,000 Hz`) and **`BlackHole 2ch`** (Drift Correction checked, `48,000 Hz`).
- [ ] **4. Start the Euclid Avatar server on the MacBook:**
  ```bash
  .venv/bin/python -m euclid_avatar serve
  ```
  - Open [`http://127.0.0.1:8765/control`](http://127.0.0.1:8765/control) in your browser on the MacBook.
  - Verify the **5-Minute Prepared Presentation (`Elements` II.13)** panel displays all 5 slides (`Slide 1`–`Slide 5`, `309.1 s`) and the **⚡ One-Click Prepared II.13 Q&A Answers** panel lists all 5 curated Professor Q&A responses.
- [ ] **5. Start OBS Studio & Virtual Camera BEFORE launching Zoom:**
  - Verify `OBS -> Settings -> Audio -> Advanced -> Monitoring Device` is set to **`BlackHole 16ch`**.
  - Verify Scene **`David`** contains your Webcam + Physical Mic (`Monitor and Output`).
  - Verify Scene **`Euclid`** contains the Browser Source (`http://127.0.0.1:8765/avatar`, `1920x1080`, `60 FPS`) and **no** physical mic source.
  - Click **Start Virtual Camera** in OBS.
- [ ] **6. Launch Zoom on the MacBook & verify audio/video settings:**
  - **Video:** Camera = `OBS Virtual Camera`; **uncheck** *"Mirror my video"*; **check** *"HD"* and *"Original ratio"*.
  - **Audio:** Speaker = `Zoom + Euclid Monitor`; Microphone = `BlackHole 16ch`; **uncheck** *"Automatically adjust microphone volume"*.
  - Enable *"Original sound for musicians"* in Zoom Audio Settings and toggle **Original Sound for Musicians: ON** in the top-left corner of the meeting window.

---

## Phase 2: 5-Minute Book II, Proposition 13 Greek Presentation (Slides 1–5)

Switch OBS to Scene **`Euclid`** (`F10`) and click **▶ Play All (5:09)** (or step slide-by-slide with **▶ Play Slide**) in `/control`:

- [ ] **Slide 1 (`II.13: the enunciation`, `59.4 s`, 3 segments):**
  - Verify the Male Australian English opening handoff from Connor Pearson and the 48-word Greek enunciation of Proposition II.13 in Erasmian IPA (`Ἐν τοῖς ὀξυγωνίοις τριγώνοις...`).
- [ ] **Slide 2 (`"Less than ... by ...": three cases`, `72.4 s`, 3 segments):**
  - Verify the specification (`λέγω, ὅτι τὸ ἀπὸ τῆς ΑΓ τετράγωνον ἔλαττόν ἐστι...`), the three grammatical cases (nominative subject, genitive of comparison, dative of degree of difference with Luschnig's `πέντε ἔτεσι νεώτερος`), and the connection to Paul Bamberg's Class 3 discussion of subtracting magnitudes without negative numbers.
- [ ] **Slide 3 (`II.12 and II.13: one sentence`, `54.1 s`, 2 segments):**
  - Verify the 7 word-for-word differences between II.12 (`ἀμβλυγωνίοις`, `μεῖζόν ἐστι`, `ἐκτός`) and II.13 (`ὀξυγωνίοις`, `ἔλαττόν ἐστι`, `ἐντός`), and the comparison with Book I Definitions 11 & 12 (`ἡ μείζων ὀρθῆς`, `ἡ ἐλάσσων ὀρθῆς`, `-σσ-` vs. `-ττ-`).
- [ ] **Slide 4 (`The article carries the figure`, `46.5 s`, 2 segments):**
  - Verify the three grammatical templates: `τὸ ἀπὸ τῆς ΑΓ τετράγωνον` (`ἀπό` + genitive for squares), `τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ περιεχομένῳ ὀρθογωνίῳ` (`ὑπό` + genitive of agent from Book II Def. 1), and `ἡ κάθετος` (two-ending compound adjective with `εὐθεῖα` understood from Book I Def. 10).
- [ ] **Slide 5 (`Then the nouns drop out`, `76.8 s`, 3 segments):**
  - Verify how all 7 figure phrases from `ἀλλά` (`τοῖς μὲν ἀπὸ τῶν ΒΔ, ΔΑ ἴσον τὸ ἀπὸ τῆς ΑΒ`) to `ὥστε` drop the nouns `τετράγωνον` and `ὀρθογωνίῳ`, and verify the closing handoff to Zahid Syed for the proof.

---

## Phase 3: Live Professor Q&A Test Sequence (10 Turns)

Ask the following 10 Professor Q&A questions from the Second Machine (or via the capture pipeline) and log observations:

### Block A — Grammar & Philology Questions (Graeme Bird Focus, Turns 1–5)
- [ ] **Turn 1 (Three Cases in the Specification):**
  - Ask: *"In the specification of Proposition II.13, how do the nominative, genitive, and dative cases express less than and by how much?"*
  - Capture (`Space`), review in `/control`, and click **✅ Approve & Speak (`A`)**.
- [ ] **Turn 2 (II.12 vs. II.13 Word-for-Word Comparison):**
  - Ask: *"How does the Greek enunciation of Proposition II.12 for obtuse-angled triangles differ word-for-word from Proposition II.13 for acute-angled triangles?"*
- [ ] **Turn 3 (Neuter Article + Preposition & Noun Ellipsis):**
  - Ask: *"How does Book II use the neuter article with the prepositions apo and hypo to name squares and rectangles, and where do the nouns drop out in II.13?"*
- [ ] **Turn 4 (Parsing `τέτμηται`, `ἤχθω`, and `προσκείσθω`):**
  - Ask: *"Can you parse the verbs tetmetai, echtho, and proskeistho in Proposition II.13 and give their principal parts?"*
- [ ] **Turn 5 (Participle `ὑποτεινούσης` & Two-Ending Adjective `ἡ κάθετος`):**
  - Ask: *"Explain the participle hypoteinousas and why he kathetos has a feminine article with an omicron-sigma ending."*

### Block B — Accents, Textual Criticism, & Mathematical Questions (Paul Bamberg & Graeme Bird Focus, Turns 6–10)
- [ ] **Turn 6 (Enclitic Accent on `ἔλαττόν ἐστι` & `-ττ-` vs `-σσ-`):**
  - Ask: *"Why does elatton esti in Proposition II.13 have two acute accents, and how does the spelling elasson in Book I Definition 12 compare?"*
- [ ] **Turn 7 (Two Misprints on Page 65 of Fitzpatrick):**
  - Ask: *"Did you find any misprints in the Greek text of Proposition II.13 on page 65 of Fitzpatrick's edition?"*
- [ ] **Turn 8 (Proof via II.7 and I.47 Without Negative Numbers):**
  - Ask: *"How does the proof of Proposition II.13 use Book II Proposition 7 and the Pythagorean theorem I.47 without using subtraction or negative numbers?"*
- [ ] **Turn 9 (Spherical & Hyperbolic Laws of Cosines — `MathNotes08.pdf`):**
  - Switch `/control` voice to `Male AU + Erasmian IPA · Chirp3-HD Charon (en-AU-Chirp3-HD-Charon)`.
  - Ask: *"Does Proposition II.13 hold in spherical and hyperbolic geometry, and how do the spherical and hyperbolic laws of cosines reduce to it?"*
- [ ] **Turn 10 (One-Click Prepared II.13 Q&A Answer Fallback + OBS Scene Switch):**
  - In `/control`, click **▶ Speak** next to **`II.13 Verbs: τέτμηται, ἤχθω, προσκείσθω, ἔτυχεν`** (`~1.1 ms` instant playback), then test switching OBS Scene **`Euclid`** <-> **`David`**.
