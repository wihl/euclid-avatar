"""Low-latency Ancient Greek TTS adapter reusing and extending `euclid-tts`."""
from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata as ud
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from .config import Config

SAMPLE_RATE = 24000
WORD_RE = re.compile(r"(?:(?![·;])[\u0370-\u03ff\u1f00-\u1fff])+")
LETTERS_RE = re.compile(r"\b[Α-Ω]+\b")

CONVENTION = "bird-handout-and-class-2026-10-08"

# 1. Verified 58-word Proposition I.23 lexicon from euclid-tts (Kokoro diphthong tokens: A=aɪ, I=eɪ, O=oʊ, W=aʊ)
# Plus curated high-frequency Euclidean geometry vocabulary following the exact Bird handout audit rules.
LEXICON: dict[str, str] = {
    # Verified 58 I.23 words from euclid-tts/src/euclid_tts/pronunciation.py
    "πρὸς": "pɹɔs", "πρός": "pɹɔs",
    "τῇ": "tI", "δοθείσῃ": "dɔˈθIsI",
    "εὐθείᾳ": "juːˈθIɑ", "καὶ": "kA", "καί": "kA",
    "τῷ": "tO", "αὐτῇ": "aʊˈtI",
    "σημείῳ": "sIˈmIO", "γωνίᾳ": "ɡOˈniːɑ", "εὐθυγράμμῳ": "juːθyˈɡɹɑmO",
    "ἴσην": "ˈiːsIn", "γωνίαν": "ɡOˈniːɑn", "εὐθύγραμμον": "juːˈθyɡɹɑmɔn",
    "συστήσασθαι": "syˈstIsɑsθA", "ἔστω": "ˈɛstO", "ἡ": "hI",
    "μὲν": "mɛn", "μέν": "mɛn", "δοθεῖσα": "dɔˈθIsɑ", "εὐθεῖα": "juːˈθIɑ",
    "τὸ": "tɔ", "τό": "tɔ",
    "δὲ": "dɛ", "δέ": "dɛ", "σημεῖον": "sIˈmIɔn", "γωνία": "ɡOˈniːɑ",
    "εὐθύγραμμος": "juːˈθyɡɹɑmɔs", "ὑπὸ": "hyˈpɔ", "ὑπό": "hyˈpɔ", "δεῖ": "dI",
    "δὴ": "dɛ", "δή": "dɛ", "εἰλήφθω": "IˈlIfθO", "ἐφ᾿": "ɛf", "ἐφ'": "ɛf",
    "ἑκατέρας": "hɛkɑˈtɛɹɑs",
    "τῶν": "tOn", "τυχόντα": "tyˈxɔntɑ", "σημεῖα": "sIˈmIɑ",
    "τὰ": "tɑ", "τά": "tɑ",
    "ἐπεζεύχθω": "ɛpɛˈzjuːxθO", "ἐκ": "ɛk", "τριῶν": "tɹɪˈOn",
    "εὐθειῶν": "juːθIˈOn", "αἵ": "hA", "αἱ": "hA", "εἰσιν": "Isɪn",
    "εἰσὶν": "Iˈsiːn", "εἰσίν": "Iˈsiːn", "ἴσαι": "ˈiːsA", "τρισὶ": "tɹɪˈsiː",
    "ταῖς": "tAs", "τρίγωνον": "ˈtɹiːɡOnɔn", "συνεστάτω": "synɛˈstɑtO", "ὥστε": "ˈhOstɛ",
    "εἶναι": "ˈInA", "τὴν": "tIn", "τήν": "tIn", "ἔτι": "ˈɛtɪ", "ἐπεὶ": "ɛˈpI", "οὖν": "uːn",
    "δύο": "ˈdyɔ", "ἑκατέρα": "hɛkɑˈtɛɹɑ", "ἑκατέρᾳ": "hɛkɑˈtɛɹɑ",
    "βάσις": "ˈbɑsɪs", "βάσει": "ˈbɑsI", "ἴση": "ˈiːsI", "ἄρα": "ˈɑɹɑ",
    "ἐστιν": "ɛstɪn", "ἐστὶν": "ɛˈstiːn", "ἐστίν": "ɛˈstiːn", "ἐστι": "ɛstɪ",
    "συνέσταται": "syˈnɛstɑtA", "ὅπερ": "ˈhɔpɛɹ",
    "ἔδει": "ˈɛdI", "ποιῆσαι": "pɔɪˈIsA",
    # Extended MATH E-139 high-frequency Euclidean vocabulary
    "δεῖξαι": "ˈdIksA",
    "σημεῖόν": "sIˈmIɔn",
    "οὗ": "huː",
    "μέρος": "ˈmɛɹɔs",
    "οὐθέν": "uːˈθɛn", "οὐδέν": "uːˈdɛn",
    "γραμμὴ": "ɡɹɑˈmI", "γραμμή": "ɡɹɑˈmI", "γραμμῆς": "ɡɹɑˈmIs", "γραμμαὶ": "ɡɹɑˈmA", "γραμμαί": "ɡɹɑˈmA",
    "μῆκος": "ˈmIkɔs",
    "ἀπλατές": "ɑplɑˈtɛs",
    "πέρατα": "ˈpɛɹɑtɑ", "πέρας": "ˈpɛɹɑs",
    "κύκλος": "ˈkyklɔs", "κύκλου": "ˈkykluː", "κύκλον": "ˈkyklɔn",
    "κέντρον": "ˈkɛntɹɔn", "κέντρῳ": "ˈkɛntɹO",
    "διάμετρος": "dɪˈɑmɛtɹɔs", "διαστήματι": "dɪɑˈstImɑtɪ",
    "περιφέρεια": "pɛɹɪˈfɛɹIɑ", "περιφερείας": "pɛɹɪfɛˈɹIɑs",
    "σχῆμα": "ˈsxImɑ", "σχῆμά": "ˈsxImɑ", "σχήματος": "ˈsxImɑtɔs", "σχήματα": "ˈsxImɑtɑ",
    "ἐπίπεδον": "ɛˈpiːpɛdɔn", "ἐπιπέδῳ": "ɛpɪˈpɛdO", "ἐπιφάνεια": "ɛpɪˈfɑnIɑ",
    "παράλληλοι": "pɑˈɹɑlIlɔɪ", "παράλληλοί": "pɑˈɹɑlIlɔɪ",
    "ὀρθὴ": "ɔɹˈθI", "ὀρθή": "ɔɹˈθI", "ὀρθὴν": "ɔɹˈθIn", "ὀρθῆς": "ɔɹˈθIs", "ὀρθὰς": "ɔɹˈθɑs", "ὀρθῶν": "ɔɹˈθOn",
    "κάθετος": "ˈkɑθɛtɔs",
    "τετράγωνον": "tɛˈtɹɑɡOnɔn", "τετράγωνα": "tɛˈtɹɑɡOnɑ",
    "πλευρᾶς": "pljuːˈɹɑs", "πλευρῶν": "pljuːˈɹOn", "πλευράς": "pljuːˈɹɑs", "πλευρὰς": "pljuːˈɹɑs",
    "ἰσόπλευρον": "ɪˈsɔpljuːɹɔn", "ἰσοσκελὲς": "ɪsɔskɛˈlɛs", "ἰσοσκελές": "ɪsɔskɛˈlɛs",
    "ὀρθογώνιον": "ɔɹθɔˈɡOnɪɔn", "ὀρθογωνίοις": "ɔɹθɔɡOˈniːɔɪs", "τριγώνοις": "tɹɪˈɡOnɔɪs",
    "ὑποτενούσης": "hypɔtIˈnuːsIs", "ὑποτείνουσα": "hypɔˈtInuːsɑ",
    "περιέχουσαι": "pɛɹɪˈɛxuːsA", "περιεχουσῶν": "pɛɹɪɛxuːˈsOn",
    "ἀλλήλοις": "ɑˈlIlɔɪs", "ἀλλήλαις": "ɑˈlIlAs",
    "πρότασις": "ˈpɹɔtɑsɪs", "ἔκθεσις": "ˈɛkθɛsɪs", "διορισμός": "dɪɔɹɪˈsmɔs",
    "κατασκευή": "kɑtɑskjuːˈI", "ἀπόδειξις": "ɑˈpɔdIksɪs", "συμπέρασμα": "symˈpɛɹɑsmɑ",
}

