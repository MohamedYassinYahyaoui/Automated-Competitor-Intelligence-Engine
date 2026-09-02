import asyncio
import time
import httpx
import re
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
)

# Headers to mimic a browser and avoid basic blocklists
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(5),
    # Explicitly catch network issues and HTTP status errors (429, 5xx)
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=True,
)
async def fetch_single_url(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a single URL with error handling and individual retry logic."""
    response = await client.get(url, headers=HEADERS, timeout=10.0)
    
    #forces httpx to raise HTTPStatusError on 4xx/5xx responses
    response.raise_for_status() 
    
    return response.text


def parse_book_html(html_content: str) -> list[dict]:
    """Parse HTML content of a category page and return normalized book records."""
    soup = BeautifulSoup(html_content, "html.parser")
    books = []

    for book in soup.select("article.product_pod"):
        title_tag = book.h3.a if book.h3 and book.h3.a else None
        if not title_tag:
            continue

        title = title_tag.get("title")
        price_tag = book.select_one("p.price_color")
        price = None
        if price_tag:
            match = re.search(r"\d+\.\d+", price_tag.text)
            price = float(match.group()) if match else None

        # Extract availability status
        availability_tag = book.select_one("p.instock.availability")
        is_in_stock = False
        if availability_tag:
            clean_text = " ".join(availability_tag.text.split())
            is_in_stock = "in stock" in clean_text.lower()

        if title and price is not None:
            books.append(
                {
                    "title": title,
                    "price_gbp": price,
                    "in_stock": is_in_stock,
                }
            )

    return books

async def fetch_all_urls(urls: list[str]) -> list[str]:
    """Manages the client session and executes batch requests concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [fetch_single_url(client, url) for url in urls]
        # return_exceptions=True prevents one failed URL from crashing the entire batch
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results
if __name__ == "__main__":
    target_urls = [
        "https://books.toscrape.com/catalogue/category/books/science_22/index.html",
        "https://books.toscrape.com/catalogue/category/books/academic_40/index.html",
        "https://books.toscrape.com/catalogue/category/books/historical-fiction_4/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        "https://books.toscrape.com/catalogue/category/books/romance_8/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"
    ]

    start = time.perf_counter()
    html_pages = asyncio.run(fetch_all_urls(target_urls))
    end = time.perf_counter()
    books = [book for html in html_pages for book in parse_book_html(html)]
    print(f"Extracted {len(books)} books from {len(html_pages)} pages.")
    print("Sample extracted books:")
    for book in books[:5]:  # Print first 5 books as a sample
        print(book)

    print(f"Successfully fetched {len(html_pages)} pages in {end - start:.2f} seconds.")