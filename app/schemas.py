from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 1. INGESTION SCHEMAS (RAW DATA VALIDATION)
# ---------------------------------------------------------------------------
class OpenLibraryBook(BaseModel):
    """Schema for validating raw Open Library work payloads."""

    key: str = Field(..., description="Unique Open Library work identifier")
    title: str = Field(..., description="Book title")
    description: Optional[str] = Field(
        default=None, description="Book description or summary"
    )
    subjects: List[str] = Field(
        default_factory=list, description="Categorical subject tags"
    )

    @field_validator("description", mode="before")
    @classmethod
    def parse_description(cls, value: Any) -> Optional[str]:
        """Handles Open Library's inconsistent description field (string vs dictionary)."""
        if isinstance(value, dict):
            return value.get("value", "")
        if isinstance(value, str):
            return value
        return None

    @field_validator("subjects", mode="before")
    @classmethod
    def sanitize_subjects(cls, value: Any) -> List[str]:
        """Ensures subjects are always formatted as a clean list of strings."""
        if isinstance(value, list):
            return [str(s).strip() for s in value if s]
        return []

    class Config:
        populate_by_name = True
        extra = "ignore"


# ---------------------------------------------------------------------------
# 2. LLM OUTPUT SCHEMAS (STRUCTURED GEMINI SYNTHESIS)
# ---------------------------------------------------------------------------
class Recommendation(BaseModel):
    """Schema for individual top book recommendations within LLM reports."""

    title: str = Field(..., description="Title of the recommended book")
    estimated_value_score: int = Field(
        ..., ge=1, le=10, description="Value/Impact score from 1 to 10"
    )
    target_audience: str = Field(
        ..., description="Primary reader demographic or field"
    )


class MarketReportSchema(BaseModel):
    """Strict schema enforcing structured output from Gemini LLM calls."""

    category_summary: str = Field(
        ..., description="Executive summary of dominant categories and themes"
    )
    price_assessment: str = Field(
        ..., description="Market analysis on pricing and value positioning"
    )
    top_recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="List of top highlighted titles with value scores",
    )
    key_takeaways: List[str] = Field(
        default_factory=list,
        description="Strategic insights derived from the dataset batch",
    )


# ---------------------------------------------------------------------------
# 3. API RESPONSE SCHEMAS
# ---------------------------------------------------------------------------
class MarketReportResponse(BaseModel):
    """Schema for returning database records via FastAPI."""

    id: str
    created_at: str
    batch_size: Optional[int] = None
    category_summary: Optional[str] = None
    price_assessment: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None