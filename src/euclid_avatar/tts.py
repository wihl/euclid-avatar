"""Low-latency Male Australian English + Erasmian Ancient Greek TTS adapter."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Iterator
import unicodedata as ud
import wave
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from .config import Config

SAMPLE_RATE = 24000
WORD_RE = re.compile(r"(?:(?![·;])[\u0370-\u03ff\u1f00-\u1fff])+")
LETTERS_RE = re.compile(r"\b[Α-Ω]+\b")
BREAK_MARKER_RE = re.compile(r"\[\[break:(\d+ms|\d+(?:\.\d+)?s)\]\]")

CONVENTION = "bird-handout-and-class-2026-10-08"

# Constants for audio trimming, normalization, and pacing
EDGE_TRIM_THRESHOLD = 0.001
EDGE_PAD_SECONDS = 0.08
PEAK_LIMIT = 0.89
MAX_FALLBACK_GAIN = 1.8
NORM_TARGET_PEAK = 0.85
PCM16_SCALE = 32767.0
PCM16_DIVISOR = 32768.0
PCM32_DIVISOR = 2147483648.0
KOKORO_MAX_TOKENS = 508
MACOS_BASE_WPM = 175
BILINGUAL_JOIN_PAUSE_S = 0.35

# 1. Verified Proposition I.23 + Proposition II.13 + Proposition II.12 + Book I/II Definitions lexicon
# Uses internal diphthong tokens: A=aɪ, I=eɪ, O=oʊ (US) / əʊ (AU), W=aʊ
# Audited against Graeme Bird's MATH E-139 course convention (bird-handout-and-class-2026-10-08).
LEXICON: dict[str, str] = {
    # Verified 58 I.23 words from euclid-tts/src/euclid_tts/pronunciation.py
    "πρὸς": "pɹɔs",
    "πρός": "pɹɔs",
    "τῇ": "tI",
    "δοθείσῃ": "dɔˈθIsI",
    "εὐθείᾳ": "juːˈθIɑ",
    "καὶ": "kA",
    "καί": "kA",
    "τῷ": "tO",
    "αὐτῇ": "aʊˈtI",
    "σημείῳ": "sIˈmIO",
    "γωνίᾳ": "ɡOˈniːɑ",
    "εὐθυγράμμῳ": "juːθyˈɡɹɑmO",
    "ἴσην": "ˈiːsIn",
    "γωνίαν": "ɡOˈniːɑn",
    "εὐθύγραμμον": "juːˈθyɡɹɑmɔn",
    "συστήσασθαι": "syˈstIsɑsθA",
    "ἔστω": "ˈɛstO",
    "ἡ": "hI",
    "μὲν": "mɛn",
    "μέν": "mɛn",
    "δοθεῖσα": "dɔˈθIsɑ",
    "εὐθεῖα": "juːˈθIɑ",
    "τὸ": "tɔ",
    "τό": "tɔ",
    "δὲ": "dɛ",
    "δέ": "dɛ",
    "σημεῖον": "sIˈmIɔn",
    "γωνία": "ɡOˈniːɑ",
    "γωνίας": "ɡOˈniːɑs",
    "εὐθύγραμμος": "juːˈθyɡɹɑmɔs",
    "ὑπὸ": "hyˈpɔ",
    "ὑπό": "hyˈpɔ",
    "δεῖ": "dI",
    "δὴ": "dɛ",
    "δή": "dɛ",
    "εἰλήφθω": "IˈlIfθO",
    "ἐφ᾿": "ɛf",
    "ἐφ'": "ɛf",
    "ἑκατέρας": "hɛkɑˈtɛɹɑs",
    "τῶν": "tOn",
    "τυχόντα": "tyˈxɔntɑ",
    "σημεῖα": "sIˈmIɑ",
    "τὰ": "tɑ",
    "τά": "tɑ",
    "ἐπεζεύχθω": "ɛpɛˈzjuːxθO",
    "ἐκ": "ɛk",
    "τριῶν": "tɹɪˈOn",
    "εὐθειῶν": "juːθIˈOn",
    "αἵ": "hA",
    "αἱ": "hA",
    "εἰσιν": "Isɪn",
    "εἰσὶν": "Iˈsiːn",
    "εἰσίν": "Iˈsiːn",
    "ἴσαι": "ˈiːsA",
    "τρισὶ": "tɹɪˈsiː",
    "ταῖς": "tAs",
    "τρίγωνον": "ˈtɹiːɡOnɔn",
    "συνεστάτω": "synɛˈstɑtO",
    "ὥστε": "ˈhOstɛ",
    "εἶναι": "ˈInA",
    "τὴν": "tIn",
    "τήν": "tIn",
    "ἔτι": "ˈɛtɪ",
    "ἐπεὶ": "ɛˈpI",
    "οὖν": "uːn",
    "δύο": "ˈdyɔ",
    "ἑκατέρα": "hɛkɑˈtɛɹɑ",
    "ἑκατέρᾳ": "hɛkɑˈtɛɹɑ",
    "βάσις": "ˈbɑsɪs",
    "βάσει": "ˈbɑsI",
    "ἴση": "ˈiːsI",
    "ἄρα": "ˈɑɹɑ",
    "ἐστιν": "ɛstɪn",
    "ἐστὶν": "ɛˈstiːn",
    "ἐστίν": "ɛˈstiːn",
    "ἐστι": "ɛˈstiː",
    "ἐστί": "ɛˈstiː",
    "ἐστὶ": "ɛˈstiː",
    "συνέσταται": "syˈnɛstɑtA",
    "ὅπερ": "ˈhɔpɛɹ",
    "ἔδει": "ˈɛdI",
    "ποιῆσαι": "pɔɪˈIsA",
    # Complete Book II Proposition 13 & 12 + Book I/II Definitions vocabulary (2026-project-ii13)
    "ἐν": "ɛn",
    "τοῖς": "tɔɪs",
    "ὀξυγωνίοις": "ɔksyɡOˈniːɔɪs",
    "ὀξυγώνιον": "ɔksyˈɡOnɪɔn",
    "τριγώνοις": "tɹɪˈɡOnɔɪs",
    "ἀπὸ": "ɑˈpɔ",
    "ἀπό": "ɑˈpɔ",
    "τῆς": "tIs",
    "ὀξεῖαν": "ɔkˈsIɑn",
    "ὀξείᾳ": "ɔkˈsIɑ",
    "ὀξεῖα": "ɔkˈsIɑ",
    "ὑποτεινούσης": "hypɔtIˈnuːsIs",
    "ὑποτενούσης": "hypɔtIˈnuːsIs",
    "ὑποτείνουσα": "hypɔˈtInuːsɑ",
    "ὑποτείνω": "hypɔˈtInO",
    "πλευρᾶς": "pljuːˈɹɑs",
    "πλευρῶν": "pljuːˈɹOn",
    "πλευράς": "pljuːˈɹɑs",
    "πλευρὰς": "pljuːˈɹɑs",
    "τετράγωνον": "tɛˈtɹɑɡOnɔn",
    "τετραγώνων": "tɛtɹɑˈɡOnOn",
    "τετράγωνα": "tɛˈtɹɑɡOnɑ",
    "τετραγώνῳ": "tɛtɹɑˈɡOnO",
    "τετραγώνοις": "tɛtɹɑˈɡOnɔɪs",
    "τετραγώνιος": "tɛtɹɑˈɡOnɪɔs",
    "ἔλαττόν": "ˈɛlɑtɔn",
    "ἔλαττον": "ˈɛlɑtɔn",
    "ἐλάττων": "ɛˈlɑtOn",
    "ἐλάσσων": "ɛˈlɑsOn",
    "περιεχουσῶν": "pɛɹɪɛxuːˈsOn",
    "περιέχουσαι": "pɛɹɪˈɛxuːsA",
    "περιεχομένῳ": "pɛɹɪɛxɔˈmɛnO",
    "περιεχόμενος": "pɛɹɪɛˈxɔmɛnɔs",
    "περιεχόμενον": "pɛɹɪɛˈxɔmɛnɔn",
    "περιέχεσθαι": "pɛɹɪˈɛxɛsθA",
    "περιέχω": "pɛɹɪˈɛxO",
    "δὶς": "diːs",
    "δίς": "diːs",
    "τε": "tɛ",
    "μιᾶς": "mɪˈɑs",
    "περὶ": "pɛˈɹiː",
    "περί": "pɛˈɹiː",
    "ἣν": "hIn",
    "ἥν": "hIn",
    "κάθετος": "ˈkɑθɛtɔs",
    "καθέτου": "kɑˈθɛtuː",
    "πίπτει": "ˈpiːptI",
    "πίπτω": "ˈpiːptO",
    "ἀπολαμβανομένης": "ɑpɔlɑmbɑnɔˈmɛnIs",
    "ἀπολαμβάνω": "ɑpɔlɑmˈbɑnO",
    "ἐντὸς": "ɛnˈtɔs",
    "ἐντός": "ɛnˈtɔs",
    "ἐκτὸς": "ɛkˈtɔs",
    "ἐκτός": "ɛkˈtɔs",
    "ἔχον": "ˈɛxɔn",
    "ἔχω": "ˈɛxO",
    "ἤχθω": "ˈIxθO",
    "ἄγω": "ˈɑɡO",
    "ἦγμαι": "ˈIɡmA",
    "τοῦ": "tuː",
    "σημείου": "sIˈmIuː",
    "ἐπὶ": "ɛˈpiː",
    "ἐπί": "ɛˈpiː",
    "λέγω": "ˈlɛɡO",
    "λέγεται": "ˈlɛɡɛtA",
    "ὅτι": "ˈhɔtɪ",
    "ὀρθογωνίῳ": "ɔɹθɔɡOˈniːO",
    "ὀρθογώνιον": "ɔɹθɔˈɡOnɪɔn",
    "ὀρθογωνίοις": "ɔɹθɔɡOˈniːɔɪs",
    "γὰρ": "ɡɑɹ",
    "γάρ": "ɡɑɹ",
    "τέτμηται": "ˈtɛtmItA",
    "τέμνω": "ˈtɛmnO",
    "τέτμημαι": "ˈtɛtmImA",
    "ὡς": "hOs",
    "ἔτυχεν": "ˈɛtyxɛn",
    "τυγχάνω": "tyŋˈxɑnO",
    "ἔτυχον": "ˈɛtyxɔn",
    "κατὰ": "kɑˈtɑ",
    "κατά": "kɑˈtɑ",
    "ἴσα": "ˈiːsɑ",
    "ἴσον": "ˈiːsɔn",
    "κοινὸν": "kɔɪˈnɔn",
    "κοινόν": "kɔɪˈnɔn",
    "προσκείσθω": "pɹɔsˈkIsθO",
    "πρόσκειμαι": "ˈpɹɔskImA",
    "ἀλλὰ": "ɑˈlɑ",
    "ἀλλά": "ɑˈlɑ",
    "ὀρθὴ": "ɔɹˈθI",
    "ὀρθή": "ɔɹˈθI",
    "ὀρθὴν": "ɔɹˈθIn",
    "ὀρθῆς": "ɔɹˈθIs",
    "ὀρθὰς": "ɔɹˈθɑs",
    "ὀρθῶν": "ɔɹˈθOn",
    "μόνον": "ˈmɔnɔn",
    "δεῖξαι": "ˈdIksA",
    "δείκνυμι": "ˈdIknymɪ",
    "ἔδειξα": "ˈɛdIksɑ",
    "εἰμί": "Iˈmiː",
    "δέω": "ˈdɛO",
    # II.12 & Book I/II Definition comparisons & Luschnig examples
    "ἀμβλυγωνίοις": "ɑmblyɡOˈniːɔɪs",
    "ἀμβλεῖαν": "ɑmˈblIɑn",
    "ἀμβλείᾳ": "ɑmˈblIɑ",
    "ἀμβλεῖα": "ɑmˈblIɑ",
    "μεῖζόν": "ˈmIzɔn",
    "μεῖζον": "ˈmIzɔn",
    "μείζων": "ˈmIzOn",
    "πέντε": "ˈpɛntɛ",
    "ἔτεσι": "ˈɛtɛsɪ",
    "ἔτεσιν": "ˈɛtɛsɪn",
    "νεώτερος": "nɛˈOtɛɹɔs",
    "μικρός": "mɪˈkɹɔs",
    "μέγας": "ˈmɛɡɑs",
    "ἤ": "I",
    "οἱ": "hɔɪ",
    "ἀγαθοί": "ɑɡɑˈθɔɪ",
    "ἐφεστηκυῖα": "ɛfɛstIˈkwɪɑ",
    "καλεῖται": "kɑˈlItA",
    # Extended MATH E-139 high-frequency Euclidean vocabulary
    "σημεῖόν": "sIˈmIɔn",
    "οὗ": "huː",
    "μέρος": "ˈmɛɹɔs",
    "οὐθέν": "uːˈθɛn",
    "οὐδέν": "uːˈdɛn",
    "γραμμὴ": "ɡɹɑˈmI",
    "γραμμή": "ɡɹɑˈmI",
    "γραμμῆς": "ɡɹɑˈmIs",
    "γραμμαὶ": "ɡɹɑˈmA",
    "γραμμαί": "ɡɹɑˈmA",
    "μῆκος": "ˈmIkɔs",
    "ἀπλατές": "ɑplɑˈtɛs",
    "πέρατα": "ˈpɛɹɑtɑ",
    "πέρας": "ˈpɛɹɑs",
    "κύκλος": "ˈkyklɔs",
    "κύκλου": "ˈkykluː",
    "κύκλον": "ˈkyklɔn",
    "κέντρον": "ˈkɛntɹɔn",
    "κέντρῳ": "ˈkɛntɹO",
    "διάμετρος": "dɪˈɑmɛtɹɔs",
    "διαστήματι": "dɪɑˈstImɑtɪ",
    "περιφέρεια": "pɛɹɪˈfɛɹIɑ",
    "περιφερείας": "pɛɹɪfɛˈɹIɑs",
    "σχῆμα": "ˈsxImɑ",
    "σχῆμά": "ˈsxImɑ",
    "σχήματος": "ˈsxImɑtɔs",
    "σχήματα": "ˈsxImɑtɑ",
    "ἐπίπεδον": "ɛˈpiːpɛdɔn",
    "ἐπιπέδῳ": "ɛpɪˈpɛdO",
    "ἐπιφάνεια": "ɛpɪˈfɑnIɑ",
    "παράλληλοι": "pɑˈɹɑlIlɔɪ",
    "παράλληλοί": "pɑˈɹɑlIlɔɪ",
    "ἰσόπλευρον": "ɪˈsɔpljuːɹɔn",
    "ἰσοσκελὲς": "ɪsɔskɛˈlɛs",
    "ἰσοσκελές": "ɪsɔskɛˈlɛs",
    "ἀλλήλοις": "ɑˈlIlɔɪs",
    "ἀλλήλαις": "ɑˈlIlAs",
    "πρότασις": "ˈpɹɔtɑsɪs",
    "ἔκθεσις": "ˈɛkθɛsɪs",
    "διορισμός": "dɪɔɹɪˈsmɔs",
    "κατασκευή": "kɑtɑskjuːˈI",
    "ἀπόδειξις": "ɑˈpɔdIksɪs",
    "συμπέρασμα": "symˈpɛɹɑsmɑ",
}

# 2. All 24 Greek uppercase letters for geometric point labels (Α–Ω)
# Uses elongated vowels and syllable boundaries so geometric labels (ΑΓ, ΓΒ, ΒΑ, ΒΔ) are recited slowly and distinctly.
ERASMIAN_LETTERS: dict[str, str] = {
    "Α": "ˈɑːl.fɑː",
    "Β": "ˈbI.tɑː",
    "Γ": "ˈɡɑːm.mɑː",
    "Δ": "ˈdɛl.tɑː",
    "Ε": "ˈɛp.sɪ.lɔn",
    "Ζ": "ˈzI.tɑː",
    "Η": "ˈI.tɑː",
    "Θ": "ˈθI.tɑː",
    "Ι": "ɪˈO.tɑː",
    "Κ": "ˈkɑːp.pɑː",
    "Λ": "ˈlɑːm.dɑː",
    "Μ": "ˈmy",
    "Ν": "ˈny",
    "Ξ": "ˈksA",
    "Ο": "ˈɔ.mɪ.kɹɔn",
    "Π": "ˈpA",
    "Ρ": "ˈɹO",
    "Σ": "ˈsɪɡ.mɑː",
    "Τ": "ˈtW",
    "Υ": "ˈyp.sɪ.lɔn",
    "Φ": "ˈfA",
    "Χ": "ˈxA",
    "Ψ": "ˈpsA",
    "Ω": "Oˈmɛ.ɡɑː",
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
    "y": {
        "engine_ipa": "uː",
        "reason": "English TTS lacks /y/; /uː/ preserves high rounded quality",
    },
    "x": {
        "engine_ipa": "k",
        "reason": "English TTS lacks /x/; /k/ preserves velar place",
    },
}

MODERN_MONOSYLLABLES = {
    "πρός",
    "τή",
    "καί",
    "τώ",
    "μέν",
    "τό",
    "δέ",
    "δή",
    "δεί",
    "τών",
    "τά",
    "έκ",
    "αί",
    "ταίς",
    "τήν",
    "ούν",
    "ή",
    "ο",
    "οι",
    "εν",
    "εις",
    "ως",
    "μη",
    "ου",
}

MODERN_RESPELLINGS = {
    "δοθείση": "δοθίσι",
    "δοθείσα": "δοθίσα",
    "ευθεία": "εφθία",
    "αυτή": "αφτή",
    "σημείω": "σιμίο",
    "σημείον": "σιμίον",
    "ευθυγράμμω": "εφθιγράμμο",
    "ευθύγραμμον": "εφθίγραμμον",
    "ευθύγραμμος": "εφθίγραμμος",
    "ίσην": "ίσιν",
    "συστήσασθαι": "σιστίσασθε",
}

DEFAULT_PAUSES = {"phrase": 0.40, "comma": 0.50, "section": 0.70, "sentence": 0.80}

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
    "acompressor=threshold=0.158489:ratio=1.25:attack=45:release=350:"
    "makeup=1.15:detection=rms,"
    "alimiter=limit=0.89:attack=5:release=50:level=0:latency=1"
)


def erasmian_g2p_word(token: str) -> str:
    """Rule-based polytonic Ancient Greek to course-target Erasmian IPA (Kokoro tokens A/I/O/W)."""
    norm = ud.normalize("NFC", token.strip("᾿'’"))
    if not norm:
        return "ɛ"
    lower_key = norm.lower()
    if lower_key in LEXICON:
        return LEXICON[lower_key]

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
            letters.append(
                {"ch": ch, "rough": False, "accent": False, "diaeresis": False}
            )

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

    units: list[dict[str, Any]] = []
    has_initial_h = any(letter["rough"] for letter in letters[:2])

    i = 0
    n = len(letters)
    while i < n:
        c1 = letters[i]["ch"]
        c2 = letters[i + 1]["ch"] if i + 1 < n else ""
        pair = c1 + c2

        if pair in diphthongs and not letters[i + 1]["diaeresis"]:
            acc = letters[i]["accent"] or letters[i + 1]["accent"]
            units.append({"ph": diphthongs[pair], "is_vowel": True, "accent": acc})
            i += 2
            continue

        if pair in {"γγ", "γκ", "γχ", "γξ"}:
            mapping = {"γγ": "ŋɡ", "γκ": "ŋk", "γχ": "ŋx", "γξ": "ŋks"}[pair]
            units.append({"ph": mapping, "is_vowel": False, "accent": False})
            i += 2
            continue
        if pair in {"λλ", "μμ", "νν", "ππ", "ρρ", "σσ", "ττ", "κκ"}:
            i += 1
            continue

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

    vowel_indices = [idx for idx, u in enumerate(units) if u["is_vowel"]]
    accented_vowel_indices = [
        idx for idx, u in enumerate(units) if u["is_vowel"] and u["accent"]
    ]

    if len(vowel_indices) >= 2:
        target_v = (
            accented_vowel_indices[0]
            if accented_vowel_indices
            else vowel_indices[0]
        )
        stress_pos = target_v
        if stress_pos > 0 and not units[stress_pos - 1]["is_vowel"]:
            if target_v == vowel_indices[0]:
                stress_pos = 0
            else:
                stress_pos = target_v - 1
                if (
                    stress_pos > 0
                    and not units[stress_pos - 1]["is_vowel"]
                    and units[stress_pos]["ph"] in {"ɹ", "l"}
                    and units[stress_pos - 1]["ph"]
                    in {"p", "t", "k", "b", "d", "ɡ", "f", "θ", "x"}
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
    "a": "α",
    "e": "ε",
    "i": "ι",
    "o": "ο",
    "u": "υ",
    "y": "υ",
    "k": "κ",
    "m": "μ",
    "n": "ν",
    "p": "π",
    "t": "τ",
    "x": "χ",
    "b": "β",
    "d": "δ",
    "g": "γ",
    "A": "Α",
    "B": "Β",
    "E": "Ε",
    "Z": "Ζ",
    "H": "Η",
    "I": "Ι",
    "K": "Κ",
    "M": "Μ",
    "N": "Ν",
    "O": "Ο",
    "P": "Ρ",
    "T": "Τ",
    "X": "Χ",
    "Y": "Υ",
})


def sanitize_greek_text(text: str) -> str:
    """Fix stray Latin homoglyphs inside Greek words while leaving pure English words untouched."""

    def fix_mixed_token(match: re.Match[str]) -> str:
        tok = match.group(0)
        if not re.search(r"[\u0370-\u03ff\u1f00-\u1fff]", tok):
            return tok
        converted = tok.translate(LATIN_TO_GREEK_INNER)
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
            return " ".join(
                ERASMIAN_LETTERS.get(c, erasmian_g2p_word(c)) for c in token
            )
        key = ud.normalize("NFC", token.lower())
        if key in LEXICON:
            return LEXICON[key]
        return erasmian_g2p_word(token)

    result = WORD_RE.sub(replace_word, text).replace("·", ";").replace("·", ";")
    return re.sub(r"\s+", " ", result).replace("g", "ɡ").replace("aʊ", "W")


def ipa(phonemes: str, locale: str = "en-US") -> str:
    """Expand diphthong tokens into IPA for the target voice locale."""
    is_au = locale.lower().startswith("en-au")
    o_diphthong = "əʊ" if is_au else "oʊ"
    for token, value in {
        "A": "aɪ",
        "I": "eɪ",
        "O": o_diphthong,
        "W": "aʊ",
    }.items():
        phonemes = phonemes.replace(token, value)
    return phonemes


def engine_phonemes(phonemes: str, backend: str, voice: str = "") -> str:
    """Map Erasmian phoneme string to engine-specific IPA inventory (en-AU, en-US, or Kokoro)."""
    if backend in {"kokoro", "kokoro_erasmian"}:
        return phonemes
    is_au = voice.lower().startswith("en-au") or backend == "google_au_bilingual"
    locale = "en-AU" if is_au else "en-US"
    result = ipa(phonemes, locale=locale)
    for target, substitute in GOOGLE_SUBSTITUTIONS.items():
        result = result.replace(target, substitute["engine_ipa"])
    if is_au:
        # Google Cloud en-AU phoneme inventory uses /ɐ/ (open vowel) and /ɒ/ (short rounded back)
        result = result.replace("ɑ", "ɐ")
        return re.sub(r"ɔ(?!ɪ|ː)", "ɒ", result)
    return re.sub(r"ɔ(?!ɪ)", "ɔː", result.replace("ɑ", "ɑː"))


GREEK_LETTER_PRE_POST_BREAK_MS = 220
GREEK_LETTER_INTER_BREAK_MS = 320
GREEK_LETTER_CLAUSE_MAX_RATE = 0.75
PURE_GREEK_WITH_LETTERS_MAX_RATE = 0.70


def erasmian_ssml_words(
    text: str, voice: str = "en-AU-Chirp3-HD-Charon"
) -> str:
    """Wrap each Greek word or geometric letter in an IPA <phoneme> tag for Google Cloud TTS."""
    text = sanitize_greek_text(text)
    is_chirp = "Chirp3-HD" in voice

    def tag(label: str, phonemes: str) -> str:
        eng_ph = engine_phonemes(phonemes, "google_cloud", voice=voice)
        return (
            f'<phoneme alphabet="ipa" ph={quoteattr(eng_ph)}>'
            f"{escape(label)}</phoneme>"
        )

    def word(match: re.Match[str]) -> str:
        token = match.group()
        if re.fullmatch(r"[Α-Ω]+", token):
            letter_tags = [
                tag(c, ERASMIAN_LETTERS.get(c, erasmian(c))) for c in token
            ]
            if is_chirp:
                # Chirp3-HD stretches <break/> tags inside <phoneme> sequences into 1.5-2s gaps;
                # space-separated elongated IPA phonemes ("ˈɑːl.fɑː" "ˈɡɑːm.mɑː") at rate 0.72-0.75
                # give slow, distinct recitation with natural intonation.
                return " ".join(letter_tags)
            inter_break = f'<break time="{GREEK_LETTER_INTER_BREAK_MS}ms"/>'
            inner = f'<prosody rate="70%">{inter_break.join(letter_tags)}</prosody>'
            bound_break = f'<break time="{GREEK_LETTER_PRE_POST_BREAK_MS}ms"/>'
            return f"{bound_break}{inner}{bound_break}"
        tagged = tag(token, erasmian(token))
        if not is_chirp:
            return f'<prosody rate="84%">{tagged}</prosody>'
        return tagged

    parts: list[str] = []
    position = 0
    for match in WORD_RE.finditer(text):
        parts.extend([escape(text[position : match.start()]), word(match)])
        position = match.end()
    parts.append(escape(text[position:]))
    return "".join(parts).replace("·", ";").replace("·", ";")


CHIRP_MAX_GREEK_WORDS_PER_CALL = 8
CHIRP_COMMA_PAUSE_S = 0.24
CHIRP_SECTION_PAUSE_S = 0.34
INLINE_LANG_SWITCH_PAUSE_S = 0.08
EM_DASH_PAUSE_S = 0.14
SENTENCE_PAUSE_S = 0.20
MAX_GOOGLE_SSML_BYTES = 4500
GOOGLE_TTS_V1BETA1_URL = (
    "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
)

EMPHASIS_KEYWORDS_RE = re.compile(
    r"\b("
    r"law of cosines|no cosine|no minus sign|hinge|equation|"
    r"not even the noun|drops? out|nominative|genitive|dative|"
    r"less than|by twice|is less|is greater|completely parallel|"
    r"never appears|not a single noun|left-hand side|standard we are comparing|"
    r"exact amount|degree of difference|grammatical case|feminine|neuter|"
    r"masculine|misprint|Proposition 7|Proposition 47|Pythagorean"
    r")\b",
    re.IGNORECASE,
)

ASIDE_PREFIX_RE = re.compile(
    r"^("
    r"Connor\b|Remember\b|That is the thing\b|Now I'll hand over\b|"
    r"or simply\b|in modern notation\b|which is\b|The two words in bold\b|"
    r"Here is what each word\b|Look at the two halves\b|This is the same claim\b|"
    r"Because every Greek\b|Before the proof\b"
    r")",
    re.IGNORECASE,
)

SIGNPOST_PREFIX_RE = re.compile(
    r"^("
    r"First\b|Second\b|Third\b|Notice\b|Compare\b|And then\b|Why\b|"
    r"Here is\b|What about\b|In Step\b"
    r")",
    re.IGNORECASE,
)


def strip_prosody_markers(text: str) -> str:
    """Remove inline **emphasis** or ~aside~ markers and [[break:...]] tags for display/subtitles."""
    cleaned = BREAK_MARKER_RE.sub(" ", text)
    cleaned = cleaned.replace("**", "").replace("~", "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def normalize_word_for_match(token: str) -> str:
    """Normalize a Greek or English token for robust word-highlighting alignment."""
    stripped = strip_prosody_markers(token)
    stripped = re.sub(
        r"^[^\w\u0370-\u03ff\u1f00-\u1fff]+|[^\w\u0370-\u03ff\u1f00-\u1fff]+$",
        "",
        stripped,
    )
    if not stripped:
        return ""
    # Fold combining accents so Greek tokens match regardless ofgrave/acute context
    nfd = ud.normalize("NFD", stripped.lower().replace("ά", "α"))
    base = "".join(c for c in nfd if not ud.combining(c))
    return ud.normalize("NFC", base)


def infer_diagram_cues(
    phrase_text: str, fallback_text: str = ""
) -> tuple[list[str], str]:
    """Map a spoken Greek/English phrase to active Proposition II.13 SVG diagram cues and caption."""
    probe = strip_prosody_markers(phrase_text)
    cues: list[str] = []
    banner = ""

    def _match(txt: str) -> tuple[list[str], str]:
        found: list[str] = []
        cap = ""
        low = txt.lower()
        # 1. Slide 5 Proof Step 1 (II.7 on ΓΒ cut at Δ)
        if (
            any(
                w in txt
                for w in (
                    "τέτμηται",
                    "τὰ ἄρα ἀπὸ τῶν ΓΒ, ΒΔ",
                    "τῷ τε δὶς ὑπὸ τῶν ΓΒ, ΒΔ",
                )
            )
            or "cut at random" in low
            or "2.7" in low
            or "proposition 7" in low
            or ("c b and b d" in low and "c d" in low)
        ):
            found.extend(["proof_ii7", "seg_CB", "seg_BD", "seg_DC", "node_D"])
            cap = "BOOK II.7 · Line ΓΒ cut at Δ: ΓΒ² + ΒΔ² = 2·ΓΒ·ΒΔ + ΔΓ²"

        # 2. Slide 5 Proof Step 2a (I.47 on right triangle ΑΒΔ)
        if (
            "ΒΔ, ΔΑ" in txt
            or "b d and d a" in low
            or ("ἀπὸ τῆς ΑΒ" in txt and "ἴσον" in txt)
            or ("pythagorean" in low and "c d" not in low)
            or "1.47" in low
        ):
            found.extend(
                ["proof_i47_ABD", "seg_BA", "seg_BD", "seg_AD", "perp_AD"]
            )
            if not cap:
                cap = "BOOK I.47 · Right Triangle △ΑΒΔ: ΑΒ² = ΒΔ² + ΔΑ²"

        # 3. Slide 5 Proof Step 2b (I.47 on right triangle ΑΔΓ)
        if (
            "ΓΔ, ΔΑ" in txt
            or "c d and d a" in low
            or ("ἀπὸ τῆς ΑΓ" in txt and "ἴσον" in txt)
            or "second half of that sentence" in low
        ):
            found.extend(
                ["proof_i47_ADC", "seg_AC", "seg_DC", "seg_AD", "perp_AD"]
            )
            if not cap:
                cap = "BOOK I.47 · Right Triangle △ΑΔΓ: ΑΓ² = ΓΔ² + ΔΑ²"

        # 4. Nominative Square on ΑΓ (τὸ ἀπὸ τῆς ΑΓ τετράγωνον)
        if (
            "ἀπὸ τῆς ΑΓ" in txt
            or "ὑποτεινούσης" in txt
            or "nominative" in low
            or "opposite the acute angle" in low
            or "square on a c" in low
            or "left-hand side" in low
            or (
                re.search(r"\bΑΓ\b", txt)
                and "ΓΔ, ΔΑ" not in txt
                and "ἴσον" not in txt
            )
        ):
            found.extend(["sq_AC", "seg_AC"])
            if not cap:
                cap = "NOMINATIVE (Subject) · □ ΑΓ² — τὸ ἀπὸ τῆς ΑΓ τετράγωνον"

        # 5. Genitive Squares on ΓΒ, ΒΑ (τῶν ἀπὸ τῶν ΓΒ, ΒΑ τετραγώνων)
        if (
            "ΓΒ, ΒΑ" in txt
            or "περιεχουσῶν" in txt
            or "genitive" in low
            or "containing that angle" in low
            or "containing the acute" in low
            or "squares on c b and b a" in low
            or "two squares are bundled" in low
        ):
            found.extend(["sq_CB_BA", "seg_CB", "seg_BA"])
            if not cap:
                cap = 'GENITIVE ("than") · □ ΓΒ² + □ ΒΑ² — τῶν ἀπὸ τῶν ΓΒ, ΒΑ'

        # 6. Dative Double-Rectangle 2·(ΓΒ × ΒΔ)
        if (
            "ΓΒ, ΒΔ" in txt
            or "περιεχομένῳ" in txt
            or "ὀρθογωνίῳ" in txt
            or "ὀρθογώνιον" in txt
            or "dative" in low
            or "twice the rectangle" in low
            or "rectangle contained by" in low
            or "2 c b times b d" in low
            or "two times c b times b d" in low
            or "degree of difference" in low
        ):
            found.extend(["rect_2_CB_BD", "seg_CB", "seg_BD"])
            if not cap:
                cap = 'DATIVE ("by") · 2 rect(ΓΒ, ΒΔ) — τῷ δὶς ὑπὸ τῶν ΓΒ, ΒΔ'

        # 7. Perpendicular ΑΔ (ἡ κάθετος)
        if (
            "κάθετος" in txt
            or "καθέτου" in txt
            or "ΑΔ" in txt
            or "perpendicular" in low
            or "a d" in low
            or "πίπτει" in txt
        ):
            found.extend(["perp_AD", "seg_AD", "node_D"])
            if not cap:
                cap = "PERPENDICULAR · ἡ ΑΔ κάθετος (AD ⊥ ΓΒ at Δ)"

        # 8. Cut-off Projection ΒΔ (ἀπολαμβανομένης ἐντὸς)
        if (
            "ἀπολαμβανομένης" in txt
            or "cuts off inside" in low
            or "cut off inside" in low
            or (
                re.search(r"\bΒΔ\b", txt)
                and "ΓΒ, ΒΔ" not in txt
                and "ΒΔ, ΔΑ" not in txt
            )
        ):
            found.extend(["seg_BD", "acute_triangle"])
            if not cap:
                cap = "PROJECTION · Segment ΒΔ cut off toward acute ∠Β"

        # 9. Hinge comparison (ἔλαττόν ἐστι / μεῖζόν ἐστι)
        if (
            "ἔλαττόν" in txt
            or "ἔλαττον" in txt
            or "μεῖζόν" in txt
            or "is less" in low
            or "hinge" in low
        ):
            found.extend(["hinge_less", "sq_AC", "sq_CB_BA"])
            if not cap:
                cap = "HINGE · ἔλαττόν ἐστι — □ ΑΓ² < □ ΓΒ² + □ ΒΑ²"

        # 10. Full equation / Law of Cosines overview
        if (
            "law of cosines" in low
            or "three grammatical cases" in low
            or "work of an equation" in low
            or "zahid" in low
        ):
            found.extend(["all_equation", "sq_AC", "sq_CB_BA", "rect_2_CB_BD"])
            if not cap:
                cap = "II.13 LAW OF COSINES · ΑΓ² = ΓΒ² + ΒΑ² − 2·ΓΒ·ΒΔ"

        # 11. Acute-angled triangle / Enunciation opening
        if (
            "ὀξυγωνίοις" in txt
            or "τριγώνοις" in txt
            or "ὀξεῖαν" in txt
            or "ὀξείᾳ" in txt
            or "acute-angled" in low
            or "acute angle" in low
        ):
            found.append("acute_triangle")
            if not cap:
                cap = "ACUTE TRIANGLE △ΑΒΓ · Acute Angle at Vertex Β (∠Β)"

        # Dedup while preserving order
        deduped = list(dict.fromkeys(found))
        return deduped, cap

    cues, banner = _match(probe)
    if not cues and fallback_text:
        cues, banner = _match(strip_prosody_markers(fallback_text))
    if not cues:
        cues = ["acute_triangle"]
        banner = "PROPOSITION II.13 · Acute-Angled Triangle △ΑΒΓ with Altitude ΑΔ"
    return cues, banner


def _clause_speaking_rate(
    clause_text: str, english_rate: float, greek_rate: float
) -> float:
    """Select a speaking rate per clause, slowing down for Greek & geometric letters."""
    greek_words = len(WORD_RE.findall(clause_text))
    english_words = len(re.findall(r"[A-Za-z]{2,}", clause_text))
    has_letters = bool(LETTERS_RE.search(clause_text))
    if greek_words > 0 and english_words == 0:
        if has_letters:
            return min(greek_rate, PURE_GREEK_WITH_LETTERS_MAX_RATE)
        return greek_rate
    if greek_words >= english_words and greek_words >= 2:
        return greek_rate
    if has_letters:
        return min(english_rate, GREEK_LETTER_CLAUSE_MAX_RATE)
    return english_rate


def _parse_break_seconds(duration_str: str) -> float:
    text = duration_str.strip().lower()
    if text.endswith("ms"):
        return float(text[:-2]) / 1000.0
    if text.endswith("s"):
        return float(text[:-1])
    return 0.20


# Matches a contiguous run of Greek words (including internal spaces and Greek punctuation)
GREEK_SPAN_RE = re.compile(
    r"[\u0370-\u03ff\u1f00-\u1fff][\u0370-\u03ff\u1f00-\u1fff\s,··;;.᾿'’\-]*[\u0370-\u03ff\u1f00-\u1fff,··;;.]|[\u0370-\u03ff\u1f00-\u1fff]+"
)


def _split_expressive_bilingual_phrases(
    spoken_text: str,
) -> list[tuple[str, str, float]]:
    """Split a bilingual utterance into pure-English and pure-Greek discourse phrases.

    Returns a list of (phrase_text, lang, trailing_pause_s) where lang is 'en' or 'gr'.
    Pure separation prevents Chirp3-HD from slurring Greek <phoneme> tags when mixed
    with English prose, while sentence/dash splitting enables dynamic per-phrase
    variation in tone, speed, and emphasis without chopping mid-sentence on commas.
    """
    raw_chunks: list[tuple[str, float]] = []
    pos = 0
    for match in BREAK_MARKER_RE.finditer(spoken_text):
        chunk = spoken_text[pos : match.start()].strip()
        # Scale down explicit break durations slightly so speech stays cohesive
        pause_s = min(0.28, _parse_break_seconds(match.group(1)) * 0.72)
        if chunk:
            raw_chunks.append((chunk, pause_s))
        pos = match.end()
    tail = spoken_text[pos:].strip()
    if tail:
        raw_chunks.append((tail, 0.0))

    # Step 1: Isolate Greek spans from English spans inside each chunk
    lang_spans: list[tuple[str, str, float]] = []
    for chunk, chunk_pause in raw_chunks:
        has_gr = bool(WORD_RE.search(chunk))
        has_en = bool(re.search(r"[A-Za-z]{2,}", chunk))
        if not has_gr:
            lang_spans.append((chunk, "en", chunk_pause))
            continue
        if not has_en:
            lang_spans.append((chunk, "gr", chunk_pause))
            continue

        # Mixed chunk: split cleanly around GREEK_SPAN_RE
        last_idx = 0
        matches = list(GREEK_SPAN_RE.finditer(chunk))
        for m_idx, m in enumerate(matches):
            before = chunk[last_idx : m.start()].strip()
            if before:
                lang_spans.append((before, "en", INLINE_LANG_SWITCH_PAUSE_S))
            gr_text = m.group().strip()
            after_idx = m.end()
            is_final_part = (
                m_idx == len(matches) - 1 and not chunk[after_idx:].strip()
            )
            gr_pause = (
                chunk_pause if is_final_part else INLINE_LANG_SWITCH_PAUSE_S
            )
            if gr_text:
                lang_spans.append((gr_text, "gr", gr_pause))
            last_idx = after_idx
        rem = chunk[last_idx:].strip()
        if rem:
            lang_spans.append((rem, "en", chunk_pause))

    # Step 2: Refine long Greek spans by clause, and English spans by sentence / em-dash
    refined: list[tuple[str, str, float]] = []
    for text, lang, trailing_pause in lang_spans:
        cleaned = text.strip()
        if not cleaned:
            continue
        if lang == "gr":
            if len(WORD_RE.findall(cleaned)) <= CHIRP_MAX_GREEK_WORDS_PER_CALL:
                # Ensure Greek span ends with sentence punctuation for clean phoneme release
                norm_gr = re.sub(r"[,··;;]+$", ".", cleaned)
                if not norm_gr.endswith((".", "!", "?")):
                    norm_gr += "."
                refined.append((norm_gr, "gr", trailing_pause))
            else:
                clauses = [
                    c.strip()
                    for c in re.split(r"(?<=[,··;;.!?])\s+", cleaned)
                    if c.strip()
                ]
                for idx, clause in enumerate(clauses):
                    is_last = idx == len(clauses) - 1
                    pause = (
                        trailing_pause
                        if is_last
                        else (
                            CHIRP_SECTION_PAUSE_S
                            if clause.endswith((";", ";", "·", "·", ".", "!"))
                            else CHIRP_COMMA_PAUSE_S
                        )
                    )
                    norm_gr = re.sub(r"[,··;;]+$", ".", clause)
                    if not norm_gr.endswith((".", "!", "?")):
                        norm_gr += "."
                    refined.append((norm_gr, "gr", pause))
        else:
            # Keep each full English sentence intact (replacing em-dashes with commas so Chirp3-HD
            # maintains a single unbroken sentence contour without mid-sentence voice resets).
            norm_en = re.sub(r"\s+—\s+", ", ", cleaned)
            raw_parts = [
                p.strip()
                for p in re.split(
                    r'(?<=[.!?])(?:["\'”’*~]+)?\s+',
                    norm_en,
                )
                if p.strip()
            ]
            if not raw_parts:
                raw_parts = [norm_en]
            parts: list[str] = []
            for p in raw_parts:
                w_count = len(re.findall(r"[A-Za-z]+", p))
                if parts and w_count < 4:
                    parts[-1] = f"{parts[-1]} {p}"
                else:
                    parts.append(p)
            if len(parts) > 1 and len(re.findall(r"[A-Za-z]+", parts[0])) < 4:
                parts[1] = f"{parts[0]} {parts[1]}"
                parts.pop(0)
            for idx, part in enumerate(parts):
                is_last = idx == len(parts) - 1
                stripped_part = part.rstrip('"\'”’*~ ')
                if is_last:
                    pause = trailing_pause
                elif stripped_part.endswith((".", "!", "?")):
                    pause = SENTENCE_PAUSE_S
                else:
                    if not stripped_part.endswith((",", ":", ";", ".", "!", "?")):
                        part = part + ","
                    pause = EM_DASH_PAUSE_S
                refined.append((part, "en", pause))
    return refined


# Consistent higher-pitch calibration (semitones) so the entire presentation uses one clear voice
UNIFORM_HIGHER_PITCH_ST = 1.25


def _compute_phrase_prosody(
    phrase_text: str,
    lang: str,
    phrase_idx: int,
    eng_rate: float,
    grk_rate: float,
    prev_bucket: str = "",
) -> tuple[float, str | None, str | None, float, float, str]:
    """Compute (speaking_rate, ssml_pitch, ssml_rate, dsp_pitch_st, dsp_gain_db, bucket) for a phrase.

    Keeps the voice identity and pitch strictly uniform at UNIFORM_HIGHER_PITCH_ST across all
    English and Greek phrases (so the voice never changes within or between sentences), while
    varying speaking rate and subtle emphasis gain naturally across sentences.
    """
    if lang == "gr":
        has_letters = bool(LETTERS_RE.search(phrase_text))
        if has_letters:
            rate = min(grk_rate, 0.76)
            return (rate, None, None, UNIFORM_HIGHER_PITCH_ST, 1.1, "gr_letters")
        return (grk_rate, None, None, UNIFORM_HIGHER_PITCH_ST, 1.0, "gr_clause")

    plain = strip_prosody_markers(phrase_text)
    has_bold = "**" in phrase_text
    has_aside = "~" in phrase_text or bool(ASIDE_PREFIX_RE.search(plain))
    has_signpost = bool(SIGNPOST_PREFIX_RE.search(plain)) or plain.endswith(
        ("?", ":")
    )
    has_emphasis = has_bold or plain.endswith("!")

    if has_aside and not has_bold:
        rate = min(1.06, max(0.92, eng_rate * 1.06))
        return (rate, None, None, UNIFORM_HIGHER_PITCH_ST, 0.4, "en_aside")

    if has_emphasis:
        rate = min(0.98, max(0.86, eng_rate * 0.96))
        return (rate, None, None, UNIFORM_HIGHER_PITCH_ST, 1.4, "en_emphasis")

    if has_signpost:
        rate = min(1.02, max(0.88, eng_rate * 1.00))
        return (rate, None, None, UNIFORM_HIGHER_PITCH_ST, 1.0, "en_signpost")

    step = phrase_idx % 2
    if step == 0:
        return (
            min(1.04, eng_rate * 1.02),
            None,
            None,
            UNIFORM_HIGHER_PITCH_ST,
            0.7,
            "en_narrative_a",
        )
    return (
        max(0.89, eng_rate * 0.98),
        None,
        None,
        UNIFORM_HIGHER_PITCH_ST,
        0.9,
        "en_narrative_b",
    )


def _shape_phrase_pcm(
    pcm: np.ndarray,
    pitch_semitones: float,
    gain_db: float,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    """Apply subtle, natural pitch inflection and dynamic emphasis gain via fast in-memory FFmpeg pipe."""
    if pcm.size == 0 or (abs(pitch_semitones) < 0.08 and abs(gain_db) < 0.08):
        return pcm
    ratio = 2.0 ** (pitch_semitones / 12.0)
    new_sr = int(round(sr * ratio))
    tempo = 1.0 / ratio
    af = f"asetrate={new_sr},aresample={sr},atempo={tempo:.5f},volume={gain_db:.2f}dB"
    try:
        res = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "f32le",
                "-ar",
                str(sr),
                "-ac",
                "1",
                "-i",
                "pipe:0",
                "-af",
                af,
                "-f",
                "f32le",
                "pipe:1",
            ],
            input=pcm.astype("<f4").tobytes(),
            capture_output=True,
            check=True,
            timeout=5,
        )
        shaped = np.frombuffer(res.stdout, dtype="<f4").copy()
        if shaped.size > 0 and np.isfinite(shaped).all():
            return np.clip(shaped, -PEAK_LIMIT, PEAK_LIMIT)
    except Exception:
        pass
    gain_lin = 10.0 ** (gain_db / 20.0)
    return np.clip(pcm * gain_lin, -PEAK_LIMIT, PEAK_LIMIT)


def _extract_phrase_word_timings(
    phrase_text: str,
    clip_pcm: np.ndarray,
    start_time_s: float,
    sr: int,
    base_index: int,
    full_segment_text: str,
) -> list[dict[str, Any]]:
    """Compute energy-aligned start and end timestamps (seconds) for each word in a phrase."""
    clean_text = strip_prosody_markers(phrase_text)
    raw_tokens = [t for t in re.findall(r"\S+", clean_text) if t.strip()]
    if not raw_tokens or clip_pcm.size == 0:
        return []

    dur_s = len(clip_pcm) / float(sr)
    cues, banner = infer_diagram_cues(clean_text, full_segment_text)

    # Compute phonemic duration weights per word
    weights: list[float] = []
    for tok in raw_tokens:
        norm = normalize_word_for_match(tok)
        w = max(1.2, float(len(norm)) * 0.85)
        if LETTERS_RE.search(tok):
            # Uppercase Greek geometric letter pairs ("ΑΓ", "ΓΒ") are spoken as full letter names
            letter_count = sum(1 for c in tok if "Α" <= c <= "Ω")
            w += letter_count * 3.2
        if tok.endswith((",", ";", ":", "—", ".", "!", "?", "·", "·")):
            w += 1.1
        weights.append(w)

    total_w = sum(weights) or 1.0
    cum_fractions = np.cumsum([0.0, *weights]) / total_w

    # Use smoothed amplitude envelope of clip_pcm to warp word boundaries to actual speech bursts
    env_win = max(1, int(0.015 * sr))
    abs_pcm = np.abs(clip_pcm)
    if len(abs_pcm) > env_win * 2:
        kernel = np.ones(env_win, dtype=np.float32) / env_win
        env = np.convolve(abs_pcm, kernel, mode="same") + 0.015
        cum_energy = np.cumsum(env)
        cum_energy = (cum_energy - cum_energy[0]) / max(
            1e-6, float(cum_energy[-1] - cum_energy[0])
        )
        time_axis = np.linspace(0.0, dur_s, len(cum_energy))
        warped_times = np.interp(cum_fractions, cum_energy, time_axis)
        # Blend 65% energy-warped + 35% linear weight so boundaries never bunch unnaturally
        linear_times = cum_fractions * dur_s
        boundary_times = 0.65 * warped_times + 0.35 * linear_times
    else:
        boundary_times = cum_fractions * dur_s

    out: list[dict[str, Any]] = []
    for idx, tok in enumerate(raw_tokens):
        w_start = start_time_s + float(boundary_times[idx])
        w_end = start_time_s + float(boundary_times[idx + 1])
        # Refine word-specific diagram cues if this specific token names a geometric object
        tok_cues, tok_banner = infer_diagram_cues(tok, clean_text)
        active_cues = tok_cues if tok_cues != ["acute_triangle"] else cues
        active_banner = tok_banner if tok_cues != ["acute_triangle"] else banner
        out.append(
            {
                "index": base_index + idx,
                "word": tok,
                "norm": normalize_word_for_match(tok),
                "is_greek": bool(WORD_RE.search(tok)),
                "start_s": round(w_start, 3),
                "end_s": round(max(w_start + 0.04, w_end), 3),
                "diagram_cues": active_cues,
                "cue_banner": active_banner,
            }
        )
    return out


def _split_bilingual_clauses_for_chirp(
    spoken_text: str,
) -> list[tuple[str, float]]:
    """Backward-compatible wrapper returning (phrase_text, pause_s)."""
    return [
        (txt, pause)
        for txt, _lang, pause in _split_expressive_bilingual_phrases(
            spoken_text
        )
    ]


def sanitize_spoken_english(text: str) -> str:
    """Strip accidental XML/SSML tags and expand LaTeX math for natural spoken TTS & subtitles."""
    # Remove any accidental <phoneme ...>, </phoneme>, <speak>, or XML tags emitted by an LLM
    cleaned = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    cleaned = cleaned.replace("**", "").replace("~", "")
    # Expand common LaTeX algebraic expressions so TTS never reads "dollar" or "caret"
    cleaned = cleaned.replace("$", "")
    cleaned = re.sub(r"\\cos\b", "cosine ", cleaned)
    cleaned = re.sub(r"\\sin\b", "sine ", cleaned)
    cleaned = re.sub(r"\\cosh\b", "hyperbolic cosine ", cleaned)
    cleaned = re.sub(r"\\sinh\b", "hyperbolic sine ", cleaned)
    cleaned = re.sub(r"\b([A-Za-z])\^2\b", r"\1 squared", cleaned)
    cleaned = re.sub(r"\b([A-Za-z])²", r"\1 squared", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def bilingual_ssml(
    text: str,
    voice: str = "en-AU-Chirp3-HD-Charon",
    ssml_pitch: str | None = None,
    ssml_rate: str | None = None,
) -> str:
    """Build <speak>...</speak> SSML for mixed Australian English + Erasmian Greek text."""
    cleaned = sanitize_spoken_english(text)
    body = erasmian_ssml_words(cleaned, voice=voice)
    if "Chirp3-HD" not in voice:
        body = BREAK_MARKER_RE.sub(r'<break time="\1"/>', body)
    else:
        body = BREAK_MARKER_RE.sub(" ", body)
    if (ssml_pitch or ssml_rate) and not WORD_RE.search(cleaned):
        attrs: list[str] = []
        if ssml_pitch:
            attrs.append(f'pitch="{ssml_pitch}"')
        if ssml_rate:
            attrs.append(f'rate="{ssml_rate}"')
        attr_str = " ".join(attrs)
        body = f"<prosody {attr_str}>{body}</prosody>"
    return f"<speak>{body}</speak>"


def modern(text: str, respelled: bool = False) -> str:
    """Normalize polytonic Ancient Greek to Modern Greek orthography for el-GR voices."""
    text = sanitize_greek_text(text)

    def replace_letters(match: re.Match[str]) -> str:
        return " ".join(MODERN_LETTERS.get(c, c) for c in match.group())

    text = LETTERS_RE.sub(replace_letters, text)
    output: list[str] = []
    for c in ud.normalize("NFD", text):
        if c in "\u0300\u0342":
            output.append("\u0301")
        elif not ud.combining(c) or c in "\u0301\u0308":
            output.append(c)
    normalized = (
        ud.normalize("NFC", "".join(output))
        .replace("·", ",")
        .replace("·", ",")
        .replace("᾿", "’")
    )

    def accent_and_spelling(match: re.Match[str]) -> str:
        token = match.group()
        if token.lower() in MODERN_MONOSYLLABLES:
            token = ud.normalize(
                "NFC",
                "".join(c for c in ud.normalize("NFD", token) if c != "\u0301"),
            )
        if respelled and token.lower() in MODERN_RESPELLINGS:
            replacement = MODERN_RESPELLINGS[token.lower()]
            token = (
                replacement.capitalize() if token[0].isupper() else replacement
            )
        return token

    return WORD_RE.sub(accent_and_spelling, normalized)


def chunks_by_clause(text: str) -> list[str]:
    parts = [
        p.strip()
        for p in re.findall(r"[^,··.!?;;]+[,··.!?;;]?", text)
        if p.strip()
    ]
    return parts or [text.strip()]


def phrase_plan(
    text: str, pauses: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    pauses = DEFAULT_PAUSES if pauses is None else pauses
    remaining = re.sub(r"\s+", " ", text).strip()
    groups: list[dict[str, Any]] = []

    for greek, boundary in OPENING_GROUPS:
        if remaining.startswith(greek):
            groups.append({"greek": greek, "boundary": boundary})
            remaining = remaining[len(greek) :].strip()
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
        group["pause_after_seconds"] = (
            pauses[group["boundary"]] if i < len(groups) - 1 else 0.0
        )
    return groups


def trim_edges(data: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    active = np.flatnonzero(np.abs(data) > EDGE_TRIM_THRESHOLD)
    if not len(active):
        return data
    pad = int(EDGE_PAD_SECONDS * sr)
    return data[
        max(0, int(active[0]) - pad) : min(len(data), int(active[-1]) + pad + 1)
    ]


def level_speech_fast(
    data: np.ndarray, sr: int = SAMPLE_RATE, use_ffmpeg: bool = True
) -> np.ndarray:
    """Apply gentle 2:1 compression & peak limiting from euclid-tts."""
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if not data.size:
        return data
    if use_ffmpeg:
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "f32le",
                    "-ar",
                    str(sr),
                    "-ac",
                    "1",
                    "-i",
                    "pipe:0",
                    "-af",
                    SPEECH_LEVEL_FILTER,
                    "-f",
                    "f32le",
                    "pipe:1",
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
    peak = float(np.max(np.abs(data)))
    if peak > 1e-4:
        return np.clip(
            data * min(MAX_FALLBACK_GAIN, NORM_TARGET_PEAK / peak),
            -PEAK_LIMIT,
            PEAK_LIMIT,
        )
    return data


def read_wav_mono24k(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as f:
        sr = f.getframerate()
        nch = f.getnchannels()
        sw = f.getsampwidth()
        raw = f.readframes(f.getnframes())
    if sw == 2:
        arr = (
            np.frombuffer(raw, dtype="<i2").astype(np.float32) / PCM16_DIVISOR
        )
    elif sw == 4:
        arr = (
            np.frombuffer(raw, dtype="<i4").astype(np.float32) / PCM32_DIVISOR
        )
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw}")
    if nch > 1:
        arr = arr.reshape(-1, nch).mean(axis=1)
    if sr != SAMPLE_RATE:
        duration = len(arr) / sr
        target_len = int(round(duration * SAMPLE_RATE))
        arr = np.interp(
            np.linspace(0.0, len(arr) - 1, target_len),
            np.arange(len(arr)),
            arr,
        ).astype(np.float32)
        sr = SAMPLE_RATE
    return arr, sr


def write_wav_mono24k(
    path: Path, data: np.ndarray, sr: int = SAMPLE_RATE
) -> None:
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    if not data.size:
        return
    peak = float(np.max(np.abs(data)))
    gain = min(1.0, PEAK_LIMIT / peak) if peak > 0 else 1.0
    pcm = np.rint(data * gain * PCM16_SCALE).astype("<i2")
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

    def __init__(self, cache_dir: Path, default_voice: str = "bm_george") -> None:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        from onnxruntime import InferenceSession, SessionOptions

        self.cache_dir = cache_dir
        os.environ.setdefault("HF_HOME", str(cache_dir))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

        def download(repo: str, filename: str, revision: str) -> Path:
            args = dict(
                repo_id=repo,
                filename=filename,
                revision=revision,
                cache_dir=cache_dir,
                token=False,
            )
            try:
                return Path(hf_hub_download(**args, local_files_only=True))
            except LocalEntryNotFoundError:
                return Path(hf_hub_download(**args))

        self._download = download
        config_path = download(
            "hexgrad/Kokoro-82M", "config.json", self.VOCAB_REVISION
        )
        model_path = download(
            self.MODEL_REPO, "onnx/model_quantized.onnx", self.MODEL_REVISION
        )

        self.vocab: dict[str, int] = json.loads(
            config_path.read_text(encoding="utf-8")
        )["vocab"]
        self.voices: dict[str, np.ndarray] = {}

        options = SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._load_voice(default_voice)

    def _load_voice(self, voice: str) -> np.ndarray:
        if voice not in self.voices:
            vpath = self._download(
                self.MODEL_REPO, f"voices/{voice}.bin", self.MODEL_REVISION
            )
            self.voices[voice] = np.fromfile(vpath, dtype=np.float32).reshape(
                -1, 1, 256
            )
        return self.voices[voice]

    def synthesize_clause(
        self, greek_text: str, voice: str, rate: float
    ) -> np.ndarray:
        styles = self._load_voice(voice)
        phonemes = engine_phonemes(erasmian(greek_text), "kokoro")
        ids = [self.vocab[p] for p in phonemes if p in self.vocab]
        if not ids:
            return np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)
        ids = ids[:KOKORO_MAX_TOKENS]
        wave_data = self.session.run(
            None,
            {
                "input_ids": np.array([[0, *ids, 0]], dtype=np.int64),
                "style": styles[min(len(ids), len(styles) - 1)],
                "speed": np.array([rate], dtype=np.float32),
            },
        )[0]
        return trim_edges(
            np.asarray(wave_data, dtype=np.float32).reshape(-1), SAMPLE_RATE
        )


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
    word_timings: list[dict[str, Any]] = field(default_factory=list)


def _voice_language_code(voice_name: str, default: str = "en-AU") -> str:
    parts = voice_name.split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return default


class GreekTTSAdapter:
    """Low-latency sentence-by-sentence Australian English + Erasmian Greek TTS adapter."""

    def __init__(self, cfg: Config, preload_kokoro: bool = True) -> None:
        self.cfg = cfg
        self._google_session: Any = None
        self._kokoro: KokoroEngine | None = None

        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession, Request

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(Request())
            self._google_session = AuthorizedSession(credentials)
            warmup_voice = self.cfg.tts_voice_english or "en-AU-Chirp3-HD-Charon"
            warmup_lang = _voice_language_code(warmup_voice, "en-AU")
            self._google_session.post(
                GOOGLE_TTS_V1BETA1_URL,
                json={
                    "input": {"text": "a"},
                    "voice": {"languageCode": warmup_lang, "name": warmup_voice},
                    "audioConfig": {
                        "audioEncoding": "LINEAR16",
                        "sampleRateHertz": SAMPLE_RATE,
                    },
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
            self._kokoro = KokoroEngine(
                hf_cache, default_voice=self.cfg.tts_voice_kokoro
            )
        return self._kokoro

    def _google_synthesize_ssml(
        self, ssml: str, voice: str, language_code: str, rate: float
    ) -> np.ndarray:
        if self._google_session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
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
            GOOGLE_TTS_V1BETA1_URL,
            json=payload,
            timeout=25,
        )
        if not response.ok:
            err = response.json().get("error", {})
            raise RuntimeError(
                f"Google Cloud TTS HTTP {response.status_code}: {err.get('status')} {err.get('message', '')}"
            )
        raw = base64.b64decode(response.json()["audioContent"])
        with wave.open(io.BytesIO(raw), "rb") as f:
            samples = (
                np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(
                    np.float32
                )
                / PCM16_DIVISOR
            )
        return trim_edges(samples, SAMPLE_RATE)

    def synthesize_bilingual_segment(
        self,
        spoken_text: str,
        *,
        english_display: str = "",
        greek_display: str = "",
        index: int = 0,
        voice: str | None = None,
        rate: float | None = None,
    ) -> SentenceAudioChunk:
        """Synthesize a presentation or Q&A segment mixing Male Australian English & Erasmian Greek."""
        t0 = time.perf_counter()
        active_voice = voice or self.cfg.tts_voice_english
        active_lang = _voice_language_code(active_voice, "en-AU")
        eng_rate = rate if rate is not None else self.cfg.tts_rate_english
        grk_rate = (
            min(rate, self.cfg.tts_rate)
            if rate is not None
            else self.cfg.tts_rate
        )

        phrases = _split_expressive_bilingual_phrases(spoken_text)
        clips: list[np.ndarray] = []
        word_timings: list[dict[str, Any]] = []
        cursor_s = 0.0
        prev_en_bucket = ""

        for phrase_idx, (phrase_text, lang, pause_s) in enumerate(phrases):
            (
                p_rate,
                ssml_pitch,
                ssml_rate,
                dsp_pitch_st,
                dsp_gain_db,
                bucket,
            ) = _compute_phrase_prosody(
                phrase_text,
                lang,
                phrase_idx,
                eng_rate,
                grk_rate,
                prev_bucket=prev_en_bucket if lang == "en" else "",
            )
            if lang == "en":
                prev_en_bucket = bucket
            phrase_ssml = bilingual_ssml(
                phrase_text,
                voice=active_voice,
                ssml_pitch=ssml_pitch if lang == "en" else None,
                ssml_rate=ssml_rate if lang == "en" else None,
            )
            clip = self._google_synthesize_ssml(
                phrase_ssml, active_voice, active_lang, p_rate
            )
            clip = _shape_phrase_pcm(clip, dsp_pitch_st, dsp_gain_db, SAMPLE_RATE)
            phrase_timings = _extract_phrase_word_timings(
                phrase_text,
                clip,
                cursor_s,
                SAMPLE_RATE,
                len(word_timings),
                spoken_text,
            )
            word_timings.extend(phrase_timings)
            clips.append(clip)
            cursor_s += len(clip) / float(SAMPLE_RATE)
            if pause_s > 0:
                pause_samples = round(SAMPLE_RATE * pause_s)
                clips.append(np.zeros(pause_samples, dtype=np.float32))
                cursor_s += pause_samples / float(SAMPLE_RATE)

        pcm = (
            np.concatenate(clips)
            if clips
            else np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)
        )
        pcm = np.clip(pcm, -PEAK_LIMIT, PEAK_LIMIT)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        duration_s = len(pcm) / float(SAMPLE_RATE)
        return SentenceAudioChunk(
            index=index,
            english=english_display or strip_prosody_markers(spoken_text),
            greek=greek_display,
            pcm=pcm,
            duration_s=round(duration_s, 3),
            synthesis_ms=round(elapsed_ms, 1),
            backend="google_au_bilingual",
            voice=active_voice,
            word_timings=word_timings,
        )

    def synthesize_sentence(
        self,
        greek_sentence: str,
        *,
        english_sentence: str = "",
        spoken_sentence: str = "",
        index: int = 0,
        backend: str | None = None,
        voice: str | None = None,
        rate: float | None = None,
    ) -> SentenceAudioChunk:
        """Synthesize a single Q&A or presentation sentence into 24 kHz mono float32 PCM."""
        t0 = time.perf_counter()
        active_backend = backend or self.cfg.tts_backend
        active_voice = voice or self.cfg.active_tts_voice(active_backend)
        active_rate = rate if rate is not None else self.cfg.tts_rate

        if active_backend == "google_au_bilingual":
            # In bilingual mode, Euclid speaks Male Australian English with embedded Erasmian Greek!
            utterance = spoken_sentence.strip()
            if not utterance:
                if english_sentence.strip() and greek_sentence.strip():
                    # If English already embeds Greek words, speak the English sentence directly;
                    # otherwise speak the Greek clause in Erasmian Greek followed by the Australian English explanation.
                    if WORD_RE.search(english_sentence):
                        utterance = english_sentence.strip()
                    else:
                        utterance = (
                            f"{greek_sentence.strip()} [[break:350ms]] "
                            f"{english_sentence.strip()}"
                        )
                elif english_sentence.strip():
                    utterance = english_sentence.strip()
                else:
                    utterance = greek_sentence.strip()

            return self.synthesize_bilingual_segment(
                utterance,
                english_display=english_sentence or utterance,
                greek_display=greek_sentence,
                index=index,
                voice=active_voice,
                rate=rate,
            )

        plan = phrase_plan(greek_sentence)

        if active_backend == "google_erasmian":
            lang = _voice_language_code(active_voice, "en-AU")
            use_chirp_split = (
                "Chirp3-HD" in active_voice
                and len(WORD_RE.findall(greek_sentence))
                > CHIRP_MAX_GREEK_WORDS_PER_CALL
            )
            if use_chirp_split:
                clips_erasmian: list[np.ndarray] = []
                for group in plan:
                    clause_text = re.sub(r"[,··;;]+$", ".", group["greek"])
                    clause_ssml = (
                        "<speak>"
                        + erasmian_ssml_words(clause_text, voice=active_voice)
                        + "</speak>"
                    )
                    clip = self._google_synthesize_ssml(
                        clause_ssml, active_voice, lang, active_rate
                    )
                    clips_erasmian.append(clip)
                    if group["pause_after_seconds"] > 0:
                        clips_erasmian.append(
                            np.zeros(
                                round(
                                    SAMPLE_RATE * group["pause_after_seconds"]
                                ),
                                dtype=np.float32,
                            )
                        )
                pcm = (
                    np.concatenate(clips_erasmian)
                    if clips_erasmian
                    else np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)
                )
            else:
                pieces: list[str] = []
                for i, group in enumerate(plan):
                    pieces.append(
                        erasmian_ssml_words(group["greek"], voice=active_voice)
                    )
                    if i < len(plan) - 1 and group["pause_after_seconds"] > 0:
                        pieces.append(
                            f'<break time="{round(1000 * group["pause_after_seconds"])}ms"/>'
                        )
                ssml = "<speak>" + " ".join(pieces) + "</speak>"
                pcm = self._google_synthesize_ssml(
                    ssml, active_voice, lang, active_rate
                )

        elif active_backend == "google_modern":
            pieces = []
            for i, group in enumerate(plan):
                pieces.append(escape(modern(group["greek"])))
                if i < len(plan) - 1 and group["pause_after_seconds"] > 0:
                    pieces.append(
                        f'<break time="{round(1000 * group["pause_after_seconds"])}ms"/>'
                    )
            ssml = "<speak>" + " ".join(pieces) + "</speak>"
            pcm = self._google_synthesize_ssml(
                ssml, active_voice, "el-GR", active_rate
            )

        elif active_backend == "kokoro_erasmian":
            kokoro = self._ensure_kokoro()
            clips: list[np.ndarray] = []
            for group in plan:
                clip = kokoro.synthesize_clause(
                    group["greek"], active_voice, active_rate
                )
                clips.append(clip)
                if group["pause_after_seconds"] > 0:
                    clips.append(
                        np.zeros(
                            round(SAMPLE_RATE * group["pause_after_seconds"]),
                            dtype=np.float32,
                        )
                    )
            pcm = (
                np.concatenate(clips)
                if clips
                else np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)
            )

        elif active_backend == "macos_modern":
            normalized = modern(greek_sentence)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                aiff_file = tmp_path / "out.aiff"
                wav_file = tmp_path / "out.wav"
                subprocess.run(
                    [
                        "say",
                        "-v",
                        "Melina",
                        "-r",
                        str(round(MACOS_BASE_WPM * active_rate)),
                        "-o",
                        str(aiff_file),
                        normalized,
                    ],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(aiff_file),
                        "-ac",
                        "1",
                        "-ar",
                        str(SAMPLE_RATE),
                        "-c:a",
                        "pcm_s16le",
                        str(wav_file),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                pcm, _ = read_wav_mono24k(wav_file)
                pcm = trim_edges(pcm, SAMPLE_RATE)
        else:
            raise ValueError(f"Unsupported TTS backend: {active_backend}")

        if self.cfg.tts_level_speech and active_backend in {
            "google_erasmian",
            "kokoro_erasmian",
        }:
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
        """Yield SentenceAudioChunk one by one as soon as each sentence is synthesized."""
        for idx, item in enumerate(sentences):
            yield self.synthesize_sentence(
                item.get("greek", ""),
                english_sentence=item.get("english", ""),
                spoken_sentence=item.get("spoken", ""),
                index=idx,
                backend=backend,
                voice=voice,
                rate=rate,
            )
