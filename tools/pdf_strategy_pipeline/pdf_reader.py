"""Step 1: PDF → cleaned text chunks ready for Claude."""

from __future__ import annotations

import fitz  # PyMuPDF


def read_pdf(path: str) -> list[str]:
    """Return one string per page from a PDF file.

    Lines shorter than 5 characters are dropped as likely headers/footers/noise.
    """
    doc = fitz.open(path)
    pages: list[str] = []
    for page in doc:
        raw = page.get_text()
        cleaned_lines = [
            line for line in raw.splitlines() if len(line.strip()) >= 5
        ]
        pages.append("\n".join(cleaned_lines))
    doc.close()
    return pages


def chunk_pages(pages: list[str], pages_per_chunk: int = 4) -> list[str]:
    """Group consecutive pages into larger chunks for Claude's context window.

    Larger chunks preserve cross-page context (e.g. a strategy described
    across two pages stays together).
    """
    chunks: list[str] = []
    for i in range(0, len(pages), pages_per_chunk):
        group = pages[i : i + pages_per_chunk]
        chunks.append("\n\n--- page break ---\n\n".join(group))
    return chunks
