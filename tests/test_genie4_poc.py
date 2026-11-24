"""Offline unit and integration tests for the Genie 4 Euclid POC package."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.request
import wave

from euclid_avatar.genie4_poc import (
    DEFAULT_DURATION_S,
    GENIE_AUDIO_CHANNELS,
    GENIE_AUDIO_RATE_HZ,
    GENIE_FPS,
    MAX_SESSION_DURATION_S,
)
from euclid_avatar.genie4_poc.diagram import (
    build_diagram_spec_for_plan,
    build_iii36_diagram_spec,
)
from euclid_avatar.genie4_poc.genie_client import (
    build_steering_schedule,
    record_genie4_session,
)
from euclid_avatar.genie4_poc.media import (
    WEBRTC_SCTP_MAX_MESSAGE_BYTES,
    WEBRTC_SEED_MAX_RAW_BYTES,
    detect_video_frame_codec,
    mux_video_with_narration_mp4,
    prepare_webrtc_seed_image,
    sniff_image_mime_type,
)
from euclid_avatar.genie4_poc.prompts import (
    build_prompt_bundle,
    build_seed_image_prompt,
    build_steering_prompt,
    build_world_setup_prompt,
    export_prompt_kit,
)
from euclid_avatar.genie4_poc.propositions import (
    DEFAULT_COURSE_REPO,
    build_curated_iii36_plan,
    extract_proposition_from_elements_pdf,
    parse_proposition_id,
)
from euclid_avatar.genie4_poc.server import create_genie4_http_server


def _make_tiny_jpeg_via_ffmpeg(width: int = 160, height: int = 90) -> bytes:
    """Create a real valid JFIF JPEG frame using FFmpeg for lossless mux testing."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise unittest.SkipTest("ffmpeg not installed")
    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#c8b08a:s={width}x{height}:d=0.05",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return proc.stdout


