import json
import logging
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_shopify_json_products(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fast Path: Parses standard Shopify /products.json response structure."""
    raw_products = data.get("products", [])
    extracted = []

    for prod in raw_products:
        variants = prod.get("variants", [])
        images = prod.get("images", [])
        
        # Calculate pricing range across all product variants
        prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
        
        extracted.append({
            "product_id": str(prod.get("id", "")),
            "title": prod.get("title", "Unknown Product"),
            "handle": prod.get("handle", ""),
            "vendor": prod.get("vendor", "Unknown Vendor"),
            "product_type": prod.get("product_type", "General"),
            "created_at": prod.get("created_at"),
            "updated_at": prod.get("updated_at"),
            "tags": prod.get("tags", []) if isinstance(prod.get("tags"), list) else [t.strip() for t in str(prod.get("tags", "")).split(",") if t.strip()],
            "price_min": min(prices) if prices else 0.0,
            "price_max": max(prices) if prices else 0.0,
            "total_variants": len(variants),
            "available": any(v.get("available", False) for v in variants),
            "image_url": images[0].get("src") if images else None,
            "extraction_source": "shopify_json"
        })

    return extracted


def extract_schema_json_ld(html_content: str) -> List[Dict[str, Any]]:
    """
    Fallback Path: Parses embedded schema.org JSON-LD microdata from raw HTML 
    when target endpoints hide JSON routes behind Cloudflare.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")
    products = []

    for index, script in enumerate(scripts):
        if not script.string:
            continue
            
        try:
            data = json.loads(script.string)
            # Schema structures can be single objects or wrapped in an @graph list
            items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [data])
            
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    offers = item.get("offers", {})
                    if isinstance(offers, list) and len(offers) > 0:
                        offers = offers[0]
                    elif not isinstance(offers, dict):
                        offers = {}

                    price = offers.get("price") or offers.get("lowPrice") or 0.0
                    try:
                        price = float(price)
                    except (ValueError, TypeError):
                        price = 0.0

                    brand = item.get("brand")
                    if isinstance(brand, dict):
                        vendor = brand.get("name", "Unknown Vendor")
                    else:
                        vendor = str(brand) if brand else "Unknown Vendor"

                    products.append({
                        "product_id": str(item.get("sku") or item.get("productID") or f"html_parsed_{index}"),
                        "title": item.get("name", "Unknown Product"),
                        "handle": item.get("name", "").lower().replace(" ", "-"),
                        "vendor": vendor,
                        "product_type": "HTML Extracted",
                        "created_at": None,
                        "updated_at": None,
                        "tags": ["schema_microdata"],
                        "price_min": price,
                        "price_max": price,
                        "total_variants": 1,
                        "available": "InStock" in str(offers.get("availability", "")),
                        "image_url": item.get("image")[0] if isinstance(item.get("image"), list) else item.get("image"),
                        "extraction_source": "html_schema_json_ld"
                    })
        except Exception as err:
            logger.debug(f"Skipping malformed JSON-LD script block: {err}")
            continue

    return products


def extract_products_from_payload(raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Unified entrypoint: Automatically routes payload through fast path (JSON) 
    or fallback path (HTML parsing) based on response contents.
    """
    if not raw_payload:
        logger.warning("Received empty payload in extractor.")
        return []

    # Path A: Standard Shopify JSON API response
    if "products" in raw_payload and isinstance(raw_payload["products"], list):
        logger.info("Parsing via Fast Path (Shopify JSON format)...")
        return extract_shopify_json_products(raw_payload)

    # Path B: Fallback HTML content returned by Playwright or browser session
    elif "raw_html" in raw_payload:
        logger.info("Parsing via Fallback Path (HTML Schema.org microdata)...")
        extracted = extract_schema_json_ld(raw_payload["raw_html"])
        if not extracted:
            logger.warning(f"Failed to find schema.org product metadata in HTML from {raw_payload.get('url')}")
        return extracted

    else:
        logger.error("Unknown payload schema structure. Unable to extract products.")
        return []