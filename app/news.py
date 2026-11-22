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

def fetch_g_news(query: str = "technology", max_results: int = 12) -> list[Article]:
    """
    Fetch news from GNews API (https://gnews.io).
    Free plan: 100 requests/day, max 10 articles per request.
    """
    api_key = os.getenv("GNEWS_API_KEY")
    if not api_key:
        print("Error: GNEWS_API_KEY environment variable is not set")
        return []

    # Free plan hard limit is 10 articles per request
    max_results = min(max_results, 10)

    url = "https://gnews.io/api/v4/search"
    params = {
        "q": query,
        "lang": "en",
        "country": "us",
        "max": max_results,
        "sortby": "publishedAt",  # or "relevance"
        "apikey": api_key,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        print(f"Error fetching news from GNews: {type(e).__name__}: {e}")
        return []

    articles = []
    for item in data.get("articles", []):
        # Published date
        published_at = None
        if item.get("publishedAt"):
            try:
                # GNews returns ISO format: 2026-11-22T14:30:00Z
                dt = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
                published_at = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                published_at = item.get("publishedAt")

        source = None
        if item.get("source") and isinstance(item["source"], dict):
            source = item["source"].get("name")

        articles.append(
            Article(
                title=item.get("title") or "No title",
                url=item.get("url") or "#",
                source=source,
                published_at=published_at,
                description=item.get("description") or item.get("content"),
            )
        )

    return articles

@router.get("/feed", response_class=HTMLResponse)
async def news_page(
    request: Request,
    q: str = Query("technology", description="Search query"),
):
    articles = fetch_g_news(query=q, max_results=12)
    return templates.TemplateResponse(
        request=request,
        name="news.html",
        context={
            "articles": articles,
            "query": q,
        },
    )