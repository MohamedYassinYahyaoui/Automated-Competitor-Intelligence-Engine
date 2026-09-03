from pydantic import BaseModel, Field

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
    variants: list[dict] | None = None