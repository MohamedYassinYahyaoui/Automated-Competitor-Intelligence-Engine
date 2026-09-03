from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DLQItem(BaseModel):
    """Data contract representing a quarantined failure record."""

    id: str
    failed_at: datetime
    source_url: str
    raw_payload: Optional[Dict[str, Any]] = None
    error_type: str
    error_message: str
    replayed: bool = False