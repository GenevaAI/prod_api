import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import httpx

load_dotenv()

router = APIRouter(prefix="/paypal", tags=["paypal"])  # optional prefix

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_BASE_URL = os.getenv("PAYPAL_BASE_URL")


# ---------- Helper: get OAuth access token ----------
async def get_paypal_access_token() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_BASE_URL}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get PayPal token")
        return response.json()["access_token"]

# ---------- Pydantic models ----------
class PayerDetails(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    address_line_1: str
    address_line_2: str | None = None
    city: str
    state: str
    postal_code: str
    country_code: str = "US"   # ISO-2
    phone: str | None = None

class CreateOrderRequest(BaseModel):
    amount: str               # e.g. "29.99"
    currency: str = "USD"
    description: str = "Order payment"
    payer: PayerDetails

# ---------- Create Order ----------
@router.post("/create-paypal-order")
async def create_paypal_order(data: CreateOrderRequest):
    access_token = await get_paypal_access_token()
    base = os.getenv("FRONTEND_URL", "http://localhost:8000")
    
    order_payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": data.currency,
                    "value": data.amount,
                },
                "description": data.description,
                "shipping": {
                    "name": {
                        "full_name": f"{data.payer.first_name} {data.payer.last_name}"
                    },
                    "address": {
                        "address_line_1": data.payer.address_line_1,
                        "address_line_2": data.payer.address_line_2 or "",
                        "admin_area_2": data.payer.city,
                        "admin_area_1": data.payer.state,
                        "postal_code": data.payer.postal_code,
                        "country_code": data.payer.country_code,
                    },
                },
            }
        ],
        "payer": {
            "name": {
                "given_name": data.payer.first_name,
                "surname": data.payer.last_name,
            },
            "email_address": data.payer.email,
        },
        "application_context": {
            "return_url": f"{base}/payment-success",
            "cancel_url": f"{base}/payment-cancel",
            "shipping_preference": "SET_PROVIDED_ADDRESS",
 	        "user_action": "PAY_NOW",
        },

    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders",
            json=order_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )

    if response.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=response.text)

    order = response.json()
    return {
        "order_id": order["id"],
        "status": order["status"],
        "links": order.get("links", []),
    }

# ---------- Capture Order (after user approves on PayPal) ----------
@router.post("/capture-paypal-order/{order_id}")
async def capture_paypal_order(order_id: str):
    access_token = await get_paypal_access_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )

    if response.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=response.text)

    result = response.json()
    # Here you would update your database: mark order as paid, etc.
    return result