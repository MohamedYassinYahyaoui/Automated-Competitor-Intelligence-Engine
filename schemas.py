from pydantic import BaseModel, Field
from typing import List

class BookInsight(BaseModel):
    title: str = Field(description="Title of the book.")
    estimated_value_score: int = Field(
        description="Value score from 1 to 10 based on content density vs price."
    )
    target_audience: str = Field(description="Intended audience for this book.")

class MarketAnalysis(BaseModel):
    category_summary: str = Field(description="Summary of the overall book category trends.")
    price_assessment: str = Field(description="Evaluation of price points across extracted items.")
    top_recommendations: List[BookInsight] = Field(
        description="Top 2-3 recommended books with scores."
    )
    key_takeaways: List[str] = Field(description="Key bullet points summarizing market position.")