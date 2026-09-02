import asyncio
import logging
from typing import Any, AsyncGenerator, List, Optional
import httpx

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
CONCURRENCY_LIMIT = 10  # Max concurrent HTTP requests
BATCH_SIZE = 50         # Items per batch to stream downstream
MAX_CONNECTIONS = 20    # HTTP connection pool limit
REQUEST_TIMEOUT = 10.0  # Timeout per request in seconds

CLIENT_LIMITS = httpx.Limits(
    max_keepalive_connections=CONCURRENCY_LIMIT,
    max_connections=MAX_CONNECTIONS,
)


# ---------------------------------------------------------------------------
# WORKER & STREAMING LOGIC
# ---------------------------------------------------------------------------
async def fetch_item(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    url: str,
    retries: int = 3,
) -> Optional[dict[str, Any]]:
    """
    Fetches a single JSON payload using a semaphore for concurrency control
    and exponential backoff for transient failures.
    """
    async with semaphore:
        for attempt in range(1, retries + 1):
            try:
                response = await client.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as err:
                if attempt == retries:
                    logging.error(f"[DROPPED] {url} | Exhausted retries | Error: {err}")
                    return None
                wait_time = 1.5 ** attempt
                logging.warning(
                    f"[RETRY {attempt}/{retries}] {url} failed: {err}. Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
        return None


async def stream_batches(
    urls: List[str], batch_size: int = BATCH_SIZE
) -> AsyncGenerator[List[dict[str, Any]], None]:
    """
    Asynchronously fetches URLs in chunks and yields clean batches of raw JSON records.
    Keeps memory footprint near zero during large ingestion runs.
    """
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async with httpx.AsyncClient(limits=CLIENT_LIMITS) as client:
        for i in range(0, len(urls), batch_size):
            chunk_urls = urls[i : i + batch_size]
            logging.info(
                f"Dispatching fetch tasks for chunk {i // batch_size + 1} ({len(chunk_urls)} URLs)..."
            )

            tasks = [fetch_item(client, semaphore, url) for url in chunk_urls]
            results = await asyncio.gather(*tasks)

            # Filter dropped/failed requests
            valid_records = [res for res in results if res is not None]

            if valid_records:
                logging.info(f"Yielding batch of {len(valid_records)} valid records.")
                yield valid_records
            else:
                logging.warning(f"Chunk starting at index {i} yielded zero valid records.")