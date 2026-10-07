from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer
from jose import jwt
from .security import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from .config import settings
import secrets
import os

from .database import Base, engine, get_db
from . import models
from .models import User

# Import routers
from .routers import profile, users, auth_routes
from .routers.auth_routes import get_current_user, verify_password, create_access_token, require_roles

# Create DB tables
models.Base.metadata.create_all(bind=engine)

# Create the FastAPI app FIRST
app = FastAPI(
    title="My API Backend",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
)

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