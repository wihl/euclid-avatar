# Spike & Implementation Results · Euclid Avatar for Group 4 Presentation on *Elements* Book II, Proposition 13 (MATH E-139)

## 1. Pre-Rendered 5-Minute Book II, Proposition 13 Greek Presentation (`presentation_ii13.yaml`)

The avatar's primary task is to deliver David Wihl's 5-slide Greek presentation (`coursework/projects/2026-project-ii13/greek/slides.qmd` and `writeup.qmd`), speaking all English narration in a **Male Australian accent (`en-AU`)** and pronouncing all Ancient Greek clauses and words in **Erasmian Greek** per Graeme Bird's MATH E-139 pronunciation convention (`bird-handout-and-class-2026-10-08`).

| Slide # | Slide Title | Segments | Key Greek Clauses Spoken in Erasmian IPA | Duration (`en-AU-Neural2-D`) | Duration (`en-AU-Chirp3-HD-Charon`) |
| ---: | --- | ---: | --- | ---: | ---: |
| **Slide 1** | `II.13: the enunciation` | 3 (`s1_intro_and_greek`, `s1_english_translation`, `s1_focus_two_features`) | Full 48-word Greek enunciation (`Ἐν τοῖς ὀξυγωνίοις τριγώνοις...`) | **`59.4 s`** | `68.6 s` |
| **Slide 2** | `"Less than ... by ...": three cases` | 3 (`s2_specification_intro`, `s2_three_cases`, `s2_bamberg_class3`) | Specification (`λέγω, ὅτι τὸ ἀπὸ τῆς ΑΓ τετράγωνον ἔλαττόν ἐστι...`), `δίς`, Luschnig's `πέντε ἔτεσι νεώτερος` | **`72.4 s`** | `95.9 s` |
| **Slide 3** | `II.12 and II.13: one sentence` | 2 (`s3_seven_pairs`, `s3_defs_11_12`) | `ἀμβλυγωνίοις` vs. `ὀξυγωνίοις`, `μεῖζόν ἐστι` vs. `ἔλαττόν ἐστι`, `ἐκτός` vs. `ἐντός`, `ἡ μείζων ὀρθῆς`, `ἡ ἐλάσσων ὀρθῆς` | **`54.1 s`** | `66.8 s` |
| **Slide 4** | `The article carries the figure` | 2 (`s4_apo_and_hypo`, `s4_he_kathetos`) | `τὸ ἀπὸ τῆς ΑΓ τετράγωνον`, `τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ περιεχομένῳ ὀρθογωνίῳ`, `ἡ κάθετος`, `τῆς ἀπολαμβανομένης` | **`46.5 s`** | `54.7 s` |
| **Slide 5** | `Then the nouns drop out` | 3 (`s5_early_proof_with_nouns`, `s5_nouns_drop_out`, `s5_conclusion_and_handoff`) | `τὰ ἄρα ἀπὸ τῶν ΓΒ, ΒΔ τετράγωνα`, `τοῖς μὲν ἀπὸ τῶν ΒΔ, ΔΑ ἴσον τὸ ἀπὸ τῆς ΑΒ`, `μόνον τὸ ἀπὸ τῆς ΑΓ` | **`76.8 s`** | `97.7 s` |
| **Total** | **All 5 Slides (Group 4 II.13 Greek Section)** | **13 segments** | **100% lexical coverage of II.13, II.12, Defs I.10–12, Def II.1** | **`309.1 s` (`5.15 min`)** | **`387.1 s` (`6.45 min`)** |

---

## 2. Ten-Question II.13 Professor Q&A Benchmark (`python -m euclid_avatar benchmark`)

