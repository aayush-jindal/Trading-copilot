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
