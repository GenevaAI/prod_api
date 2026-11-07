from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer
from jose import jwt
from .security import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from .config import settings
import secrets
import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from io import BytesIO
from dotenv import load_dotenv

from .database import Base, engine, get_db
from . import models
from .models import User

# Import routers
from .routers import profile, users, auth_routes
from .routers.auth_routes import get_current_user, verify_password, create_access_token, require_roles
from .weather import router as weather_router   # import the Weather router

# Create DB tables
models.Base.metadata.create_all(bind=engine)

# Create the FastAPI app FIRST
app = FastAPI(
    title="Ahmed's API coded in Python and HTML using Visual Studio Code, Containerization: Docker, Code hosting: GitHub, Cloud Hosting: Render, Database: PostgreSQL, Cloud Storage: Cloudflare R2, EMail delivery: Resend",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
)

@app.get("/")
def root():
    return {"status": "ok", "message": "API is running"}

#HealthCheck
@app.get("/health")
async def health():
    # optional: quick DB ping with timeout
    return {
        "status": "ok",
        "version": settings.VERSION
    }

# NOW include the routers
app.include_router(profile.router)
app.include_router(users.router)
app.include_router(auth_routes.router, prefix="/api")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/Swiss_Flag.png")

# Protected endpoint
@app.get("/secret")
def secret_area(current_user: User = Depends(get_current_user)):
    return {
        "message": "Top secret",
        "user": current_user.username,
        "role": current_user.role
    }

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/login-page", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
    )
    
#Login Successful

@app.get("/login-success", response_class=HTMLResponse)
def login_success(request: Request, username: str):
    return templates.TemplateResponse(
        request=request,                    # ← required
        name="login_success.html",
        context={"username": username}      # "request" no longer needed inside context
    )
    

# This serializer encrypts + signs the cookie so nobody can tamper with it.

serializer = URLSafeTimedSerializer(SECRET_KEY)

@app.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
    remember_me: str = Form(None),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password):
        return {"error": "Invalid credentials"}

    #Last Login
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    #Remember Me
    
    # Short session = 1 hour
    short_expiry = 3600

    # Long session = 30 days
    long_expiry = 60 * 60 * 24 * 30

    # Choose expiry based on checkbox
    expiry = long_expiry if remember_me else short_expiry


    # Create JWT with correct expiry
    token = create_access_token({"sub": username}, expires_delta=expiry)

    # Encrypt + sign the JWT
    encrypted_token = serializer.dumps(token)

    # Create CSRF token
    csrf_token = secrets.token_hex(32)

    response = RedirectResponse(url="/dashboard", status_code=302)

    # Set encrypted cookie
    # JWT is created normally
	#JWT is encrypted + signed
	# Cookie is HTTP only
	# Cookie expires in 1 hour
	# Browser cannot read or modify it

    is_production = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="session_token",
        value=encrypted_token,
        httponly=False,
        secure=is_production,       # True only in production
        samesite="lax",
        max_age=expiry              # 1 hour or 30 days
    )

    # Set CSRF cookie (NOT httponly)
    # Why CSRF cookie must NOT be httponly:
    # Because your HTML form must read it and send it back

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,             # must be readable by browser
        secure=is_production,       # True only in production
        samesite="lax",
        max_age=expiry
    )

    return response

# CSRF validation middleware
# What this middleware does
# - Every POST request must include a CSRF token
# - The token must match the cookie
# - If not → request is rejected with 403 Forbidden
# This is exactly how Django and Flask protect forms

@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    # Paths that do NOT need CSRF protection
    excluded_paths = {
        "/login",
        "/logout",
        # add other public POSTs here if needed
    }

    if request.method in ("POST", "PUT", "DELETE") and request.url.path not in excluded_paths:

        content_type = request.headers.get("content-type", "")

        # Skip CSRF check for JSON requests (Swagger, frontend fetch, etc.)
        if "application/json" in content_type:
            return await call_next(request)

        csrf_cookie = request.cookies.get("csrf_token")
        csrf_form = None

        if content_type.startswith("application/x-www-form-urlencoded") or \
           content_type.startswith("multipart/form-data"):

            # ---- Cache the body so the route can still read it ----
            body = await request.body()

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
            # -------------------------------------------------------

            form = await request.form()
            csrf_form = form.get("csrf_token")

            # Re-cache again after request.form() also consumed it
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive

        if not csrf_cookie or not csrf_form or csrf_cookie != csrf_form:
            raise HTTPException(status_code=403, detail="CSRF token invalid or missing")

    return await call_next(request)

