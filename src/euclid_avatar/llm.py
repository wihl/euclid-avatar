"""Single-pass structured Gemini LLM generator returning aligned English + Ancient Greek JSON."""
from __future__ import annotations

import json
import time
import unicodedata as ud
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .config import Config
from .index import RetrievedChunk
from .tts import sanitize_greek_text


class SentencePair(BaseModel):
    english: str = Field(description="Single sentence in English.")
    greek: str = Field(description="Exact corresponding sentence in polytonic Ancient Greek (NFC).")


class EuclidResponseSchema(BaseModel):
    sources: list[str] = Field(description="Cited course sources, e.g. ['COURSE.md', 'Elements I.23'].")
    english: str = Field(description="Full 2-4 sentence English answer.")
    greek: str = Field(description="Full polytonic Ancient Greek translation.")
    sentences: list[SentencePair] = Field(description="Sentence-by-sentence aligned English and Ancient Greek pairs (2 to 4 sentences).")


@dataclass
class LLMGenerationResult:
    sources: list[str]
    english: str
    greek: str
    sentences: list[dict[str, str]]
    model: str
    elapsed_ms: float
    raw_json: str


class EuclidLLM:
    """Low-latency single-pass structured Gemini generator for Euclid."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        if not cfg.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env or environment.")
        self.client = genai.Client(api_key=cfg.gemini_api_key)
        self.persona_path = cfg.prompts_dir / "euclid_persona.md"
        self.system_instruction = self._load_persona()

    def _load_persona(self) -> str:
        if self.persona_path.exists():
            return self.persona_path.read_text(encoding="utf-8")
        return "You are Euclid of Alexandria answering questions for MATH E-139 in English and polytonic Ancient Greek."

    def reload_persona(self) -> None:
        self.system_instruction = self._load_persona()

    def generate(
        self,
        question: str,
        retrieved_chunks: list[RetrievedChunk],
        *,
        temperature: float = 0.2,
    ) -> LLMGenerationResult:
        t0 = time.perf_counter()

        context_blocks: list[str] = []
        for idx, ch in enumerate(retrieved_chunks, start=1):
            context_blocks.append(
                f"--- SOURCE {idx}: {ch.source_label} ({ch.rel_path}) ---\n"
                f"Title: {ch.title}\n"
                f"{ch.content[:1800]}"
            )
        context_str = "\n\n".join(context_blocks) if context_blocks else "No additional chunks retrieved; use pinned course knowledge."

        user_prompt = (
            f"RETRIEVED MATH E-139 COURSE CONTEXT:\n{context_str}\n\n"
            f"STUDENT / INSTRUCTOR QUESTION:\n{question.strip()}\n\n"
            "Return strict JSON with `sources`, `english`, `greek`, and `sentences` (2 to 4 concise sentence pairs). "
            "Ensure `greek` uses authentic polytonic Ancient Greek (Heiberg/Fitzpatrick vocabulary) and quotes original Greek verbatim when an enunciation, definition, postulate, or common notion is asked for."
        )

        # Configure minimum thinking overhead based on model family for lowest latency (~1.3-2.2s)
        gen_config_kwargs: dict[str, Any] = {
            "system_instruction": self.system_instruction,
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_schema": EuclidResponseSchema,
        }

        model_to_use = getattr(self, "_resolved_model", self.cfg.gemini_model)
        if "lite" not in model_to_use:
            if "2.5" in model_to_use:
                gen_config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            else:
                gen_config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                )

        try:
            response = self.client.models.generate_content(
                model=model_to_use,
                contents=user_prompt,
                config=types.GenerateContentConfig(**gen_config_kwargs),
            )
        except Exception as exc:
            err_str = str(exc)
            if "404" in err_str or "no longer available" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                fallback_model = (
                    "gemini-3-flash-preview"
                    if model_to_use != "gemini-3-flash-preview"
                    else "gemini-3.1-flash-lite"
                )
                model_to_use = fallback_model
                if "lite" in model_to_use:
                    gen_config_kwargs.pop("thinking_config", None)
                else:
                    gen_config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL
                    )
                response = self.client.models.generate_content(
                    model=model_to_use,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(**gen_config_kwargs),
                )
            elif "thinking" in err_str.lower() or "400" in err_str:
                gen_config_kwargs.pop("thinking_config", None)
                response = self.client.models.generate_content(
                    model=model_to_use,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(**gen_config_kwargs),
                )
            else:
                raise

        raw_text = (response.text or "{}").strip()
        data = json.loads(raw_text)

        sentences_raw = data.get("sentences", [])
        sentences: list[dict[str, str]] = []
        for s in sentences_raw:
            eng_s = str(s.get("english", "")).strip()
            grk_s = sanitize_greek_text(ud.normalize("NFC", str(s.get("greek", "")).strip()))
            if eng_s and grk_s:
                sentences.append({"english": eng_s, "greek": grk_s})

        english_full = str(data.get("english", "")).strip()
        greek_full = sanitize_greek_text(ud.normalize("NFC", str(data.get("greek", "")).strip()))

        if not sentences and english_full and greek_full:
            sentences = [{"english": english_full, "greek": greek_full}]
        if not english_full and sentences:
            english_full = " ".join(s["english"] for s in sentences)
        if not greek_full and sentences:
            greek_full = " ".join(s["greek"] for s in sentences)

        sources = [str(src) for src in data.get("sources", [])]
        if not sources and retrieved_chunks:
            sources = [c.source_label for c in retrieved_chunks[:2]]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return LLMGenerationResult(
            sources=sources,
            english=english_full,
            greek=greek_full,
            sentences=sentences,
            model=model_to_use,
            elapsed_ms=round(elapsed_ms, 1),
            raw_json=raw_text,
        )
