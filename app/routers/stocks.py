# routers/stocks.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import os

router = APIRouter(prefix="/stocks", tags=["Stocks"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Major world stock exchange indexes (Yahoo Finance symbols)
MAJOR_INDEXES = {
    "^GSPC": "S&P 500 (USA)",
    "^DJI": "Dow Jones (USA)",
    "^IXIC": "NASDAQ Composite (USA)",
    "^RUT": "Russell 2000 (USA)",
    "^FTSE": "FTSE 100 (UK)",
    "^GDAXI": "DAX (Germany)",
    "^FCHI": "CAC 40 (France)",
    "^STOXX50E": "Euro Stoxx 50",
    "^N225": "Nikkei 225 (Japan)",
    "^HSI": "Hang Seng (Hong Kong)",
    "000001.SS": "Shanghai Composite (China)",
    "^BSESN": "BSE Sensex (India)",
    "^AXJO": "ASX 200 (Australia)",
    "^BVSP": "Bovespa (Brazil)",
    "^MXX": "IPC Mexico",
    "^KS11": "KOSPI (South Korea)",
    "^TWII": "TSEC Weighted (Taiwan)",
    "^STI": "STI (Singapore)",
    "^BFX": "BEL 20 (Belgium)",
    "^AEX": "AEX (Netherlands)",
    "^IBEX": "IBEX 35 (Spain)",
    "^SSMI": "SMI (Switzerland)",
    "^OMX": "OMX Stockholm 30",
}


def fetch_index(symbol: str, name: str):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        # Prefer regularMarketPrice, fall back to previousClose
        price = info.get("regularMarketPrice") or info.get("previousClose")
        prev_close = info.get("previousClose") or price
        change = None
        change_pct = None
        if price is not None and prev_close is not None and prev_close != 0:
            change = price - prev_close
            change_pct = (change / prev_close) * 100

        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2) if price is not None else None,
            "previous_close": round(prev_close, 2) if prev_close is not None else None,
            "change": round(change, 2) if change is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "currency": info.get("currency", "USD"),
            "market_state": info.get("marketState", "UNKNOWN"),
        }
    except Exception as e:
        return {
            "symbol": symbol,
            "name": name,
            "price": None,
            "error": str(e),
        }


@router.get("/api/indexes")
async def get_indexes():
    """JSON endpoint – returns all major indexes"""
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(fetch_index, symbol, name)
            for symbol, name in MAJOR_INDEXES.items()
        ]
        for future in futures:
            results.append(future.result())
    return JSONResponse(content={"indexes": results})


@router.get("/", response_class=HTMLResponse)
async def stocks_page(request: Request):
    """HTML page that auto-refreshes"""
    return templates.TemplateResponse(
        request=request,
        name="stocks.html",
        context={},
    )