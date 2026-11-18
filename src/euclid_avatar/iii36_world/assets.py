"""Asset caching, Gemini 3.8 TTS voiceover synthesis, and acoustic highlight cue alignment.

Pure Python standard library + FFmpeg implementation compatible with
`/opt/homebrew/bin/python3`. Enforces the < 7-minute (`420.0 s`) total duration
ceiling, aligns spoken geometric letter sequences (`DB`, `AD`, `DC`, `△FBD`,
`△EFC`, `△EFD`, `EF`, `ED`, etc.) to the actual WAV speech envelope and breath
pauses, and never logs or prints API keys.
"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request
import wave

from .geometry import build_world_spec

# Network & Gemini TTS constants ("Sadaltager" = Google's calm, knowledgeable academic voice)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"
GEMINI_TTS_VOICE_NAME = "Sadaltager"
THREE_JS_CDN_URL = "https://unpkg.com/three@0.170.0/build/three.module.js"
HTTP_TIMEOUT_S = 90.0
MAX_API_RETRIES = 3
RETRY_BACKOFF_BASE_S = 2.0

# Audio format & timeline pacing constants
AUDIO_SAMPLE_RATE_HZ = 24000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH_BYTES = 2
PCM16_PEAK_LIMIT = 28500
SILENCE_TRIM_THRESHOLD = 220
EDGE_PAD_S = 0.06
INTER_SEGMENT_PAUSE_S = 0.28
INTER_SLIDE_PAUSE_S = 0.58
OPENING_LEAD_IN_S = 0.30
CLOSING_TAIL_S = 0.70
MAX_PRESENTATION_DURATION_S = 420.0

# Acoustic word/clause alignment constants
ENVELOPE_WINDOW_S = 0.010
CLAUSE_SEARCH_RADIUS_S = 0.52
CUE_LEAD_IN_S = 0.05
CUE_HOLD_AFTER_S = 0.42
SPEECH_FLOOR_AMP = 190.0
ENERGY_WARP_BLEND = 0.65

PLACEHOLDER_KEY = "your_gemini_api_key_here"
ENV_KEY_RE = re.compile(r"^\s*GEMINI_API_KEY\s*=\s*(.+?)\s*$")
CLAUSE_SPLIT_RE = re.compile(r"([^.;:—,]+[.;:—,]?)")
GEO_LETTERS = frozenset({"A", "B", "C", "D", "E", "F", "G"})
VALID_TRIANGLES = frozenset({"FBD", "EFC", "EFD", "EBD"})

# Canonical segment lookup for unordered 2-letter pairs
CANONICAL_SEGMENTS: dict[frozenset[str], str] = {
    frozenset({"D", "B"}): "DB",
    frozenset({"D", "G"}): "DG",
    frozenset({"A", "D"}): "AD",
    frozenset({"D", "C"}): "DC",
    frozenset({"A", "C"}): "AC",
    frozenset({"F", "B"}): "FB",
    frozenset({"F", "C"}): "FC",
    frozenset({"F", "D"}): "FD",
    frozenset({"E", "F"}): "EF",
    frozenset({"E", "C"}): "EC",
    frozenset({"E", "D"}): "ED",
    frozenset({"E", "B"}): "EB",
}

SEGMENT_TO_SLAB: dict[str, str] = {
    "DB": "sqDB",
    "FC": "sqFC",
    "EC": "sqFC",
    "FB": "sqFB",
    "EB": "sqFB",
    "FD": "sqFD",
    "ED": "sqFD",
    "EF": "sqFE",
}


def _read_key_from_env_file(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = ENV_KEY_RE.match(raw_line)
        if not match:
            continue
        candidate = match.group(1).strip().strip("'\"")
        if candidate and candidate != PLACEHOLDER_KEY:
            return candidate
    return ""


def discover_gemini_api_key(worktree_root: Path) -> str:
    course_key = _read_key_from_env_file(
        Path.home() / "Projects/Courses/26Fall/mathe139/.env"
    )
    if course_key:
        return course_key
    env_val = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_val and env_val != PLACEHOLDER_KEY:
        return env_val
    local_key = _read_key_from_env_file(worktree_root / ".env")
    if local_key:
        return local_key
    return _read_key_from_env_file(Path.home() / "Projects/codex/euclid-tts/.env")


def _gemini_post_json(model: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY for III.36 voiceover synthesis.")
    url = f"{GEMINI_API_BASE_URL}/{model}:generateContent?key={api_key}"
    body_bytes = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(MAX_API_RETRIES):
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            if attempt + 1 < MAX_API_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE_S * (attempt + 1))
    raise RuntimeError(f"Gemini API call to {model} failed: {type(last_err).__name__}")


def ensure_three_js_cached(cache_dir: Path) -> Path:
    vendor_dir = cache_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    target = vendor_dir / "three.module.js"
    if target.exists() and target.stat().st_size > 100_000:
        return target
    req = urllib.request.Request(
        THREE_JS_CDN_URL,
        headers={"User-Agent": "euclid-avatar-iii36-world/1.0"},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
        target.write_bytes(resp.read())
    return target


def _normalize_audio_to_wav24k(raw_bytes: bytes, mime_type: str, out_wav: Path) -> float:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        decoded_wav = tmp_dir / "decoded.wav"
        if raw_bytes[:4] == b"RIFF":
            raw_in = tmp_dir / "in.wav"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_in),
                "-ac", str(AUDIO_CHANNELS), "-ar", str(AUDIO_SAMPLE_RATE_HZ),
                "-c:a", "pcm_s16le", str(decoded_wav),
            ]
        else:
            rate_match = re.search(r"rate=(\d+)", mime_type or "")
            in_rate = int(rate_match.group(1)) if rate_match else AUDIO_SAMPLE_RATE_HZ
            raw_in = tmp_dir / "in.pcm"
            raw_in.write_bytes(raw_bytes)
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "s16le", "-ar", str(in_rate), "-ac", str(AUDIO_CHANNELS),
                "-i", str(raw_in), "-ac", str(AUDIO_CHANNELS),
                "-ar", str(AUDIO_SAMPLE_RATE_HZ), "-c:a", "pcm_s16le", str(decoded_wav),
            ]
        subprocess.run(cmd, check=True)
        with wave.open(str(decoded_wav), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        samples = array.array("h")
        samples.frombytes(frames)

    if not samples:
        raise RuntimeError("Decoded TTS audio contained zero samples.")

    n_total = len(samples)
    start_idx = 0
    while start_idx < n_total and abs(samples[start_idx]) < SILENCE_TRIM_THRESHOLD:
        start_idx += 1
    end_idx = n_total - 1
    while end_idx > start_idx and abs(samples[end_idx]) < SILENCE_TRIM_THRESHOLD:
        end_idx -= 1

    pad_samples = int(EDGE_PAD_S * AUDIO_SAMPLE_RATE_HZ)
    start_idx = max(0, start_idx - pad_samples)
    end_idx = min(n_total, end_idx + pad_samples + 1)
    trimmed = samples[start_idx:end_idx]

    peak = max((abs(s) for s in trimmed), default=1)
    if peak > 0:
        gain = min(2.2, PCM16_PEAK_LIMIT / float(peak))
        scaled = array.array(
            "h",
            (max(-32768, min(32767, int(round(s * gain)))) for s in trimmed),
        )
    else:
        scaled = trimmed

    with wave.open(str(out_wav), "wb") as wf_out:
        wf_out.setnchannels(AUDIO_CHANNELS)
        wf_out.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
        wf_out.setframerate(AUDIO_SAMPLE_RATE_HZ)
        wf_out.writeframes(scaled.tobytes())

    return len(scaled) / float(AUDIO_SAMPLE_RATE_HZ)


def _read_wav_duration_and_samples(wav_path: Path) -> tuple[float, array.array]:
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    return len(samples) / float(rate), samples


def synthesize_segment_wav(
    segment_id: str,
    spoken_text: str,
    audio_cache_dir: Path,
    api_key: str,
) -> tuple[Path, float]:
    digest = hashlib.sha256(
        f"v1:{GEMINI_TTS_MODEL}:{GEMINI_TTS_VOICE_NAME}:{spoken_text}".encode("utf-8")
    ).hexdigest()[:12]
    wav_path = audio_cache_dir / f"{segment_id}_{digest}.wav"
    if wav_path.exists() and wav_path.stat().st_size > 1024:
        dur, _ = _read_wav_duration_and_samples(wav_path)
        return wav_path, dur

    payload = {
        "contents": [{"parts": [{"text": spoken_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE_NAME}
                }
            },
        },
    }
    resp = _gemini_post_json(GEMINI_TTS_MODEL, payload, api_key)
    candidates = resp.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"No audio candidates returned for {segment_id}.")
    parts = candidates[0].get("content", {}).get("parts", [])
    inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
    if not inline or not inline.get("data"):
        raise RuntimeError(f"Missing inlineData audio payload for {segment_id}.")

    raw_bytes = base64.b64decode(inline["data"])
    mime_type = inline.get("mimeType", "audio/wav")
    dur = _normalize_audio_to_wav24k(raw_bytes, mime_type, wav_path)
    return wav_path, dur


def _clean_token(tok: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", tok)


def _token_phonemic_weight(tok: str, include_pause: bool = True) -> float:
    clean = _clean_token(tok)
    if not clean:
        return 0.5
    if clean in GEO_LETTERS:
        weight = 3.1
    elif any(ch.isdigit() for ch in clean):
        weight = 3.6 + 0.7 * len(clean)
    else:
        weight = max(1.35, 0.80 * len(clean))
    if include_pause:
        if tok.endswith((".", ";", ":", "—")):
            weight += 3.8
        elif tok.endswith(","):
            weight += 2.1
    return weight


def _align_words_to_waveform(
    spoken_text: str,
    samples: array.array,
    sample_rate: int,
    seg_start_s: float,
) -> list[dict[str, Any]]:
    """Align spoken words to 10 ms acoustic amplitude envelope and breath pauses."""
    win_samples = max(1, int(round(ENVELOPE_WINDOW_S * sample_rate)))
    n_wins = max(1, len(samples) // win_samples)
    env: list[float] = []
    for w_idx in range(n_wins):
        lo = w_idx * win_samples
        hi = min(len(samples), lo + win_samples)
        env.append(sum(abs(samples[k]) for k in range(lo, hi)) / float(max(1, hi - lo)))

    # 3-window smoothed envelope for finding breath/punctuation silence valleys
    smooth_env = [
        (env[max(0, i - 1)] + env[i] + env[min(n_wins - 1, i + 1)]) / 3.0
        for i in range(n_wins)
    ]

    clauses = [c.strip() for c in CLAUSE_SPLIT_RE.findall(spoken_text) if c.strip()]
    if not clauses:
        return []

    clause_weights = [
        sum(_token_phonemic_weight(t, include_pause=True) for t in c.split())
        for c in clauses
    ]
    total_cw = sum(clause_weights) or 1.0

    # Snap internal clause boundaries to actual acoustic silence valleys
    clause_bounds_win = [0]
    cum_w = 0.0
    search_rad_wins = int(round(CLAUSE_SEARCH_RADIUS_S / ENVELOPE_WINDOW_S))
    for idx in range(len(clauses) - 1):
        cum_w += clause_weights[idx]
        expected_win = int(round((cum_w / total_cw) * (n_wins - 1)))
        lo_w = max(clause_bounds_win[-1] + 4, expected_win - search_rad_wins)
        hi_w = min(n_wins - 4, expected_win + search_rad_wins)
        if lo_w <= hi_w:
            best_w = min(
                range(lo_w, hi_w + 1),
                key=lambda w: smooth_env[w] + 1.8 * abs(w - expected_win),
            )
        else:
            best_w = max(clause_bounds_win[-1] + 1, min(n_wins - 2, expected_win))
        clause_bounds_win.append(best_w)
    clause_bounds_win.append(n_wins - 1)

    timed_tokens: list[dict[str, Any]] = []
    for c_idx, clause in enumerate(clauses):
        toks = [t for t in clause.split() if t]
        if not toks:
            continue
        w0 = clause_bounds_win[c_idx]
        w1 = clause_bounds_win[c_idx + 1]
        # Trim leading/trailing silence inside this clause so words sit on voiced speech
        while w0 < w1 and smooth_env[w0] < SPEECH_FLOOR_AMP:
            w0 += 1
        while w1 > w0 and smooth_env[w1] < SPEECH_FLOOR_AMP:
            w1 -= 1
        c_start = w0 * ENVELOPE_WINDOW_S
        c_dur = max(0.08, (w1 - w0 + 1) * ENVELOPE_WINDOW_S)

        t_weights = [_token_phonemic_weight(t, include_pause=False) for t in toks]
        sum_tw = sum(t_weights) or 1.0
        cum_fracs = [0.0]
        acc = 0.0
        for tw in t_weights:
            acc += tw / sum_tw
            cum_fracs.append(min(1.0, acc))

        # Cumulative acoustic energy inside [w0..w1]
        sub_env = [smooth_env[w] + 25.0 for w in range(w0, w1 + 1)]
        cum_e = [0.0]
        e_sum = 0.0
        for val in sub_env:
            e_sum += val
            cum_e.append(e_sum)
        e_tot = cum_e[-1] or 1.0
        norm_e = [v / e_tot for v in cum_e]

        def _interp_energy_frac(target_f: float) -> float:
            for k in range(len(norm_e) - 1):
                if norm_e[k] <= target_f <= norm_e[k + 1]:
                    span = max(1e-6, norm_e[k + 1] - norm_e[k])
                    frac = (target_f - norm_e[k]) / span
                    return (k + frac) / max(1, len(norm_e) - 1)
            return target_f

        for ti, raw_tok in enumerate(toks):
            f_lo = cum_fracs[ti]
            f_hi = cum_fracs[ti + 1]
            w_lo = ENERGY_WARP_BLEND * _interp_energy_frac(f_lo) + (1.0 - ENERGY_WARP_BLEND) * f_lo
            w_hi = ENERGY_WARP_BLEND * _interp_energy_frac(f_hi) + (1.0 - ENERGY_WARP_BLEND) * f_hi
            timed_tokens.append(
                {
                    "raw": raw_tok,
                    "clean": _clean_token(raw_tok),
                    "start_s": round(seg_start_s + c_start + w_lo * c_dur, 4),
                    "end_s": round(seg_start_s + c_start + w_hi * c_dur, 4),
                }
            )

    return timed_tokens


def extract_segment_highlight_cues(
    spoken_text: str,
    samples: array.array,
    sample_rate: int,
    seg_start_s: float,
) -> list[dict[str, Any]]:
    """Extract timestamped 3D highlight cues for every spoken point, segment, triangle, and area."""
    tokens = _align_words_to_waveform(spoken_text, samples, sample_rate, seg_start_s)
    n = len(tokens)
    cues: list[dict[str, Any]] = []
    idx = 0

    while idx < n:
        c0 = tokens[idx]["clean"]
        low0 = c0.lower()

        # 1. 3-letter Triangle: e.g. "F B D", "E F C", "E F D", "E B D"
        if (
            idx + 2 < n
            and c0 in GEO_LETTERS
            and tokens[idx + 1]["clean"] in GEO_LETTERS
            and tokens[idx + 2]["clean"] in GEO_LETTERS
        ):
            tri_id = c0 + tokens[idx + 1]["clean"] + tokens[idx + 2]["clean"]
            if tri_id in VALID_TRIANGLES:
                t_lo = tokens[idx]["start_s"]
                if idx > 0 and tokens[idx - 1]["clean"].lower() == "triangle":
                    t_lo = tokens[idx - 1]["start_s"]
                t_hi = tokens[idx + 2]["end_s"]
                pts = [c0, tokens[idx + 1]["clean"], tokens[idx + 2]["clean"]]
                segs = [
                    CANONICAL_SEGMENTS[frozenset({pts[0], pts[1]})],
                    CANONICAL_SEGMENTS[frozenset({pts[1], pts[2]})],
                    CANONICAL_SEGMENTS[frozenset({pts[0], pts[2]})],
                ]
                cues.append(
                    {
                        "start_s": round(max(seg_start_s, t_lo - CUE_LEAD_IN_S), 4),
                        "end_s": round(t_hi + CUE_HOLD_AFTER_S, 4),
                        "label": f"△{tri_id}",
                        "triangles": [tri_id],
                        "segments": segs,
                        "points": pts,
                        "slabs": [],
                    }
                )
                idx += 3
                continue

        # 2. 2-letter Line Segment (or "square on X Y"): e.g. "D B", "A D", "D C", "E F", "E D"
        if idx + 1 < n and c0 in GEO_LETTERS and tokens[idx + 1]["clean"] in GEO_LETTERS:
            p1, p2 = c0, tokens[idx + 1]["clean"]
            seg_key = CANONICAL_SEGMENTS.get(frozenset({p1, p2}))
            if seg_key:
                t_lo = tokens[idx]["start_s"]
                t_hi = tokens[idx + 1]["end_s"]
                # Check preceding 2-3 tokens for "square(s) [built] on"
                prev_words = [
                    tokens[k]["clean"].lower() for k in range(max(0, idx - 4), idx)
                ]
                is_sq = any(w in ("square", "squares") for w in prev_words) and (
                    "on" in prev_words
                )
                slabs = [SEGMENT_TO_SLAB[seg_key]] if (is_sq and seg_key in SEGMENT_TO_SLAB) else []
                if seg_key in ("AD", "DC") and "rectangle" in prev_words:
                    slabs.append("rectADDC")
                label = f"Square {p1}{p2}²" if is_sq else f"Segment {p1}{p2}"
                cues.append(
                    {
                        "start_s": round(max(seg_start_s, t_lo - CUE_LEAD_IN_S), 4),
                        "end_s": round(t_hi + CUE_HOLD_AFTER_S, 4),
                        "label": label,
                        "triangles": [],
                        "segments": [seg_key],
                        "points": [p1, p2],
                        "slabs": slabs,
                    }
                )
                idx += 2
                continue

        # 3. Named geometric shapes without letters ("blue rectangle", "gnomon")
        if low0 == "gnomon":
            cues.append(
                {
                    "start_s": round(max(seg_start_s, tokens[idx]["start_s"] - CUE_LEAD_IN_S), 4),
                    "end_s": round(tokens[idx]["end_s"] + CUE_HOLD_AFTER_S, 4),
                    "label": "II.6 Gnomon (AD·DC)",
                    "triangles": [],
                    "segments": ["AD", "DC"],
                    "points": [],
                    "slabs": ["gnomon", "rectADDC"],
                }
            )
            idx += 1
            continue

        if low0 == "rectangle" and idx > 0 and tokens[idx - 1]["clean"].lower() == "blue":
            cues.append(
                {
                    "start_s": round(max(seg_start_s, tokens[idx - 1]["start_s"] - CUE_LEAD_IN_S), 4),
                    "end_s": round(tokens[idx]["end_s"] + CUE_HOLD_AFTER_S, 4),
                    "label": "Rectangle AD·DC",
                    "triangles": [],
                    "segments": [],
                    "points": [],
                    "slabs": ["rectADDC", "gnomon"],
                }
            )
            idx += 1
            continue

        # 4. Single-letter Point ("D", "B", "C", "A", "E", "F", "G")
        # Guard against sentence-initial English article "A <lowercase_noun>"
        if c0 in GEO_LETTERS:
            is_english_article_a = (
                c0 == "A"
                and idx + 1 < n
                and tokens[idx + 1]["clean"].islower()
                and tokens[idx + 1]["clean"]
                not in ("and", "is", "to", "from", "on", "at", "in", "of", "by", "equals", "shortens", "times")
            )
            if not is_english_article_a:
                cues.append(
                    {
                        "start_s": round(max(seg_start_s, tokens[idx]["start_s"] - CUE_LEAD_IN_S), 4),
                        "end_s": round(tokens[idx]["end_s"] + 0.32, 4),
                        "label": f"Point {c0}",
                        "triangles": [],
                        "segments": [],
                        "points": [c0],
                        "slabs": [],
                    }
                )
        idx += 1

    return cues


def build_all_world_assets(worktree_root: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    """Prepare Three.js, synthesize voiceover segments (< 7 min), and align highlight cues."""
    resolved_cache = cache_dir or (worktree_root / ".cache" / "iii36_world")
    audio_dir = resolved_cache / "audio"
    resolved_cache.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    api_key = discover_gemini_api_key(worktree_root)
    three_path = ensure_three_js_cached(resolved_cache)

    spec = build_world_spec()
    cursor_s = OPENING_LEAD_IN_S
    master_samples = array.array(
        "h", [0] * int(round(OPENING_LEAD_IN_S * AUDIO_SAMPLE_RATE_HZ))
    )

    timeline_segments: list[dict[str, Any]] = []
    all_cues: list[dict[str, Any]] = []
    slides = spec["slides"]
    for slide_idx, slide in enumerate(slides):
        segs = slide["segments"]
        for seg_idx, seg in enumerate(segs):
            wav_path, dur_s = synthesize_segment_wav(
                seg["id"], seg["spoken"], audio_dir, api_key
            )
            _, seg_samples = _read_wav_duration_and_samples(wav_path)
            start_s = cursor_s
            end_s = start_s + dur_s
            cues = extract_segment_highlight_cues(
                seg["spoken"], seg_samples, AUDIO_SAMPLE_RATE_HZ, start_s
            )
            all_cues.extend(cues)

            master_samples.extend(seg_samples)
            cursor_s = end_s

            is_last_slide = slide_idx == len(slides) - 1
            is_last_seg_in_slide = seg_idx == len(segs) - 1
            if is_last_slide and is_last_seg_in_slide:
                pause_after_s = CLOSING_TAIL_S
            elif is_last_seg_in_slide:
                pause_after_s = INTER_SLIDE_PAUSE_S
            else:
                pause_after_s = INTER_SEGMENT_PAUSE_S

            master_samples.extend(
                [0] * int(round(pause_after_s * AUDIO_SAMPLE_RATE_HZ))
            )
            cursor_s += pause_after_s

            seg_entry = {
                **seg,
                "slide_number": slide["slide_number"],
                "slide_id": slide["id"],
                "slide_title": slide["title"],
                "wav_filename": wav_path.name,
                "wav_path": str(wav_path),
                "start_s": round(start_s, 4),
                "end_s": round(end_s, 4),
                "hold_end_s": round(end_s + pause_after_s, 4),
                "duration_s": round(dur_s, 4),
                "highlight_cues": cues,
            }
            seg.update(seg_entry)
            timeline_segments.append(seg_entry)

    total_duration_s = len(master_samples) / float(AUDIO_SAMPLE_RATE_HZ)
    if total_duration_s > MAX_PRESENTATION_DURATION_S:
        raise RuntimeError(
            f"Presentation duration {total_duration_s:.1f}s exceeds 7-minute limit ({MAX_PRESENTATION_DURATION_S}s)."
        )

    master_wav_path = audio_dir / "iii36_voiceover_full.wav"
    with wave.open(str(master_wav_path), "wb") as wf_master:
        wf_master.setnchannels(AUDIO_CHANNELS)
        wf_master.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
        wf_master.setframerate(AUDIO_SAMPLE_RATE_HZ)
        wf_master.writeframes(master_samples.tobytes())

    spec["timeline"] = {
        "total_duration_s": round(total_duration_s, 4),
        "opening_lead_in_s": OPENING_LEAD_IN_S,
        "closing_tail_s": CLOSING_TAIL_S,
        "master_wav_url": "/assets/audio/iii36_voiceover_full.wav",
        "segments": timeline_segments,
        "highlight_cues": all_cues,
    }
    manifest_path = resolved_cache / "world_manifest.json"
    manifest_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    return {
        "spec": spec,
        "cache_dir": resolved_cache,
        "three_path": three_path,
        "master_wav_path": master_wav_path,
        "manifest_path": manifest_path,
    }
