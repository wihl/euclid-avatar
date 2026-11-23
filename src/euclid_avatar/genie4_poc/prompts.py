"""Historically accurate Genie 4 world, seed-image, and live steering prompt builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .propositions import PropositionPlan, SteeringStep

SETTING_DESCRIPTION = (
    "First-person POV standing as a student beside a low, plain wooden teaching table "
    "inside an austere, sun-lit limestone courtyard portico in Ptolemaic Alexandria "
    "around 300 BCE. Photorealistic, ungraded natural-light documentary footage with "
    "subtle 35mm realism; warm late-morning Mediterranean sunlight casts clean shadows "
    "across plain pale limestone columns, a worn stone floor, and an uncluttered "
    "courtyard wall. No decorative clutter, no museum props, no modern objects, no "
    "glowing overlays, and no floating text."
)

INSTRUMENTS_DESCRIPTION = (
    "Foreground anchor: directly in front of the viewer sits a shallow rectangular "
    "wooden sand-tray (abax) filled with smooth, finely leveled pale-ochre sand. "
    "Resting on the wooden rim are only three simple, historically accurate ancient "
    "Greek instruments: "
    "(1) a two-legged hinged bronze drafting divider (diabētēs) for drawing circles — "
    "two slender, weathered tapered bronze arms joined at the top by a simple riveted "
    "pin hinge, one leg ending in a sharp metal pivot spike and the other ending in a "
    "tapered pointed bronze scoring leg (strictly a circle-drawing divider, NOT a "
    "magnetic or navigational compass with a dial); "
    "(2) a plain, completely unmarked flat wooden straightedge bar (kanōn) with smooth "
    "straight edges and zero numbers, tick marks, or measurement graduations; and "
    "(3) a slender pointed bronze stylus for inscribing Greek letters in the sand."
)

EUCLID_PERSONA_VISUAL = (
    "Midground: across the sand-tray stands Euclid of Alexandria, a calm Greek "
    "mathematician in his late fifties with weathered Mediterranean skin, short "
    "trimmed salt-and-pepper hair and beard, wearing a simple undyed off-white linen "
    "chiton and plain draped wool himation."
)

ERASMIAN_SPEECH_DIRECTION = (
    "He speaks calmly and deliberately in Ancient Greek (classical Erasmian "
    "pronunciation, clear distinct vowels, audible rough breathing, unhurried "
    "scholarly cadence):"
)

AMBIENT_AUDIO_LINE = (
    "Audio: crisp natural grit of the bronze tip scoring fine sand, light wooden tap "
    "of the straightedge on the tray rim, Euclid's measured Ancient Greek voice, faint "
    "warm breeze in a quiet stone courtyard. No music."
)

AMBIENT_ONLY_AUDIO_LINE = (
    "Audio: crisp natural grit of the bronze tip scoring fine sand, light wooden tap "
    "of the straightedge on the tray rim, faint warm breeze in a quiet stone courtyard. "
    "No background speech and no music."
)


def _inline_phrase(text: str) -> str:
    """Format a descriptive clause cleanly for inline embedding inside a sentence."""
    cleaned = text.strip().rstrip(".")
    if len(cleaned) >= 2 and cleaned[0].isupper() and cleaned[1].islower():
        return cleaned[0].lower() + cleaned[1:]
    return cleaned


def build_seed_image_prompt(plan: PropositionPlan) -> str:
    """Build the 16:9 photorealistic starting-frame prompt for Nano Banana 2.1."""
    diagram_clause = _inline_phrase(plan.seed_diagram_description)
    return (
        "16:9 photorealistic documentary still from a first-person student viewpoint "
        "standing across a low plain wooden table in an austere, sun-lit limestone "
        "courtyard portico in ancient Alexandria, c. 300 BCE. On the table sits a "
        "shallow rectangular wooden sand-tray (abax) filled with smooth pale-ochre "
        f"sand showing {diagram_clause}. "
        "Resting on the wooden tray rim are only three simple ancient Greek tools: "
        "a two-legged riveted bronze drafting divider with one sharp metal pivot spike "
        "and one tapered bronze writing tip (strictly a circle-drawing compass, NOT a "
        "magnetic compass with a needle or dial), a plain completely unmarked flat "
        "wooden straightedge bar with zero numbers or tick marks, and a slender bronze "
        "stylus. Across the table stands Euclid, a calm Greek scholar in his late "
        "fifties with a short trimmed salt-and-pepper beard, dressed in a simple "
        "undyed off-white linen chiton and plain wool himation, leaning slightly "
        "forward with one hand guiding the bronze divider over the sand. Warm natural "
        "Mediterranean daylight, pale weathered limestone columns behind him, zero "
        "clutter, zero modern objects, zero text overlays, natural 35mm photography."
    )


def build_world_setup_prompt(
    plan: PropositionPlan,
    *,
    ambient_only_audio: bool = False,
) -> str:
    """Build the Genie 4 ``world_setup.world_prompt.text`` initialization prompt."""
    if ambient_only_audio:
        action_block = f"Action: {plan.initial_drawing_action}"
        audio_block = AMBIENT_ONLY_AUDIO_LINE
    else:
        action_block = (
            f"Action: {plan.initial_drawing_action} "
            f"{ERASMIAN_SPEECH_DIRECTION} \"{plan.enunciation_greek}\""
        )
        audio_block = AMBIENT_AUDIO_LINE

    return (
        f"{SETTING_DESCRIPTION}\n\n"
        f"{INSTRUMENTS_DESCRIPTION}\n\n"
        f"{EUCLID_PERSONA_VISUAL}\n\n"
        f"{action_block}\n\n"
        f"{audio_block}"
    )


def build_steering_prompt(
    step: SteeringStep,
    *,
    ambient_only_audio: bool = False,
) -> str:
    """Build a single live mid-session text steering prompt for Genie 4."""
    if ambient_only_audio:
        return (
            f"{step.drawing_action} Keep the camera steady on the wooden sand-tray, "
            "hinged bronze divider, and unmarked wooden straightedge. No music."
        )
    return (
        f"{step.drawing_action} Keep the camera steady on the wooden sand-tray and "
        "ancient instruments while Euclid speaks calmly in Ancient Greek "
        f"(classical Erasmian pronunciation): \"{step.greek_text}\""
    )


def build_prompt_bundle(
    plan: PropositionPlan,
    *,
    ambient_only_audio: bool = False,
) -> dict[str, Any]:
    """Assemble the complete seed, world-setup, and mid-session steering prompts."""
    return {
        "proposition_id": plan.proposition_id,
        "title": plan.title,
        "greek_letters": plan.greek_letters,
        "source_note": plan.source_note,
        "ambient_only_audio": ambient_only_audio,
        "seed_image_prompt": build_seed_image_prompt(plan),
        "world_setup_prompt": build_world_setup_prompt(
            plan, ambient_only_audio=ambient_only_audio
        ),
        "steering_steps": [
            {
                "id": step.id,
                "label": step.label,
                "offset_fraction": step.offset_fraction,
                "english_summary": step.english_summary,
                "greek_text": step.greek_text,
                "steering_prompt": build_steering_prompt(
                    step, ambient_only_audio=ambient_only_audio
                ),
            }
            for step in plan.steps
        ],
    }


def export_prompt_kit(
    plan: PropositionPlan,
    output_dir: Path,
    *,
    ambient_only_audio: bool = False,
) -> dict[str, Path]:
    """Write ``lesson_plan.json``, ``prompts.json``, and ``prompts.md`` to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_prompt_bundle(plan, ambient_only_audio=ambient_only_audio)

    plan_path = output_dir / "lesson_plan.json"
    prompts_json_path = output_dir / "prompts.json"
    prompts_md_path = output_dir / "prompts.md"

    plan_path.write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    prompts_json_path.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_lines = [
        f"# Genie 4 Prompt Kit · Euclid *Elements* {plan.proposition_id}",
        "",
        f"- **Title:** {plan.title}",
        f"- **Heiberg Greek letters:** {', '.join(plan.greek_letters)}",
        f"- **Source:** {plan.source_note}",
        f"- **Audio mode:** {'Ambient-only (for external TTS mix)' if ambient_only_audio else 'Native Genie 4 Ancient Greek speech + ambient'}",
        "",
        "## 1. Seed Image Prompt (`gemini-nano-banana-2.1`, 16:9)",
        "",
        "```text",
        bundle["seed_image_prompt"],
        "```",
        "",
        "## 2. Genie 4 Initial World Prompt (`world_setup`)",
        "",
        "```text",
        bundle["world_setup_prompt"],
        "```",
        "",
        "## 3. Mid-Session Live Steering Prompts",
        "",
    ]
    for idx, step in enumerate(bundle["steering_steps"], start=1):
        md_lines.extend(
            [
                f"### Step {idx}: {step['label']} (`offset={step['offset_fraction']:.2f}`)",
                "",
                f"*{step['english_summary']}*",
                "",
                "```text",
                step["steering_prompt"],
                "```",
                "",
            ]
        )

    prompts_md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return {
        "lesson_plan": plan_path,
        "prompts_json": prompts_json_path,
        "prompts_md": prompts_md_path,
    }
