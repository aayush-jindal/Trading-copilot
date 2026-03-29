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

    # Backtesting player: runs and signals (isolated from main copilot)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id                      SERIAL PRIMARY KEY,
            run_id                  UUID NOT NULL UNIQUE,
            ticker                  VARCHAR(10) NOT NULL,
            run_label               VARCHAR(100) NOT NULL,
            lookback_years          INTEGER NOT NULL,
            entry_score_threshold   INTEGER NOT NULL,
            watch_score_threshold   INTEGER NOT NULL,
            min_rr_ratio            NUMERIC(4,2) NOT NULL,
            min_support_strength    VARCHAR(10) NOT NULL,
            require_weekly_aligned  BOOLEAN NOT NULL,
            status                  VARCHAR(20) NOT NULL,
            total_signals           INTEGER,
            entry_signals           INTEGER,
            watch_signals           INTEGER,
            win_count               INTEGER,
            loss_count              INTEGER,
            expired_count           INTEGER,
            win_rate                NUMERIC(5,2),
            expected_value          NUMERIC(8,4),
            avg_return_pct          NUMERIC(8,4),
            avg_mae                 NUMERIC(8,4),
            avg_mfe                 NUMERIC(8,4),
            avg_days_to_outcome     NUMERIC(6,2),
            expired_pct             NUMERIC(5,2),
            created_at              TIMESTAMP DEFAULT NOW(),
            completed_at            TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_signals (
            id                      SERIAL PRIMARY KEY,
            run_id                  UUID NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
            ticker                  VARCHAR(10) NOT NULL,
            signal_date             DATE NOT NULL,
            verdict                 VARCHAR(10) NOT NULL,
            setup_score             INTEGER NOT NULL,
            score_decile            INTEGER NOT NULL,
            uptrend_confirmed       BOOLEAN NOT NULL,
            weekly_trend_aligned    BOOLEAN NOT NULL,
            near_support            BOOLEAN NOT NULL,
            support_strength        VARCHAR(10),
            reversal_found          BOOLEAN NOT NULL,
            trigger_ok              BOOLEAN NOT NULL,
            rr_ratio                NUMERIC(6,2),
            rr_label                VARCHAR(20),
            support_is_provisional  BOOLEAN NOT NULL,
            entry_price             NUMERIC(10,2) NOT NULL,
            stop_loss               NUMERIC(10,2),
            target                 NUMERIC(10,2),
            outcome                 VARCHAR(10),
            outcome_date            DATE,
            days_to_outcome         INTEGER,
            exit_price              NUMERIC(10,2),
            return_pct              NUMERIC(8,4),
            mae                     NUMERIC(8,4),
            mfe                     NUMERIC(8,4),
            created_at              TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_run_id ON backtest_signals(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_verdict ON backtest_signals(verdict)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_outcome ON backtest_signals(outcome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_ticker ON backtest_runs(ticker)")

    # win_rate split columns on backtest_runs — added after initial release; idempotent
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS win_rate_entry NUMERIC(5,2)")
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS win_rate_watch NUMERIC(5,2)")
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS win_rate_all   NUMERIC(5,2)")

    # P&L columns on backtest_runs — added after initial release; idempotent
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS entry_signal_count INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS fixed_pnl          NUMERIC(10,2) DEFAULT 0")
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS compound_pnl       NUMERIC(10,2) DEFAULT 0")
    conn.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS compound_final_pot NUMERIC(10,2) DEFAULT 1000")

    # 4H columns on backtest_signals — added after initial release; idempotent
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_available BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_confirmed BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_reversal  BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_trigger   BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_rsi       NUMERIC(6,2)")
    conn.execute("ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS four_h_upgrade   BOOLEAN DEFAULT FALSE")

    # Phase 7.1: strategy name + conditions JSONB — backward compatible defaults
    conn.execute(
        "ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS "
        "strategy_name VARCHAR(50) DEFAULT 'S1_TrendPullback'"
    )
    conn.execute(
        "ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS "
        "strategy_name VARCHAR(50) DEFAULT 'S1_TrendPullback'"
    )
    conn.execute(
        "ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS conditions JSONB"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS hourly_price_history (
            id          SERIAL PRIMARY KEY,
            symbol      VARCHAR(10) NOT NULL,
            timestamp   TIMESTAMP NOT NULL,
            open        NUMERIC(12,4) NOT NULL,
            high        NUMERIC(12,4) NOT NULL,
            low         NUMERIC(12,4) NOT NULL,
            close       NUMERIC(12,4) NOT NULL,
            volume      BIGINT NOT NULL,
            created_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE(symbol, timestamp)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hourly_symbol_ts ON hourly_price_history(symbol, timestamp DESC)"
    )

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
