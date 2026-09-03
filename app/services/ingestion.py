import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from curl_cffi.requests import AsyncSession

# Optional import for Playwright fallback
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)

# Standard browser context to pass basic Cloudflare fingerprint checks
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


async def fetch_with_playwright(url: str, timeout_ms: int = 30000) -> Dict[str, Any]:
    """
    Escalation path: Launches a headless browser to bypass JavaScript challenges
    and anti-bot barriers when standard HTTP requests hit Cloudflare (403).
    """
    if not HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright is not installed. Install via `pip install playwright` "
            "and `playwright install chromium` to enable JS challenge escalation."
        )

    logger.info(f"[PLAYWRIGHT ESCALATION] Launching stealth browser for target: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=BROWSER_HEADERS["user-agent"],
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        try:
            response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            
            if not response or response.status >= 400:
                status = response.status if response else "NO_RESPONSE"
                raise Exception(f"Playwright navigation failed with HTTP {status}")

            # Grab inner text for JSON endpoints or full raw HTML for page parsing
            content = await page.evaluate("() => document.body.innerText")
            
            try:
                # Attempt to return parsed JSON if standard API endpoint
                return json.loads(content)
            except json.JSONDecodeError:
                # Return page HTML content if structured raw page
                raw_html = await page.content()
                return {"raw_html": raw_html, "url": url}

        finally:
            await browser.close()


async def fetch_target_payload(
    url: str, 
    fallback_urls: Optional[List[str]] = None, 
    timeout: int = 20
) -> Dict[str, Any]:
    """
    Main fetch engine. Tries curl_cffi Chrome impersonation first.
    Escalates to Playwright if anti-bot protection triggers a 403.
    """
    targets_to_try = [url] + (fallback_urls or [])
    last_exception = None

    # Step 1: Fast Path via curl_cffi impersonation
    async with AsyncSession(impersonate="chrome120") as session:
        for target in targets_to_try:
            try:
                cleaned_url = target.rstrip("/")
                request_headers = BROWSER_HEADERS.copy()

                logger.info(f"Attempting ingestion on {cleaned_url} via curl_cffi...")
                response = await session.get(
                    cleaned_url,
                    headers=request_headers,
                    allow_redirects=True,
                    timeout=timeout
                )

                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception:
                        # Non-JSON content (e.g. HTML storefront page)
                        return {"raw_html": response.text, "url": cleaned_url}

                elif response.status_code == 403:
                    logger.warning(f"HTTP 403 Anti-bot block detected on {cleaned_url}. Escalating to Playwright...")
                    if HAS_PLAYWRIGHT:
                        return await fetch_with_playwright(cleaned_url)
                    else:
                        last_exception = Exception(f"[403 HTTP STATUS] Anti-bot block on {cleaned_url}. Playwright not installed.")

                elif response.status_code == 404:
                    logger.warning(f"HTTP 404 on {cleaned_url}. Trying next fallback route...")
                    last_exception = Exception(f"[404 HTTP STATUS] Missing resource on {cleaned_url}")
                    continue

                else:
                    response.raise_for_status()

            except Exception as e:
                last_exception = e
                logger.warning(f"Fetch attempt failed on {target}: {e}")
                continue

    # Step 2: Final emergency escalation if all primary paths threw errors
    if HAS_PLAYWRIGHT:
        try:
            logger.info(f"Attempting final Playwright recovery on primary target: {url}")
            return await fetch_with_playwright(url)
        except Exception as py_err:
            last_exception = py_err

    raise last_exception or Exception(f"Failed to fetch payload from {url}")


async def ingest_single_target(target_config: Dict[str, Any]) -> Dict[str, Any]:
    """Worker entrypoint for single target ingestion."""
    main_url = target_config["url"]
    fallbacks = target_config.get("fallbacks", [])
    return await fetch_target_payload(main_url, fallback_urls=fallbacks)


async def fetch_and_process_batch(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch execution helper for concurrent ingestion."""
    tasks = [ingest_single_target(target) for target in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    valid_payloads = []
    for target, result in zip(targets, results):
        if isinstance(result, Exception):
            logger.error(f"Batch fetch failed for target '{target.get('name')}': {result}")
        elif result:
            valid_payloads.append(result)
            
    return valid_payloads