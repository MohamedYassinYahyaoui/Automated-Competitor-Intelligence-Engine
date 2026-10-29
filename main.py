import asyncio
import json
import logging
import sys
import time
import duckdb
from dotenv import load_dotenv
from app.db.dlq import log_to_dlq
from app.services.ingestion import ingest_single_target
from app.services.extractor import extract_products_from_payload
from app.services.transform import persist_and_prune_catalog
from app.services.analyzer import generate_intelligence_report

# Ensure UTF-8 console output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator")

TARGETS = [
    {
        "name": "Allbirds",
        "url": "https://www.allbirds.com/products.json?limit=10",
        "fallbacks": [],
    },
    {
        "name": "Red Bull Shop",
        "url": "https://www.redbullshopus.com/products.json?limit=10",
        "fallbacks": [],
    },
    {
        "name": "Gymshark US",
        "url": "https://us.shop.gymshark.com/products.json?limit=10",
        "fallbacks": [],
    },
]


def print_duckdb_olap_summary(db_path: str = "analytics.duckdb") -> None:
    """Executes deterministic OLAP aggregation in DuckDB and prints a formatted summary table."""
    with duckdb.connect(db_path, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT
                target_name,
                COUNT(*) AS total_products,
                ROUND(AVG(price_min), 2) AS avg_price,
                ROUND(MIN(price_min), 2) AS min_price,
                ROUND(MAX(price_max), 2) AS max_price,
                ROUND(AVG(total_variants), 1) AS avg_variants,
                SUM(CASE WHEN available = FALSE THEN 1 ELSE 0 END) AS oos_count
            FROM products
            GROUP BY target_name
            ORDER BY total_products DESC, target_name ASC;
            """
        ).fetchall()

    print("\n=== DUCKDB OLAP ANALYTICAL SUMMARY (analytics.duckdb) ===")
    print(f"{'Target Brand':<18} | {'Products':>8} | {'Avg ($)':>9} | {'Min ($)':>9} | {'Max ($)':>9} | {'Avg Variants':>12} | {'OOS':>5}")
    print("-" * 86)
    for r in rows:
        print(f"{str(r[0]):<18} | {r[1]:>8} | {r[2]:>9.2f} | {r[3]:>9.2f} | {r[4]:>9.2f} | {r[5]:>12.1f} | {r[6]:>5}")
    print("-" * 86)


async def run_pipeline():
    logger.info(
        f"Starting Automated Competitor Intelligence Engine -- concurrent asyncio.gather across {len(TARGETS)} targets..."
    )
    t0 = time.perf_counter()

    # Step 1: Concurrent Ingestion via asyncio.gather (curl_cffi Chrome TLS + Playwright 403 escalation)
    tasks = [ingest_single_target(target) for target in TARGETS]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    ingest_elapsed = time.perf_counter() - t0
    logger.info(f"Concurrent ingestion completed in {ingest_elapsed:.2f}s.")

    extracted_catalogs = []
    raw_bytes_total = 0

    # Step 2: Dual-Path Extraction (Shopify JSON / Schema.org JSON-LD) & DLQ Routing
    for target, result in zip(TARGETS, raw_results):
        if isinstance(result, Exception):
            logger.error(f"Pipeline failed for target '{target['name']}' ({target['url']}): {result}")
            log_to_dlq(
                source_url=target["url"],
                raw_payload={"status": "http_fetch_failed", "url": target["url"]},
                error=result,
                target_name=target["name"],
                db_path="analytics.duckdb",
            )
            continue

        try:
            raw_bytes_total += len(json.dumps(result))
            clean_products = extract_products_from_payload(result)
            extracted_catalogs.append(
                {
                    "target": target["name"],
                    "url": target["url"],
                    "products": clean_products,
                }
            )
            logger.info(f"Successfully extracted {len(clean_products)} products from {target['name']}")
        except Exception as extract_err:
            logger.error(f"Extraction failed for target '{target['name']}': {extract_err}")
            log_to_dlq(
                source_url=target["url"],
                raw_payload=result,
                error=extract_err,
                target_name=target["name"],
                db_path="analytics.duckdb",
            )

    if not extracted_catalogs:
        logger.warning("No target payloads successfully ingested. Exiting pipeline.")
        return

    # Step 3: Transform, Validate (Pydantic v2), Upsert (DuckDB ON CONFLICT), & Prune Tokens
    pruned_payload = persist_and_prune_catalog(
        extracted_catalogs,
        db_path="analytics.duckdb",
        raw_bytes_total=raw_bytes_total,
    )

    # Display deterministic DuckDB OLAP summary table
    print_duckdb_olap_summary(db_path="analytics.duckdb")

    # Step 4: Analyze (Synthesize insights via Gemini 2.5 Flash or deterministic OLAP fallback)
    logger.info("Feeding pruned records to synthesis engine...")
    report = await generate_intelligence_report(pruned_payload, db_path="analytics.duckdb")

    print("\n--- SYNTHESIS REPORT SUMMARY ---\n")
    print(report)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
