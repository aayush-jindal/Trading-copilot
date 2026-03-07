import os

# Shared with main app — reads from the same .env file
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_copilot",
)

# Where extracted strategies are persisted between runs
STRATEGIES_FILE = os.getenv(
    "STRATEGIES_FILE",
    os.path.join(os.path.dirname(__file__), "strategies.json"),
)
