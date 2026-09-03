import json
from typing import Any, Dict, List
import duckdb
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings

router = APIRouter(prefix="/api/v1", tags=["Competitor Intelligence Engine"])


def get_db_connection():
    """Returns a DuckDB connection instance using configured path."""
    return duckdb.connect(settings.DB_PATH, read_only=True)


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


@router.get("/reports")
def get_market_reports(
    limit: int = Query(default=10, le=100)
) -> List[Dict[str, Any]]:
    """Retrieves synthesized market reports produced by Gemini."""
    try:
        with get_db_connection() as con:
            query = """
                SELECT id, created_at, batch_size, category_summary, price_assessment, raw_json 
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
                    "category_summary": row[3],
                    "price_assessment": row[4],
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
                SELECT id, failed_at, source_url, raw_payload, error_type, error_message, replayed
                FROM dead_letter_queue
                WHERE replayed = ?
                ORDER BY failed_at DESC
                LIMIT ?
            """
            rows = con.execute(query, [replayed, limit]).fetchall()

        dlq_items = []
        for row in rows:
            dlq_items.append(
                {
                    "id": row[0],
                    "failed_at": str(row[1]),
                    "source_url": row[2],
                    "raw_payload": json.loads(row[3]) if row[3] else None,
                    "error_type": row[4],
                    "error_message": row[5],
                    "replayed": row[6],
                }
            )
        return dlq_items
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to query DLQ: {str(e)}"
        )