# 2. All 24 Greek uppercase letters for geometric point labels (Α–Ω)
ERASMIAN_LETTERS: dict[str, str] = {
    "Α": "ˈɑlfɑ",
    "Β": "ˈbItɑ",
    "Γ": "ˈɡɑmɑ",
    "Δ": "ˈdɛltɑ",
    "Ε": "ˈɛpsɪlɔn",
    "Ζ": "ˈzItɑ",
    "Η": "ˈItɑ",
    "Θ": "ˈθItɑ",
    "Ι": "ɪˈOtɑ",
    "Κ": "ˈkɑpɑ",
    "Λ": "ˈlɑmdɑ",
    "Μ": "ˈmy",
    "Ν": "ˈny",
    "Ξ": "ˈksA",
    "Ο": "ˈɔmɪkɹɔn",
    "Π": "ˈpA",
    "Ρ": "ˈɹO",
    "Σ": "ˈsɪɡmɑ",
    "Τ": "ˈtW",
    "Υ": "ˈypsɪlɔn",
    "Φ": "ˈfA",
    "Χ": "ˈxA",
    "Ψ": "ˈpsA",
    "Ω": "Oˈmɛɡɑ",
}

MODERN_LETTERS: dict[str, str] = {
    "Α": "άλφα",
    "Β": "βήτα",
    "Γ": "γάμμα",
    "Δ": "δέλτα",
    "Ε": "έψιλον",
    "Ζ": "ζήτα",
    "Η": "ήτα",
    "Θ": "θήτα",
    "Ι": "ιώτα",
    "Κ": "κάππα",
    "Λ": "λάμδα",
    "Μ": "μι",
    "Ν": "νι",
    "Ξ": "ξι",
    "Ο": "όμικρον",
    "Π": "πι",
    "Ρ": "ρο",
    "Σ": "σίγμα",
    "Τ": "ταυ",
    "Υ": "ύψιλον",
    "Φ": "φι",
    "Χ": "χι",
    "Ψ": "ψι",
    "Ω": "ωμέγα",
}

