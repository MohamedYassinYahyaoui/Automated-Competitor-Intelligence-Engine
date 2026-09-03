import json
import logging
import duckdb
from app.core.config import settings


def log_to_dlq(
    source_url: str,
    raw_payload: dict,
    error: Exception,
    db_path: str = settings.DB_PATH,
) -> None:
    """Persists malformed or failing payloads directly into the dead_letter_queue table."""
    try:
        with duckdb.connect(db_path) as con:
            con.execute(
                """
                INSERT INTO dead_letter_queue (source_url, raw_payload, error_type, error_message)
                VALUES (?, ?, ?, ?)
            """,
                [
                    source_url,
                    json.dumps(raw_payload) if isinstance(raw_payload, dict) else str(raw_payload),
                    type(error).__name__,
                    str(error),
                ],
            )
        logging.warning(
            f"[DLQ QUARANTINE] Payload from '{source_url}' routed to DLQ. Cause: {type(error).__name__}"
        )
    except Exception as db_err:
        logging.critical(
            f"[DLQ CRITICAL] Failed to write payload to DLQ: {db_err}"
        )


def get_unhandled_dlq_count(db_path: str = settings.DB_PATH) -> int:
    """Returns total count of un-replayed quarantined records."""
    with duckdb.connect(db_path) as con:
        result = con.execute(
            "SELECT COUNT(*) FROM dead_letter_queue WHERE replayed = FALSE"
        ).fetchone()
        return result[0] if result else 0