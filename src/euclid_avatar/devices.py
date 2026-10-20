"""CoreAudio device diagnostics, virtual audio routing checks, and OBS scene switching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sounddevice as sd

from .config import Config


@dataclass
class AudioDeviceInfo:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool
    is_default_output: bool


def query_coreaudio_devices() -> list[AudioDeviceInfo]:
    devices = sd.query_devices()
    default_in, default_out = sd.default.device
    results: list[AudioDeviceInfo] = []
    for idx, d in enumerate(devices):
        results.append(
            AudioDeviceInfo(
                index=idx,
                name=str(d.get("name", "")),
                max_input_channels=int(d.get("max_input_channels", 0)),
                max_output_channels=int(d.get("max_output_channels", 0)),
                default_samplerate=float(d.get("default_samplerate", 0.0)),
                is_default_input=(idx == default_in),
                is_default_output=(idx == default_out),
            )
        )
    return results


def find_device_index(
    name_substring: str,
    *,
    kind: str = "input",
    fallback_to_default: bool = True,
) -> tuple[int | None, str, bool]:
    """Find a CoreAudio device by substring.

    Returns (device_index, matched_name, is_exact_target_match).
    """
    devices = query_coreaudio_devices()
    target = name_substring.strip().lower()
    if target:
        for d in devices:
            if target in d.name.lower():
                if kind == "input" and d.max_input_channels > 0:
                    return d.index, d.name, True
                if kind == "output" and d.max_output_channels > 0:
                    return d.index, d.name, True

    if not fallback_to_default:
        return None, "", False

    for d in devices:
        if kind == "input" and d.is_default_input and d.max_input_channels > 0:
            return d.index, d.name, False
        if kind == "output" and d.is_default_output and d.max_output_channels > 0:
            return d.index, d.name, False

    for d in devices:
        if kind == "input" and d.max_input_channels > 0:
            return d.index, d.name, False
        if kind == "output" and d.max_output_channels > 0:
            return d.index, d.name, False

    return None, "None", False


def inspect_routing(cfg: Config) -> dict[str, Any]:
    devices = query_coreaudio_devices()
    bh2_in, bh2_name, bh2_found = find_device_index(
        cfg.audio_input_device, kind="input", fallback_to_default=False
    )
    bh16_out, bh16_name, bh16_found = find_device_index(
        cfg.audio_output_device, kind="output", fallback_to_default=False
    )
    op_mic_idx, op_mic_name, op_mic_found = find_device_index(
        cfg.operator_mic_device, kind="input", fallback_to_default=True
    )
    multi_out_idx, multi_out_name, multi_out_found = find_device_index(
        "Multi-Output", kind="output", fallback_to_default=False
    )

    active_in_idx, active_in_name, _ = find_device_index(
        cfg.audio_input_device, kind="input", fallback_to_default=True
    )
    active_out_idx, active_out_name, _ = find_device_index(
        cfg.audio_output_device, kind="output", fallback_to_default=True
    )

    return {
        "devices": [
            {
                "index": d.index,
                "name": d.name,
                "in_ch": d.max_input_channels,
                "out_ch": d.max_output_channels,
                "sr": int(d.default_samplerate),
                "default_in": d.is_default_input,
                "default_out": d.is_default_output,
            }
            for d in devices
        ],
        "checks": {
            "blackhole_2ch": {
                "configured": cfg.audio_input_device,
                "found": bh2_found,
                "index": bh2_in,
                "name": bh2_name,
                "active_fallback_index": active_in_idx,
                "active_fallback_name": active_in_name,
            },
            "blackhole_16ch": {
                "configured": cfg.audio_output_device,
                "found": bh16_found,
                "index": bh16_out,
                "name": bh16_name,
                "active_fallback_index": active_out_idx,
                "active_fallback_name": active_out_name,
            },
            "operator_mic": {
                "configured": cfg.operator_mic_device,
                "found": op_mic_found,
                "index": op_mic_idx,
                "name": op_mic_name,
            },
            "multi_output_device": {
                "found": multi_out_found,
                "index": multi_out_idx,
                "name": multi_out_name,
            },
        },
        "ready_for_zoom": bool(bh2_found and bh16_found),
    }


def format_devices_report(cfg: Config) -> str:
    info = inspect_routing(cfg)
    lines = [
        "=== CoreAudio Devices Detected ===",
        f"{'ID':>3}  {'In':>2}  {'Out':>3}  {'SR':>6}  {'Default':<8}  Name",
        "-" * 68,
    ]
    for d in info["devices"]:
        flags = []
        if d["default_in"]:
            flags.append("IN")
        if d["default_out"]:
            flags.append("OUT")
        flag_str = ",".join(flags)
        lines.append(
            f"{d['index']:>3}  {d['in_ch']:>2}  {d['out_ch']:>3}  {d['sr']:>6}  {flag_str:<8}  {d['name']}"
        )

    lines.append("")
    lines.append("=== Zoom & Virtual Audio Routing Verification ===")
    checks = info["checks"]

    bh2 = checks["blackhole_2ch"]
    if bh2["found"]:
        lines.append(
            f"[OK]   Zoom -> Capture ({bh2['configured']}): found at index {bh2['index']} ({bh2['name']})"
        )
    else:
        lines.append(
            f"[WARN] Zoom -> Capture ({bh2['configured']}): NOT FOUND (falling back to [{bh2['active_fallback_index']}] {bh2['active_fallback_name']})"
        )
        lines.append("       Install with: brew install blackhole-2ch")

    bh16 = checks["blackhole_16ch"]
    if bh16["found"]:
        lines.append(
            f"[OK]   Euclid -> Zoom Mic ({bh16['configured']}): found at index {bh16['index']} ({bh16['name']})"
        )
    else:
        lines.append(
            f"[WARN] Euclid -> Zoom Mic ({bh16['configured']}): NOT FOUND (falling back to [{bh16['active_fallback_index']}] {bh16['active_fallback_name']})"
        )
        lines.append("       Install with: brew install blackhole-16ch")

    op = checks["operator_mic"]
    lines.append(
        f"[OK]   Operator Physical Mic ({op['configured']}): index {op['index']} ({op['name']})"
    )

    mo = checks["multi_output_device"]
    if mo["found"]:
        lines.append(
            f"[OK]   Multi-Output Device (Headphones + BlackHole 2ch): index {mo['index']} ({mo['name']})"
        )
    else:
        lines.append(
            "[INFO] Multi-Output Device not detected yet. Create one in macOS 'Audio MIDI Setup'"
        )
        lines.append(
            "       combining your Headphones (master clock) + BlackHole 2ch (drift correction ON)."
        )

    return "\n".join(lines)


class OBSController:
    """Optional obs-websocket controller for synchronized video & audio scene switching."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.current_scene = cfg.obs_scene_euclid
        self.connected = False
        self._client: Any = None

    def connect(self) -> bool:
        if not self.cfg.obs_ws_enabled:
            return False
        try:
            import obsws_python as obs
            self._client = obs.ReqClient(
                host=self.cfg.obs_ws_host,
                port=self.cfg.obs_ws_port,
                password=self.cfg.obs_ws_password,
                timeout=2,
            )
            self.connected = True
            return True
        except Exception:
            self.connected = False
            self._client = None
            return False

    def switch_scene(self, scene_name: str) -> dict[str, Any]:
        self.current_scene = scene_name
        if not self.connected and self.cfg.obs_ws_enabled:
            self.connect()
        if self.connected and self._client is not None:
            try:
                self._client.set_current_program_scene(scene_name)
                return {
                    "scene": scene_name,
                    "obs_ws_switched": True,
                    "mode": "obs-websocket + OBS Audio Monitoring",
                }
            except Exception as exc:
                self.connected = False
                return {
                    "scene": scene_name,
                    "obs_ws_switched": False,
                    "error": type(exc).__name__,
                }
        return {
            "scene": scene_name,
            "obs_ws_switched": False,
            "mode": "pipeline-gated audio (OBS WebSocket disabled or offline)",
        }
