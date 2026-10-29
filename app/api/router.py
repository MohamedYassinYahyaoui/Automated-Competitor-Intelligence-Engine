import json
from typing import Any, Dict, List
import duckdb
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.db.connection import init_db

router = APIRouter(prefix="/api/v1", tags=["Competitor Intelligence Engine"])


def get_db_connection():
    """Returns a DuckDB connection instance using configured path."""
    init_db(settings.DB_PATH)
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
