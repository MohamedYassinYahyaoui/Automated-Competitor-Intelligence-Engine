from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RawBookPayload(BaseModel):
    """Loose validation contract for incoming HTTP JSON responses."""

    key: str
    title: Optional[str] = None
    description: Optional[Any] = None
    subjects: Optional[List[str]] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class BookRecord(BaseModel):
    """Strict internal data contract required for ingestion into raw_books table."""

    key: str = Field(..., min_length=3, description="Unique target identifier or URL key.")
    title: str = Field(..., min_length=1, description="Entity title. Must not be empty.")
    description: str = Field(
        default="No description provided.",
        description="Cleaned textual description.",
    )
    subjects: List[str] = Field(
        default_factory=list, description="Categorical tags."
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, value: str) -> str:
        """Enforces title presence to prevent empty records in DuckDB."""
        cleaned = value.strip() if value else ""
        if not cleaned:
            raise ValueError("Title field cannot be empty or whitespace.")
        return cleaned

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> str:
        """Normalizes heterogeneous description shapes (string vs nested dicts)."""
        if isinstance(value, dict) and "value" in value:
            return str(value["value"]).strip()
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "No description provided."