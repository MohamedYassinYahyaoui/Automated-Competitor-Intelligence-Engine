import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List
import duckdb
from fastapi import APIRouter, FastAPI, HTTPException, Query
from app.core.config import settings
from app.db.connection import init_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Competitor Intelligence Engine"])


def get_db_connection(max_retries: int = 4, retry_delay: float = 0.05) -> duckdb.DuckDBPyConnection:
    """Returns a DuckDB connection instance using configured path in read-only mode,
    with exponential retry to gracefully handle concurrent write transactions.
    """
    db_path = settings.DB_PATH
    if not Path(db_path).exists():
        init_db(db_path)

    for attempt in range(max_retries):
        try:
            return duckdb.connect(db_path, read_only=True)
        except (duckdb.IOException, duckdb.Error) as e:
            if attempt == max_retries - 1:
                logger.error(
                    f"Failed to acquire read connection on '{db_path}' after {max_retries} attempts: {e}"
                )
                raise
            time.sleep(retry_delay * (2 ** attempt))


@router.get("/health")
def health_check() -> Dict[str, str]:
    """Pipeline and DB connectivity health check."""
    try:
        with get_db_connection() as con:
            con.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Database unreachable: {str(e)}"
        )


@router.get("/summary")
def get_brand_pricing_summary() -> List[Dict[str, Any]]:
    """Executes analytical DuckDB SQL aggregations across tracked competitor brands."""
    try:
        with get_db_connection() as con:
            rows = con.execute(
                """
                SELECT
                    target_name,
                    COUNT(*) AS product_count,
                    ROUND(AVG(price_min), 2) AS avg_price,
                    ROUND(MIN(price_min), 2) AS min_price,
                    ROUND(MAX(price_max), 2) AS max_price,
                    ROUND(AVG(total_variants), 1) AS avg_variants,
                    SUM(CASE WHEN NOT available THEN 1 ELSE 0 END) AS oos_count
                FROM products
                GROUP BY target_name
                ORDER BY product_count DESC
                """
            ).fetchall()
        return [
            {
                "target_name": r[0],
                "product_count": r[1],
                "avg_price": r[2],
                "min_price": r[3],
                "max_price": r[4],
                "avg_variants": r[5],
                "oos_count": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to compute OLAP summary: {str(e)}"
        )


@router.get("/reports")
def get_market_reports(
    limit: int = Query(default=10, le=100)
) -> List[Dict[str, Any]]:
    """Retrieves synthesized market reports persisted in DuckDB."""
    try:
        with get_db_connection() as con:
            query = """
                SELECT id, created_at, batch_size, model_used, report_markdown, raw_json
                FROM market_reports
                ORDER BY created_at DESC
                LIMIT ?
            """
            rows = con.execute(query, [limit]).fetchall()

        reports = []
        for row in rows:
            reports.append(
                {
                    "id": row[0],
                    "created_at": str(row[1]),
                    "batch_size": row[2],
                    "model_used": row[3],
                    "report_markdown": row[4],
                    "raw_json": json.loads(row[5]) if row[5] else None,
                }
            )
        return reports
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch reports: {str(e)}"
        )


@router.get("/dlq")
def get_dead_letter_queue(
    replayed: bool = Query(default=False), limit: int = Query(default=20, le=100)
) -> List[Dict[str, Any]]:
    """Inspects quarantined payloads that failed validation or processing."""
    try:
        with get_db_connection() as con:
            query = """
                SELECT id, quarantined_at, target_name, source_url, raw_payload, error_type, error_message, replayed
                FROM dead_letter_queue
                WHERE replayed = ?
                ORDER BY quarantined_at DESC
                LIMIT ?
            """
            rows = con.execute(query, [replayed, limit]).fetchall()

        dlq_items = []
        for row in rows:
            try:
                parsed_raw = json.loads(row[4]) if row[4] else None
            except Exception:
                parsed_raw = row[4]

            dlq_items.append(
                {
                    "id": row[0],
                    "quarantined_at": str(row[1]),
                    "target_name": row[2],
                    "source_url": row[3],
                    "raw_payload": parsed_raw,
                    "error_type": row[5],
                    "error_message": row[6],
                    "replayed": row[7],
                }
            )
        return dlq_items
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to query DLQ: {str(e)}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes DuckDB tables once on server startup rather than on per-request hot paths."""
    try:
        init_db(settings.DB_PATH)
    except Exception as e:
        logger.warning(f"Could not initialize DuckDB at startup: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Operational OLAP & DLQ inspection API for the Automated Competitor Intelligence Engine.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)
