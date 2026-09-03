import sys
import asyncio
import logging
import duckdb
from typing import List, Dict, Any
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Required fix for curl_cffi on Windows platforms
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.services.ingestion import ingest_single_target

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("orchestrator")

TARGETS: List[Dict[str, Any]] = [
    {
        "name": "Gymshark",
        "url": "https://www.gymshark.com/products.json?limit=10"
    },
    {
        "name": "Allbirds",
        "url": "https://www.allbirds.com/products.json?limit=10"
    },
    {
        "name": "RedBull Shop",
        "url": "https://www.redbullshop.com/en-int/products.json?limit=10",
        "fallbacks": [
            "https://www.redbullshop.com/products.json?limit=10"
        ]
    }
]

def init_database(db_path: str = "analytics.duckdb") -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_catalog (
            id VARCHAR,
            title VARCHAR,
            vendor VARCHAR,
            product_type VARCHAR,
            price DOUBLE,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dlq_quarantine (
            target_url VARCHAR,
            error_message VARCHAR,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn

def route_to_dlq(conn: duckdb.DuckDBPyConnection, url: str, error: str):
    try:
        conn.execute(
            "INSERT INTO dlq_quarantine (target_url, error_message) VALUES (?, ?)",
            (url, str(error))
        )
    except Exception as db_err:
        logger.error(f"Failed to record to DLQ: {db_err}")
    logger.warning(f"[DLQ QUARANTINE] Payload from '{url}' routed to DLQ. Cause: {error}")

async def run_pipeline():
    logger.info("Starting Automated Competitor Intelligence Engine pipeline execution...")
    
    db_conn = init_database("analytics.duckdb")
    logger.info("Database initialized successfully at 'analytics.duckdb'.")

    valid_payloads: List[Dict[str, Any]] = []

    logger.info(f"Dispatching batch ingestion for {len(TARGETS)} targets...")
    for target in TARGETS:
        url = target.get("url")
        try:
            payload = await ingest_single_target(target)
            
            # Extract products list safely
            products = []
            if isinstance(payload, dict):
                products = payload.get("products", [])
            elif isinstance(payload, list):
                products = payload

            if products:
                valid_payloads.append(payload)
                for p in products:
                    variants = p.get("variants", [])
                    price = float(variants[0]["price"]) if variants and "price" in variants[0] else 0.0
                    db_conn.execute(
                        "INSERT INTO product_catalog (id, title, vendor, product_type, price) VALUES (?, ?, ?, ?, ?)",
                        (str(p.get("id")), str(p.get("title")), str(p.get("vendor")), str(p.get("product_type")), price)
                    )
                logger.info(f"Successfully ingested {len(products)} products from {target['name']}")
            else:
                logger.warning(f"Target returned empty product set: {url}")
                route_to_dlq(db_conn, url, "Empty product array returned")

        except Exception as e:
            logger.error(f"Target ingestion failed for {url}: {e}", exc_info=True)
            route_to_dlq(db_conn, url, str(e))

    record_count = db_conn.execute("SELECT COUNT(*) FROM product_catalog").fetchone()[0]
    logger.info(f"Persisted total valid records in DuckDB: {record_count}")
    logger.info(f"Ingestion complete. Valid records ingested this run: {len(valid_payloads)}")

    # Synthesis via Gemini 2.5 Flash
    if valid_payloads:
        logger.info("Feeding ingested records to Gemini 2.5 Flash for analysis...")
        client = genai.Client()
        chat = client.chats.create(model="gemini-2.5-flash")
        
        synthesis_prompt = (
            "Analyze the following ingested competitor raw JSON catalog data. "
            "Produce a structured intelligence briefing detailing product distribution, "
            "pricing anomalies, vendor breakdown, and strategic insights:\n\n"
            f"{valid_payloads}"
        )
        
        response = chat.send_message(synthesis_prompt)
        logger.info("--- SYNTHESIS REPORT SUMMARY ---")
        print("\n" + response.text + "\n")
    else:
        logger.error("No valid payloads ingested. Skipping synthesis step.")

    db_conn.close()

if __name__ == "__main__":
    asyncio.run(run_pipeline())