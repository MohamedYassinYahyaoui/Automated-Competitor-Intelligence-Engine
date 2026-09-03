import json
import logging
import sys
from pathlib import Path

# Add project root to path for direct execution
sys.path.append(str(Path(__file__).resolve().parent.parent))

import duckdb
from app.core.config import settings
from app.schemas.book import BookRecord, RawBookPayload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import duckdb
from app.core.config import settings

def purge_dead_404s():
    """Purges non-recoverable HTTP 404 records from the DLQ."""
    with duckdb.connect(settings.DB_PATH) as con:
        deleted = con.execute("""
            DELETE FROM dead_letter_queue 
            WHERE error_message LIKE '%HTTP Fetch failed%' 
               OR error_message LIKE '%404%'
        """).fetchone()
        print(f"Purged non-recoverable 404 records from DLQ.")

if __name__ == "__main__":
    purge_dead_404s()
def inspect_and_replay_dlq() -> None:
    """Queries unhandled DLQ items, attempts re-validation, and promotes fixed records to raw_books."""
    logging.info("Connecting to DuckDB DLQ table...")

    with duckdb.connect(settings.DB_PATH) as con:
        # Fetch non-replayed items
        unhandled = con.execute(
            """
            SELECT id, source_url, raw_payload, error_type, error_message 
            FROM dead_letter_queue 
            WHERE replayed = FALSE
        """
        ).fetchall()

        if not unhandled:
            logging.info("No quarantined records pending replay.")
            return

        logging.info(f"Found {len(unhandled)} unhandled item(s) in Dead-Letter Queue:\n")

        replayed_ids = []
        for item_id, url, raw_json_str, err_type, err_msg in unhandled:
            logging.info(f"--- DLQ ID: {item_id} ---")
            logging.info(f"Source URL: {url}")
            logging.info(f"Error Type: {err_type} | Message: {err_msg}")
            
            try:
                payload = json.loads(raw_json_str) if raw_json_str else {}
            except Exception:
                payload = {}

            # Check if this item is a hard 404/network failure vs schema validation issue
            if payload.get("status") == "http_fetch_failed":
                logging.warning("--> Cannot auto-replay HTTP network failures or missing 404 endpoints. Skipping.")
                continue

            # Example manual remediation logic
            try:
                raw_payload = RawBookPayload(**payload)
                record = BookRecord(
                    key=raw_payload.key,
                    title=raw_payload.title or "REPLAYED_FIXED_TITLE",
                    description=raw_payload.description or "",
                    subjects=raw_payload.subjects or [],
                )

                # Insert valid replayed item into database
                con.execute(
                    """
                    INSERT OR REPLACE INTO raw_books (key, title, description, subjects)
                    VALUES (?, ?, ?, ?)
                """,
                    (record.key, record.title, record.description, record.subjects),
                )

                replayed_ids.append(item_id)
                logging.info(f"--> SUCCESS: Replayed and promoted record '{record.key}' to raw_books.")

            except Exception as fix_err:
                logging.error(f"--> REPLAY FAILED: Item still invalid under current schema: {fix_err}")

        # Mark replayed records in DLQ
        if replayed_ids:
            con.executemany(
                "UPDATE dead_letter_queue SET replayed = TRUE WHERE id = ?",
                [(i,) for i in replayed_ids],
            )
            logging.info(f"\nSuccessfully marked {len(replayed_ids)} record(s) as replayed in DLQ.")


if __name__ == "__main__":
    inspect_and_replay_dlq()