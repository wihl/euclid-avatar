"""Configuration management for euclid-avatar. Never logs or prints secret keys."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    gemini_api_key: str = field(repr=False, default="")
    gemini_model: str = "gemini-2.5-flash"

    course_repo_path: Path = Path.home() / "Projects/Courses/26Fall/mathe139"
    euclid_tts_path: Path = Path.home() / "Projects/codex/euclid-tts"
    cache_dir: Path = ROOT_DIR / ".cache"
    logs_dir: Path = ROOT_DIR / "logs"
    prompts_dir: Path = ROOT_DIR / "prompts"
    canned_file: Path = ROOT_DIR / "canned_responses.yaml"

    tts_backend: str = "google_erasmian"
    tts_voice_erasmian: str = "en-US-Neural2-D"
    tts_voice_modern: str = "el-GR-Wavenet-B"
    tts_voice_kokoro: str = "af_heart"
    tts_rate: float = 0.78
    tts_level_speech: bool = True

    stt_model: str = "mlx-community/whisper-large-v3-turbo"

    audio_input_device: str = "BlackHole 2ch"
    operator_mic_device: str = "MacBook Pro Microphone"
    audio_output_device: str = "BlackHole 16ch"
    audio_monitor_device: str = ""

    obs_ws_enabled: bool = False
    obs_ws_host: str = "127.0.0.1"
    obs_ws_port: int = 4455
    obs_ws_password: str = field(repr=False, default="")
    obs_scene_david: str = "David"
    obs_scene_euclid: str = "Euclid"

    host: str = "127.0.0.1"
    port: int = 8765

    @property
    def index_db_path(self) -> Path:
        return self.cache_dir / "course_index.sqlite"

    @property
    def turns_log_path(self) -> Path:
        return self.logs_dir / "turns.jsonl"

    @property
    def audio_log_dir(self) -> Path:
        return self.logs_dir / "audio"

    def active_tts_voice(self, backend: str | None = None) -> str:
        b = backend or self.tts_backend
        if b == "google_erasmian":
            return self.tts_voice_erasmian
        if b == "google_modern":
            return self.tts_voice_modern
        if b == "kokoro_erasmian":
            return self.tts_voice_kokoro
        if b == "macos_modern":
            return "Melina"
        return self.tts_voice_erasmian


def load_config(env_file: Path | None = None) -> Config:
    dotenv_path = env_file or (ROOT_DIR / ".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        # Fallback to euclid-tts .env if present (read-only)
        fallback_env = Path.home() / "Projects/codex/euclid-tts/.env"
        if fallback_env.exists():
            for line in fallback_env.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("'\"")
                    break

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

    cfg = Config(
        gemini_api_key=api_key,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        course_repo_path=course_path,
        euclid_tts_path=tts_path,
        tts_backend=os.environ.get("TTS_BACKEND", "google_erasmian").strip(),
        tts_voice_erasmian=os.environ.get("TTS_VOICE_ERASMIAN", "en-US-Neural2-D").strip(),
        tts_voice_modern=os.environ.get("TTS_VOICE_MODERN", "el-GR-Wavenet-B").strip(),
        tts_voice_kokoro=os.environ.get("TTS_VOICE_KOKORO", "af_heart").strip(),
        tts_rate=float(os.environ.get("TTS_RATE", "0.78")),
        tts_level_speech=os.environ.get("TTS_LEVEL_SPEECH", "true").lower() in {"1", "true", "yes"},
        stt_model=os.environ.get("STT_MODEL", "mlx-community/whisper-large-v3-turbo").strip(),
        audio_input_device=os.environ.get("AUDIO_INPUT_DEVICE", "BlackHole 2ch").strip(),
        operator_mic_device=os.environ.get("OPERATOR_MIC_DEVICE", "MacBook Pro Microphone").strip(),
        audio_output_device=os.environ.get("AUDIO_OUTPUT_DEVICE", "BlackHole 16ch").strip(),
        audio_monitor_device=os.environ.get("AUDIO_MONITOR_DEVICE", "").strip(),
        obs_ws_enabled=os.environ.get("OBS_WS_ENABLED", "false").lower() in {"1", "true", "yes"},
        obs_ws_host=os.environ.get("OBS_WS_HOST", "127.0.0.1").strip(),
        obs_ws_port=int(os.environ.get("OBS_WS_PORT", "4455")),
        obs_ws_password=os.environ.get("OBS_WS_PASSWORD", "").strip(),
        obs_scene_david=os.environ.get("OBS_SCENE_DAVID", "David").strip(),
        obs_scene_euclid=os.environ.get("OBS_SCENE_EUCLID", "Euclid").strip(),
        host=os.environ.get("HOST", "127.0.0.1").strip(),
        port=int(os.environ.get("PORT", "8765")),
    )
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_log_dir.mkdir(parents=True, exist_ok=True)
    return cfg
