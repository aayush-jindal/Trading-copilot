"""Application configuration.

All settings are read from environment variables with safe defaults for local
development. In production, set the variables via Docker env files or secrets.
"""

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_copilot",
)
STALENESS_HOURS = 4
HISTORY_PERIOD = "6y"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SYNTHESIS_PROVIDER = os.getenv("SYNTHESIS_PROVIDER", "anthropic")  # "anthropic" | "openai"

# ── Auth ──────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 1440  # 24 hours

# Hardcoded users for v1 — set via env vars or change defaults here
# username → plaintext password (hashed at startup, never stored plain)
HARDCODED_USERS: dict[str, str] = {
    os.getenv("ADMIN_USERNAME", "admin"): os.getenv("ADMIN_PASSWORD", "changeme"),
}

# ── Internal scheduler secret ─────────────────────────────────────────────────
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
