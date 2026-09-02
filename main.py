import asyncio
from scraper import fetch_all_urls, parse_book_html
from analyzer import analyze_extracted_books, MarketAnalysis

if __name__ == "__main__":
    target_urls = [
        "https://books.toscrape.com/catalogue/category/books/science_22/index.html",
        "https://books.toscrape.com/catalogue/category/books/academic_40/index.html",
    ]

    print("Fetching raw HTML...")
    html_pages = asyncio.run(fetch_all_urls(target_urls))
    
    print("Parsing HTML into structured records...")
    raw_books = [book for html in html_pages for book in parse_book_html(html)]
    
    print(f"Sending {len(raw_books)} records to Gemini API for analysis...")
    analysis_result: MarketAnalysis = analyze_extracted_books(raw_books)
    
    # Printed output is now a typed Pydantic object, not raw string text
    print("\n--- GEMINI ANALYSIS RESULT ---")
    print(f"Summary: {analysis_result.category_summary}\n")
    print(f"Price Assessment: {analysis_result.price_assessment}\n")
    print("Top Recommendations:")
    for book in analysis_result.top_recommendations:
        print(f" - {book.title} (Score: {book.estimated_value_score}/10): {book.target_audience}")