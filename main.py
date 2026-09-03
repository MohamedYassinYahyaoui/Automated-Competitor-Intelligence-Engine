import asyncio
import logging
import sys
from app.core.config import settings
from app.db.connection import init_db
from app.db.dlq import get_unhandled_dlq_count
from app.services.analyzer import analyze_batch
from app.services.ingestion import fetch_and_process_batch

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("orchestrator")


async def run_pipeline(target_urls: list[str]) -> None:
    """Orchestrates end-to-end execution: Init DB -> Ingest & Trap Errors -> Synthesize -> Audit."""
    logger.info(f"Starting {settings.APP_NAME} pipeline execution...")

    # Step 1: Ensure database tables & migration states exist
    init_db()

    # Step 2: Concurrently fetch, validate, and store records (Routing failures to DLQ)
    logger.info(f"Dispatching batch ingestion for {len(target_urls)} targets...")
    valid_records = await fetch_and_process_batch(target_urls)
    logger.info(
        f"Ingestion complete. Valid records: {len(valid_records)}/{len(target_urls)}"
    )

    # Step 3: Run Gemini LLM Synthesis on valid datasets
    if valid_records:
        logger.info("Feeding ingested records to Gemini 2.5 Flash for analysis...")
        report = analyze_batch(valid_records)
        if report:
            logger.info("--- SYNTHESIS REPORT SUMMARY ---")
            logger.info(f"Category Summary: {report.category_summary}")
            logger.info(f"Price Assessment: {report.price_assessment}")
            logger.info(f"Takeaways: {', '.join(report.key_takeaways)}")
    else:
        logger.warning(
            "Skipping Gemini synthesis step: Zero valid records passed validation."
        )

    # Step 4: Health check & Dead-Letter Queue quarantine count audit
    unhandled_dlq = get_unhandled_dlq_count()
    if unhandled_dlq > 0:
        logger.warning(
            f"[SYSTEM AUDIT] Pipeline completed with {unhandled_dlq} quarantined record(s) in DLQ."
        )
        logger.warning(
            "Inspect quarantined items via '/api/v1/dlq' or execute 'scripts/replay_dlq.py'."
        )
    else:
        logger.info("[SYSTEM AUDIT] Pipeline completed with 0 errors in DLQ.")


def main():
    # Sample Target Dataset (Replace with live target lists/scraped index endpoints)
    # Real commercial endpoints carrying live product, pricing, and variant data
    # Real commercial endpoints carrying live product, pricing, and variant data
    sample_targets = [
        # Gymshark (Fitness/Apparel) - Live Shopify Catalog
        "https://www.gymshark.com/products.json?limit=10",
    
        # Allbirds (Footwear/Apparel) - Live Shopify Catalog
        "https://www.allbirds.com/products.json?limit=10",
    
        # Red Bull Shop (Merchandise/Beverages) - Live Shopify Catalog
        "https://www.redbullshop.com/products.json?limit=10",
    
        # Intentionally malformed URL to verify DLQ trapping
        "https://www.gymshark.com/invalid_endpoint_for_dlq_test.json"
    ]
    try:
        asyncio.run(run_pipeline(sample_targets))
    except KeyboardInterrupt:
        logger.info("Pipeline execution terminated by user.")
    except Exception as fatal_err:
        logger.critical(f"Fatal crash during pipeline execution: {fatal_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()