GOOGLE_SUBSTITUTIONS = {
    "y": {"engine_ipa": "uː", "reason": "en-US lacks /y/; /uː/ preserves high rounded quality"},
    "x": {"engine_ipa": "k", "reason": "en-US lacks /x/; /k/ preserves velar place"},
}

MODERN_MONOSYLLABLES = {
    "πρός", "τή", "καί", "τώ", "μέν", "τό", "δέ", "δή", "δεί",
    "τών", "τά", "έκ", "αί", "ταίς", "τήν", "ούν", "ή", "ο", "οι", "εν", "εις", "ως", "μη", "ου",
}

MODERN_RESPELLINGS = {
    "δοθείση": "δοθίσι", "δοθείσα": "δοθίσα", "ευθεία": "εφθία",
    "αυτή": "αφτή", "σημείω": "σιμίο", "σημείον": "σιμίον",
    "ευθυγράμμω": "εφθιγράμμο", "ευθύγραμμον": "εφθίγραμμον",
    "ευθύγραμμος": "εφθίγραμμος", "ίσην": "ίσιν",
    "συστήσασθαι": "σιστίσασθε",
}

DEFAULT_PAUSES = {"phrase": 0.45, "comma": 0.60, "section": 0.85, "sentence": 0.95}

OPENING_GROUPS = [
    ("Πρὸς τῇ δοθείσῃ εὐθείᾳ", "phrase"),
    ("καὶ τῷ πρὸς αὐτῇ σημείῳ", "phrase"),
    ("τῇ δοθείσῃ γωνίᾳ εὐθυγράμμῳ", "phrase"),
    ("ἴσην γωνίαν εὐθύγραμμον συστήσασθαι.", "sentence"),
    ("Ἔστω ἡ μὲν δοθεῖσα εὐθεῖα ἡ ΑΒ,", "comma"),
    ("τὸ δὲ πρὸς αὐτῇ σημεῖον τὸ Α,", "comma"),
    ("ἡ δὲ δοθεῖσα γωνία εὐθύγραμμος ἡ ὑπὸ ΔΓΕ·", "section"),
    ("δεῖ δὴ πρὸς τῇ δοθείσῃ εὐθείᾳ τῇ ΑΒ", "phrase"),
    ("καὶ τῷ πρὸς αὐτῇ σημείῳ τῷ Α", "phrase"),
    ("τῇ δοθείσῃ γωνίᾳ εὐθυγράμμῳ τῇ ὑπὸ ΔΓΕ", "phrase"),
    ("ἴσην γωνίαν εὐθύγραμμον συστήσασθαι.", "sentence"),
]

SPEECH_LEVEL_FILTER = (
    "acompressor=threshold=0.063096:ratio=2:attack=5:release=80:"
    "makeup=1.995262:detection=rms,"
    "alimiter=limit=0.89:attack=5:release=50:level=0:latency=1"
)


