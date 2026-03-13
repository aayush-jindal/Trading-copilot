"""Step 1: Ingest PDFs from resources/ → chunk → embed → store in pgvector.

Re-running is fully idempotent: files already in knowledge_chunks are skipped.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBED_DIMS,
    EMBED_MODEL,
    OPENAI_API_KEY,
    RESOURCES_DIR,
)


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding-window character chunking with overlap."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if len(c) > 50]  # drop tiny trailing chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings via OpenAI text-embedding-3-small (batches of 100)."""
    from openai import OpenAI  # noqa: PLC0415
    client = OpenAI(api_key=OPENAI_API_KEY)
    results: list[list[float]] = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=EMBED_MODEL, input=batch)
        results.extend(item.embedding for item in response.data)
    return results


# ── Database upsert ───────────────────────────────────────────────────────────

def _vec_str(embedding: list[float]) -> str:
    """Convert Python list to pgvector literal format: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


def _upsert_chunks(
    source_file: str,
    page_nums: list[int],
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    """INSERT chunks into knowledge_chunks, skipping duplicates."""
    from app.database import get_db  # lazy import — needs DATABASE_URL

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        for chunk_idx, (page_num, content, embedding) in enumerate(
            zip(page_nums, chunks, embeddings)
        ):
            conn.execute(
                """
                INSERT INTO knowledge_chunks
                    (source_file, page_num, chunk_idx, content, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                ON CONFLICT (source_file, chunk_idx) DO NOTHING
                """,
                (source_file, page_num, chunk_idx, content, _vec_str(embedding), now),
            )
        conn.commit()
    finally:
        conn.close()


def _already_indexed(source_file: str) -> bool:
    """Return True if this file already has chunks in the DB."""
    from app.database import get_db

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM knowledge_chunks WHERE source_file = %s",
            (source_file,),
        ).fetchone()
        return (row["cnt"] if row else 0) > 0
    finally:
        conn.close()


# ── Per-PDF ingestion ─────────────────────────────────────────────────────────

def _ingest_pdf(path: str) -> int:
    """Chunk, embed, and upsert one PDF. Returns number of chunks stored."""
    from tools.pdf_strategy_pipeline.pdf_reader import read_pdf  # lazy import

    source_file = os.path.basename(path)

    if _already_indexed(source_file):
        print(f"  [skip] {source_file} — already indexed.")
        return 0

    print(f"  Reading {source_file}…")
    pages: list[str] = read_pdf(path)
    print(f"    {len(pages)} pages")

    # Build (page_num, chunk) pairs by sliding over the full text
    # We track which page each chunk starts on by accumulating page lengths
    all_chunks: list[str] = []
    all_page_nums: list[int] = []

    for page_num, page_text in enumerate(pages, start=1):
        page_chunks = _chunk_text(page_text)
        all_chunks.extend(page_chunks)
        all_page_nums.extend([page_num] * len(page_chunks))

    if not all_chunks:
        print(f"    No text extracted — skipping.")
        return 0

    print(f"    {len(all_chunks)} chunks → embedding…")
    embeddings = _embed_texts(all_chunks)

    print(f"    Storing in DB…")
    _upsert_chunks(source_file, all_page_nums, all_chunks, embeddings)
    print(f"    Done: {len(all_chunks)} chunks indexed.")
    return len(all_chunks)


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_all(resources_dir: str = RESOURCES_DIR) -> None:
    """Find all PDFs in resources_dir and ingest any not yet indexed."""
    if not os.path.isdir(resources_dir):
        print(f"Resources directory not found: {resources_dir}")
        print("Create it and drop your PDF books inside, then re-run.")
        return

    pdf_paths = [
        os.path.join(resources_dir, f)
        for f in sorted(os.listdir(resources_dir))
        if f.lower().endswith(".pdf")
    ]

    if not pdf_paths:
        print(f"No PDFs found in {resources_dir}")
        return

    print(f"Found {len(pdf_paths)} PDF(s) in {resources_dir}\n")
    total_chunks = 0
    for path in pdf_paths:
        total_chunks += _ingest_pdf(path)

    print(f"\nIngestion complete. {total_chunks} new chunks added.")


def show_status() -> None:
    """Print a table of indexed files and their chunk counts."""
    from app.database import get_db

    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT source_file,
                   COUNT(*)   AS chunks,
                   MIN(created_at) AS indexed_at
            FROM knowledge_chunks
            GROUP BY source_file
            ORDER BY source_file
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("Knowledge base is empty. Run 'ingest' first.")
        return

    total = sum(r["chunks"] for r in rows)
    print(f"\n{'File':<50} {'Chunks':>7}  Indexed")
    print("-" * 70)
    for r in rows:
        print(f"  {r['source_file']:<48} {r['chunks']:>7}  {r['indexed_at'][:10]}")
    print("-" * 70)
    print(f"  {'TOTAL':<48} {total:>7}")
