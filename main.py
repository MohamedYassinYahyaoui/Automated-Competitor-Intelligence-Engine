import asyncio
import logging
from pydantic import ValidationError

from app import (
    init_duckdb,
    stream_batches,
    bulk_save_to_duckdb,
    generate_batch_market_report,
    save_llm_report,
    OpenLibraryBook,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def run_pipeline():
    init_duckdb()

    target_urls = [
        f"https://openlibrary.org/works/OL{i}W.json"
        for i in range(10000, 10100)
    ]

    async for raw_batch in stream_batches(target_urls):
        # 1. Convert raw dicts to validated Pydantic models
        validated_batch: list[OpenLibraryBook] = []
        for raw_item in raw_batch:
            try:
                validated_item = OpenLibraryBook.model_validate(raw_item)
                validated_batch.append(validated_item)
            except ValidationError as ve:
                logging.warning(f"Skipping malformed item: {ve}")

        if not validated_batch:
            continue

        # 2. Store Validated Raw Data in DuckDB
        bulk_save_to_duckdb(validated_batch)

        # 3. Synthesize Market Insights via LLM
        report = await generate_batch_market_report(validated_batch)

        # 4. Store LLM Market Report safely
        if report is not None:
            save_llm_report(report, len(validated_batch))
        else:
            logging.warning("Skipping report storage due to failed LLM synthesis.")

if __name__ == "__main__":
    asyncio.run(run_pipeline())