def erasmian_g2p_word(token: str) -> str:
    """Rule-based polytonic Ancient Greek to course-target Erasmian IPA (Kokoro tokens A/I/O/W).

    Implements Graeme Bird's MATH E-139 course convention (`bird-handout-and-class-2026-10-08`):
      - ευ / ηυ -> juː
      - ου -> uː
      - αυ -> W (aʊ)
      - αι -> A (aɪ)
      - ει -> I (eɪ)
      - οι -> ɔɪ
      - υι -> wɪ
      - υ -> y (Google substitute uː)
      - ι -> iː when accented, ɪ when unaccented
      - ο -> ɔ
      - ε -> ɛ
      - η -> I (eɪ)
      - ω -> O (oʊ)
      - α -> ɑ (silent iota subscript \u0345 discarded)
      - rough breathing \u0314 on initial vowel/diphthong/ρ -> initial h
    """
    norm = ud.normalize("NFC", token.strip("᾿'’"))
    if not norm:
        return "ɛ"
    lower_key = norm.lower()
    if lower_key in LEXICON:
        return LEXICON[lower_key]

    # Parse into base Greek letters + per-letter diacritic flags
    letters: list[dict[str, Any]] = []
    for ch in ud.normalize("NFD", lower_key):
        if ch == "\u0345":
            # Silent iota subscript per Class 3 lecture note (01:03:00)
            continue
        if ud.combining(ch):
            if letters:
                if ch == "\u0314":
                    letters[-1]["rough"] = True
                elif ch in {"\u0301", "\u0300", "\u0342"}:
                    letters[-1]["accent"] = True
                elif ch == "\u0308":
                    letters[-1]["diaeresis"] = True
        elif "\u0370" <= ch <= "\u03ff" or "\u1f00" <= ch <= "\u1fff":
            letters.append({"ch": ch, "rough": False, "accent": False, "diaeresis": False})

    if not letters:
        return "ɛ"

    vowels_set = {"α", "ε", "η", "ι", "ο", "υ", "ω"}
    diphthongs = {
        "ευ": "juː",
        "ηυ": "juː",
        "ου": "uː",
        "αυ": "W",
        "αι": "A",
        "ει": "I",
        "οι": "ɔɪ",
        "υι": "wɪ",
    }

    # Segment into phoneme units with vowel/accent markers so we can place primary stress ˈ
    units: list[dict[str, Any]] = []
    has_initial_h = any(l["rough"] for l in letters[:2])

    i = 0
    n = len(letters)
    while i < n:
        c1 = letters[i]["ch"]
        c2 = letters[i + 1]["ch"] if i + 1 < n else ""
        pair = c1 + c2

        # Check vowel diphthong (unless second vowel has diaeresis)
        if pair in diphthongs and not letters[i + 1]["diaeresis"]:
            acc = letters[i]["accent"] or letters[i + 1]["accent"]
            units.append({"ph": diphthongs[pair], "is_vowel": True, "accent": acc})
            i += 2
            continue

        # Check consonant digraphs
        if pair in {"γγ", "γκ", "γχ", "γξ"}:
            mapping = {"γγ": "ŋɡ", "γκ": "ŋk", "γχ": "ŋx", "γξ": "ŋks"}[pair]
            units.append({"ph": mapping, "is_vowel": False, "accent": False})
            i += 2
            continue
        if pair in {"λλ", "μμ", "νν", "ππ", "ρρ", "σσ", "ττ", "κκ"}:
            # Geminates reduce to single consonant in English Erasmian rendering
            i += 1
            continue

        # Single vowel
        if c1 in vowels_set:
            acc = letters[i]["accent"]
            if c1 == "α":
                ph = "ɑ"
            elif c1 == "ε":
                ph = "ɛ"
            elif c1 == "η":
                ph = "I"
            elif c1 == "ι":
                ph = "iː" if acc else "ɪ"
            elif c1 == "ο":
                ph = "ɔ"
            elif c1 == "υ":
                ph = "y"
            elif c1 == "ω":
                ph = "O"
            else:
                ph = "ɑ"
            units.append({"ph": ph, "is_vowel": True, "accent": acc})
            i += 1
            continue

        # Single consonant
        cons_map = {
            "β": "b",
            "γ": "ɡ",
            "δ": "d",
            "ζ": "z",
            "θ": "θ",
            "κ": "k",
            "λ": "l",
            "μ": "m",
            "ν": "n",
            "ξ": "ks",
            "π": "p",
            "ρ": "ɹ",
            "σ": "z" if c2 in {"β", "γ", "δ", "μ"} else "s",
            "ς": "s",
            "τ": "t",
            "φ": "f",
            "χ": "x",
            "ψ": "ps",
        }
        units.append({"ph": cons_map.get(c1, ""), "is_vowel": False, "accent": False})
        i += 1

    if has_initial_h:
        units.insert(0, {"ph": "h", "is_vowel": False, "accent": False})

    # Place primary stress ˈ before the syllable onset of the accented vowel (if >= 2 vowels)
    vowel_indices = [idx for idx, u in enumerate(units) if u["is_vowel"]]
    accented_vowel_indices = [idx for idx, u in enumerate(units) if u["is_vowel"] and u["accent"]]

    if len(vowel_indices) >= 2:
        target_v = accented_vowel_indices[0] if accented_vowel_indices else vowel_indices[0]
        # Walk back up to 1 consonant onset (or 2 if stop+liquid like τρ, πρ, κλ, γρ)
        stress_pos = target_v
        if stress_pos > 0 and not units[stress_pos - 1]["is_vowel"]:
            # If before the first vowel, place stress at index 0
            if target_v == vowel_indices[0]:
                stress_pos = 0
            else:
                stress_pos = target_v - 1
                if (
                    stress_pos > 0
                    and not units[stress_pos - 1]["is_vowel"]
                    and units[stress_pos]["ph"] in {"ɹ", "l"}
                    and units[stress_pos - 1]["ph"] in {"p", "t", "k", "b", "d", "ɡ", "f", "θ", "x"}
                ):
                    stress_pos -= 1
        out_parts: list[str] = []
        for idx, u in enumerate(units):
            if idx == stress_pos:
                out_parts.append("ˈ")
            out_parts.append(u["ph"])
        return "".join(out_parts)

    return "".join(u["ph"] for u in units)


