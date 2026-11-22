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
    """
    Fetch news from Google News RSS (no API key required).
    """
    encoded_query = quote_plus(query)
    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    )

    # Use httpx for better reliability + timeout
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"Error fetching news: {e}")
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