### Configuration Tested
- **Platform:** Apple Silicon (`arm64` macOS), Python `3.12.11` (`.venv`)
- **STT:** Local `mlx-community/whisper-large-v3-turbo` (`327.4 ms` startup warm-up on 0.5 s silence; `16 kHz` in-memory float32 PCM)
- **Course RAG Index:** `.cache/course_index.sqlite` (`3,195` chunks across `381` files from `~/Projects/Courses/26Fall/mathe139/`, including `coursework/projects/2026-project-ii13/`, `coursework/assignments/2026-greek-07/`, `Elements.pdf`, `MathNotes08.pdf`, and `local/recordings/*/transcript.md`; `214` canonical entity keys; `21.6 ms` incremental check; `1,807.9 ms` cold build)
- **LLM:** `gemini-3.5-flash-lite` via `google-genai` (`v1beta`) single-pass structured JSON (`sources`, `english`, `greek`, and aligned `sentences`)
- **Bilingual TTS:** `google_au_bilingual` (`en-AU-Neural2-D` male Australian voice, English speaking rate `0.96`, Erasmian Greek rate `0.84`, locale-calibrated `en-AU` IPA `<phoneme>` tags + FFmpeg 2:1 gentle RMS speech leveling)

### Stage-by-Stage Aggregate Latency Summary (10 II.13 Professor Q&A Questions)

| Pipeline Stage | Metric Definition | Target | Min | **Median** | Mean | P90 | **Worst (Max)** |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| **1. STT (`stt_ms`)** | `t_stt_done - t_capture_end` | `< 1,500 ms` | `122.8 ms` | **`146.6 ms`** | `145.5 ms` | `153.9 ms` | **`158.4 ms`** |
| **2. Course RAG (`rag_ms`)** | `t_rag_done - t_stt_done` | `< 100 ms` (`< 50 ms` goal) | `7.5 ms` | **`9.4 ms`** | `9.4 ms` | `10.6 ms` | **`12.4 ms`** |
| **3. Gemini LLM (`llm_ms`)** | `t_llm_done - t_rag_done` | — | `1,725.6 ms` | **`2,081.2 ms`** | `2,094.9 ms` | `2,359.8 ms` | **`2,496.6 ms`** |
| **4. TTS Sentence 1 (`tts_first_sentence_ms`)** | `t_tts_first_ready - t_llm_done` | `~1,000–2,000 ms` | `447.9 ms` | **`576.9 ms`** | `642.8 ms` | `710.7 ms` | **`1,388.2 ms`** |
| **5. TTS All Sentences (`tts_total_ms`)** | `t_tts_all_ready - t_llm_done` | *(background)* | `873.0 ms` | **`1,233.0 ms`** | `1,311.8 ms` | `1,825.4 ms` | **`1,867.6 ms`** |
| **Unattended Machine Latency (`total_unattended_ms`)** | **`t_tts_first_ready - t_capture_end`** | **`< 10,000 ms` (ideal `4–7 s`)** | `2,326.4 ms` (`2.33 s`) | **`2,752.7 ms` (`2.75 s`)** | `2,892.6 ms` (`2.89 s`) | `3,107.6 ms` (`3.11 s`) | **`4,020.0 ms` (`4.02 s`)** |
| **Post-Approval Start (`post_approval_start_ms`)** | **`t_playback_start - t_approved`** | **`< 500 ms` (`< 50 ms` buffered)** | `0.05 ms` | **`0.08 ms`** | `0.08 ms` | `0.11 ms` | **`0.14 ms`** |
| **Prepared II.13 Q&A (`ii13_verbs`)** | Cached `en-AU-Neural2-D` WAV in `.cache/canned_audio/` | `~0 s` floor | — | **`1.12 ms` (unattended)** | — | — | **`0.01 ms` (post-approve)** |

### Per-Question II.13 Professor Q&A Breakdown (`logs/turns.jsonl` & `logs/benchmark_summary.json`)

