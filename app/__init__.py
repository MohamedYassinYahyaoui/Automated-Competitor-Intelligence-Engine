"""App Package: Automated Market & Competitor Analysis Pipeline."""

from app.analyzer import generate_batch_market_report
from app.database import bulk_save_to_duckdb, init_duckdb, save_llm_report
from app.ingestion import stream_batches
from app.schemas import MarketReportSchema, OpenLibraryBook

__all__ = [
    "init_duckdb",
    "bulk_save_to_duckdb",
    "save_llm_report",
    "OpenLibraryBook",
    "MarketReportSchema",
    "stream_batches",
    "generate_batch_market_report",
]