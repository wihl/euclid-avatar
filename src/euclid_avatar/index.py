"""Fast local SQLite FTS5 (BM25) + exact proposition/entity indexer and retriever for MATH E-139."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata as ud
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz  # PyMuPDF

from .config import Config

# Spacing breathings/accents before capital letters in Fitzpatrick's Elements.pdf
PRE_CAPITAL_DIACRITICS: dict[str, str] = {
    "\u1fbf": "\u0313",  # ᾿ -> smooth breathing
    "\u1ffe": "\u0314",  # ῾ -> rough breathing
    "\u1fce": "\u0313\u0301",  # ῎ -> smooth + acute
    "\u1fcd": "\u0313\u0300",  # ῍ -> smooth + grave
    "\u1fcf": "\u0313\u0342",  # ῏ -> smooth + circumflex
    "\u1fde": "\u0314\u0301",  # ῞ -> rough + acute
    "\u1fdd": "\u0314\u0300",  # ῝ -> rough + grave
    "\u1fdf": "\u0314\u0342",  # ῟ -> rough + circumflex
    "’": "\u0313",
}

PRE_CAPITAL_RE = re.compile(r"([\u1fbf\u1ffe\u1fce\u1fcd\u1fcf\u1fde\u1fdd\u1fdf])([Α-Ω])")

# Exact Book page ranges in Fitzpatrick's Elements.pdf (1-indexed page numbers)
ELEMENTS_BOOK_RANGES: list[tuple[str, int, int, int]] = [
    ("I", 1, 6, 48),
    ("II", 2, 50, 67),
    ("III", 3, 70, 107),
    ("IV", 4, 110, 127),
    ("V", 5, 130, 153),
    ("VI", 6, 156, 191),
    ("VII", 7, 194, 226),
    ("VIII", 8, 228, 252),
    ("IX", 9, 254, 279),
    ("X", 10, 282, 421),
    ("XI", 11, 424, 470),
    ("XII", 12, 472, 504),
    ("XIII", 13, 506, 544),
]

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
}
INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}


def normalize_greek_pdf_text(text: str, filename: str = "") -> str:
    """Normalize polytonic Greek text extracted from course PDFs."""
    # Fix pre-capital spacing diacritics in Elements.pdf
    text = PRE_CAPITAL_RE.sub(
        lambda m: m.group(2) + PRE_CAPITAL_DIACRITICS.get(m.group(1), ""),
        text,
    )
    # Replace U+2206 INCREMENT with Greek capital Delta U+0394
    text = text.replace("\u2206", "\u0394")
    # Fix MICRO SIGN U+00B5 -> Greek mu U+03BC in lexicon PDF
    text = text.replace("\u00b5", "\u03bc")
    # Fix "σv" extraction artifact in definitions (1).pdf and postulates and common notions.pdf
    if "definitions" in filename.lower() or "postulates" in filename.lower():
        text = text.replace("σv", "σ")
    # Rejoin line-end hyphenated Greek words
    text = re.sub(r"([\u0370-\u03ff\u1f00-\u1fff])-\s*\n\s*([\u0370-\u03ff\u1f00-\u1fff])", r"\1\2", text)
    return ud.normalize("NFC", text)


@dataclass
class RetrievedChunk:
    chunk_id: int
    source_label: str
    rel_path: str
    entity_keys: list[str]
    title: str
    content: str
    match_type: str  # "exact" or "bm25"
    score: float


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS indexed_files (
            rel_path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL,
            source_label TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            entity_keys_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entity_map (
            entity_key TEXT NOT NULL,
            chunk_id INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (entity_key, chunk_id)
        );
        CREATE INDEX IF NOT EXISTS idx_entity_key ON entity_map(entity_key, priority);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            title,
            source_label,
            entity_keys_json,
            content,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
        """
    )


