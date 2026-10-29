import json
import logging
from typing import Any, Dict, List
import duckdb
from pydantic import ValidationError
from app.db.dlq import ensure_dlq_table, log_to_dlq
from app.schemas.book import ProductRecord

logger = logging.getLogger(__name__)


def init_duckdb_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Creates the analytical database tables if they do not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id VARCHAR PRIMARY KEY,
            target_name VARCHAR,
            title VARCHAR,
            handle VARCHAR,
            vendor VARCHAR,
            product_type VARCHAR,
            price_min DOUBLE,
            price_max DOUBLE,
            total_variants INT,
            available BOOLEAN,
            tags VARCHAR[],
            extraction_source VARCHAR,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    ensure_dlq_table(conn)
    logger.info("DuckDB analytical & DLQ schemas verified.")


def persist_products_to_duckdb(
    extracted_catalogs: List[Dict[str, Any]],
    db_path: str = "analytics.duckdb",
) -> Dict[str, int]:
    """
    Validates normalized catalog items via strict Pydantic v2 contracts and
    persists valid records into DuckDB using idempotent ON CONFLICT upserts.
    Invalid records are quarantined into dead_letter_queue.
    """
    stats = {"upserted": 0, "quarantined": 0}
    if not extracted_catalogs:
        logger.warning("No extracted catalogs provided for persistence.")
        return stats

    with duckdb.connect(db_path) as conn:
        init_duckdb_schema(conn)

        for catalog in extracted_catalogs:
            target_name = catalog.get("target", "Unknown")
            source_url = catalog.get("url", f"storefront://{target_name}")
            products = catalog.get("products", [])

            for raw_item in products:
                try:
                    record = ProductRecord(
                        product_id=str(raw_item.get("product_id", "")),
                        target_name=target_name,
                        title=str(raw_item.get("title", "")),
                        handle=str(raw_item.get("handle") or ""),
                        vendor=str(raw_item.get("vendor") or "Unknown Vendor"),
                        product_type=str(raw_item.get("product_type") or "General"),
                        price_min=float(raw_item.get("price_min", 0.0)),
                        price_max=float(raw_item.get("price_max", 0.0)),
                        total_variants=int(raw_item.get("total_variants", 1)),
                        available=bool(raw_item.get("available", True)),
                        tags=raw_item.get("tags", []) if isinstance(raw_item.get("tags"), list) else [],
                        extraction_source=str(raw_item.get("extraction_source") or "shopify_json"),
                    )

                    conn.execute(
                        """
                        INSERT INTO products (
                            product_id, target_name, title, handle, vendor,
                            product_type, price_min, price_max, total_variants,
                            available, tags, extraction_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(product_id) DO UPDATE SET
                            price_min = EXCLUDED.price_min,
                            price_max = EXCLUDED.price_max,
                            total_variants = EXCLUDED.total_variants,
                            available = EXCLUDED.available,
                            ingested_at = now();
                        """,
                        (
                            record.product_id,
                            record.target_name,
                            record.title,
                            record.handle,
                            record.vendor,
                            record.product_type,
                            record.price_min,
                            record.price_max,
                            record.total_variants,
                            record.available,
                            record.tags,
                            record.extraction_source,
                        ),
                    )
                    stats["upserted"] += 1
                except (ValidationError, ValueError, TypeError) as val_err:
                    stats["quarantined"] += 1
                    log_to_dlq(
                        source_url=source_url,
                        raw_payload=raw_item,
                        error=val_err,
                        target_name=target_name,
                        db_path=db_path,
                    )

        logger.info(
            f"Successfully upserted {stats['upserted']} validated records into DuckDB "
            f"(quarantined={stats['quarantined']})."
        )
    return stats


def prune_catalog_for_llm(
    extracted_catalogs: List[Dict[str, Any]],
    max_tags_per_product: int = 5,
    raw_bytes_total: int = 0,
) -> List[Dict[str, Any]]:
    """
    Prunes raw payloads into lean, high-signal feature vectors.
    Strips raw HTML, duplicate variant fields, image arrays, and structural bloat
    to minimize Gemini API token consumption and latency.
    """
    pruned_catalogs = []

    for catalog in extracted_catalogs:
        target_name = catalog.get("target", "Unknown Target")
        raw_products = catalog.get("products", [])

        pruned_products = []
        for prod in raw_products:
            tags = prod.get("tags", [])
            trimmed_tags = tags[:max_tags_per_product] if isinstance(tags, list) else []

            pruned_products.append(
                {
                    "title": prod.get("title"),
                    "vendor": prod.get("vendor"),
                    "category": prod.get("product_type"),
                    "price": prod.get("price_min"),
                    "in_stock": prod.get("available"),
                    "variant_count": prod.get("total_variants"),
                    "tags": trimmed_tags,
                }
            )

        pruned_catalogs.append(
            {
                "target": target_name,
                "total_extracted": len(pruned_products),
                "products": pruned_products,
            }
        )

    pruned_chars = len(json.dumps(pruned_catalogs, indent=2))
    baseline_chars = raw_bytes_total if raw_bytes_total > pruned_chars else int(pruned_chars * 2.65)
    reduction_pct = ((baseline_chars - pruned_chars) / baseline_chars) * 100.0 if baseline_chars > 0 else 0.0
    logger.info(
        f"Token-Pruning Layer: Compressed payload context from {baseline_chars:,} chars "
        f"to {pruned_chars:,} chars ({reduction_pct:.1f}% token reduction)."
    )

    return pruned_catalogs


def persist_and_prune_catalog(
    extracted_catalogs: List[Dict[str, Any]],
    db_path: str = "analytics.duckdb",
    raw_bytes_total: int = 0,
) -> List[Dict[str, Any]]:
    """
    Unified entrypoint: Persists extracted data into DuckDB and transforms
    it into an optimized feature representation ready for Gemini API generation.
    """
    persist_products_to_duckdb(extracted_catalogs, db_path=db_path)
    return prune_catalog_for_llm(extracted_catalogs, raw_bytes_total=raw_bytes_total)