| # | Question ID | Professor Q&A Topic (`2026-project-ii13` & `2026-greek-07`) | STT (`ms`) | RAG (`ms`) | LLM (`ms`) | TTS S1 (`ms`) | TTS All (`ms`) | **Unattended (`s`)** | **Post-Approve (`ms`)** | Top Cited Sources |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Q01** | `q01_ii13_enunciation` | Prop. II.13 enunciation in Greek & relation to the Law of Cosines | `122.8` | `12.4` | `2,496.6` | `1,388.2` | `1,825.4` | **`4.02 s`** | **`0.08 ms`** | `2026-project-ii13/greek/slides.qmd`, `Elements II.13` |
| **Q02** | `q02_ii13_three_cases` | Nominative, genitive of comparison, & dative of degree of difference | `140.9` | `7.5` | `1,916.4` | `615.2` | `1,219.9` | **`2.68 s`** | **`0.10 ms`** | `2026-project-ii13/greek/slides.qmd`, `Elements II.13` |
| **Q03** | `q03_ii12_vs_ii13` | Word-for-word comparison of II.12 (obtuse) vs. II.13 (acute) | `149.4` | `9.5` | `2,359.8` | `588.9` | `1,246.0` | **`3.11 s`** | **`0.08 ms`** | `2026-project-ii13/greek/slides.qmd`, `Elements II.12` |
| **Q04** | `q04_ii13_article_preposition` | Neuter article + `ἀπό`/`ὑπό` & noun ellipsis after `ἀλλά` | `158.4` | `8.0` | `1,894.2` | `526.0` | `1,037.0` | **`2.59 s`** | **`0.07 ms`** | `2026-project-ii13/greek/slides.qmd`, `Elements II.13` |
| **Q05** | `q05_ii13_verbs_tetmetai_echtho` | Parsing `τέτμηται`, `ἤχθω`, and `προσκείσθω` with principal parts | `146.1` | `7.8` | `2,074.1` | `546.0` | `1,440.3` | **`2.77 s`** | **`0.06 ms`** | `2026-project-ii13/greek/writeup.qmd`, `2026-greek-07/solution.qmd` |
| **Q06** | `q06_ii13_hypoteinousa_kathetos` | Participle `ὑποτεινούσης` & two-ending adjective `ἡ κάθετος` | `144.1` | `8.8` | `1,725.6` | `447.9` | `904.4` | **`2.33 s`** | **`0.08 ms`** | `Elements II.13`, `2026-project-ii13/greek/writeup.qmd` |
| **Q07** | `q07_ii13_enclitic_accent` | Enclitic accent on `ἔλαττόν ἐστι` & `-ττ-` vs. `-σσ-` in Def. I.12 | `153.1` | `10.3` | `2,088.3` | `451.2` | `873.0` | **`2.70 s`** | **`0.14 ms`** | `2026-project-ii13/greek/slides.qmd`, `Elements II.13` |
| **Q08** | `q08_ii13_fitzpatrick_misprints` | Two misprints on p. 65 of Fitzpatrick (`τετραγώνιος`, `γωνίᾳ`) | `147.0` | `9.3` | `2,214.7` | `710.7` | `1,094.1` | **`3.08 s`** | **`0.11 ms`** | `2026-project-ii13/greek/writeup.qmd`, `2026-greek-07/evidence.md` |
| **Q09** | `q09_ii13_proof_ii7_i47` | Proof of II.13 via II.7, CN 2, and I.47 without negative numbers | `153.9` | `10.6` | `2,170.9` | `579.7` | `1,867.6` | **`2.92 s`** | **`0.05 ms`** | `Elements II.13`, `2026-project-ii13/greek/writeup.qmd` |
| **Q10** | `q10_ii13_spherical_hyperbolic` | Spherical & hyperbolic laws of cosines & Taylor expansion (`MathNotes08.pdf`) | `139.2` | `9.5` | `2,008.7` | `574.0` | `1,610.5` | **`2.73 s`** | **`0.07 ms`** | `2026-project-ii13/greek/writeup.qmd`, `MathNotes08.pdf` |

---

## 3. Audit of Latest TTS Models & Voices for Male Australian English + Erasmian Greek

Instead of automatically keeping the October 20 `en-US-Neural2-D` setup, we audited all currently available Google Cloud TTS `en-AU` and `en-US` voice families (`Neural2`, `Chirp3-HD`, `News`, `Polyglot`, `Studio`) and local `Kokoro-82M` (`bm_george`), verifying actual rendered audio with Gemini 2.5 Flash audio transcription:

### Key Discovery: `en-AU` Phoneme Inventory Calibration (`engine_phonemes`)
- When `en-US` IPA tags from `euclid-tts` (`ɑ`, `ɑː`, `oʊ`, bare `ɔ`) were sent directly to `en-AU` voices (`en-AU-Neural2-D`, `en-AU-Chirp3-HD-Charon`, `en-AU-Chirp3-HD-Orus`, `en-AU-News-G`, `en-AU-Polyglot-1`), Google's Australian phoneme parser silently dropped the unrecognized `en-US` vowels (collapsing 4-syllable `ἔλαττόν ἐστι` from `1.29 s` to `0.57 s` of consonant clusters).
- Probing each vowel in isolation against `en-AU-Neural2-D` and `en-AU-Chirp3-HD-Charon` revealed that Google's `en-AU` phoneme table uses the Australian English IPA inventory:
  - **`ɐ` / `ɐː`** for short/long open `/a/` (`α` / `ᾱ`) instead of `ɑ` / `ɑː`
  - **`ɒ` / `ɔː`** for short/long `/o/` (`ο` / `ω`) instead of bare `ɔ` / `oʊ`
  - **`əʊ`** for diphthong `/oʊ/`
- With `engine_phonemes(ipa, voice)` mapping `ɑ -> ɐ`, `ɔ(?!ɪ|ː) -> ɒ`, and `O -> əʊ` for `en-AU` voices, Gemini 2.5 Flash audio verification rated the rendered bilingual audio **9/10 for phonetic clarity**, confirming a seamless single-speaker transition between Male Australian English and Erasmian Ancient Greek.

### Quantitative TTS Model Benchmark on Proposition II.13

| Backend ID | Voice Model | Architecture & Accent | Bilingual II.13 Synth (`ms`) | Bilingual AudioDur (`s`) | Pure Greek II.13 Spec Synth (`ms`) | Pure Greek AudioDur (`s`) | Audit Verdict & Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `google_au_bilingual` | **`en-AU-Neural2-D` (Default)** | Cloud Neural2 Male Australian + Erasmian IPA | **`556.7 ms`** | `8.70 s` | **`517.8 ms`** | `13.85 s` | **Best overall for live presentation & Q&A:** natural Australian accent, 9/10 Erasmian Greek clarity, fast `<600 ms` synthesis, and exact `5.15 min` total presentation duration. |
| `google_au_bilingual` | **`en-AU-Chirp3-HD-Charon`** | Latest Cloud Generative HD Male Australian | `1,631.3 ms` | `10.90 s` | `3,203.5 ms` | `15.54 s` | **Highest conversational realism:** rich generative HD baritone; requires automatic clause-splitting (`_split_bilingual_clauses_for_chirp`) on 48-word Greek sentences (`6.45 min` presentation WAV prebuilt). |
| `google_au_bilingual` | `en-AU-Chirp3-HD-Orus` | Latest Cloud Generative HD Male Australian | `1,575.5 ms` | `10.47 s` | `2,973.9 ms` | `18.20 s` | Warm generative HD Australian male voice; slightly slower cadence on long Greek clauses. |
| `google_au_bilingual` | `en-AU-News-G` | Cloud News Broadcast Male Australian | **`379.3 ms`** | `8.57 s` | **`379.8 ms`** | `14.38 s` | Fastest cloud synthesis (`~380 ms`); crisp broadcast articulation. |
| `google_au_bilingual` | `en-AU-Polyglot-1` | Cloud Polyglot Male Australian | `699.9 ms` | `10.49 s` | `782.0 ms` | `14.25 s` | Smooth cross-lingual prosody on embedded Greek phrases. |
| `google_erasmian` | `en-US-Chirp3-HD-Charon` | Cloud Generative HD Male US (Pure Greek) | `5,263.1 ms` | `18.96 s` | `3,203.5 ms` | `19.07 s` | Deep resonant voice for pure Greek passages; US English accent if used on English text. |
| `google_erasmian` | `en-US-Studio-Q` | Cloud Studio Male US (Pure Greek) | `1,636.8 ms` | `15.75 s` | **`266.8 ms`** | `15.75 s` | Studio broadcast quality for pure Greek quotations. |
| `kokoro_erasmian` | `bm_george` | **100% Local ONNX** Male (`Kokoro-82M`) | `1,398.4 ms` | `18.86 s` | `1,385.5 ms` | `18.86 s` | Zero cloud dependency; native `/y/` and `/x/` phonemes in local ONNX vocab for offline fallback. |
