import duckdb
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def init_duckdb_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Creates the analytical database tables and views if they do not exist."""
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

        CREATE TABLE IF NOT EXISTS dlq_quarantine (
            quarantine_id VARCHAR PRIMARY KEY,
            target_name VARCHAR,
            target_url VARCHAR,
            error_reason VARCHAR,
            http_status INT,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    logger.info("DuckDB analytical schema verified.")


def persist_products_to_duckdb(
    extracted_catalogs: List[Dict[str, Any]], 
    db_path: str = "analytics.duckdb"
) -> None:
    """
    Persists normalized catalog items into DuckDB using UPSERT logic
    to avoid primary key duplication errors during back-to-back pipeline runs.
    """
    if not extracted_catalogs:
        logger.warning("No extracted catalogs provided for persistence.")
        return

    # Use context manager to ensure database lock is released promptly
    with duckdb.connect(db_path) as conn:
        init_duckdb_schema(conn)

        for catalog in extracted_catalogs:
            target_name = catalog.get("target", "Unknown")
            products = catalog.get("products", [])

            for p in products:
                conn.execute("""
                    INSERT INTO products (
                        product_id, target_name, title, handle, vendor, 
                        product_type, price_min, price_max, total_variants, 
                        available, tags, extraction_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        price_min = EXCLUDED.price_min,
                        price_max = EXCLUDED.price_max,
                        available = EXCLUDED.available,
                        ingested_at = now();
                """, (
                    p.get("product_id"),
                    target_name,
                    p.get("title"),
                    p.get("handle"),
                    p.get("vendor"),
                    p.get("product_type"),
                    p.get("price_min", 0.0),
                    p.get("price_max", 0.0),
                    p.get("total_variants", 1),
                    p.get("available", True),
                    p.get("tags", []),
                    p.get("extraction_source", "unknown")
                ))

        logger.info(f"Successfully persisted catalog items across targets into DuckDB.")


def prune_catalog_for_llm(
    extracted_catalogs: List[Dict[str, Any]], 
    max_tags_per_product: int = 5
) -> List[Dict[str, Any]]:
    """
    Prunes raw payloads into lean, high-signal feature vectors.
    Strips raw HTML, duplicate variant fields, image arrays, and structural bloat
    to keep API token consumption minimal.
    """
    pruned_catalogs = []

    for catalog in extracted_catalogs:
        target_name = catalog.get("target", "Unknown Target")
        raw_products = catalog.get("products", [])
        
        pruned_products = []
        for prod in raw_products:
            # Strip tags list down to top N relevant entries
            tags = prod.get("tags", [])
            trimmed_tags = tags[:max_tags_per_product] if isinstance(tags, list) else []

            pruned_products.append({
                "title": prod.get("title"),
                "vendor": prod.get("vendor"),
                "category": prod.get("product_type"),
                "price": prod.get("price_min"),
                "in_stock": prod.get("available"),
                "variant_count": prod.get("total_variants"),
                "tags": trimmed_tags
            })

        pruned_catalogs.append({
            "target": target_name,
            "total_extracted": len(pruned_products),
            "products": pruned_products
        })

    return pruned_catalogs


def persist_and_prune_catalog(
    extracted_catalogs: List[Dict[str, Any]], 
    db_path: str = "analytics.duckdb"
) -> List[Dict[str, Any]]:
    """
    Unified entrypoint: Persists extracted data into DuckDB and transforms
    it into an optimized feature representation ready for Gemini API generation.
    """
    # Step 1: OLAP Storage
    persist_products_to_duckdb(extracted_catalogs, db_path=db_path)

    # Step 2: Token Pruning
    pruned_payload = prune_catalog_for_llm(extracted_catalogs)
    
    return pruned_payload