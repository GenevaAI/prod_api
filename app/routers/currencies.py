# routers/currencies.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
import os

router = APIRouter(prefix="/currencies", tags=["Currencies"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Major currencies we want to highlight (Frankfurter supports many more)
MAJOR_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "CNY", "HKD", "SGD", "INR", "KRW", "BRL", "MXN", "ZAR",
    "SEK", "NOK", "DKK", "TRY", "RUB", "PLN", "THB", "IDR",
    "MYR", "PHP", "AED", "SAR", "ILS", "TWD"
]


@router.get("/api/rates")
async def get_rates(base: str = "USD"):
    """
    Returns latest exchange rates.
    Uses free Frankfurter API (no key required).
    Rates are official reference rates (updated multiple times per day).
    """
    base = base.upper()
    url = f"https://api.frankfurter.dev/v1/latest?base={base}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            # Filter to major currencies + keep the base
            rates = data.get("rates", {})
            filtered = {cur: rates[cur] for cur in MAJOR_CURRENCIES if cur in rates}
            # Always include the base itself
            filtered[base] = 1.0

            return JSONResponse({
                "base": data.get("base", base),
                "date": data.get("date"),
                "rates": dict(sorted(filtered.items())),
                "source": "Frankfurter (ECB reference rates)"
            })
        except Exception as e:
            return JSONResponse(
                {"error": str(e)},
                status_code=502
            )


@router.get("/", response_class=HTMLResponse)
async def currencies_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="currencies.html",
        context={},
    )