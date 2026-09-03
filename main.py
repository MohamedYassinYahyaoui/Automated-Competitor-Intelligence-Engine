import asyncio
import logging
from dotenv import load_dotenv
from app.services.ingestion import ingest_single_target
from app.services.extractor import extract_products_from_payload
from app.services.transform import persist_and_prune_catalog
from app.services.analyzer import generate_intelligence_report
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator")

TARGETS = [
    {
        "name": "Allbirds",
        "url": "https://www.allbirds.com/products.json?limit=10",
        "fallbacks": []
    },
    {
        "name": "Red Bull Shop",
        "url": "https://www.redbullshopus.com/products.json?limit=10",
        "fallbacks": []
    },
    {
        "name": "Gymshark US",
        # Use Gymshark's active US collections endpoint
        "url": "https://us.shop.gymshark.com/products.json?limit=10",
        "fallbacks": []
    }
]

async def run_pipeline():
    logger.info("Starting Automated Competitor Intelligence Engine pipeline execution...")
    
    extracted_catalogs = []

    for target in TARGETS:
        try:
            # Step 1: Ingest (Network transport & fallbacks)
            raw_payload = await ingest_single_target(target)
            
            # Step 2: Extract (Standardize JSON / microdata schema)
            clean_products = extract_products_from_payload(raw_payload)
            extracted_catalogs.append({"target": target["name"], "products": clean_products})
            logger.info(f"Successfully extracted {len(clean_products)} products from {target['name']}")
            
        except Exception as e:
            logger.error(f"Pipeline failed for target {target['url']}: {e}")
            # Route to DLQ quarantine handling in DuckDB here

    if not extracted_catalogs:
        logger.warning("No target payloads successfully ingested. Exiting pipeline.")
        return

    # Step 3: Transform & Persist (Prune tokens for LLM & record in DuckDB)
    pruned_payload = persist_and_prune_catalog(extracted_catalogs, db_path="analytics.duckdb")
    logger.info("Persisted records to DuckDB and pruned payload context for LLM.")

    # Step 4: Analyze (Synthesize insights via Gemini 2.5 Flash)
    logger.info("Feeding pruned records to Gemini 2.5 Flash for analysis...")
    report = await generate_intelligence_report(pruned_payload)
    
    print("\n--- SYNTHESIS REPORT SUMMARY ---\n")
    print(report)

if __name__ == "__main__":
    asyncio.run(run_pipeline())