LATIN_TO_GREEK_INNER = str.maketrans({
    "a": "α", "e": "ε", "i": "ι", "o": "ο", "u": "υ", "y": "υ",
    "k": "κ", "m": "μ", "n": "ν", "p": "π", "t": "τ", "x": "χ", "b": "β", "d": "δ", "g": "γ",
    "A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ", "M": "Μ", "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "X": "Χ", "Y": "Υ",
})


def sanitize_greek_text(text: str) -> str:
    """Fix stray Latin homoglyphs inside Greek words (e.g. 'ὑποτεinoύσης' -> 'ὑποτεινούσης', 'ἐλάσσονas' -> 'ἐλάσσονας')."""
    def fix_mixed_token(match: re.Match[str]) -> str:
        tok = match.group(0)
        # Only normalize if token contains at least one true Greek character
        if not re.search(r"[\u0370-\u03ff\u1f00-\u1fff]", tok):
            return tok
        converted = tok.translate(LATIN_TO_GREEK_INNER)
        # Handle 's' -> 'ς' at word end, 'σ' internally
        converted = re.sub(r"s\b", "ς", converted)
        converted = converted.replace("s", "σ")
        return ud.normalize("NFC", converted)

    return re.sub(r"[A-Za-z\u0370-\u03ff\u1f00-\u1fff]+", fix_mixed_token, text)


def erasmian(text: str) -> str:
    """Convert arbitrary polytonic Greek text into course-target Erasmian phonemes."""
    text = sanitize_greek_text(text)
    def replace_word(match: re.Match[str]) -> str:
        token = match.group()
        if re.fullmatch(r"[Α-Ω]+", token):
            return " ".join(ERASMIAN_LETTERS.get(c, erasmian_g2p_word(c)) for c in token)
        key = ud.normalize("NFC", token.lower())
        if key in LEXICON:
            return LEXICON[key]
        return erasmian_g2p_word(token)

    result = WORD_RE.sub(replace_word, text).replace("·", ";").replace("·", ";")
    return re.sub(r"\s+", " ", result).replace("g", "ɡ").replace("aʊ", "W")


def ipa(phonemes: str) -> str:
    for token, value in {"A": "aɪ", "I": "eɪ", "O": "oʊ", "W": "aʊ"}.items():
        phonemes = phonemes.replace(token, value)
    return phonemes


def engine_phonemes(phonemes: str, backend: str) -> str:
    if backend in {"kokoro", "kokoro_erasmian"}:
        return phonemes
    result = ipa(phonemes)
    for target, substitute in GOOGLE_SUBSTITUTIONS.items():
        result = result.replace(target, substitute["engine_ipa"])
    return re.sub(r"ɔ(?!ɪ)", "ɔː", result.replace("ɑ", "ɑː"))


def erasmian_ssml_words(text: str) -> str:
    """Wrap each Greek word or geometric letter in an IPA <phoneme> tag for Google Cloud TTS."""
    text = sanitize_greek_text(text)
    def tag(label: str, phonemes: str) -> str:
        eng_ph = engine_phonemes(phonemes, "google_cloud")
        return f'<phoneme alphabet="ipa" ph={quoteattr(eng_ph)}>{escape(label)}</phoneme>'

    def word(match: re.Match[str]) -> str:
        token = match.group()
        if re.fullmatch(r"[Α-Ω]+", token):
            return " ".join(tag(c, ERASMIAN_LETTERS.get(c, erasmian(c))) for c in token)
        return tag(token, erasmian(token))

    parts: list[str] = []
    position = 0
    for match in WORD_RE.finditer(text):
        parts.extend([escape(text[position:match.start()]), word(match)])
        position = match.end()
    parts.append(escape(text[position:]))
    return "".join(parts).replace("·", ";").replace("·", ";")


