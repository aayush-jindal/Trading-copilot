"""Configuration for the RAG knowledge base tool."""

from __future__ import annotations

import os

# API keys — shared with the main app via the same .env file
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Where to look for PDF books (drop your PDFs here)
RESOURCES_DIR = os.getenv(
    "RESOURCES_DIR",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "resources")),
)

# Local embedding model via sentence-transformers — no API key required
# all-MiniLM-L6-v2: ~80 MB download, 384-dim vectors, fast and accurate
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIMS  = 384

# Chunking parameters
CHUNK_SIZE    = 1500  # characters per chunk (~400 tokens)
CHUNK_OVERLAP = 200   # character overlap between consecutive chunks

# How many retrieved passages to send to Claude
TOP_K_RETRIEVAL = 8
