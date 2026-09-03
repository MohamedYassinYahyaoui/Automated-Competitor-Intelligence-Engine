import json
import logging
from typing import Any, Dict, List
import duckdb
from app.schemas import MarketReportSchema, OpenLibraryBook

DB_FILE = "analytics.duckdb"


def init_dlq_table(db_path: str = DB_FILE) -> None:
    """Creates the quarantine table for unprocessable or malformed records."""
    with duckdb.connect(db_path) as con:
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


def log_to_dlq(
    source_url: str,
    raw_payload: dict,
    error: Exception,
    db_path: str = DB_FILE,
) -> None:
    """Persists a failed payload and its trace into the DLQ quarantine table."""
    with duckdb.connect(db_path) as con:
        con.execute(
            """
            INSERT INTO dead_letter_queue (source_url, raw_payload, error_type, error_message)
            VALUES (?, ?, ?, ?)
        """,
            [
                source_url,
                json.dumps(raw_payload),
                type(error).__name__,
                str(error),
            ],
        )
    logging.warning(
        f"[DLQ QUARANTINE] Payload from {source_url} routed to DLQ. Error: {type(error).__name__}"
    )
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# INITIALIZATION & MIGRATIONS
def init_duckdb(db_path: str = DB_FILE) -> None:
    """Initializes the DuckDB database tables if they do not exist."""
    with duckdb.connect(db_path) as con:
        # Table 1: Raw Ingested Book Records
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
    logging.info(f"Database initialized successfully at '{db_path}'.")


# ---------------------------------------------------------------------------
# VECTORIZED BULK INGESTION
# ---------------------------------------------------------------------------
def bulk_save_to_duckdb(
    validated_items: List[OpenLibraryBook], db_path: str = DB_FILE
) -> None:
    """
    Performs vectorized bulk insert into DuckDB using parameter binding.
    Avoids item-by-item loop overhead and handles conflict resolution on primary keys.
    """
    if not validated_items:
        logging.warning("No validated items provided for DuckDB insertion.")
        return

    # Transform Pydantic objects into a list of dictionaries for bulk operation
    records = [
        {
            "key": item.key,
            "title": item.title,
            "description": item.description,
            "subjects": item.subjects,
        }
        for item in validated_items
    ]

    with duckdb.connect(db_path) as con:
        con.executemany(
            """
            INSERT INTO raw_books (key, title, description, subjects)
            VALUES ($key, $title, $description, $subjects)
            ON CONFLICT (key) DO UPDATE SET 
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                subjects = EXCLUDED.subjects
        """,
            records,
        )
    logging.info(
        f"Bulk-inserted/updated {len(records)} records in 'raw_books'."
    )


# ---------------------------------------------------------------------------
# REPORT PERSISTENCE
# ---------------------------------------------------------------------------
def save_llm_report(
    report_data: MarketReportSchema, batch_size: int, db_path: str = DB_FILE
) -> None:
    """Saves structured LLM market synthesis into the 'market_reports' table."""
    raw_json_str = report_data.model_dump_json()

    with duckdb.connect(db_path) as con:
        con.execute(
            """
            INSERT INTO market_reports (batch_size, category_summary, price_assessment, raw_json)
            VALUES (?, ?, ?, ?)
        """,
            [
                batch_size,
                report_data.category_summary,
                report_data.price_assessment,
                raw_json_str,
            ],
        )
    logging.info("Persisted LLM Market Report to 'market_reports' table.")