def _extract_entities_from_text(title: str, content: str, rel_path: str) -> list[str]:
    """Detect canonical entity keys (e.g., PROP:I.23, DEF:I.15, POST:5, CN:1, CLASS:6) in a chunk."""
    combined = f"{rel_path}\n{title}\n{content[:1200]}"
    entities: set[str] = set()

    # Propositions: I.23, II.12, III.20, IV.10, VI.1, etc.
    for m in re.finditer(r"\b(I{1,3}|IV|VI{0,3}|IX|XI{0,3})\.(\d{1,3})\b", combined):
        book_rom, prop_num = m.group(1), int(m.group(2))
        if book_rom in ROMAN_TO_INT and 1 <= prop_num <= 115:
            entities.add(f"PROP:{book_rom}.{prop_num}")

    # "Proposition 23" / "Prop. 47" (default to Book I if no Roman numeral attached)
    for m in re.finditer(r"\bProp(?:osition|\.)\s*(\d{1,2})\b", combined, re.IGNORECASE):
        prop_num = int(m.group(1))
        if 1 <= prop_num <= 48:
            entities.add(f"PROP:I.{prop_num}")

    # Project folders like 2026-project-ii13, 2026-project-i23, 2026-project-i12, 2026-project-i8
    for m in re.finditer(r"project-(i{1,3}|iv|vi{0,3})(\d{1,2})\b", rel_path, re.IGNORECASE):
        rom = m.group(1).upper()
        if rom in ROMAN_TO_INT:
            entities.add(f"PROP:{rom}.{int(m.group(2))}")
    if "greek-07" in rel_path.lower():
        entities.add("PROP:II.13")
        entities.add("TOPIC:II13_VERBS")
    if "project-ii13" in rel_path.lower():
        entities.add("PROP:II.13")
        entities.add("PROP:II.12")
        entities.add("TOPIC:II13_GRAMMAR")

    # Definitions: Definition 15, Def. 23, Def 1
    for m in re.finditer(r"\bDef(?:inition|\.)?\s*(\d{1,2})\b", combined, re.IGNORECASE):
        def_num = int(m.group(1))
        if 1 <= def_num <= 23:
            entities.add(f"DEF:I.{def_num}")

    # Postulates: Postulate 1..5
    for m in re.finditer(r"\bPostulate\s*([1-5])\b", combined, re.IGNORECASE):
        entities.add(f"POST:{m.group(1)}")
    if re.search(r"\b(fifth|parallel)\s+postulate\b", combined, re.IGNORECASE):
        entities.add("POST:5")

    # Common Notions: Common Notion 1..9, CN 1..9
    for m in re.finditer(r"\b(?:Common\s+Notion|CN)\s*([1-9])\b", combined, re.IGNORECASE):
        entities.add(f"CN:{m.group(1)}")

    # Class numbers: Class 1..13, class-02..class-12, MathNotes01..12
    for m in re.finditer(r"\bClass[\s_-]*0?(\d{1,2})\b", combined, re.IGNORECASE):
        cnum = int(m.group(1))
        if 1 <= cnum <= 13:
            entities.add(f"CLASS:{cnum}")
    for m in re.finditer(r"MathNotes0?(\d{1,2})", rel_path, re.IGNORECASE):
        cnum = int(m.group(1))
        if 1 <= cnum <= 13:
            entities.add(f"CLASS:{cnum}")

    # Key mathematical & Greek topics
    topic_patterns = {
        "TOPIC:CAYLEY_KLEIN": r"Cayley[-\s]Klein|nine\s+plane\s+geometries",
        "TOPIC:HYPERBOLIC": r"\bhyperbolic\b|Poincar[eé]|Hermes\s+model|upper\s+half[-\s]plane|Klein\s+model|hyperboloid",
        "TOPIC:SPHERICAL": r"\bspherical\b|\belliptic\b|great\s+circle",
        "TOPIC:PYTHAGOREAN": r"\bPythagorean\b|I\.47|Proposition\s+47",
        "TOPIC:PROP_PARTS": r"πρότασις|ἔκθεσις|διορισμός|κατασκευή|ἀπόδειξις|συμπέρασμα|Parts\s+of\s+a\s+Euclidean\s+Proposition|ὅπερ\s+ἔδει",
        "TOPIC:PRONUNCIATION": r"Erasmian|GreekAlphabetSequence|pronunciation|diphthong|breathing",
        "TOPIC:ISOSCELES": r"\bisosceles\b|ἰσοσκελ|pous\s+asinorum|I\.5",
        "TOPIC:PARALLEL": r"\bparallel\b|παράλληλ|I\.27|I\.29|I\.31|I\.32",
    }
    for key, pat in topic_patterns.items():
        if re.search(pat, combined, re.IGNORECASE):
            entities.add(key)

    return sorted(entities)


