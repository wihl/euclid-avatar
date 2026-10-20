# Spike · Euclid avatar on a Zoom call

## Goal

Find out, with measurements, whether a live "Euclid" avatar is workable on a Zoom
call. Euclid hears a question in English, gets an LLM to answer the question in 
English, translates the answer aloud in Ancient Greek, and
shows the English response as subtitles. Everything runs on my primary MacBook and reaches Zoom
as an ordinary camera and microphone.

This is a spike. The deliverable is working code plus numbers and findings, not
a product. Prefer the simplest thing that answers each question below, and
write down what you learned even when the answer is "no".

## Questions the spike must answer

1. **Latency.** Measure each stage from the end of a question to Euclid's
   first audible syllable: capture, transcription, generation, synthesis,
   playback start. Report median and worst case over at least ten questions.
   The target is under 10 s; report the result either way.
2. **Greek audio over Zoom.** Is the synthesized Greek intelligible as heard by
   another participant? Compare Zoom's default noise suppression against
   "Original sound for musicians".
3. **Subtitles.** Are they readable in another participant's speaker view and
   gallery view?
4. **Switching.** Does an OBS scene change between my webcam and Euclid go out
   cleanly, with the audio source switching with it?
5. **Control.** Can I see and approve each answer before Euclid speaks it?

## Fixed decisions

- **Platform.** macOS on Apple Silicon, Python 3. Keys live in a gitignored
  `.env`, with names only in `.env.example`.
- **Routing.** No Zoom SDK and no bot. Zoom on the MacBook uses OBS Virtual
  Camera as its camera and a virtual audio device as its mic.
  - Use BlackHole, which is free, with two separate instances: one carries the
    class audio into the pipeline, the other carries Euclid's voice out to
    Zoom. Two devices keep Euclid from hearing himself.
  - Monitoring goes through macOS Multi-Output Devices, so I hear both the
    class and Euclid on headphones.
  - Document the exact device setup in the README.
- **Turn-taking is manual.** I press a hotkey to start and stop capturing a
  question; there is no automatic question detection. After generation, the
  control window shows:
  - the transcript;
  - the Greek;
  - the English;
  - approve, regenerate and discard controls.
  
- **Speech-to-text.** Run it locally on Apple Silicon (for example mlx-whisper
  or whisper.cpp); pick one and record why and which model size. Use a cloud
  service only if local is clearly too slow, and record that measurement.
- **Generation.** Use the Gemini API, with the model as a config value. Start
  with Argon for latency. Euclid answers briefly, in two to four
  sentences, as JSON `{greek, english}`. Write the persona prompt in a separate
  file so I can edit it.
- **Greek speech.** Use my `euclid-tts` (https://github.com/wihl/euclid-tts;
  local checkout at `~/Projects/codex/euclid-tts`). Read its README, call it
  through its own interface, and do not fork or copy its internals. If its
  synthesis time dominates the latency, say so with numbers.
- **Avatar.** A local web page loaded in OBS as a Browser Source, fed over a
  local WebSocket.
  - Draw a stylized Euclid bust with mouth or glow movement driven by the
    playback audio's amplitude.
  - Put English subtitles under it, timed to the audio.
  - Do not attempt photorealistic lip-sync.
- **OBS scenes.** Two scenes, "David" (webcam plus my real mic) and "Euclid"
  (avatar plus the Euclid voice device), switched by a hotkey. Document how the
  audio switches with the scene: either an OBS audio routing or a
  pipeline-side mute.
- **Logging.** Write one JSONL record per turn with the stage timestamps,
  transcript, Greek, English, model, decision (approved, regenerated or
  discarded) and audio file paths. Keep the generated audio files.

## Test without Zoom first

Build a dry-run mode that takes a WAV file as the question and plays Euclid's
answer to the speakers, so the whole pipeline can be timed with no call
running. Report the dry-run latencies in `results.md` before I run the live
session.

## Optional, only if everything above works

Add a canned mode: a YAML list of prepared questions and answers with
pre-rendered audio, picked from the control window. It gives the latency floor
and a fallback when generated Greek can't be trusted.

## Out of scope

- The Zoom Meeting SDK and bots.
- Automatic detection of when a question is addressed to Euclid.
- Realistic avatars and lip-sync.
- Packaging, installers and tests beyond what the spike needs.
- Judging the quality of the Greek. Log it; I will review it.

## Live test protocol

Write this as a checklist in `TESTING.md`. I will run it in a Zoom room nobody
uses, joining twice:

- **MacBook (Euclid).** Zoom with OBS Virtual Camera and the Euclid voice
  device, the pipeline running, headphones on.
- **Second machine (audience).** Joined as me, speaker view, recording its own
  screen and system audio with macOS screen recording. This recording is the
  evidence for questions 2–4.

The checklist must cover:

- **Before joining.**
  - Start OBS Virtual Camera before launching Zoom.
  - Turn off "Mirror my video" and automatic mic volume adjustment on the
    MacBook.
  - Check whether one Zoom account can be in the meeting from both machines at
    once. If it can't, the second machine joins with another account or as a
    signed-out guest. Find this out first.
  - Prevent acoustic feedback between two machines in one room: headphones on
    both, or the second machine's speakers muted while it records.
- **Sequence.** Ten or more questions asked from the second machine.
  - Run at least three with noise suppression on auto and three with "Original
    sound for musicians".
  - Do at least two scene switches in each direction.
  - Include one discard and one regenerate.
- **After.** Fill in `results.md` from the JSONL log and the recording.

## Deliverables

- The code, with a `README.md` covering setup, the audio routing and how to
  run both modes.
- `TESTING.md`.
- `results.md`:
  - the dry-run numbers;
  - a table for the live numbers, for me to complete;
  - findings;
  - a one-paragraph go/no-go recommendation with the main risks.

I'll create the repo. Commit to a branch and open a PR; I merge.
