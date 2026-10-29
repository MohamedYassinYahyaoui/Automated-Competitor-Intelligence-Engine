import duckdb
import logging
from app.core.config import settings
from app.db.dlq import ensure_dlq_table


def ensure_reports_table(con: duckdb.DuckDBPyConnection) -> None:
    """Ensures the DuckDB market_reports table exists."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS market_reports (
            id VARCHAR PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            batch_size INT,
            model_used VARCHAR,
            report_markdown VARCHAR,
            raw_json VARCHAR
        )
    """)


def init_db(db_path: str | None = None) -> None:
    target_db = db_path or settings.DB_PATH
    with duckdb.connect(target_db) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id VARCHAR PRIMARY KEY,
                target_name VARCHAR,
                title VARCHAR,
                handle VARCHAR,
                vendor VARCHAR,
                product_type VARCHAR,
                price_min DOUBLE,
                price_max DOUBLE,
                total_variants INT,
                available BOOLEAN,
                tags VARCHAR[],
                extraction_source VARCHAR,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        ensure_dlq_table(con)
        ensure_reports_table(con)

    logging.info(f"Database initialized successfully at '{target_db}'.")
