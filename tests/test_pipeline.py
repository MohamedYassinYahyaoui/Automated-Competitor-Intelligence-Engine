import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from app.api import router as api_router
from app.core.config import settings
from app.db.dlq import get_unhandled_dlq_count
from app.services.analyzer import generate_intelligence_report
from app.services.extractor import extract_products_from_payload
from app.services.ingestion import fetch_target_payload
from app.services.transform import persist_products_to_duckdb, prune_catalog_for_llm
from scripts.replay_dlq import inspect_and_replay_dlq, purge_dead_404s, seed_demo_dlq_records


def test_extract_shopify_json_fast_path():
    raw_shopify = {
        "products": [
            {
                "id": 8819201,
                "title": "Wool Runner Mizzle",
                "handle": "wool-runner-mizzle",
                "vendor": "Allbirds",
                "product_type": "Shoes",
                "tags": "water-repellent, merino, winter, sustainable, mens, extra-tag",
                "variants": [
                    {"price": "115.00", "available": False},
                    {"price": "135.00", "available": True},
                ],
                "images": [{"src": "https://cdn.shopify.com/shoe.jpg"}],
            }
        ]
    }
    extracted = extract_products_from_payload(raw_shopify)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["product_id"] == "8819201"
    assert item["price_min"] == 115.0
    assert item["price_max"] == 135.0
    assert item["total_variants"] == 2
    assert item["available"] is True
    assert item["extraction_source"] == "shopify_json"


def test_extract_schema_json_ld_html_fallback():
    html_payload = {
        "url": "https://us.shop.gymshark.com/products/vital-seamless",
        "raw_html": """
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "sku": "GS-VITAL-001",
          "name": "Vital Seamless 2.0 Leggings",
          "brand": {"@type": "Brand", "name": "Gymshark"},
          "offers": {
            "@type": "Offer",
            "price": "54.00",
            "availability": "https://schema.org/InStock"
          }
        }
        </script>
        </head><body></body></html>
        """,
    }
    extracted = extract_products_from_payload(html_payload)
    assert len(extracted) == 1
    item = extracted[0]
    assert item["product_id"] == "GS-VITAL-001"
    assert item["title"] == "Vital Seamless 2.0 Leggings"
    assert item["vendor"] == "Gymshark"
    assert item["price_min"] == 54.0
    assert item["available"] is True
    assert item["extraction_source"] == "html_schema_json_ld"


def test_ingestion_escalates_to_playwright_on_http_403():
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.get.return_value = mock_resp

    expected_playwright_data = {"raw_html": "<html></html>", "url": "https://protected.example.com"}

    with patch("app.services.ingestion.AsyncSession", return_value=mock_session), \
         patch("app.services.ingestion.HAS_PLAYWRIGHT", True), \
         patch("app.services.ingestion.fetch_with_playwright", new_callable=AsyncMock) as pw_mock:
        pw_mock.return_value = expected_playwright_data
        result = asyncio.run(fetch_target_payload("https://protected.example.com"))

        assert result == expected_playwright_data
        pw_mock.assert_awaited_once_with("https://protected.example.com")


def test_pydantic_v2_validation_and_idempotent_duckdb_upsert(tmp_path: Path):
    db_file = str(tmp_path / "test_upsert.duckdb")

    catalog_run_1 = [
        {
            "target": "Allbirds",
            "url": "https://www.allbirds.com/products.json",
            "products": [
                {
                    "product_id": "ab-100",
                    "title": "Tree Dasher 2",
                    "handle": "tree-dasher-2",
                    "vendor": "Allbirds",
                    "product_type": "Running",
                    "price_min": 135.0,
                    "price_max": 135.0,
                    "total_variants": 8,
                    "available": True,
                    "tags": ["running", "lightweight"],
                    "extraction_source": "shopify_json",
                }
            ],
        }
    ]
    stats1 = persist_products_to_duckdb(catalog_run_1, db_path=db_file)
    assert stats1 == {"upserted": 1, "quarantined": 0}

    # Run 2: Same product_id with a markdown price ($108.00) and OOS update -> must upsert idempotently
    catalog_run_2 = [
        {
            "target": "Allbirds",
            "url": "https://www.allbirds.com/products.json",
            "products": [
                {
                    "product_id": "ab-100",
                    "title": "Tree Dasher 2",
                    "handle": "tree-dasher-2",
                    "vendor": "Allbirds",
                    "product_type": "Running",
                    "price_min": 108.0,
                    "price_max": 135.0,
                    "total_variants": 8,
                    "available": False,
                    "tags": ["running", "sale"],
                    "extraction_source": "shopify_json",
                }
            ],
        }
    ]
    stats2 = persist_products_to_duckdb(catalog_run_2, db_path=db_file)
    assert stats2 == {"upserted": 1, "quarantined": 0}

    with duckdb.connect(db_file, read_only=True) as con:
        count, p_min, avail = con.execute(
            "SELECT COUNT(*), MIN(price_min), MIN(available) FROM products WHERE product_id = 'ab-100'"
        ).fetchone()
        assert count == 1
        assert p_min == 108.0
        assert avail is False


