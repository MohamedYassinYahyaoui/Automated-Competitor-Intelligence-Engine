import asyncio
import logging
import duckdb
from curl_cffi import requests
from app.core.config import settings
from app.db.dlq import log_to_dlq
from app.schemas.book import BookRecord


async def fetch_item(session: requests.AsyncSession, url: str) -> tuple[str, dict | None]:
    """Fetches URL impersonating a real Chrome browser fingerprint."""
    for attempt in range(settings.MAX_RETRIES):
        try:
            # impersonate="chrome" handles TLS signatures to bypass Cloudflare
            response = await session.get(url, impersonate="chrome", allow_redirects=True, timeout=12)
            if response.status_code == 200:
                return url, response.json()
            elif response.status_code in (403, 401):
                logging.warning(f"[{response.status_code} BLOCKED] Anti-bot blocked request: {url}")
                return url, None
            elif response.status_code == 404:
                logging.warning(f"[404 NOT FOUND] Target resource missing: {url}")
                return url, None
            elif response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            logging.error(f"Fetch error for {url} on attempt {attempt + 1}: {exc}")
            await asyncio.sleep(1)
    return url, None


async def fetch_and_process_batch(urls: list[str]) -> list[BookRecord]:
    """Fetches store endpoints and extracts records with defensive dictionary parsing."""
    valid_records: list[BookRecord] = []

    async with requests.AsyncSession() as session:
        tasks = [fetch_item(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    for url, raw_json in results:
        if raw_json is None:
            log_to_dlq(
                source_url=url,
                raw_payload={"status": "http_fetch_failed_or_blocked"},
                error=ValueError("HTTP Fetch failed or anti-bot blocked request."),
            )
            continue

        try:
            # Shopify catalog endpoint returns a top-level "products" list
            products = raw_json.get("products", []) if isinstance(raw_json, dict) else []

            if not products:
                log_to_dlq(source_url=url, raw_payload=raw_json, error=ValueError("Empty or missing 'products' array"))
                continue

            for item in products:
                try:
                    # Defensive parsing without rigid Pydantic models
                    key_val = str(item.get("id") or item.get("handle") or "unknown_key")
                    title_val = str(item.get("title") or "Untitled Product").strip()
                    
                    # Extract vendor & category
                    vendor_val = str(item.get("vendor") or "Unknown Vendor")
                    category_val = str(item.get("product_type") or "General")

                    # Extract pricing safely from the first variant
                    price_val = 0.0
                    variants = item.get("variants") or []
                    if isinstance(variants, list) and len(variants) > 0:
                        first_variant = variants[0]
                        if isinstance(first_variant, dict) and "price" in first_variant:
                            price_val = float(first_variant["price"])

                    # Build validated BookRecord domain model
                    record = BookRecord(
                        key=key_val,
                        title=title_val,
                        description=f"Vendor: {vendor_val} | Category: {category_val}",
                        price=price_val,
                        vendor=vendor_val,
                        category=category_val,
                    )
                    valid_records.append(record)

                except Exception as item_err:
                    log_to_dlq(source_url=url, raw_payload=item, error=item_err)

        except Exception as batch_err:
            log_to_dlq(source_url=url, raw_payload=raw_json, error=batch_err)

    # Bulk store valid extracted records into DuckDB
    if valid_records:
        with duckdb.connect(settings.DB_PATH) as con:
            records_data = [
                (r.key, r.title, r.description, [getattr(r, "category", "General")])
                for r in valid_records
            ]
            con.executemany(
                """
                INSERT OR REPLACE INTO raw_books (key, title, description, subjects)
                VALUES (?, ?, ?, ?)
            """,
                records_data,
            )
        logging.info(f"Persisted {len(valid_records)} valid records into DuckDB.")

    return valid_records