def modern(text: str, respelled: bool = False) -> str:
    """Normalize polytonic Ancient Greek to Modern Greek orthography for el-GR voices."""
    text = sanitize_greek_text(text)
    def replace_letters(match: re.Match[str]) -> str:
        return " ".join(MODERN_LETTERS.get(c, c) for c in match.group())

    text = LETTERS_RE.sub(replace_letters, text)
    output: list[str] = []
    for c in ud.normalize("NFD", text):
        if c in "\u0300\u0342":
            output.append("\u0301")  # grave/circumflex become tonos
        elif not ud.combining(c) or c in "\u0301\u0308":
            output.append(c)  # strip breathings & iota subscript
    normalized = ud.normalize("NFC", "".join(output)).replace("·", ",").replace("·", ",").replace("᾿", "’")

    def accent_and_spelling(match: re.Match[str]) -> str:
        token = match.group()
        if token.lower() in MODERN_MONOSYLLABLES:
            token = ud.normalize("NFC", "".join(c for c in ud.normalize("NFD", token) if c != "\u0301"))
        if respelled and token.lower() in MODERN_RESPELLINGS:
            replacement = MODERN_RESPELLINGS[token.lower()]
            token = replacement.capitalize() if token[0].isupper() else replacement
        return token

    return WORD_RE.sub(accent_and_spelling, normalized)


def chunks_by_clause(text: str) -> list[str]:
    parts = [p.strip() for p in re.findall(r"[^,··.!?;;]+[,··.!?;;]?", text) if p.strip()]
    return parts or [text.strip()]


def phrase_plan(text: str, pauses: dict[str, float] | None = None) -> list[dict[str, Any]]:
    pauses = DEFAULT_PAUSES if pauses is None else pauses
    fold = lambda value: re.sub(r"\s+", " ", value).strip()
    remaining = fold(text)
    groups: list[dict[str, Any]] = []

    for greek, boundary in OPENING_GROUPS:
        if remaining.startswith(greek):
            groups.append({"greek": greek, "boundary": boundary})
            remaining = remaining[len(greek):].strip()
            if not remaining:
                break

    if remaining:
        for greek in chunks_by_clause(remaining):
            boundary = (
                "sentence"
                if greek.endswith((".", "!", "?", ";", ";"))
                else "section"
                if greek.endswith(("·", "·"))
                else "comma"
            )
            groups.append({"greek": greek, "boundary": boundary})

    for i, group in enumerate(groups):
        group["pause_after_seconds"] = pauses[group["boundary"]] if i < len(groups) - 1 else 0.0
    return groups


def trim_edges(data: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    active = np.flatnonzero(np.abs(data) > 0.001)
    if not len(active):
        return data
    pad = int(0.08 * sr)
    return data[max(0, int(active[0]) - pad):min(len(data), int(active[-1]) + pad + 1)]


def level_speech_fast(data: np.ndarray, sr: int = SAMPLE_RATE, use_ffmpeg: bool = True) -> np.ndarray:
    """Apply gentle 2:1 compression & peak limiting from euclid-tts."""
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if not data.size:
        return data
    if use_ffmpeg:
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                    "-af", SPEECH_LEVEL_FILTER,
                    "-f", "f32le", "pipe:1",
                ],
                input=data.astype("<f4").tobytes(),
                capture_output=True,
                check=True,
                timeout=5,
            )
            leveled = np.frombuffer(result.stdout, dtype="<f4").copy()
            if len(leveled) == len(data) and np.isfinite(leveled).all():
                return leveled
        except Exception:
            pass
    # Fallback pure-NumPy peak normalization
    peak = float(np.max(np.abs(data)))
    if peak > 1e-4:
        return np.clip(data * min(1.8, 0.85 / peak), -0.89, 0.89)
    return data


def read_wav_mono24k(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as f:
        sr = f.getframerate()
        nch = f.getnchannels()
        sw = f.getsampwidth()
        raw = f.readframes(f.getnframes())
    if sw == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw}")
    if nch > 1:
        arr = arr.reshape(-1, nch).mean(axis=1)
    if sr != SAMPLE_RATE:
        # Linear interpolation resample to 24000 Hz
        duration = len(arr) / sr
        target_len = int(round(duration * SAMPLE_RATE))
        arr = np.interp(
            np.linspace(0.0, len(arr) - 1, target_len),
            np.arange(len(arr)),
            arr,
        ).astype(np.float32)
        sr = SAMPLE_RATE
    return arr, sr


