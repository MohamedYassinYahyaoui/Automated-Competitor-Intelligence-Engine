import uuid
import json
import logging
import duckdb
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def log_to_dlq(conn, target_url: str, error_message: str):
    """
    Logs an ingestion failure payload into the DuckDB DLQ table.
    """
    try:
        conn.execute(
            "INSERT INTO dlq_quarantine (target_url, error_message) VALUES (?, ?)",
            (target_url, str(error_message))
        )
        logger.warning(f"[DLQ QUARANTINE] Logged failure for {target_url}")
    except Exception as e:
        logger.error(f"Failed to write to DLQ table: {e}")

def get_unhandled_dlq_count(conn) -> int:
    """
    Returns the total count of unhandled records in the Dead Letter Queue.
    """
    try:
        result = conn.execute(
            "SELECT COUNT(*) FROM dlq_quarantine"
        ).fetchone()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Failed to fetch DLQ count: {e}")
        return 0
def log_to_dlq(source_url: str, raw_payload: dict | str, error: Exception):
    """Safely logs failing or blocked target payloads into DLQ."""
    try:
        payload_str = json.dumps(raw_payload) if isinstance(raw_payload, dict) else str(raw_payload)
        record_id = str(uuid.uuid4())
        
        with duckdb.connect(settings.DB_PATH) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id VARCHAR PRIMARY KEY,
                    source_url VARCHAR,
                    raw_payload VARCHAR,
                    error_message VARCHAR,
                    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                INSERT INTO dead_letter_queue (id, source_url, raw_payload, error_message)
                VALUES (?, ?, ?, ?)
            """, (record_id, source_url, payload_str, str(error)))
            
        logging.warning(f"[DLQ QUARANTINE] Payload from '{source_url}' routed to DLQ. Cause: {type(error).__name__}")
    except Exception as exc:
        logging.critical(f"[DLQ CRITICAL] Failed to write payload to DLQ: {exc}")