def _chunk_markdown(text: str, rel_path: str, source_label: str) -> list[dict[str, Any]]:
    """Split a Markdown/Quarto file by H1/H2/H3 sections into indexable chunks."""
    lines = text.splitlines()
    chunks: list[dict[str, Any]] = []
    curr_title = source_label
    curr_lines: list[str] = []

    def _chunk_priority() -> int:
        if "project-ii13" in rel_path or "greek-07" in rel_path:
            return 0
        if "study/" in rel_path or "COURSE.md" in rel_path or "project-i23" in rel_path:
            return 1
        return 2

    def flush(title: str, body_lines: list[str]) -> None:
        body = "\n".join(body_lines).strip()
        if not body or len(body) < 20:
            return
        prio = _chunk_priority()
        # Cap individual chunk size around 2400 chars with sub-splits if huge
        if len(body) <= 2600:
            entities = _extract_entities_from_text(title, body, rel_path)
            chunks.append(
                {
                    "rel_path": rel_path,
                    "source_label": source_label,
                    "title": title,
                    "content": body,
                    "entity_keys": entities,
                    "priority": prio,
                }
            )
        else:
            paragraphs = body.split("\n\n")
            buf: list[str] = []
            buf_len = 0
            part = 1
            for p in paragraphs:
                if buf_len + len(p) > 2200 and buf:
                    sub_body = "\n\n".join(buf)
                    sub_title = f"{title} (part {part})"
                    entities = _extract_entities_from_text(sub_title, sub_body, rel_path)
                    chunks.append(
                        {
                            "rel_path": rel_path,
                            "source_label": source_label,
                            "title": sub_title,
                            "content": sub_body,
                            "entity_keys": entities,
                            "priority": prio,
                        }
                    )
                    buf = [p]
                    buf_len = len(p)
                    part += 1
                else:
                    buf.append(p)
                    buf_len += len(p) + 2
            if buf:
                sub_body = "\n\n".join(buf)
                sub_title = f"{title} (part {part})" if part > 1 else title
                entities = _extract_entities_from_text(sub_title, sub_body, rel_path)
                chunks.append(
                    {
                        "rel_path": rel_path,
                        "source_label": source_label,
                        "title": sub_title,
                        "content": sub_body,
                        "entity_keys": entities,
                        "priority": prio,
                    }
                )

    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            flush(curr_title, curr_lines)
            curr_title = f"{source_label} — {m.group(2).strip()}"
            curr_lines = [line]
        else:
            curr_lines.append(line)
    flush(curr_title, curr_lines)
    return chunks