def write_wav_mono24k(path: Path, data: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if not data.size:
        return
    peak = float(np.max(np.abs(data)))
    gain = min(1.0, 0.89 / peak) if peak > 0 else 1.0
    pcm = np.rint(data * gain * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())


class KokoroEngine:
    """Pre-loaded local Kokoro-82M ONNX engine reusing euclid-tts's HuggingFace cache."""

    MODEL_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
    MODEL_REVISION = "1939ad2a8e416c0acfeecc08a694d14ef25f2231"
    VOCAB_REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"

    def __init__(self, cache_dir: Path, default_voice: str = "af_heart") -> None:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        from onnxruntime import InferenceSession, SessionOptions

        self.cache_dir = cache_dir
        os.environ.setdefault("HF_HOME", str(cache_dir))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

        def download(repo: str, filename: str, revision: str) -> Path:
            args = dict(repo_id=repo, filename=filename, revision=revision, cache_dir=cache_dir, token=False)
            try:
                return Path(hf_hub_download(**args, local_files_only=True))
            except LocalEntryNotFoundError:
                return Path(hf_hub_download(**args))

        self._download = download
        config_path = download("hexgrad/Kokoro-82M", "config.json", self.VOCAB_REVISION)
        model_path = download(self.MODEL_REPO, "onnx/model_quantized.onnx", self.MODEL_REVISION)

        self.vocab: dict[str, int] = json.loads(config_path.read_text(encoding="utf-8"))["vocab"]
        self.voices: dict[str, np.ndarray] = {}

        options = SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        self._load_voice(default_voice)

    def _load_voice(self, voice: str) -> np.ndarray:
        if voice not in self.voices:
            vpath = self._download(self.MODEL_REPO, f"voices/{voice}.bin", self.MODEL_REVISION)
            self.voices[voice] = np.fromfile(vpath, dtype=np.float32).reshape(-1, 1, 256)
        return self.voices[voice]

    def synthesize_clause(self, greek_text: str, voice: str, rate: float) -> np.ndarray:
        styles = self._load_voice(voice)
        phonemes = engine_phonemes(erasmian(greek_text), "kokoro")
        ids = [self.vocab[p] for p in phonemes if p in self.vocab]
        if not ids:
            return np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)
        ids = ids[:508]
        wave_data = self.session.run(
            None,
            {
                "input_ids": np.array([[0, *ids, 0]], dtype=np.int64),
                "style": styles[min(len(ids), len(styles) - 1)],
                "speed": np.array([rate], dtype=np.float32),
            },
        )[0]
        return trim_edges(np.asarray(wave_data, dtype=np.float32).reshape(-1), SAMPLE_RATE)


@dataclass
class SentenceAudioChunk:
    index: int
    english: str
    greek: str
    pcm: np.ndarray
    duration_s: float
    synthesis_ms: float
    backend: str
    voice: str