#User Dashboard

#Dasboard with JWT and CSRF

# Protect the dashboard using the encrypted JWT cookie
@app.get("/dashboard", response_class=HTMLResponse)

# Protects the dashboard
def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user)   # any logged-in user
    # current_user: User = Depends(require_roles(["admin", "user"]))  # if you want to restrict
):
    csrf_token = request.cookies.get("csrf_token")

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "username": current_user.username,
            "role": current_user.role,          # now available in template
            "csrf_token": csrf_token,
        }
    )

#Logout with CSRF
@app.get("/logout")
@app.post("/logout")

def logout(request: Request):
    response = RedirectResponse(url="/login-page", status_code=302)
    response.delete_cookie("session_token")
    response.delete_cookie("csrf_token")
    return response

load_dotenv()

# -------------------------------------------------
# Cloudflare R2 client (re-use this if you already have one)
# -------------------------------------------------
s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    config=Config(signature_version="s3v4"),
    region_name="auto",          # R2 uses "auto"
)

BUCKET_NAME = os.getenv("R2_BUCKET")
FILE_KEY = "Python API.docx"     # exact object key in R2

@app.get("/download/python-api-docx", tags=["Public Downloads"])
async def download_python_api_docx():

    # Public endpoint – anyone can download the Word document without authentication.

    try:
        # Fetch the object from R2
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=FILE_KEY)
        file_content = response["Body"].read()

        # Prepare streaming response
        return StreamingResponse(
            BytesIO(file_content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="Python API.docx"'
            },
        )
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="File not found in R2")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

BUCKET_NAME2 = os.getenv("R2_BUCKET")
FILE_KEY2 = "Python API - Weather Page.docx"     # exact object key in R2

@app.get("/download/python-api-weather-page-docx", tags=["Public Downloads"])
async def download_python_api_weather_page_docx():

    # Public endpoint – anyone can download the Word document without authentication.

    try:
        # Fetch the object from R2
        response = s3_client.get_object(Bucket=BUCKET_NAME2, Key=FILE_KEY2)
        file_content = response["Body"].read()

        # Prepare streaming response
        return StreamingResponse(
            BytesIO(file_content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="Python API - Weather Page.docx"'
            },
        )
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="File not found in R2")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

BUCKET_NAME3 = os.getenv("R2_BUCKET")
FILE_KEY3 = "Kubernetes - A Detailed Guide.docx"

@app.get(
    "/download/kubernetes-a-detailed-guide-docx",
    response_class=HTMLResponse,
    tags=["Public Downloads"]
)
async def download_kubernetes_a_detailed_guide_docx():
    try:
        # Generate a short-lived pre-signed URL
        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME3,
                "Key": FILE_KEY3,
                "ResponseContentDisposition": 'attachment; filename="Kubernetes - A Detailed Guide.docx"',
                "ResponseContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
            ExpiresIn=3600,  # 1 hour
        )

        # Simple, clean download page
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download – Kubernetes Guide</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            color: #1e293b;
        }}
        .card {{
            background: white;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            text-align: center;
            max-width: 420px;
            width: 90%;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }}
        p {{
            color: #64748b;
            margin-bottom: 2rem;
            line-height: 1.5;
        }}
        .download-btn {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 0.875rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1.05rem;
            transition: background 0.2s;
        }}
        .download-btn:hover {{
            background: #1d4ed8;
        }}
        .note {{
            margin-top: 1.5rem;
            font-size: 0.875rem;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Kubernetes – A Detailed Guide</h1>
        <p>Click the button below to download the document<br>(approximately 10 MB).</p>
        
        <a href="{presigned_url}" class="download-btn" download>
            Download Document
        </a>

        <p class="note">The download will start immediately after you click.</p>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html_content)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="File not found in R2")
        raise HTTPException(status_code=500, detail=f"R2 error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating download page: {str(e)}")

# Include the weather router
app.include_router(weather_router)
