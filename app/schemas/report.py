from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SynthesizedReport(BaseModel):
    """Structured output schema enforced on Gemini analysis responses."""

    category_summary: str = Field(
        ..., description="High-level category trends synthesized from batch."
    )
    price_assessment: str = Field(
        ..., description="Market pricing positioning and competitive insights."
    )
    key_takeaways: List[str] = Field(
        default_factory=list, description="Actionable strategic points."
    )


class MarketReportResponse(BaseModel):
    """API payload schema returned by router.py endpoints."""

    id: str
    created_at: datetime
    batch_size: Optional[int] = None
    category_summary: str
    price_assessment: str
    raw_json: Optional[Dict[str, Any]] = None