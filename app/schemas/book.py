from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ProductRecord(BaseModel):
    """Strict Pydantic v2 contract for normalized e-commerce catalog records."""

    product_id: str = Field(..., min_length=1, description="Unique product identifier or SKU")
    target_name: str = Field(default="Unknown", description="Competitor storefront name")
    title: str = Field(..., min_length=1, description="Normalized product title")
    handle: str = Field(default="", description="URL slug / handle")
    vendor: str = Field(default="Unknown Vendor", description="Brand or manufacturer")
    product_type: str = Field(default="General", description="Product category or type")
    price_min: float = Field(..., ge=0.0, description="Minimum variant price in USD")
    price_max: float = Field(..., ge=0.0, description="Maximum variant price in USD")
    total_variants: int = Field(default=1, ge=1, description="Total SKU variant count")
    available: bool = Field(default=True, description="Whether at least one variant is in stock")
    tags: List[str] = Field(default_factory=list, description="Normalized product tags")
    extraction_source: str = Field(default="shopify_json", description="Extraction path identifier")

    @field_validator("price_max")
    @classmethod
    def validate_price_range(cls, v: float, info) -> float:
        price_min = info.data.get("price_min", 0.0)
        if v < price_min:
            raise ValueError(f"price_max ({v}) cannot be less than price_min ({price_min})")
        return v


# Backward-compatible aliases
class BookRecord(BaseModel):
    key: str = Field(..., description="Unique product identifier or handle")
    title: str = Field(..., description="Product title")
    description: str = Field(default="", description="Product summary or description")
    price: float = Field(default=0.0, description="Product price in USD")
    vendor: str = Field(default="Unknown", description="Brand or manufacturer")
    category: str = Field(default="General", description="Product category or type")


class RawBookPayload(BaseModel):
    id: int | str | None = None
    title: str | None = None
    body_html: str | None = None
    vendor: str | None = None
    product_type: str | None = None
    variants: Optional[List[dict]] = None