def _index_elements_pdf(pdf_path: Path, rel_path: str) -> list[dict[str, Any]]:
    """Extract parallel Greek (left column) & English (right column) propositions from Elements.pdf."""
    chunks: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))
    left_rect = fitz.Rect(0, 0, 306, 792)
    right_rect = fitz.Rect(306, 0, 612, 792)

    prop_header_re = re.compile(r"(?m)^\s*Proposition\s+(\d+)[†‡§*]*\s*$")
    greek_header_re = re.compile(r"(?m)^\s*([^\s]+þ\.)\s*$")

    # Priority books in MATH E-139 syllabus: Books I, II, III, IV, VI
    syllabus_books = {"I", "II", "III", "IV", "VI"}

    for book_rom, book_num, start_page, end_page in ELEMENTS_BOOK_RANGES:
        if book_rom not in syllabus_books:
            continue

        greek_pages: list[str] = []
        eng_pages: list[str] = []
        for pno in range(start_page, min(end_page + 1, len(doc) + 1)):
            page = doc[pno - 1]
            g_txt = normalize_greek_pdf_text(page.get_text("text", clip=left_rect), "Elements.pdf")
            e_txt = page.get_text("text", clip=right_rect)
            greek_pages.append(f"[p.{pno}]\n{g_txt}")
            eng_pages.append(f"[p.{pno}]\n{e_txt}")

        full_greek = "\n".join(greek_pages)
        full_eng = "\n".join(eng_pages)

        # Split English by Proposition headers
        eng_matches = list(prop_header_re.finditer(full_eng))
        # Split Greek by legacy keraia header (excluding STOIQEIWN)
        greek_matches = [
            m for m in greek_header_re.finditer(full_greek)
            if "STOIQEIWN" not in full_greek[max(0, m.start() - 20):m.end()]
        ]

        # Extract Book Definitions / Postulates / Common Notions preamble (before Proposition 1)
        if eng_matches:
            preamble_eng = full_eng[:eng_matches[0].start()].strip()
            preamble_grk = full_greek[:greek_matches[0].start()].strip() if greek_matches else ""
            if preamble_eng:
                entity_keys = [f"DEF:{book_rom}"]
                if book_rom == "I":
                    entity_keys.extend([f"DEF:I.{i}" for i in range(1, 24)])
                    entity_keys.extend([f"POST:{i}" for i in range(1, 6)])
                    entity_keys.extend([f"CN:{i}" for i in range(1, 10)])
                chunks.append(
                    {
                        "rel_path": rel_path,
                        "source_label": f"Elements Book {book_rom} Definitions & Axioms",
                        "title": f"Euclid's Elements Book {book_rom} — Definitions, Postulates, Common Notions",
                        "content": f"=== GREEK (Heiberg) ===\n{preamble_grk[:2500]}\n\n=== ENGLISH (Fitzpatrick) ===\n{preamble_eng[:2500]}",
                        "entity_keys": entity_keys,
                        "priority": 0,
                    }
                )

        # Pair each Proposition N in English with its corresponding Greek block
        for idx, em in enumerate(eng_matches):
            prop_num = int(em.group(1))
            e_start = em.start()
            e_end = eng_matches[idx + 1].start() if idx + 1 < len(eng_matches) else len(full_eng)
            e_block = full_eng[e_start:e_end].strip()

            g_block = ""
            if idx < len(greek_matches):
                g_start = greek_matches[idx].start()
                g_end = greek_matches[idx + 1].start() if idx + 1 < len(greek_matches) else len(full_greek)
                g_block = full_greek[g_start:g_end].strip()

            prop_id = f"{book_rom}.{prop_num}"
            entity_keys = [f"PROP:{prop_id}"]
            if prop_id == "I.47":
                entity_keys.append("TOPIC:PYTHAGOREAN")
            elif prop_id == "I.5":
                entity_keys.append("TOPIC:ISOSCELES")
            elif prop_id in {"I.27", "I.29", "I.31", "I.32"}:
                entity_keys.append("TOPIC:PARALLEL")

            content = (
                f"Proposition {prop_id} (Euclid's Elements, Book {book_rom}, Proposition {prop_num})\n"
                f"=== GREEK (Heiberg) ===\n{g_block[:2200]}\n\n"
                f"=== ENGLISH (Fitzpatrick) ===\n{e_block[:2200]}"
            )
            chunks.append(
                {
                    "rel_path": rel_path,
                    "source_label": f"Elements {prop_id}",
                    "title": f"Elements {prop_id} (Book {book_rom}, Proposition {prop_num})",
                    "content": content,
                    "entity_keys": entity_keys,
                    "priority": 0,
                }
            )

    doc.close()
    return chunks


def _index_generic_pdf(pdf_path: Path, rel_path: str, source_label: str) -> list[dict[str, Any]]:
    """Extract text page-by-page from greek-resources/*.pdf and math-notes/*.pdf."""
    chunks: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))
    fname = pdf_path.name
    for idx, page in enumerate(doc):
        pno = idx + 1
        raw = page.get_text("text")
        text = normalize_greek_pdf_text(raw, fname).strip()
        if len(text) < 25:
            continue
        title = f"{source_label} (p. {pno})"
        entities = _extract_entities_from_text(title, text, rel_path)
        if "definitions" in fname.lower():
            entities.append("DEF:I")
        if "postulates" in fname.lower():
            entities.extend(["POST:1", "POST:2", "POST:3", "POST:4", "POST:5", "CN:1", "CN:5", "CN:9"])
        if "parts of a euclidean proposition" in fname.lower():
            entities.append("TOPIC:PROP_PARTS")
        if "greekalphabetsequence" in fname.lower():
            entities.append("TOPIC:PRONUNCIATION")
        chunks.append(
            {
                "rel_path": rel_path,
                "source_label": f"{source_label} p.{pno}",
                "title": title,
                "content": text[:2800],
                "entity_keys": sorted(set(entities)),
                "priority": 1,
            }
        )
    doc.close()
    return chunks


