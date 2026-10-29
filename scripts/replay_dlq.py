import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path for direct CLI execution
sys.path.append(str(Path(__file__).resolve().parent.parent))

import duckdb
from app.core.config import settings
from app.db.dlq import ensure_dlq_table, log_to_dlq
from app.schemas.book import ProductRecord
from app.services.transform import init_duckdb_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def seed_demo_dlq_records(db_path: str) -> None:
    """Seeds two realistic failure records into dead_letter_queue for remediation testing."""
    with duckdb.connect(db_path) as con:
        init_duckdb_schema(con)

    # 1. Recoverable schema anomaly (inverted price_min/price_max & missing title fallback)
    log_to_dlq(
        source_url="https://us.shop.gymshark.com/products.json?limit=10",
        raw_payload={
            "product_id": "gs-apex-seamless-9910",
            "target_name": "Gymshark US",
            "title": "",
            "handle": "apex-seamless-t-shirt-black",
            "vendor": "Gymshark",
            "product_type": "Mens Tops",
            "price_min": 46.0,
            "price_max": 38.0,  # Inverted range that triggered ValidationError
            "total_variants": 5,
            "available": True,
            "tags": ["seamless", "mens", "performance"],
            "extraction_source": "shopify_json",
        },
        error=ValueError("ValidationError: title must not be empty; price_max (38.0) < price_min (46.0)"),
        target_name="Gymshark US",
        db_path=db_path,
    )

    # 2. Non-recoverable HTTP 404 endpoint failure
    log_to_dlq(
        source_url="https://www.allbirds.com/legacy-v1-catalog.json",
        raw_payload={"status": "http_fetch_failed", "http_status": 404},
        error=RuntimeError("[404 HTTP STATUS] Missing resource on https://www.allbirds.com/legacy-v1-catalog.json"),
        target_name="Allbirds",
        db_path=db_path,
    )


def purge_dead_404s(db_path: str) -> int:
    """Purges non-recoverable HTTP 404 records from the DLQ."""
    with duckdb.connect(db_path) as con:
        ensure_dlq_table(con)
        count_row = con.execute(
            """
            SELECT COUNT(*) FROM dead_letter_queue
            WHERE error_message LIKE '%HTTP Fetch failed%'
               OR error_message LIKE '%404%'
            """
        ).fetchone()
        purged_count = count_row[0] if count_row else 0
        if purged_count > 0:
            con.execute(
                """
                DELETE FROM dead_letter_queue
                WHERE error_message LIKE '%HTTP Fetch failed%'
                   OR error_message LIKE '%404%'
                """
            )
            logging.info(f"Purged {purged_count} non-recoverable HTTP 404 record(s) from DLQ.")
        return purged_count


def inspect_and_replay_dlq(db_path: str | None = None) -> None:
    """Queries unhandled DLQ items, remediates schema anomalies, and upserts valid records into products."""
    target_db = db_path or settings.DB_PATH
    logging.info(f"Connecting to DuckDB DLQ table in '{target_db}'...")

    with duckdb.connect(target_db) as con:
        init_duckdb_schema(con)

        unhandled = con.execute(
            """
            SELECT id, target_name, source_url, raw_payload, error_type, error_message
            FROM dead_letter_queue
            WHERE replayed = FALSE
            ORDER BY quarantined_at DESC
            """
        ).fetchall()

        if not unhandled:
            logging.info("No quarantined records pending replay.")
            return

        logging.info(f"Found {len(unhandled)} unhandled item(s) in Dead-Letter Queue:\n")

        replayed_ids = []
        for item_id, target_name, url, raw_json_str, err_type, err_msg in unhandled:
            logging.info(f"--- DLQ ID: {item_id[:8]} | Target: {target_name} ---")
            logging.info(f"Source URL: {url}")
            logging.info(f"Error Type: {err_type} | Message: {err_msg}")

            try:
                payload = json.loads(raw_json_str) if raw_json_str else {}
            except Exception:
                payload = {}

            if not isinstance(payload, dict) or payload.get("status") == "http_fetch_failed" or "404" in str(err_msg):
                logging.warning("--> Skipping non-recoverable HTTP 404 / transport failure (use --purge-404 to clean).")
                continue

            # Deterministic schema remediation before Pydantic v2 re-validation
            try:
                p_min = float(payload.get("price_min", 0.0))
                p_max = float(payload.get("price_max", p_min))
                if p_max < p_min:
                    p_min, p_max = p_max, p_min

                raw_title = str(payload.get("title") or "").strip()
                handle_slug = str(payload.get("handle") or "remediated-product").replace("-", " ").title()
                fixed_title = raw_title if raw_title else handle_slug

                record = ProductRecord(
                    product_id=str(payload.get("product_id") or payload.get("key") or f"replayed_{item_id[:8]}"),
                    target_name=str(payload.get("target_name") or target_name or "Unknown"),
                    title=fixed_title,
                    handle=str(payload.get("handle") or ""),
                    vendor=str(payload.get("vendor") or target_name or "Unknown Vendor"),
                    product_type=str(payload.get("product_type") or "Remediated Catalog"),
                    price_min=max(0.0, p_min),
                    price_max=max(0.0, p_max),
                    total_variants=max(1, int(payload.get("total_variants", 1))),
                    available=bool(payload.get("available", True)),
                    tags=payload.get("tags", []) if isinstance(payload.get("tags"), list) else [],
                    extraction_source=str(payload.get("extraction_source") or "dlq_replay"),
                )

                con.execute(
                    """
                    INSERT INTO products (
                        product_id, target_name, title, handle, vendor,
                        product_type, price_min, price_max, total_variants,
                        available, tags, extraction_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        price_min = EXCLUDED.price_min,
                        price_max = EXCLUDED.price_max,
                        available = EXCLUDED.available,
                        extraction_source = EXCLUDED.extraction_source,
                        ingested_at = now();
                    """,
                    (
                        record.product_id,
                        record.target_name,
                        record.title,
                        record.handle,
                        record.vendor,
                        record.product_type,
                        record.price_min,
                        record.price_max,
                        record.total_variants,
                        record.available,
                        record.tags,
                        record.extraction_source,
                    ),
                )

                replayed_ids.append(item_id)
                logging.info(
                    f"--> SUCCESS: Remediated & upserted product '{record.product_id}' "
                    f"('{record.title}', ${record.price_min:.2f}-${record.price_max:.2f}) into DuckDB 'products'."
                )
            except Exception as fix_err:
                logging.error(f"--> REPLAY FAILED: Item still invalid under Pydantic v2 schema: {fix_err}")

        if replayed_ids:
            con.executemany(
                "UPDATE dead_letter_queue SET replayed = TRUE WHERE id = ?",
                [(i,) for i in replayed_ids],
            )
            logging.info(f"Marked {len(replayed_ids)} record(s) as replayed=TRUE in dead_letter_queue.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect, remediate, and replay DuckDB Dead-Letter Queue records.")
    parser.add_argument("--seed-demo", action="store_true", help="Seed sample DLQ anomalies before running replay.")
    parser.add_argument("--purge-404", action="store_true", help="Purge non-recoverable HTTP 404 entries from DLQ.")
    args = parser.parse_args()

    if args.seed_demo:
        seed_demo_dlq_records(settings.DB_PATH)
    inspect_and_replay_dlq(settings.DB_PATH)
    if args.purge_404:
        purge_dead_404s(settings.DB_PATH)