class GreekTTSAdapter:
    """Low-latency sentence-by-sentence Ancient Greek TTS adapter."""

    def __init__(self, cfg: Config, preload_kokoro: bool = True) -> None:
        self.cfg = cfg
        self._google_session: Any = None
        self._kokoro: KokoroEngine | None = None

        # Pre-authenticate Google Cloud TTS session & warm up OAuth2 token + TLS socket at startup
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession, Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            credentials.refresh(Request())
            self._google_session = AuthorizedSession(credentials)
            # Warm up TLS socket to texttospeech.googleapis.com so Turn 1 has no cold handshake
            self._google_session.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                json={
                    "input": {"text": "α"},
                    "voice": {"languageCode": "el-GR", "name": self.cfg.tts_voice_modern},
                    "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SAMPLE_RATE},
                },
                timeout=10,
            )
        except Exception:
            self._google_session = None

        if preload_kokoro:
            self._ensure_kokoro()

    def _ensure_kokoro(self) -> KokoroEngine:
        if self._kokoro is None:
            hf_cache = self.cfg.euclid_tts_path / ".cache/huggingface"
            if not hf_cache.exists():
                hf_cache = self.cfg.cache_dir / "huggingface"
            self._kokoro = KokoroEngine(hf_cache, default_voice=self.cfg.tts_voice_kokoro)
        return self._kokoro

    def _google_synthesize_ssml(self, ssml: str, voice: str, language_code: str, rate: float) -> np.ndarray:
        if self._google_session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self._google_session = AuthorizedSession(credentials)

        payload = {
            "input": {"ssml": ssml},
            "voice": {"languageCode": language_code, "name": voice},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "speakingRate": rate,
            },
        }
        response = self._google_session.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            json=payload,
            timeout=20,
        )
        if not response.ok:
            err = response.json().get("error", {})
            raise RuntimeError(f"Google Cloud TTS HTTP {response.status_code}: {err.get('status')}")
        raw = base64.b64decode(response.json()["audioContent"])
        with wave.open(io.BytesIO(raw), "rb") as f:
            samples = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        return trim_edges(samples, SAMPLE_RATE)

    def synthesize_sentence(
        self,
        greek_sentence: str,
        *,
        english_sentence: str = "",
        index: int = 0,
        backend: str | None = None,
        voice: str | None = None,
        rate: float | None = None,
    ) -> SentenceAudioChunk:
        """Synthesize a single Greek sentence into 24 kHz mono float32 PCM in memory."""
        t0 = time.perf_counter()
        active_backend = backend or self.cfg.tts_backend
        active_voice = voice or self.cfg.active_tts_voice(active_backend)
        active_rate = rate if rate is not None else self.cfg.tts_rate

        plan = phrase_plan(greek_sentence)

        if active_backend == "google_erasmian":
            pieces: list[str] = []
            for i, group in enumerate(plan):
                pieces.append(erasmian_ssml_words(group["greek"]))
                if i < len(plan) - 1 and group["pause_after_seconds"] > 0:
                    pieces.append(f'<break time="{round(1000 * group["pause_after_seconds"])}ms"/>')
            ssml = "<speak>" + " ".join(pieces) + "</speak>"
            pcm = self._google_synthesize_ssml(ssml, active_voice, "en-US", active_rate)

        elif active_backend == "google_modern":
            pieces = []
            for i, group in enumerate(plan):
                pieces.append(escape(modern(group["greek"])))
                if i < len(plan) - 1 and group["pause_after_seconds"] > 0:
                    pieces.append(f'<break time="{round(1000 * group["pause_after_seconds"])}ms"/>')
            ssml = "<speak>" + " ".join(pieces) + "</speak>"
            pcm = self._google_synthesize_ssml(ssml, active_voice, "el-GR", active_rate)

        elif active_backend == "kokoro_erasmian":
            kokoro = self._ensure_kokoro()
            clips: list[np.ndarray] = []
            for group in plan:
                clip = kokoro.synthesize_clause(group["greek"], active_voice, active_rate)
                clips.append(clip)
                if group["pause_after_seconds"] > 0:
                    clips.append(np.zeros(round(SAMPLE_RATE * group["pause_after_seconds"]), dtype=np.float32))
            pcm = np.concatenate(clips) if clips else np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)

        elif active_backend == "macos_modern":
            normalized = modern(greek_sentence)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                aiff_file = tmp_path / "out.aiff"
                wav_file = tmp_path / "out.wav"
                subprocess.run(
                    ["say", "-v", "Melina", "-r", str(round(175 * active_rate)), "-o", str(aiff_file), normalized],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(aiff_file), "-ac", "1", "-ar", str(SAMPLE_RATE),
                        "-c:a", "pcm_s16le", str(wav_file),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                pcm, _ = read_wav_mono24k(wav_file)
                pcm = trim_edges(pcm, SAMPLE_RATE)
        else:
            raise ValueError(f"Unsupported TTS backend: {active_backend}")

        if self.cfg.tts_level_speech and active_backend in {"google_erasmian", "kokoro_erasmian"}:
            pcm = level_speech_fast(pcm, SAMPLE_RATE, use_ffmpeg=True)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        duration_s = len(pcm) / float(SAMPLE_RATE)
        return SentenceAudioChunk(
            index=index,
            english=english_sentence,
            greek=greek_sentence,
            pcm=pcm,
            duration_s=round(duration_s, 3),
            synthesis_ms=round(elapsed_ms, 1),
            backend=active_backend,
            voice=active_voice,
        )

    def synthesize_sentences_iter(
        self,
        sentences: list[dict[str, str]],
        *,
        backend: str | None = None,
        voice: str | None = None,
        rate: float | None = None,
    ) -> Iterator[SentenceAudioChunk]:
        """Yield synthesized sentence chunks one-by-one for speculative pre-synthesis."""
        for idx, s in enumerate(sentences):
            yield self.synthesize_sentence(
                s["greek"],
                english_sentence=s.get("english", ""),
                index=idx,
                backend=backend,
                voice=voice,
                rate=rate,
            )