def build_or_update_index(cfg: Config, force: bool = False) -> dict[str, Any]:
    """Build or incrementally update `.cache/course_index.sqlite` in strictly read-only mode on COURSE_REPO_PATH."""
    t0 = time.perf_counter()
    repo = cfg.course_repo_path
    if not repo.exists():
        raise FileNotFoundError(f"Course repository not found at {repo}")

    db_path = cfg.index_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    _init_db(conn)

    if force:
        conn.executescript(
            """
            DELETE FROM indexed_files;
            DELETE FROM entity_map;
            DELETE FROM chunks;
            INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');
            """
        )
        conn.commit()

    existing: dict[str, tuple[float, int]] = {
        row[0]: (float(row[1]), int(row[2]))
        for row in conn.execute("SELECT rel_path, mtime, size FROM indexed_files")
    }

    # Discover target files strictly read-only
    candidates: list[tuple[Path, str, str]] = []

    def add_glob(pattern: str, label_prefix: str = "", allow_local: bool = False) -> None:
        for p in sorted(repo.glob(pattern)):
            if not p.is_file():
                continue
            rel = str(p.relative_to(repo))
            if rel.startswith("local/") and not allow_local:
                continue
            # Avoid indexing candidate draft subdirs in greek-01
            if "candidate-" in rel:
                continue
            # Skip duplicate Elements of Euclid.pdf in greek-resources (we index materials/books/Elements.pdf)
            if p.name == "Elements of Euclid.pdf":
                continue
            # Skip redundant Beamer PDFs since MathNotes01..12 have cleaner printable text
            if "Beamer.pdf" in p.name:
                continue
            label = label_prefix or p.stem
            candidates.append((p, rel, label))

    add_glob("coursework/COURSE.md", "COURSE.md")
    add_glob("coursework/study/*.md")
    add_glob("coursework/lectures/**/*.md")
    add_glob("coursework/assignments/**/*.md")
    add_glob("coursework/assignments/**/*.qmd")
    add_glob("coursework/projects/**/*.md")
    add_glob("coursework/projects/**/*.qmd")
    if cfg.include_local_recordings:
        add_glob("local/recordings/*/transcript.md", allow_local=True)
    add_glob("materials/course/canvas-week-by-week-euclid-links.md", "canvas-week-by-week-euclid-links.md")
    add_glob("materials/course/greek-resources/*.pdf")
    add_glob("materials/course/math-notes/*.pdf")
    add_glob("materials/books/Elements.pdf", "Elements.pdf")

    updated_files = 0
    total_chunks_added = 0

    for abs_path, rel_path, default_label in candidates:
        stat = abs_path.stat()
        mtime, size = stat.st_mtime, stat.st_size
        if not force and rel_path in existing:
            old_mtime, old_size = existing[rel_path]
            if abs(old_mtime - mtime) < 1e-3 and old_size == size:
                continue

        # Remove old chunks for this file if updating
        old_ids = [
            r[0] for r in conn.execute("SELECT id FROM chunks WHERE rel_path = ?", (rel_path,))
        ]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            conn.execute(f"DELETE FROM entity_map WHERE chunk_id IN ({placeholders})", old_ids)
            conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", old_ids)

        if rel_path == "materials/books/Elements.pdf":
            file_chunks = _index_elements_pdf(abs_path, rel_path)
        elif abs_path.suffix.lower() == ".pdf":
            file_chunks = _index_generic_pdf(abs_path, rel_path, abs_path.stem)
        else:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
            label = rel_path.replace("coursework/", "").replace("materials/course/", "")
            file_chunks = _chunk_markdown(text, rel_path, label)

        for ch in file_chunks:
            entity_keys = ch["entity_keys"]
            cur = conn.execute(
                """
                INSERT INTO chunks (rel_path, source_label, title, content, entity_keys_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ch["rel_path"],
                    ch["source_label"],
                    ch["title"],
                    ch["content"],
                    json.dumps(entity_keys, ensure_ascii=False),
                ),
            )
            chunk_id = int(cur.lastrowid)
            prop_count = sum(1 for ek in entity_keys if ek.startswith("PROP:"))
            base_prio = int(ch.get("priority", 1))
            for ek in entity_keys:
                prio = base_prio
                if ek.startswith("PROP:") and prop_count > 5 and base_prio > 0:
                    prio = 3  # Syllabus/overview tables listing many propositions
                conn.execute(
                    "INSERT OR REPLACE INTO entity_map (entity_key, chunk_id, priority) VALUES (?, ?, ?)",
                    (ek, chunk_id, prio),
                )
            total_chunks_added += 1

        conn.execute(
            "INSERT OR REPLACE INTO indexed_files (rel_path, mtime, size) VALUES (?, ?, ?)",
            (rel_path, mtime, size),
        )
        updated_files += 1

    if updated_files > 0 or force:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        conn.commit()

    total_files = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    total_entities = conn.execute("SELECT COUNT(DISTINCT entity_key) FROM entity_map").fetchone()[0]
    conn.close()

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "db_path": str(db_path),
        "updated_files": updated_files,
        "total_files": total_files,
        "total_chunks": total_chunks,
        "distinct_entity_keys": total_entities,
        "elapsed_ms": round(elapsed_ms, 1),
    }


WORD_NUMBERS = {
    "first": 1, "one": 1, "1st": 1,
    "second": 2, "two": 2, "2nd": 2,
    "third": 3, "three": 3, "3rd": 3,
    "fourth": 4, "four": 4, "4th": 4,
    "fifth": 5, "five": 5, "5th": 5,
    "sixth": 6, "six": 6, "6th": 6,
    "seventh": 7, "seven": 7, "7th": 7,
    "eighth": 8, "eight": 8, "8th": 8,
    "ninth": 9, "nine": 9, "9th": 9,
    "tenth": 10, "ten": 10, "10th": 10,
    "eleventh": 11, "11th": 11,
    "twelfth": 12, "12th": 12,
    "fifteenth": 15, "fifteen": 15, "15th": 15,
    "twentieth": 20, "twenty": 20, "20th": 20,
    "twenty-third": 23, "twenty third": 23, "23rd": 23,
    "forty-seventh": 47, "forty seventh": 47, "47th": 47,
}


def parse_query_entities(query: str) -> list[str]:
    """Fast exact proposition / entity parser (< 0.2 ms)."""
    q = query.strip()
    q_lower = q.lower()
    entities: list[str] = []

    def add(ek: str) -> None:
        if ek not in entities:
            entities.append(ek)

    # 1. Explicit Book.Prop in Roman or Arabic (e.g. I.23, 1.23, Book 1 Prop 23, Book I Proposition 47)
    for m in re.finditer(r"\b(I{1,3}|IV|VI{0,3}|IX|XI{0,3})\s*[.,:]\s*(\d{1,3})\b", q, re.IGNORECASE):
        rom = m.group(1).upper()
        if rom in ROMAN_TO_INT:
            add(f"PROP:{rom}.{int(m.group(2))}")

    for m in re.finditer(r"\b(?:Book\s+(I{1,3}|IV|VI{0,3}|\d{1,2})[\s,]+)?Prop(?:osition|\.)?\s*(\d{1,3})\b", q, re.IGNORECASE):
        b_raw, p_raw = m.group(1), int(m.group(2))
        if b_raw:
            b_up = b_raw.upper()
            rom = b_up if b_up in ROMAN_TO_INT else INT_TO_ROMAN.get(int(b_raw), "I")
        else:
            rom = "I"
        add(f"PROP:{rom}.{p_raw}")

    for m in re.finditer(r"\b([1-6])\.(\d{1,2})\b", q):
        rom = INT_TO_ROMAN.get(int(m.group(1)), "I")
        add(f"PROP:{rom}.{int(m.group(2))}")

    # Spoken numbers like "Proposition twenty-three" or "I twenty-three"
    for word, num in WORD_NUMBERS.items():
        if re.search(rf"\b(?:proposition|prop|book\s+one|i)\s+{re.escape(word)}\b", q_lower):
            add(f"PROP:I.{num}")
        if re.search(rf"\b(?:postulate)\s+{re.escape(word)}\b|\b{re.escape(word)}\s+postulate\b", q_lower) and 1 <= num <= 5:
            add(f"POST:{num}")
        if re.search(rf"\b(?:common\s+notion)\s+{re.escape(word)}\b|\b{re.escape(word)}\s+common\s+notion\b", q_lower) and 1 <= num <= 9:
            add(f"CN:{num}")
        if re.search(rf"\b(?:definition)\s+{re.escape(word)}\b|\b{re.escape(word)}\s+definition\b", q_lower) and 1 <= num <= 23:
            add(f"DEF:I.{num}")
        if re.search(rf"\bclass\s+{re.escape(word)}\b", q_lower) and 1 <= num <= 13:
            add(f"CLASS:{num}")

    # 2. Definitions
    for m in re.finditer(r"\bDef(?:inition|\.)?\s*(\d{1,2})\b", q, re.IGNORECASE):
        add(f"DEF:I.{int(m.group(1))}")
    if re.search(r"\bdefine\b|\bdefinition\b|ὅρος|ὅροι", q_lower):
        if "point" in q_lower or "σημεῖον" in q_lower:
            add("DEF:I.1")
        if "line" in q_lower and "straight" not in q_lower and "parallel" not in q_lower:
            add("DEF:I.2")
        if "straight" in q_lower or "εὐθεῖα" in q_lower:
            add("DEF:I.4")
        if "right angle" in q_lower or "perpendicular" in q_lower or "κάθετος" in q_lower:
            add("DEF:I.10")
        if "circle" in q_lower or "κύκλος" in q_lower:
            add("DEF:I.15")
        if "equilateral" in q_lower or "isosceles" in q_lower or "scalene" in q_lower:
            add("DEF:I.20")
        if "parallel" in q_lower or "παράλληλ" in q_lower:
            add("DEF:I.23")
        add("DEF:I")

    # 3. Postulates
    for m in re.finditer(r"\bPostulate\s*([1-5])\b", q, re.IGNORECASE):
        add(f"POST:{m.group(1)}")
    if re.search(r"\bparallel\s+postulate\b|\bfifth\s+postulate\b", q_lower):
        add("POST:5")

    # 4. Common Notions
    for m in re.finditer(r"\b(?:Common\s+Notion|CN)\s*([1-9])\b", q, re.IGNORECASE):
        add(f"CN:{m.group(1)}")

    # 5. Classes
    for m in re.finditer(r"\bClass\s*0?(\d{1,2})\b", q, re.IGNORECASE):
        add(f"CLASS:{int(m.group(1))}")

    # 6. Well-known named theorems & course topics
    if "pythagor" in q_lower or "hypotenuse" in q_lower:
        add("PROP:I.47")
        add("TOPIC:PYTHAGOREAN")
    if "equilateral triangle" in q_lower and "construct" in q_lower:
        add("PROP:I.1")
    if "isosceles" in q_lower or "pons asinorum" in q_lower or "base angles" in q_lower:
        add("PROP:I.5")
        add("TOPIC:ISOSCELES")
    if "bisect" in q_lower and "angle" in q_lower:
        add("PROP:I.9")
    if "bisect" in q_lower and ("line" in q_lower or "segment" in q_lower):
        add("PROP:I.10")
    if "perpendicular" in q_lower and ("drop" in q_lower or "outside" in q_lower or "not on" in q_lower):
        add("PROP:I.12")
    if "copy" in q_lower and "angle" in q_lower or ("given rectilinear angle" in q_lower):
        add("PROP:I.23")
    if "cayley" in q_lower or "klein" in q_lower:
        add("TOPIC:CAYLEY_KLEIN")
    if "hyperbolic" in q_lower or "poincar" in q_lower or "hermes" in q_lower:
        add("TOPIC:HYPERBOLIC")
    if "spherical" in q_lower or "sphere" in q_lower or "elliptic" in q_lower:
        add("TOPIC:SPHERICAL")
    if re.search(r"parts\s+of\s+a.*proposition|six\s+parts|πρότασις|ἔκθεσις|διορισμός|κατασκευή|ἀπόδειξις|συμπέρασμα|ὅπερ\s+ἔδει", q_lower):
        add("TOPIC:PROP_PARTS")

    # 7. Group 4 Presentation Focus: Book II Proposition 13 (Law of Cosines, 15 verbs, 3 cases, article + preposition)
    if re.search(
        r"cosine|acute|obtuse|ὀξυγων|ἀμβλυγων|ἔλαττ|ἐλάσσ|μεῖζ|τέτμηται|ἤχθω|προσκείσθω|ὑποτειν|περιεχ|ἀπολαμβαν|κάθετ|misprint|fitzpatrick|genitive\s+of\s+comparison|degree\s+of\s+difference|three\s+cases|noun.*drop|article|presentation|slide|zahid|connor",
        q_lower,
    ):
        add("PROP:II.13")
        add("TOPIC:II13_GRAMMAR")
    if re.search(r"\bverb|parse|principal\s+part|reduplicat|aorist|perfect|imperative|participle|τέτμηται|ἤχθω|προσκείσθω|ἔτυχεν", q_lower):
        add("PROP:II.13")
        add("TOPIC:II13_VERBS")
    if not any(e.startswith("PROP:") for e in entities):
        # Default context during Group 4's II.13 presentation Q&A
        add("PROP:II.13")

    return entities


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "euclid",
    "explain", "for", "from", "give", "greek", "how", "in", "is", "it", "me", "of",
    "on", "or", "please", "quote", "say", "state", "tell", "that", "the", "to",
    "translate", "what", "when", "where", "which", "who", "why", "with", "you", "your",
}


class CourseRetriever:
    """In-process low-latency (< 50 ms) hybrid exact-entity + SQLite FTS5 BM25 retriever."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        if not cfg.index_db_path.exists():
            build_or_update_index(cfg)
        self.conn = sqlite3.connect(f"file:{cfg.index_db_path}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def retrieve(self, query: str, k: int = 4) -> tuple[list[RetrievedChunk], float]:
        """Return up to k best chunks combining exact entity matches + FTS5 BM25 in < 50 ms."""
        t0 = time.perf_counter()
        results: list[RetrievedChunk] = []
        seen_ids: set[int] = set()

        entities = parse_query_entities(query)
        exact_limit = max(2, k - 1) if k > 2 else k
        if entities:
            placeholders = ",".join("?" for _ in entities)
            rows = self.conn.execute(
                f"""
                SELECT c.id, c.source_label, c.rel_path, c.title, c.content, c.entity_keys_json,
                       MIN(em.priority) AS min_prio, COUNT(DISTINCT em.entity_key) AS matched_keys
                FROM entity_map em
                JOIN chunks c ON c.id = em.chunk_id
                WHERE em.entity_key IN ({placeholders})
                GROUP BY c.id
                ORDER BY matched_keys DESC,
                         min_prio ASC,
                         CASE
                             WHEN c.source_label IN ('Elements II.13', 'Elements II.12') THEN 0
                             WHEN c.rel_path LIKE '%2026-project-ii13/greek/%' THEN 1
                             WHEN c.rel_path LIKE '%2026-greek-07/solution%' THEN 2
                             WHEN c.rel_path LIKE '%2026-project-ii13/%' THEN 3
                             WHEN c.rel_path LIKE '%2026-greek-07/%' THEN 4
                             WHEN c.source_label LIKE 'Elements %' THEN 5
                             ELSE 6
                         END ASC,
                         c.id ASC
                LIMIT ?
                """,
                (*entities, exact_limit),
            ).fetchall()
            for r in rows:
                cid = int(r["id"])
                seen_ids.add(cid)
                results.append(
                    RetrievedChunk(
                        chunk_id=cid,
                        source_label=str(r["source_label"]),
                        rel_path=str(r["rel_path"]),
                        entity_keys=json.loads(r["entity_keys_json"]),
                        title=str(r["title"]),
                        content=str(r["content"]),
                        match_type="exact",
                        score=float(r["matched_keys"] * 10 - r["min_prio"]),
                    )
                )

        # Fill remaining slots (plus up to k total) using FTS5 BM25
        if len(results) < k:
            tokens = [
                t for t in re.findall(r"[\w\u0370-\u03ff\u1f00-\u1fff]+", query.lower())
                if len(t) > 1 and t not in STOPWORDS
            ]
            if tokens:
                # Build OR query with prefix matching so BM25 ranks documents with the most matching terms
                fts_query = " OR ".join(f'"{t}"*' for t in tokens[:12])
                try:
                    fts_rows = self.conn.execute(
                        """
                        SELECT c.id, c.source_label, c.rel_path, c.title, c.content, c.entity_keys_json,
                               bm25(chunks_fts, 5.0, 4.0, 6.0, 1.0) AS rank_score
                        FROM chunks_fts
                        JOIN chunks c ON c.id = chunks_fts.rowid
                        WHERE chunks_fts MATCH ?
                        ORDER BY rank_score ASC
                        LIMIT ?
                        """,
                        (fts_query, k * 2),
                    ).fetchall()
                    for r in fts_rows:
                        cid = int(r["id"])
                        if cid in seen_ids:
                            continue
                        seen_ids.add(cid)
                        results.append(
                            RetrievedChunk(
                                chunk_id=cid,
                                source_label=str(r["source_label"]),
                                rel_path=str(r["rel_path"]),
                                entity_keys=json.loads(r["entity_keys_json"]),
                                title=str(r["title"]),
                                content=str(r["content"]),
                                match_type="bm25",
                                score=float(-r["rank_score"]),
                            )
                        )
                        if len(results) >= k:
                            break
                except sqlite3.OperationalError:
                    pass

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return results[:k], elapsed_ms
