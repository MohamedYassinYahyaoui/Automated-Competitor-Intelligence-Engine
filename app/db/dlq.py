import uuid
import json
import logging
import duckdb
from app.core.config import settings

logger = logging.getLogger(__name__)


def ensure_dlq_table(con: duckdb.DuckDBPyConnection) -> None:
    """Ensures the DuckDB dead_letter_queue table exists."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id VARCHAR PRIMARY KEY,
            target_name VARCHAR DEFAULT 'Unknown',
            source_url VARCHAR,
            raw_payload VARCHAR,
            error_type VARCHAR DEFAULT 'IngestionError',
            error_message VARCHAR,
            replayed BOOLEAN DEFAULT FALSE,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def log_to_dlq(
    source_url: str,
    raw_payload: dict | str,
    error: Exception | str,
    target_name: str = "Unknown",
    db_path: str | None = None,
) -> str:
    """Safely logs failing or schema-violating payloads into the DuckDB Dead-Letter Queue."""
    target_db = db_path or settings.DB_PATH
    record_id = str(uuid.uuid4())
    error_type = type(error).__name__ if isinstance(error, Exception) else "ValidationError"
    error_msg = str(error)
    payload_str = json.dumps(raw_payload) if isinstance(raw_payload, (dict, list)) else str(raw_payload)

    try:
        with duckdb.connect(target_db) as con:
            ensure_dlq_table(con)
            con.execute(
                """
                INSERT INTO dead_letter_queue (
                    id, target_name, source_url, raw_payload, error_type, error_message, replayed
                ) VALUES (?, ?, ?, ?, ?, ?, FALSE)
                """,
                (record_id, target_name, source_url, payload_str, error_type, error_msg),
            )
        logger.warning(
            f"[DLQ QUARANTINE] Target='{target_name}' ({source_url}) routed to DLQ (id={record_id[:8]}). Cause: {error_type}: {error_msg}"
        )
        return record_id
    except Exception as exc:
        logger.critical(f"[DLQ CRITICAL] Failed to write payload to DLQ: {exc}")
        return ""


def get_unhandled_dlq_count(db_path: str | None = None) -> int:
    """Returns the total count of unhandled records in the Dead-Letter Queue."""
    target_db = db_path or settings.DB_PATH
    try:
        with duckdb.connect(target_db) as con:
            ensure_dlq_table(con)
            result = con.execute(
                "SELECT COUNT(*) FROM dead_letter_queue WHERE replayed = FALSE"
            ).fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Failed to fetch DLQ count: {e}")
        return 0