def _make_tiny_wav(path: Path, duration_s: float = 0.5, rate: int = 24000) -> Path:
    n_samples = int(duration_s * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return path


@dataclass
class _FakeDelta:
    type: str
    data: str | None = None
    mime_type: str | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass
class _FakeEvent:
    event_type: str
    delta: _FakeDelta | None = None
    error: str | None = None


class _FakeGenieSession:
    """Simulates Genie 4's real producer wire format (JFIF tagged video/jpeg2000 + 48kHz stereo PCM)."""

    def __init__(
        self,
        jpeg_bytes: bytes,
        *,
        total_frames: int,
        fail_at_frame: int | None = None,
    ) -> None:
        self._jpeg_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        # 48000 Hz * 2 ch * 2 bytes / 24 fps = 8000 bytes/frame (matches live Genie 4 probe)
        self._pcm_b64 = base64.b64encode(b"\x10\x00\xf0\xff" * 2000).decode("ascii")
        self._total_frames = total_frames
        self._fail_at_frame = fail_at_frame
        self.sent_payloads: list[object] = []
        self.complete_calls = 0

    async def __aenter__(self) -> _FakeGenieSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send(self, payload: object) -> None:
        self.sent_payloads.append(payload)

    async def complete(self) -> None:
        self.complete_calls += 1

    async def receive(self):
        yield _FakeEvent("interaction.connected")
        yield _FakeEvent("step.start")
        for idx in range(1, self._total_frames + 1):
            if self._fail_at_frame is not None and idx == self._fail_at_frame:
                raise RuntimeError("Simulated mid-stream disconnect")
            # Intentionally tag JFIF bytes as video/jpeg2000 to mirror live Genie 4 output
            yield _FakeEvent(
                "step.delta",
                delta=_FakeDelta(
                    type="video",
                    data=self._jpeg_b64,
                    mime_type="video/jpeg2000",
                ),
            )
            yield _FakeEvent(
                "step.delta",
                delta=_FakeDelta(
                    type="audio",
                    data=self._pcm_b64,
                    sample_rate=GENIE_AUDIO_RATE_HZ,
                    channels=GENIE_AUDIO_CHANNELS,
                ),
            )
            if self.complete_calls > 0:
                break
        yield _FakeEvent("step.stop")
        yield _FakeEvent("interaction.completed")


class _FakeAsyncInteractions:
    def __init__(self, session: _FakeGenieSession) -> None:
        self._session = session
        self.created_models: list[str] = []

    async def create(self, *, model: str, api_version: str = "v1beta"):
        self.created_models.append(model)
        return SimpleNamespace(id="v1_fake_genie4_interaction", status="idle")

    def connect(self, interaction_id: str, *, api_version: str = "v1beta"):
        return self._session


class _FakeClient:
    def __init__(self, session: _FakeGenieSession) -> None:
        self.aio = SimpleNamespace(interactions=_FakeAsyncInteractions(session))
        self.interactions = SimpleNamespace(
            create=lambda *, model, api_version="v1beta": SimpleNamespace(
                id="v1_fake_webrtc_id"
            ),
            auth_tokens=SimpleNamespace(
                create=lambda interaction_id, *, api_version="v1beta": SimpleNamespace(
                    auth_token="ephemeral_tok_12345",
                    expires_at=datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc),
                )
            ),
        )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestGenie4Poc(unittest.TestCase):
    """Verify proposition parsing, prompt invariants, live wire decoding, and safety caps."""

    def test_parse_proposition_id_variants(self) -> None:
        self.assertEqual(parse_proposition_id("III.36"), (3, 36, "III.36"))
        self.assertEqual(parse_proposition_id("3.36"), (3, 36, "III.36"))
        self.assertEqual(parse_proposition_id("iii36"), (3, 36, "III.36"))
        self.assertEqual(parse_proposition_id("I.47"), (1, 47, "I.47"))
        self.assertEqual(parse_proposition_id("ii.13"), (2, 13, "II.13"))
        with self.assertRaises(ValueError):
            parse_proposition_id("Book XCV")

    def test_curated_iii36_heiberg_greek_and_prompt_invariants(self) -> None:
        plan = build_curated_iii36_plan()
        self.assertEqual(plan.proposition_id, "III.36")
        self.assertEqual(plan.slug, "iii36")
        self.assertEqual(plan.greek_letters, ["Α", "Β", "Γ", "Δ", "Ε", "Ζ"])
        self.assertEqual(len(plan.steps), 4)
        self.assertIn("Ἐὰν κύκλου ληφθῇ τι σημεῖον ἐκτός", plan.enunciation_greek)
        self.assertIn("ὅπερ ἔδει δεῖξαι", plan.steps[-1].greek_text)

        seed_prompt = build_seed_image_prompt(plan)
        world_prompt = build_world_setup_prompt(plan, ambient_only_audio=False)
        ambient_prompt = build_world_setup_prompt(plan, ambient_only_audio=True)
        steer_prompt = build_steering_prompt(plan.steps[1])

        # Historical accuracy invariants
        for txt in (seed_prompt, world_prompt):
            self.assertIn("Alexandria", txt)
            self.assertIn("NOT a magnetic", txt)
            self.assertIn("unmarked", txt)
            self.assertIn("sand-tray", txt)
            self.assertIn("pivot spike", txt)
        self.assertIn("No music.", world_prompt)
        self.assertIn("No background speech and no music.", ambient_prompt)
        self.assertIn(plan.enunciation_greek, world_prompt)
        self.assertNotIn(plan.enunciation_greek, ambient_prompt)
        self.assertIn(plan.steps[1].greek_text, steer_prompt)

    def test_magic_byte_codec_detection_handles_genie4_jfif_quirk(self) -> None:
        jfif = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01"
        png = b"\x89PNG\r\n\x1a\n\x00\x00"
        jp2 = b"\x00\x00\x00\x0cjP  \r\n"
        self.assertEqual(detect_video_frame_codec(jfif), ("mjpeg", ".jpg", "image/jpeg"))
        self.assertEqual(detect_video_frame_codec(png), ("png", ".png", "image/png"))
        self.assertEqual(detect_video_frame_codec(jp2), ("jpeg2000", ".jp2", "image/jp2"))
        self.assertEqual(sniff_image_mime_type(jfif), "image/jpeg")

    def test_elements_pdf_extractor_book_boundary_accuracy(self) -> None:
        pdf_path = DEFAULT_COURSE_REPO / "materials/books/Elements.pdf"
        if not pdf_path.exists() or not shutil.which("pdftotext"):
            self.skipTest("Elements.pdf or pdftotext not available locally")
        text_336, pages_336 = extract_proposition_from_elements_pdf("III.36")
        self.assertEqual(pages_336[:2], [105, 106])
        self.assertIn("Proposition 36", text_336)
        self.assertIn("ἐφαπτομένης", text_336)

        text_147, pages_147 = extract_proposition_from_elements_pdf("I.47")
        self.assertEqual(pages_147[0], 46)
        self.assertNotIn(331, pages_147)
        self.assertIn("Proposition 47", text_147)

        # II.13 prints a footnote dagger ("Proposition 13†") in Fitzpatrick's PDF
        text_213, pages_213 = extract_proposition_from_elements_pdf("II.13")
        self.assertEqual(pages_213[0], 65)
        self.assertIn("ὀξυγωνίοις", text_213)

    def test_export_prompt_kit_writes_all_files(self) -> None:
        plan = build_curated_iii36_plan()
        with tempfile.TemporaryDirectory() as tmp:
            paths = export_prompt_kit(plan, Path(tmp))
            for key in ("lesson_plan", "prompts_json", "prompts_md"):
                self.assertTrue(paths[key].exists())
            parsed = json.loads(paths["prompts_json"].read_text(encoding="utf-8"))
            self.assertEqual(parsed["proposition_id"], "III.36")
            self.assertEqual(len(parsed["steering_steps"]), 4)

    def test_steering_schedule_monotonic_and_bounded(self) -> None:
        plan = build_curated_iii36_plan()
        target_frames = int(DEFAULT_DURATION_S * GENIE_FPS)
        schedule = build_steering_schedule(plan, target_frames)
        self.assertEqual(len(schedule), 4)
        frames = [s.frame_index for s in schedule]
        self.assertEqual(frames, sorted(frames))
        self.assertGreaterEqual(frames[0], 24)
        self.assertLessEqual(frames[-1], target_frames - 24)

    def test_record_genie4_session_end_to_end_mux_and_complete_guarantee(self) -> None:
        jpeg_bytes = _make_tiny_jpeg_via_ffmpeg()
        plan = build_curated_iii36_plan()

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            seed_path = out_dir / "seed.jpg"
            seed_path.write_bytes(jpeg_bytes)

            # 5.0 s at 24 fps = 120 frames -> enough room for steering + clean completion
            fake_session = _FakeGenieSession(jpeg_bytes, total_frames=140)
            fake_client = _FakeClient(fake_session)

            report = asyncio.run(
                record_genie4_session(
                    plan,
                    api_key="",
                    output_dir=out_dir,
                    seed_image_path=seed_path,
                    duration_s=5.0,
                    client_override=fake_client,
                )
            )

            self.assertTrue(report.completed_cleanly)
            self.assertEqual(fake_session.complete_calls, 1)
            self.assertEqual(report.video_frames, 120)
            self.assertEqual(report.detected_video_codec, "mjpeg")
            self.assertEqual(report.reported_video_mime, "video/jpeg2000")
            self.assertGreater(len(report.steering_events), 0)

            # Verify world_setup included reference_image + world_prompt
            first_sent = fake_session.sent_payloads[0]
            self.assertIsInstance(first_sent, dict)
            self.assertEqual(first_sent["event_type"], "world_setup")
            self.assertIn("reference_image", first_sent)
            self.assertEqual(first_sent["reference_image"]["mime_type"], "image/jpeg")

            # Verify valid MP4 with video + audio streams
            mp4 = Path(report.output_mp4_path)
            self.assertTrue(mp4.exists())
            self.assertGreater(mp4.stat().st_size, 1000)

            # Verify companion narration mux works cleanly
            wav_path = _make_tiny_wav(out_dir / "narr.wav", duration_s=1.0)
            narrated_mp4 = mux_video_with_narration_mp4(
                mp4, wav_path, out_dir / "narrated.mp4"
            )
            self.assertTrue(narrated_mp4.exists())
            self.assertGreater(narrated_mp4.stat().st_size, 1000)

    def test_record_genie4_session_completes_on_error_and_enforces_duration_cap(self) -> None:
        plan = build_curated_iii36_plan()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                asyncio.run(
                    record_genie4_session(
                        plan,
                        api_key="dummy",
                        output_dir=Path(tmp),
                        duration_s=MAX_SESSION_DURATION_S + 1.0,
                    )
                )

            jpeg_bytes = _make_tiny_jpeg_via_ffmpeg()
            failing_session = _FakeGenieSession(
                jpeg_bytes, total_frames=40, fail_at_frame=5
            )
            fake_client = _FakeClient(failing_session)
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    record_genie4_session(
                        plan,
                        api_key="",
                        output_dir=Path(tmp),
                        duration_s=2.0,
                        client_override=fake_client,
                    )
                )
            # Billing safety: complete() MUST be called even when stream fails mid-flight
            self.assertEqual(failing_session.complete_calls, 1)

    def test_studio_http_server_routes_and_ephemeral_token_isolation(self) -> None:
        jpeg_bytes = _make_tiny_jpeg_via_ffmpeg()
        plan = build_curated_iii36_plan()
        fake_session = _FakeGenieSession(jpeg_bytes, total_frames=10)
        fake_client = _FakeClient(fake_session)
        port = _pick_free_port()

        with tempfile.TemporaryDirectory() as tmp:
            seed_path = Path(tmp) / "seed.jpg"
            seed_path.write_bytes(jpeg_bytes)
            server = create_genie4_http_server(
                plan,
                seed_path,
                api_key="SECRET_NEVER_EXPOSED_TO_BROWSER",
                host="127.0.0.1",
                port=port,
                client_override=fake_client,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{port}"
                html = urllib.request.urlopen(f"{base}/").read().decode("utf-8")
                self.assertIn("III.36", html)
                self.assertIn('id="exact-diagram"', html)
                self.assertIn("renderExactDiagram", html)
                self.assertNotIn("SECRET_NEVER_EXPOSED_TO_BROWSER", html)

                plan_json = json.loads(
                    urllib.request.urlopen(f"{base}/api/plan").read().decode("utf-8")
                )
                self.assertEqual(plan_json["proposition_id"], "III.36")
                self.assertTrue(plan_json["has_seed_image"])
                self.assertTrue(plan_json["diagram"]["has_exact_geometry"])
                self.assertIn("step_2_case1", plan_json["diagram"]["scenes"])
                self.assertIn("step_3_case2", plan_json["diagram"]["scenes"])

                seed_resp = urllib.request.urlopen(f"{base}/assets/seed").read()
                self.assertEqual(seed_resp, jpeg_bytes)

                req = urllib.request.Request(f"{base}/api/session", method="POST", data=b"")
                sess_json = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
                self.assertEqual(sess_json["interaction_id"], "v1_fake_webrtc_id")
                self.assertEqual(sess_json["auth_token"], "ephemeral_tok_12345")
                self.assertNotIn("SECRET_NEVER_EXPOSED_TO_BROWSER", json.dumps(sess_json))
                setup_bytes = len(
                    json.dumps(
                        {
                            "event_type": "world_setup",
                            "world_prompt": {"text": sess_json["world_prompt"]},
                            "reference_image": {
                                "data": sess_json["seed_image_b64"],
                                "mime_type": sess_json["seed_mime_type"],
                            },
                        }
                    ).encode("utf-8")
                )
                self.assertLess(setup_bytes, WEBRTC_SCTP_MAX_MESSAGE_BYTES)
            finally:
                server.shutdown()
                server.server_close()

    def test_webrtc_seed_image_downscales_oversized_2k_image_under_sctp_limit(self) -> None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            self.skipTest("ffmpeg not installed")
        # Generate a noisy 2752x1536 PNG (> 500 KiB) mimicking Nano Banana 2K output
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=2752x1536:d=0.05,noise=alls=40:allf=t",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            check=True,
        )
        big_png = proc.stdout
        self.assertGreater(len(big_png), WEBRTC_SEED_MAX_RAW_BYTES)

        compressed, mime = prepare_webrtc_seed_image(big_png)
        self.assertEqual(mime, "image/jpeg")
        self.assertGreater(len(compressed), 1000)
        self.assertLessEqual(len(compressed), WEBRTC_SEED_MAX_RAW_BYTES)
        # Base64-encoded image plus typical prompt stays comfortably below 256 KiB SCTP limit
        b64_len = len(base64.b64encode(compressed))
        self.assertLess(b64_len + 8000, WEBRTC_SCTP_MAX_MESSAGE_BYTES)

    def test_exact_iii36_diagram_spec_and_generic_plan_fallback(self) -> None:
        spec = build_iii36_diagram_spec()
        self.assertTrue(spec["has_exact_geometry"])
        self.assertEqual(spec["proposition_id"], "III.36")
        scenes = spec["scenes"]
        for key in (
            "step_0_enunciation",
            "step_1_ekthesis",
            "step_2_case1",
            "step_3_case2",
            "step_4_conclusion",
        ):
            self.assertIn(key, scenes)

        # Case 1 uses Heiberg center Ζ and right angle ∠ΖΒΔ = 90°
        c1 = scenes["step_2_case1"]
        c1_pts = {p["id"] for p in c1["points"]}
        self.assertEqual(c1_pts, {"Α", "Β", "Γ", "Δ", "Ζ"})
        self.assertEqual(len(c1["right_angles"]), 1)
        self.assertEqual(len(c1["ticks"]), 2)

        # Case 2 uses Heiberg center Ε, perpendicular foot Ζ, and two right angles
        c2 = scenes["step_3_case2"]
        c2_pts = {p["id"] for p in c2["points"]}
        self.assertEqual(c2_pts, {"Α", "Β", "Γ", "Δ", "Ε", "Ζ"})
        self.assertEqual(len(c2["right_angles"]), 2)
        self.assertEqual(len(c2["ticks"]), 4)
        self.assertIn("16.00", c2["formula_numeric"])

        # Non-III.36 propositions gracefully degrade without throwing
        plan = build_curated_iii36_plan()
        other_plan = plan.model_copy(update={"proposition_id": "II.13", "book": 2, "number": 13})
        fallback = build_diagram_spec_for_plan(other_plan)
        self.assertFalse(fallback["has_exact_geometry"])
        self.assertIn("step_0_enunciation", fallback["scenes"])
        self.assertIn("step_1_ekthesis", fallback["scenes"])


if __name__ == "__main__":
    unittest.main()
