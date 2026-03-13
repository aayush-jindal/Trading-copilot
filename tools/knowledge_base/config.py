"""Configuration for the RAG knowledge base tool."""

from __future__ import annotations

import os

# API keys — shared with the main app via the same .env file
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

# Where to look for PDF books (drop your PDFs here)
RESOURCES_DIR = os.getenv(
    "RESOURCES_DIR",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "resources")),
)

# OpenAI embedding model — 1536-dim vectors, no local model download required
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMS  = 1536

# Chunking parameters
CHUNK_SIZE    = 1500  # characters per chunk (~400 tokens)
CHUNK_OVERLAP = 200   # character overlap between consecutive chunks

# How many retrieved passages to send to Claude
TOP_K_RETRIEVAL = 8