def test_corrupt_schema_quarantined_to_dlq_and_replayed(tmp_path: Path):
    db_file = str(tmp_path / "test_dlq.duckdb")

    seed_demo_dlq_records(db_file)
    assert get_unhandled_dlq_count(db_path=db_file) == 2

    inspect_and_replay_dlq(db_path=db_file)
    # 1 recoverable schema error replayed; 1 unrecoverable HTTP 404 remains until purged
    assert get_unhandled_dlq_count(db_path=db_file) == 1

    purged = purge_dead_404s(db_file)
    assert purged == 1
    assert get_unhandled_dlq_count(db_path=db_file) == 0

    with duckdb.connect(db_file, read_only=True) as con:
        row = con.execute(
            "SELECT title, price_min, price_max FROM products WHERE product_id = 'gs-apex-seamless-9910'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Apex Seamless T Shirt Black"
        assert row[1] == 38.0
        assert row[2] == 46.0


def test_token_pruning_layer_reduces_payload_size():
    bloated_catalog = [
        {
            "target": "Red Bull Shop",
            "products": [
                {
                    "product_id": f"rb-{i}",
                    "title": f"Oracle Red Bull Racing Team Polo {i}",
                    "vendor": "Red Bull",
                    "product_type": "Apparel",
                    "price_min": 75.0,
                    "price_max": 85.0,
                    "total_variants": 6,
                    "available": True,
                    "tags": [f"tag-{t}" for t in range(25)],
                    "body_html": "<div>" + ("Heavy HTML description bloat " * 80) + "</div>",
                    "images": [{"src": f"https://cdn.example.com/img_{img}.png"} for img in range(15)],
                }
                for i in range(10)
            ],
        }
    ]
    raw_size = len(json.dumps(bloated_catalog))
    pruned = prune_catalog_for_llm(bloated_catalog, max_tags_per_product=5, raw_bytes_total=raw_size)
    pruned_size = len(json.dumps(pruned))

    reduction_ratio = (raw_size - pruned_size) / raw_size
    assert reduction_ratio > 0.70
    assert len(pruned[0]["products"][0]["tags"]) == 5
    assert "body_html" not in pruned[0]["products"][0]


def test_fastapi_operational_router_endpoints(tmp_path: Path, monkeypatch):
    db_file = str(tmp_path / "test_api.duckdb")
    monkeypatch.setattr(settings, "DB_PATH", db_file)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    seed_demo_dlq_records(db_file)
    sample_pruned = [
        {
            "target": "Allbirds",
            "total_extracted": 1,
            "products": [
                {
                    "title": "Wool Runner",
                    "vendor": "Allbirds",
                    "category": "Shoes",
                    "price": 110.0,
                    "in_stock": True,
                    "variant_count": 5,
                    "tags": ["merino"],
                }
            ],
        }
    ]
    asyncio.run(generate_intelligence_report(sample_pruned, db_path=db_file))

    health = api_router.health_check()
    assert health["status"] == "healthy"

    dlq_rows = api_router.get_dead_letter_queue(replayed=False, limit=10)
    assert len(dlq_rows) == 2

    reports = api_router.get_market_reports(limit=5)
    assert len(reports) == 1
    assert "Allbirds" in reports[0]["report_markdown"]
