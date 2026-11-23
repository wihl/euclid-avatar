"""End-to-end Genie 4 proof of concept for Euclid teaching propositions in Ancient Greek.

Combines the Gemini API models used in ``euclid-avatar`` with Google DeepMind's
``genie-4`` interactive world model on the Interactions API (``v1beta``):

- Proposition planning & dynamic prompt generation: ``gemini-3.5-flash-lite``
  grounded in ``~/Projects/Courses/26Fall/mathe139/materials/books/Elements.pdf``
  (read-only), with a curated Heiberg Greek default for *Elements* III.36.
- Photorealistic 16:9 seed frame generation: ``gemini-nano-banana-2.1``
  (current replacement for deprecated ``gemini-3.1-flash-image``; configurable
  via ``--image-model``).
- Real-time interactive world generation: ``genie-4`` (24 fps 16:9 video +
  48 kHz stereo PCM audio over WebSockets, plus WebRTC browser mode via
  interaction-scoped ephemeral auth tokens).
- Optional classroom-grade Ancient Greek narration overlay:
  ``gemini-3.8-flash-tts`` (``Sadaltager`` / ``Charon``) or ``euclid-avatar``'s
  Erasmian IPA TTS adapter (``en-AU-Chirp3-HD-Charon``,
  ``bird-handout-and-class-2026-10-08``).
"""

from __future__ import annotations

GENIE_MODEL = "genie-4"
GENIE_API_VERSION = "v1beta"
DEFAULT_LLM_MODEL = "gemini-3.5-flash-lite"
DEFAULT_IMAGE_MODEL = "gemini-nano-banana-2.1"
LEGACY_IMAGE_MODEL = "gemini-3.1-flash-image"
DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
DEFAULT_TTS_VOICE = "Sadaltager"

GENIE_FPS = 24
GENIE_AUDIO_RATE_HZ = 48000
GENIE_AUDIO_CHANNELS = 2
GENIE_VIDEO_TOKENS_PER_FRAME = 240
GENIE_VIDEO_PRICE_PER_1M_TOKENS_USD = 17.50

DEFAULT_DURATION_S = 24.0
MAX_SESSION_DURATION_S = 90.0

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8795

__all__ = [
    "DEFAULT_DURATION_S",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "DEFAULT_TTS_MODEL",
    "DEFAULT_TTS_VOICE",
    "GENIE_API_VERSION",
    "GENIE_AUDIO_CHANNELS",
    "GENIE_AUDIO_RATE_HZ",
    "GENIE_FPS",
    "GENIE_MODEL",
    "GENIE_VIDEO_PRICE_PER_1M_TOKENS_USD",
    "GENIE_VIDEO_TOKENS_PER_FRAME",
    "LEGACY_IMAGE_MODEL",
    "MAX_SESSION_DURATION_S",
]
