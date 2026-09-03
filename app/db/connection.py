import logging
import duckdb
from app.core.config import settings


def init_db(db_path: str = settings.DB_PATH) -> None:
    """Initializes DuckDB tables and performs lightweight migrations."""
    with duckdb.connect(db_path) as con:
        # Table 1: Ingested Raw Book Records
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_books (
                key VARCHAR PRIMARY KEY,
                title VARCHAR,
                description VARCHAR,
                subjects VARCHAR[],
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Table 2: Synthesized LLM Market Reports
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS market_reports (
                id VARCHAR DEFAULT uuid(),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batch_size INTEGER,
                category_summary VARCHAR,
                price_assessment VARCHAR,
                raw_json JSON
            )
        """
        )

        # Table 3: Dead-Letter Queue (Quarantine)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id VARCHAR DEFAULT uuid(),
                failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_url VARCHAR,
                raw_payload JSON,
                error_type VARCHAR,
                error_message VARCHAR,
                replayed BOOLEAN DEFAULT FALSE
            )
        """
        )

        # Migration guard: Ensure batch_size column exists for older table versions
        con.execute(
            "ALTER TABLE market_reports ADD COLUMN IF NOT EXISTS batch_size INTEGER"
        )

    logging.info(f"Database initialized successfully at '{db_path}'.")