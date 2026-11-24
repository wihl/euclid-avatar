"""Proposition parsing, read-only Elements.pdf extraction, and Gemini lesson planning.

Provides:
- Curated, verified Heiberg Ancient Greek lesson plan for *Elements* Book III,
  Proposition 36 (grounded in Fitzpatrick/Heiberg pp. 105-106).
- Read-only proposition extractor for ``~/Projects/Courses/26Fall/mathe139/materials/books/Elements.pdf``
  using ``pdftotext`` (never mutates or copies course PDFs into the repo).
- Dynamic lesson planner powered by ``gemini-3.5-flash-lite`` on the Gemini
  Interactions API with strict Pydantic JSON schema output for arbitrary
  propositions (e.g., ``I.47``, ``II.13``, ``III.18``, ``IV.11``).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata as ud

from pydantic import BaseModel, Field

from . import DEFAULT_LLM_MODEL

DEFAULT_COURSE_REPO = Path.home() / "Projects/Courses/26Fall/mathe139"
ELEMENTS_PDF_REL_PATH = Path("materials/books/Elements.pdf")
MAX_EXTRACTED_PAGES = 3
MAX_PDF_EXCERPT_CHARS = 9000

ROMAN_BOOKS: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
}
INT_TO_ROMAN: dict[int, str] = {v: k for k, v in ROMAN_BOOKS.items()}

PROP_ID_RE = re.compile(
    r"^\s*(?P<book>XIII|XII|XI|X|IX|VIII|VII|VI|IV|V|III|II|I|1[0-3]|[1-9])"
    r"[\s.:_-]*(?P<num>[1-9]\d{0,2})\s*$",
    re.IGNORECASE,
)


class SteeringStep(BaseModel):
    """One live mid-session drawing and Ancient Greek speech beat for Genie 4."""

    id: str = Field(description="Short snake_case identifier for this proof stage.")
    label: str = Field(description="Human-readable label for UI buttons and logs.")
    drawing_action: str = Field(
        description=(
            "Concrete physical drawing motion Euclid performs in the fine sand "
            "using only his two-legged hinged bronze divider, unmarked wooden "
            "straightedge, and bronze stylus."
        )
    )
    greek_text: str = Field(
        description=(
            "Exact polytonic Ancient Greek (NFC) clause spoken by Euclid from "
            "Heiberg's text of the Elements."
        )
    )
    english_summary: str = Field(
        description="Concise one-sentence English gloss for operator UI display."
    )
    offset_fraction: float = Field(
        ge=0.0,
        le=0.95,
        description=(
            "Normalized timestamp in [0.0, 0.95] at which to inject this live "
            "steering prompt during an automated Genie 4 capture."
        ),
    )


class PropositionPlan(BaseModel):
    """Complete historically grounded Genie 4 teaching plan for an Elements proposition."""

    proposition_id: str = Field(description="Canonical ID, e.g. 'III.36'.")
    book: int = Field(ge=1, le=13, description="Book number (1-13).")
    number: int = Field(ge=1, description="Proposition number within the book.")
    title: str = Field(description="Short English title of the proposition.")
    greek_letters: list[str] = Field(
        description="Greek uppercase point labels used in Heiberg's diagram (e.g. Α, Β, Γ, Δ, Ε, Ζ)."
    )
    seed_diagram_description: str = Field(
        description=(
            "Description of the initial diagram visible in the sand-tray for "
            "the 16:9 seed image."
        )
    )
    initial_drawing_action: str = Field(
        description=(
            "Opening physical strokes Euclid performs immediately after world_setup "
            "with the hinged bronze divider and unmarked straightedge."
        )
    )
    enunciation_greek: str = Field(
        description="Exact polytonic Ancient Greek enunciation (πρότασις) spoken at opening."
    )
    steps: list[SteeringStep] = Field(
        description="Ordered mid-session steering beats (setting-out, proof steps, conclusion)."
    )
    source_note: str = Field(
        description="Citation of the Heiberg/Fitzpatrick source used."
    )

    @property
    def slug(self) -> str:
        """Filesystem-safe lowercase identifier such as ``iii36``."""
        return f"{INT_TO_ROMAN[self.book].lower()}{self.number}"


def parse_proposition_id(raw: str) -> tuple[int, int, str]:
    """Parse proposition identifiers like ``III.36``, ``3.36``, or ``iii36``.

    Returns:
        Tuple of ``(book_int, proposition_int, canonical_id)`` where
        ``canonical_id`` uses Roman numerals (e.g., ``'III.36'``).
    """
    match = PROP_ID_RE.match(raw or "")
    if not match:
        raise ValueError(
            f"Unrecognized Elements proposition identifier {raw!r}. "
            "Expected formats like 'III.36', '3.36', 'II.13', or 'I.47'."
        )
    book_tok = match.group("book").upper()
    book = int(book_tok) if book_tok.isdigit() else ROMAN_BOOKS[book_tok]
    number = int(match.group("num"))
    return book, number, f"{INT_TO_ROMAN[book]}.{number}"


def build_curated_iii36_plan() -> PropositionPlan:
    """Return the verified Heiberg Greek Genie 4 teaching plan for *Elements* III.36.

    Text verified against J. L. Heiberg's Greek text in Richard Fitzpatrick's
    parallel edition (``Elements.pdf``, pp. 105-106), with NFC polytonic Greek
    normalization and exact Greek lettering (Α, Β, Γ, Δ, Ε, Ζ).
    """
    return PropositionPlan(
        proposition_id="III.36",
        book=3,
        number=36,
        title="Secant-Tangent Area Equivalence (Power of a Point)",
        greek_letters=["Α", "Β", "Γ", "Δ", "Ε", "Ζ"],
        seed_diagram_description=(
            "a freshly scribed circle ΑΒΓ in the smooth sand with an outside point Δ "
            "to the lower-left and two straight lines from Δ toward the circle: one "
            "cutting cleanly across the circle at Γ and Α, and one tangent touching "
            "the lower rim at Β"
        ),
        initial_drawing_action=(
            "Euclid plants the sharp pivot spike of the bronze hinged divider firmly "
            "into the fine sand and rotates the pointed writing leg smoothly to scribe "
            "a crisp circle in the sand. He marks a point outside the circle with the "
            "stylus, lays the unmarked wooden straightedge across the tray, and scribes "
            "two clean straight lines from the outside point: one cutting cleanly "
            "through the circle, and one just touching its lower rim."
        ),
        enunciation_greek=ud.normalize(
            "NFC",
            "Ἐὰν κύκλου ληφθῇ τι σημεῖον ἐκτός, καὶ ἀπ᾿ αὐτοῦ πρὸς τὸν κύκλον "
            "προσπίπτωσι δύο εὐθεῖαι, καὶ ἡ μὲν αὐτῶν τέμνῃ τὸν κύκλον, ἡ δὲ "
            "ἐφάπτηται, ἔσται τὸ ὑπὸ ὅλης τῆς τεμνούσης καὶ τῆς ἐκτὸς "
            "ἀπολαμβανομένης μεταξὺ τοῦ τε σημείου καὶ τῆς κυρτῆς περιφερείας "
            "ἴσον τῷ ἀπὸ τῆς ἐφαπτομένης τετραγώνῳ.",
        ),
        steps=[
            SteeringStep(
                id="step_1_ekthesis",
                label="1. Setting-Out & Claim (Ἔκθεσις)",
                drawing_action=(
                    "Euclid uses the slender bronze stylus to neatly inscribe the Greek "
                    "capital letters Α, Β, Γ around the circle, Δ at the outside point, "
                    "Γ at the nearer crossing, and Α at the farther crossing, tracing "
                    "slowly along cutting line ΔΓΑ and tangent ΔΒ."
                ),
                greek_text=ud.normalize(
                    "NFC",
                    "Κύκλου γὰρ τοῦ ΑΒΓ εἰλήφθω τι σημεῖον ἐκτὸς τὸ Δ, καὶ ἀπὸ τοῦ Δ "
                    "πρὸς τὸν ΑΒΓ κύκλον προσπιπτέτωσαν δύο εὐθεῖαι αἱ ΔΓΑ, ΔΒ· καὶ "
                    "ἡ μὲν ΔΓΑ τεμνέτω τὸν ΑΒΓ κύκλον, ἡ δὲ ΒΔ ἐφαπτέσθω· λέγω, ὅτι "
                    "τὸ ὑπὸ τῶν ΑΔ, ΔΓ περιεχόμενον ὀρθογώνιον ἴσον ἐστὶ τῷ ἀπὸ τῆς "
                    "ΔΒ τετραγώνῳ.",
                ),
                english_summary=(
                    "Take Δ outside circle ΑΒΓ with secant ΔΓΑ and tangent ΔΒ; "
                    "claim rect(ΑΔ, ΔΓ) = sq(ΔΒ)."
                ),
                offset_fraction=0.20,
            ),
            SteeringStep(
                id="step_2_case1",
                label="2. Case 1 · Through Center Ζ (III.18, II.6, I.47)",
                drawing_action=(
                    "Euclid marks the center Ζ directly on the diameter ΑΓ, lays his "
                    "unmarked wooden straightedge between center Ζ and tangent point Β, "
                    "and scores radius ΖΒ firmly into the sand to form right angle ΖΒΔ."
                ),
                greek_text=ud.normalize(
                    "NFC",
                    "Ἡ ἄρα ΔΓΑ ἤτοι διὰ τοῦ κέντρου ἐστὶν ἢ οὔ. ἔστω πρότερον διὰ τοῦ "
                    "κέντρου, καὶ ἔστω τὸ Ζ κέντρον τοῦ ΑΒΓ κύκλου, καὶ ἐπεζεύχθω ἡ ΖΒ· "
                    "ὀρθὴ ἄρα ἐστὶν ἡ ὑπὸ ΖΒΔ. καὶ ἐπεὶ εὐθεῖα ἡ ΑΓ δίχα τέτμηται κατὰ "
                    "τὸ Ζ, πρόσκειται δὲ αὐτῇ ἡ ΓΔ, τὸ ἄρα ὑπὸ τῶν ΑΔ, ΔΓ μετὰ τοῦ ἀπὸ "
                    "τῆς ΖΓ ἴσον ἐστὶ τῷ ἀπὸ τῆς ΖΔ. κοινὸν ἀφῃρήσθω τὸ ἀπὸ τῆς ΖΒ· "
                    "λοιπὸν ἄρα τὸ ὑπὸ τῶν ΑΔ, ΔΓ ἴσον ἐστὶ τῷ ἀπὸ τῆς ΔΒ ἐφαπτομένης.",
                ),
                english_summary=(
                    "When ΔΓΑ passes through center Ζ, join ΖΒ ⟂ ΔΒ (III.18), apply "
                    "II.6 and I.47, and subtract sq(ΖΒ)."
                ),
                offset_fraction=0.44,
            ),
            SteeringStep(
                id="step_3_case2",
                label="3. Case 2 · General Secant & Perpendicular ΕΖ",
                drawing_action=(
                    "Euclid smooths part of the sand flat with the back of his hand, "
                    "scribes a fresh circle ΑΒΓ with the two-legged hinged bronze divider, "
                    "marks center Ε above cutting line ΔΓΑ, drops perpendicular ΕΖ from "
                    "Ε onto chord ΑΓ using the divider and unmarked straightedge, and "
                    "joins straight lines ΕΒ, ΕΓ, and ΕΔ."
                ),
                greek_text=ud.normalize(
                    "NFC",
                    "Ἀλλὰ δὴ ἡ ΔΓΑ μὴ ἔστω διὰ τοῦ κέντρου τοῦ ΑΒΓ κύκλου, καὶ "
                    "εἰλήφθω τὸ κέντρον τὸ Ε, καὶ ἀπὸ τοῦ Ε ἐπὶ τὴν ΑΓ κάθετος ἤχθω "
                    "ἡ ΕΖ, καὶ ἐπεζεύχθωσαν αἱ ΕΒ, ΕΓ, ΕΔ· ὀρθὴ ἄρα ἐστὶν ἡ ὑπὸ ΕΒΔ. "
                    "κοινὸν προσκείσθω τὸ ἀπὸ τῆς ΖΕ· τὸ ἄρα ὑπὸ τῶν ΑΔ, ΔΓ μετὰ τῶν "
                    "ἀπὸ τῶν ΓΖ, ΖΕ ἴσον ἐστὶ τοῖς ἀπὸ τῶν ΖΔ, ΖΕ. κοινὸν ἀφῃρήσθω "
                    "τὸ ἀπὸ τῆς ΕΒ· λοιπὸν ἄρα τὸ ὑπὸ τῶν ΑΔ, ΔΓ ἴσον ἐστὶ τῷ ἀπὸ "
                    "τῆς ΔΒ.",
                ),
                english_summary=(
                    "When ΔΓΑ misses center Ε, drop ΕΖ ⟂ ΑΓ (I.12, III.3), add sq(ΖΕ) "
                    "to both sides, apply I.47 three times, and subtract sq(ΕΒ)."
                ),
                offset_fraction=0.68,
            ),
            SteeringStep(
                id="step_4_conclusion",
                label="4. Conclusion (Συμπέρασμα · ὅπερ ἔδει δεῖξαι)",
                drawing_action=(
                    "Euclid sets the bronze hinged divider and unmarked wooden "
                    "straightedge neatly back onto the wooden rim of the sand-tray and "
                    "looks up calmly toward the student as he delivers the conclusion."
                ),
                greek_text=ud.normalize(
                    "NFC",
                    "Ἐὰν ἄρα κύκλου ληφθῇ τι σημεῖον ἐκτός, καὶ ἀπ᾿ αὐτοῦ πρὸς τὸν "
                    "κύκλον προσπίπτωσι δύο εὐθεῖαι, καὶ ἡ μὲν αὐτῶν τέμνῃ τὸν κύκλον, "
                    "ἡ δὲ ἐφάπτηται, ἔσται τὸ ὑπὸ ὅλης τῆς τεμνούσης καὶ τῆς ἐκτὸς "
                    "ἀπολαμβανομένης μεταξὺ τοῦ τε σημείου καὶ τῆς κυρτῆς περιφερείας "
                    "ἴσον τῷ ἀπὸ τῆς ἐφαπτομένης τετραγώνῳ· ὅπερ ἔδει δεῖξαι.",
                ),
                english_summary=(
                    "Concludes Proposition III.36: the very thing it was required to "
                    "show (ὅπερ ἔδει δεῖξαι)."
                ),
                offset_fraction=0.86,
            ),
        ],
        source_note=(
            "J. L. Heiberg Greek text / R. Fitzpatrick parallel edition, "
            "Elements Book III, Proposition 36, pp. 105-106 (MATH E-139)."
        ),
    )


def extract_proposition_from_elements_pdf(
    prop_id: str,
    course_repo_path: Path = DEFAULT_COURSE_REPO,
) -> tuple[str, list[int]]:
    """Extract the Greek and English pages for a proposition from ``Elements.pdf``.

    Reads ``materials/books/Elements.pdf`` strictly read-only via ``pdftotext``.
    Uses word-boundary book headers (``ELEMENTS BOOK <book>\\b``) so Book 1
    never falsely matches Books 10-13.

    Returns:
        Tuple of ``(extracted_text, matched_1based_page_numbers)``.
    """
    book, number, canonical = parse_proposition_id(prop_id)
    pdf_path = course_repo_path / ELEMENTS_PDF_REL_PATH
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Elements.pdf not found at {pdf_path}. "
            "Pass --course-repo pointing to ~/Projects/Courses/26Fall/mathe139."
        )
    pdftotext_bin = shutil.which("pdftotext")
    if not pdftotext_bin:
        raise RuntimeError(
            "pdftotext binary not found on PATH (install poppler via Homebrew)."
        )

    proc = subprocess.run(
        [pdftotext_bin, str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    pages = proc.stdout.split("\x0c")
    book_re = re.compile(rf"ELEMENTS BOOK {book}(?!\d)")
    prop_re = re.compile(rf"(?m)^\s*Proposition\s+{number}[†‡*§\s]*$")
    next_prop_re = re.compile(rf"(?m)^\s*Proposition\s+{number + 1}[†‡*§\s]*$")

    start_idx: int | None = None
    for idx, page_text in enumerate(pages):
        if book_re.search(page_text) and prop_re.search(page_text):
            start_idx = idx
            break
    if start_idx is None:
        raise ValueError(
            f"Could not locate {canonical} (Book {book}, Proposition {number}) in {pdf_path}."
        )

    collected_pages: list[int] = []
    chunks: list[str] = []
    for offset in range(MAX_EXTRACTED_PAGES):
        page_idx = start_idx + offset
        if page_idx >= len(pages):
            break
        page_text = pages[page_idx]
        if offset > 0 and not book_re.search(page_text):
            break
        collected_pages.append(page_idx + 1)
        chunks.append(page_text)
        if offset > 0 and next_prop_re.search(page_text):
            break

    combined = "\n\n".join(chunks).strip()[:MAX_PDF_EXCERPT_CHARS]
    return combined, collected_pages


def plan_proposition_with_gemini(
    prop_id: str,
    elements_excerpt: str,
    api_key: str,
    *,
    model: str = DEFAULT_LLM_MODEL,
) -> PropositionPlan:
    """Use ``gemini-3.5-flash-lite`` on Interactions API to build a Genie 4 lesson plan.

    Grounds Euclid's spoken Ancient Greek strictly in the extracted Heiberg text
    from ``Elements.pdf`` and restricts physical drawing gestures to the
    historically accurate bronze hinged divider, unmarked wooden straightedge,
    and bronze stylus on a wooden sand-tray.
    """
    from google import genai

    book, number, canonical = parse_proposition_id(prop_id)
    if not api_key:
        raise RuntimeError(
            f"Missing GEMINI_API_KEY required to plan {canonical} with {model}."
        )

    prompt = (
        f"You are preparing a historically accurate Genie 4 interactive world lesson "
        f"plan for Euclid of Alexandria (~300 BCE) teaching Elements {canonical} "
        f"(Book {book}, Proposition {number}) in Ancient Greek for Harvard MATH E-139.\n\n"
        "STRICT RULES:\n"
        "1. Every `enunciation_greek` and `steps[*].greek_text` field MUST use authentic "
        "polytonic Ancient Greek (NFC) copied verbatim from the Heiberg/Fitzpatrick excerpt "
        "below (fixing obvious PDF accent typos if any, without inventing new prose).\n"
        "2. Physical drawing actions MUST use ONLY historically accurate tools of ~300 BCE: "
        "a two-legged hinged bronze drafting divider (pivot spike + writing leg, NEVER a "
        "magnetic compass), a plain completely unmarked wooden straightedge (zero tick marks), "
        "and a bronze stylus drawing in a shallow wooden sand-tray (abax).\n"
        "3. Produce exactly 4 ordered `steps` with `offset_fraction` values near "
        "[0.20, 0.44, 0.68, 0.86]: setting-out/claim, main construction/proof stage 1, "
        "main proof stage 2, and conclusion ending in ὅπερ ἔδει δεῖξαι or ὅπερ ἔδει ποιῆσαι.\n"
        "4. Use the exact Greek uppercase diagram letters from the Greek column.\n\n"
        f"ELEMENTS.PDF EXCERPT FOR {canonical}:\n{elements_excerpt}"
    )

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    interaction = client.interactions.create(
        model=model,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": PropositionPlan.model_json_schema(),
        },
    )
    raw_json = (interaction.output_text or "").strip()
    if not raw_json:
        raise RuntimeError(f"Empty structured response from {model} for {canonical}.")
    plan = PropositionPlan.model_validate_json(raw_json)
    # Enforce canonical proposition coordinates and NFC Greek normalization
    plan.proposition_id = canonical
    plan.book = book
    plan.number = number
    plan.enunciation_greek = ud.normalize("NFC", plan.enunciation_greek)
    for step in plan.steps:
        step.greek_text = ud.normalize("NFC", step.greek_text)
    return plan


def load_or_build_proposition_plan(
    prop_id: str,
    *,
    api_key: str = "",
    course_repo_path: Path = DEFAULT_COURSE_REPO,
    llm_model: str = DEFAULT_LLM_MODEL,
    use_llm: bool = False,
    cache_path: Path | None = None,
) -> PropositionPlan:
    """Return a validated ``PropositionPlan`` for any proposition.

    Uses the verified built-in Heiberg plan for ``III.36`` unless ``use_llm=True``.
    For any other proposition (e.g., ``I.47``, ``II.13``, ``III.18``), extracts
    the Greek/English pages read-only from ``Elements.pdf`` and plans the steps
    using ``gemini-3.5-flash-lite``.
    """
    _, _, canonical = parse_proposition_id(prop_id)
    if canonical == "III.36" and not use_llm:
        return build_curated_iii36_plan()

    if cache_path and cache_path.exists():
        cached = PropositionPlan.model_validate_json(
            cache_path.read_text(encoding="utf-8")
        )
        if cached.proposition_id == canonical:
            return cached

    excerpt, pages = extract_proposition_from_elements_pdf(
        canonical, course_repo_path=course_repo_path
    )
    plan = plan_proposition_with_gemini(
        canonical, excerpt, api_key, model=llm_model
    )
    if pages:
        page_span = (
            f"p. {pages[0]}" if len(pages) == 1 else f"pp. {pages[0]}-{pages[-1]}"
        )
        if page_span not in plan.source_note:
            plan.source_note = (
                f"Heiberg/Fitzpatrick Elements {canonical}, {page_span} "
                f"(planned via {llm_model})."
            )
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return plan
