"""PostgreSQL database connection and schema initialisation.

get_db() returns a _Conn wrapper that exposes the same execute/commit/close
interface as sqlite3, so the rest of the codebase is DB-agnostic.

init_db() is called once at application startup (via FastAPI lifespan) and
creates all tables + indexes idempotently. It also seeds hardcoded users.
"""

import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL


class _Conn:
    """Thin wrapper giving psycopg2 the same conn.execute() interface as sqlite3."""

    def __init__(self, raw_conn: psycopg2.extensions.connection) -> None:
        self._conn = raw_conn
        self._cur = raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql: str, params=None):
        self._cur.execute(sql, params)
        return self._cur

    def executemany(self, sql: str, seq_of_params):
        self._cur.executemany(sql, seq_of_params)
        return self._cur

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._cur.close()
        self._conn.close()


def get_db() -> _Conn:
    raw = psycopg2.connect(DATABASE_URL)
    return _Conn(raw)


def init_db() -> None:
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol       TEXT PRIMARY KEY,
            company_name TEXT,
            sector       TEXT,
            market_cap   DOUBLE PRECISION,
            last_updated TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id            SERIAL PRIMARY KEY,
            ticker_symbol TEXT NOT NULL,
            date          TEXT NOT NULL,
            open          DOUBLE PRECISION,
            high          DOUBLE PRECISION,
            low           DOUBLE PRECISION,
            close         DOUBLE PRECISION,
            adj_close     DOUBLE PRECISION,
            volume        BIGINT,
            UNIQUE (ticker_symbol, date),
            FOREIGN KEY (ticker_symbol) REFERENCES tickers(symbol)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_price_history (
            id            SERIAL PRIMARY KEY,
            ticker_symbol TEXT NOT NULL,
            date          TEXT NOT NULL,
            open          DOUBLE PRECISION,
            high          DOUBLE PRECISION,
            low           DOUBLE PRECISION,
            close         DOUBLE PRECISION,
            adj_close     DOUBLE PRECISION,
            volume        BIGINT,
            UNIQUE (ticker_symbol, date),
            FOREIGN KEY (ticker_symbol) REFERENCES tickers(symbol)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS syntheses (
            id             SERIAL PRIMARY KEY,
            ticker_symbol  TEXT NOT NULL,
            generated_date TEXT NOT NULL,
            provider       TEXT NOT NULL,
            narrative      TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            UNIQUE (ticker_symbol, generated_date),
            FOREIGN KEY (ticker_symbol) REFERENCES tickers(symbol)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )
    """)

    conn.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS account_size NUMERIC(12,2) DEFAULT 10000.00,
            ADD COLUMN IF NOT EXISTS risk_pct      NUMERIC(5,4)  DEFAULT 0.0100
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            ticker_symbol TEXT NOT NULL,
            date_added    TEXT NOT NULL,
            UNIQUE (user_id, ticker_symbol),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read    BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # pgvector extension — requires pgvector/pgvector:pg16 Docker image
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    conn.execute("""
        ALTER TABLE knowledge_chunks
            ADD COLUMN IF NOT EXISTS book_type VARCHAR(20) DEFAULT 'equity_ta'
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_book_type ON knowledge_chunks(book_type)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id          SERIAL PRIMARY KEY,
            source_file TEXT NOT NULL,
            page_num    INT,
            chunk_idx   INT NOT NULL,
            content     TEXT NOT NULL,
            embedding   vector(1536),
            created_at  TEXT NOT NULL,
            UNIQUE (source_file, chunk_idx)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS open_trades (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            ticker          VARCHAR(10) NOT NULL,
            strategy_name   VARCHAR(50) NOT NULL,
            strategy_type   VARCHAR(20) NOT NULL,
            entry_price     NUMERIC(12,4) NOT NULL,
            stop_loss       NUMERIC(12,4) NOT NULL,
            target          NUMERIC(12,4) NOT NULL,
            shares          INTEGER NOT NULL,
            entry_date      DATE NOT NULL DEFAULT CURRENT_DATE,
            risk_reward     NUMERIC(6,3),
            status          VARCHAR(20) NOT NULL DEFAULT 'open',
            exit_price      NUMERIC(12,4),
            exit_date       DATE,
            exit_reason     VARCHAR(50),
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_open_trades_user
            ON open_trades(user_id) WHERE status = 'open'
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_strategy_cache (
            ticker     TEXT NOT NULL,
            cache_date DATE NOT NULL,
            result     JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (ticker, cache_date)
        )
    """)

    conn.commit()
    conn.close()

    _seed_users()


def _seed_users() -> None:
    """Insert hardcoded users if they don't exist yet. Runs at every startup (idempotent)."""
    from app.config import HARDCODED_USERS
    from app.services.auth import get_password_hash
    from datetime import datetime, timezone

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    for username, password in HARDCODED_USERS.items():
        if not username:
            continue
        conn.execute(
            """INSERT INTO users (username, password_hash, created_at)
               VALUES (%s, %s, %s)
               ON CONFLICT (username) DO NOTHING""",
            (username, get_password_hash(password), now),
        )
    conn.commit()
    conn.close()
