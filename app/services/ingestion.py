import asyncio
import logging
from typing import Any, Dict, List, Optional
from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

# Standard browser context to pass Cloudflare fingerprint checks
BROWSER_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
}


async def fetch_target_payload(
    url: str, 
    fallback_urls: Optional[List[str]] = None, 
    timeout: int = 20
) -> Dict[str, Any]:
    """
    Fetches raw JSON payload using curl_cffi Chrome impersonation.
    """
    targets_to_try = [url] + (fallback_urls or [])
    last_exception = None

    async with AsyncSession(impersonate="chrome120") as session:
        for target in targets_to_try:
            try:
                cleaned_url = target.rstrip("/")
                request_headers = BROWSER_HEADERS.copy()

                response = await session.get(
                    cleaned_url,
                    headers=request_headers,
                    allow_redirects=True,
                    timeout=timeout
                )

                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as json_err:
                        raise ValueError(f"Invalid JSON payload returned from {cleaned_url}: {json_err}")

                elif response.status_code in (403, 404):
                    logger.warning(f"Endpoint HTTP {response.status_code} on {cleaned_url}. Attempting fallback route...")
                    last_exception = Exception(f"[{response.status_code} HTTP STATUS] Anti-bot block or missing resource on {cleaned_url}.")
                    continue

                else:
                    response.raise_for_status()

            except Exception as e:
                last_exception = e
                logger.warning(f"Fetch failed on {target}: {e}")
                continue

    raise last_exception or Exception(f"Failed to fetch payload from {url}")


async def ingest_single_target(target_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Worker function for single target execution."""
    main_url = target_config["url"]
    fallbacks = target_config.get("fallbacks", [])
    return await fetch_target_payload(main_url, fallback_urls=fallbacks)


async def fetch_and_process_batch(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch execution entrypoint required by package exports."""
    tasks = [ingest_single_target(target) for target in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    valid_payloads = []
    for target, result in zip(targets, results):
        if isinstance(result, Exception):
            logger.warning(f"Batch fetch failed for {target.get('url')}: {result}")
        elif result:
            valid_payloads.append(result)
            
    return valid_payloads