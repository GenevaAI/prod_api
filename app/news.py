# news.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
import os
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import feedparser
from urllib.parse import quote_plus
from datetime import datetime
import httpx

router = APIRouter(tags=["news"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class Article(BaseModel):
    title: str
    url: str
    source: Optional[str] = None
    published_at: Optional[str] = None
    description: Optional[str] = None

def fetch_google_news(query: str = "technology", max_results: int = 12) -> list[Article]:
    encoded_query = quote_plus(query)
    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(rss_url, headers=headers)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
    except Exception as e:
        # Temporary: surface the error so you can see it
        print(f"Error fetching news: {type(e).__name__}: {e}")
        # You can also temporarily return a dummy article with the error message
        return []

    articles = []
    for entry in feed.entries[:max_results]:
        # Source
        source = None
        if hasattr(entry, "source") and entry.source:
            source = getattr(entry.source, "title", None) or str(entry.source)

        # Published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6])
                published_at = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                published_at = getattr(entry, "published", None)

        # Description / summary
        description = getattr(entry, "summary", None) or getattr(entry, "description", None)

        articles.append(
            Article(
                title=entry.title,
                url=entry.link,
                source=source,
                published_at=published_at,
                description=description,
            )
        )

    return articles


@router.get("/feed", response_class=HTMLResponse)
async def news_page(
    request: Request,
    q: str = Query("technology", description="Search query"),
):
    articles = fetch_google_news(query=q, max_results=12)
    return templates.TemplateResponse(
        request=request,
        name="news.html",
        context={
            "articles": articles,
            "query": q,
        },
    )