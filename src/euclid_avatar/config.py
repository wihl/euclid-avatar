"""Configuration management for euclid-avatar. Never logs or prints secret keys."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_TTS_BACKEND = "google_au_bilingual"
DEFAULT_TTS_VOICE_ENGLISH = "en-AU-Neural2-D"
DEFAULT_TTS_VOICE_ERASMIAN = "en-AU-Neural2-D"
DEFAULT_TTS_VOICE_MODERN = "el-GR-Wavenet-B"
DEFAULT_TTS_VOICE_KOKORO = "bm_george"
DEFAULT_TTS_RATE_ENGLISH = 0.96
DEFAULT_TTS_RATE_GREEK = 0.84
DEFAULT_STT_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_AUDIO_INPUT = "BlackHole 2ch"
DEFAULT_OPERATOR_MIC = "MacBook Pro Microphone"
DEFAULT_AUDIO_OUTPUT = "BlackHole 16ch"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_OBS_PORT = 4455
PLACEHOLDER_API_KEY = "your_gemini_api_key_here"
TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes"})


@dataclass
class Config:
    """Runtime configuration for the II.13 presentation and live Q&A avatar."""

    gemini_api_key: str = field(repr=False, default="")
    gemini_model: str = DEFAULT_GEMINI_MODEL

    course_repo_path: Path = Path.home() / "Projects/Courses/26Fall/mathe139"
    include_local_recordings: bool = True
    euclid_tts_path: Path = Path.home() / "Projects/codex/euclid-tts"
    cache_dir: Path = ROOT_DIR / ".cache"
    logs_dir: Path = ROOT_DIR / "logs"
    prompts_dir: Path = ROOT_DIR / "prompts"
    canned_file: Path = ROOT_DIR / "canned_responses.yaml"
    presentation_file: Path = ROOT_DIR / "presentation_ii13.yaml"

    tts_backend: str = DEFAULT_TTS_BACKEND
    tts_voice_english: str = DEFAULT_TTS_VOICE_ENGLISH
    tts_voice_erasmian: str = DEFAULT_TTS_VOICE_ERASMIAN
    tts_voice_modern: str = DEFAULT_TTS_VOICE_MODERN
    tts_voice_kokoro: str = DEFAULT_TTS_VOICE_KOKORO
    tts_rate_english: float = DEFAULT_TTS_RATE_ENGLISH
    tts_rate: float = DEFAULT_TTS_RATE_GREEK
    tts_level_speech: bool = True

    stt_model: str = DEFAULT_STT_MODEL

    audio_input_device: str = DEFAULT_AUDIO_INPUT
    operator_mic_device: str = DEFAULT_OPERATOR_MIC
    audio_output_device: str = DEFAULT_AUDIO_OUTPUT
    audio_monitor_device: str = ""

    obs_ws_enabled: bool = False
    obs_ws_host: str = DEFAULT_HOST
    obs_ws_port: int = DEFAULT_OBS_PORT
    obs_ws_password: str = field(repr=False, default="")
    obs_scene_david: str = "David"
    obs_scene_euclid: str = "Euclid"

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @property
    def index_db_path(self) -> Path:
        return self.cache_dir / "course_index.sqlite"

    @property
    def presentation_cache_dir(self) -> Path:
        return self.cache_dir / "presentation_ii13"

    @property
    def turns_log_path(self) -> Path:
        return self.logs_dir / "turns.jsonl"

    @property
    def audio_log_dir(self) -> Path:
        return self.logs_dir / "audio"

    def active_tts_voice(self, backend: str | None = None) -> str:
        """Return the primary TTS voice identifier for the selected backend."""
        resolved_backend = backend or self.tts_backend
        if resolved_backend == "google_au_bilingual":
            return self.tts_voice_english
        if resolved_backend == "google_erasmian":
            return self.tts_voice_erasmian
        if resolved_backend == "google_modern":
            return self.tts_voice_modern
        if resolved_backend == "kokoro_erasmian":
            return self.tts_voice_kokoro
        if resolved_backend == "macos_modern":
            return "Melina"
        return self.tts_voice_english


def _read_key_from_dotenv(dotenv_file: Path) -> str:
    """Read GEMINI_API_KEY from a .env file without logging or mutating it."""
    if not dotenv_file.exists():
        return ""
    values = dotenv_values(dotenv_file)
    key = (values.get("GEMINI_API_KEY") or "").strip().strip("'\"")
    if key and key != PLACEHOLDER_API_KEY:
        return key
    return ""


def load_config(env_file: Path | None = None) -> Config:
    """Load configuration from environment variables and .env files."""
    dotenv_path = env_file or (ROOT_DIR / ".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    course_path = Path(
        os.environ.get(
            "COURSE_REPO_PATH",
            str(Path.home() / "Projects/Courses/26Fall/mathe139"),
        )
    ).expanduser()
    tts_path = Path(
        os.environ.get(
            "EUCLID_TTS_PATH",
            str(Path.home() / "Projects/codex/euclid-tts"),
        )
    ).expanduser()

    # Prefer course repo / euclid-tts .env keys if local .env is missing or placeholder
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    course_key = _read_key_from_dotenv(course_path / ".env")
    euclid_tts_key = _read_key_from_dotenv(tts_path / ".env")
    if not api_key or api_key == PLACEHOLDER_API_KEY:
        api_key = course_key or euclid_tts_key
    elif course_key and api_key != course_key:
        # Prefer the active key from mathe139/.env if the local .env key was rotated
        api_key = course_key

    pres_raw = os.environ.get("PRESENTATION_FILE", "presentation_ii13.yaml").strip()
    pres_path = Path(pres_raw)
    if not pres_path.is_absolute():
        pres_path = ROOT_DIR / pres_path

    cfg = Config(
        gemini_api_key=api_key,
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip(),
        course_repo_path=course_path,
        include_local_recordings=os.environ.get(
            "INCLUDE_LOCAL_RECORDINGS", "true"
        ).lower()
        in TRUTHY_ENV_VALUES,
        euclid_tts_path=tts_path,
        presentation_file=pres_path,
        tts_backend=os.environ.get("TTS_BACKEND", DEFAULT_TTS_BACKEND).strip(),
        tts_voice_english=os.environ.get(
            "TTS_VOICE_ENGLISH", DEFAULT_TTS_VOICE_ENGLISH
        ).strip(),
        tts_voice_erasmian=os.environ.get(
            "TTS_VOICE_ERASMIAN", DEFAULT_TTS_VOICE_ERASMIAN
        ).strip(),
        tts_voice_modern=os.environ.get(
            "TTS_VOICE_MODERN", DEFAULT_TTS_VOICE_MODERN
        ).strip(),
        tts_voice_kokoro=os.environ.get(
            "TTS_VOICE_KOKORO", DEFAULT_TTS_VOICE_KOKORO
        ).strip(),
        tts_rate_english=float(
            os.environ.get("TTS_RATE_ENGLISH", str(DEFAULT_TTS_RATE_ENGLISH))
        ),
        tts_rate=float(os.environ.get("TTS_RATE", str(DEFAULT_TTS_RATE_GREEK))),
        tts_level_speech=os.environ.get("TTS_LEVEL_SPEECH", "true").lower()
        in TRUTHY_ENV_VALUES,
        stt_model=os.environ.get("STT_MODEL", DEFAULT_STT_MODEL).strip(),
        audio_input_device=os.environ.get(
            "AUDIO_INPUT_DEVICE", DEFAULT_AUDIO_INPUT
        ).strip(),
        operator_mic_device=os.environ.get(
            "OPERATOR_MIC_DEVICE", DEFAULT_OPERATOR_MIC
        ).strip(),
        audio_output_device=os.environ.get(
            "AUDIO_OUTPUT_DEVICE", DEFAULT_AUDIO_OUTPUT
        ).strip(),
        audio_monitor_device=os.environ.get("AUDIO_MONITOR_DEVICE", "").strip(),
        obs_ws_enabled=os.environ.get("OBS_WS_ENABLED", "false").lower()
        in TRUTHY_ENV_VALUES,
        obs_ws_host=os.environ.get("OBS_WS_HOST", DEFAULT_HOST).strip(),
        obs_ws_port=int(os.environ.get("OBS_WS_PORT", str(DEFAULT_OBS_PORT))),
        obs_ws_password=os.environ.get("OBS_WS_PASSWORD", "").strip(),
        obs_scene_david=os.environ.get("OBS_SCENE_DAVID", "David").strip(),
        obs_scene_euclid=os.environ.get("OBS_SCENE_EUCLID", "Euclid").strip(),
        host=os.environ.get("HOST", DEFAULT_HOST).strip(),
        port=int(os.environ.get("PORT", str(DEFAULT_PORT))),
    )
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.presentation_cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_log_dir.mkdir(parents=True, exist_ok=True)
    return cfg
