"""Automated Competitor Intelligence Engine Package."""

__version__ = "0.1.0"
__author__ = "Yassin Yahyaoui"

# Expose key entrypoints for clean top-level importing in main.py
from app.core.config import settings
from app.db.connection import init_db
from app.services.analyzer import analyze_batch
from app.services.ingestion import fetch_and_process_batch

__all__ = [
    "settings",
    "init_db",
    "fetch_and_process_batch",
    "analyze_batch",
]