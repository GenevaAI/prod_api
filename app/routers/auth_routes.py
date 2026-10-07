from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import List
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..database import get_db
from ..crud import create_reset_token, reset_password
from ..schemas import PasswordResetRequest, PasswordResetConfirm
from ..models import User
from ..config import settings
from ..SMTP import send_password_reset_email 
from ..security import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    hash_password, verify_password
)

# Frontend URL
import os
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:8000")  # set real URL in production

# ---------- Robust template setup (fixes the unhashable dict error) ----------
BASE_DIR = Path(__file__).resolve().parent.parent          # project root
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# --------------------------------------------------------------------------

router = APIRouter()

# JWT creation
def create_access_token(data: dict, expires_delta: int = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -------------------------------------------------
# Cookie-based authentication
# -------------------------------------------------
serializer = URLSafeTimedSerializer(SECRET_KEY)

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    encrypted_token = request.cookies.get("session_token")
    if not encrypted_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = serializer.loads(encrypted_token, max_age=60 * 60 * 24 * 30)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, BadSignature, SignatureExpired, Exception):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# -------------------------------------------------
# RBAC helper
# -------------------------------------------------
def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker

# -------------------------------------------------
# Password Reset Endpoints
# -------------------------------------------------

import secrets
from fastapi.responses import HTMLResponse

@router.get("/password-reset", response_class=HTMLResponse)
def password_reset_page(request: Request):
    csrf_token = secrets.token_hex(32)

    response = templates.TemplateResponse(
        request=request,                    # ← required keyword
        name="password_reset.html",
        context={
            "csrf_token": csrf_token,
        }
    )

    is_production = settings.ENVIRONMENT == "production"
    
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=is_production,  #True only in production
        samesite="lax",
        max_age=3600
    )
    return response

@router.post("/password-reset")
def request_password_reset(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    token = create_reset_token(db, email)
    
    if token:

        # The email function already builds the correct link using settings.FRONTEND_URL
        # reset_link = f"{FRONTEND_URL}/api/password-reset/confirm?token={token}"

        # Keep the debug print if you still want it in development
        # print("=== PASSWORD RESET LINK ===")
        # print(reset_link)
        # print("===========================")

        # Actually send the email
        try:
            send_password_reset_email(email, token)
            # return success response to the client
        except Exception as e:
            # log the error, return 500 or appropriate error
            raise

    # Re-render the same page with a success message (better than JSON)
    return templates.TemplateResponse(
        request=request,
        name="password_reset.html",
        context={
            "message": "If the email exists, a reset link has been sent.",
            "message_type": "success",
            "email": email,
            "csrf_token": request.cookies.get("csrf_token"),
        }
    )
       
@router.get("/password-reset/confirm", response_class=HTMLResponse)
def password_reset_confirm_page(request: Request, token: str):
    import secrets
    csrf_token = secrets.token_hex(32)

    response = templates.TemplateResponse(
        request=request,
        name="password_reset_confirm.html",
        context={
            "token": token,
            "csrf_token": csrf_token,
        }
    )

    is_production = settings.ENVIRONMENT == "production"
    
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=is_production,  #True only in production 
        samesite="lax",
        max_age=3600
    )
    
    return response

@router.post("/password-reset/confirm")
def password_reset_confirm(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),          # ← required
    db: Session = Depends(get_db)
):
    # 1. Passwords must match
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="password_reset_confirm.html",
            context={
                "token": token,
                "csrf_token": request.cookies.get("csrf_token"),
                "messages": [{"tags": "danger", "message": "Passwords do not match"}],
            },
            status_code=400
        )

    # 2. Optional but recommended minimum length
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="password_reset_confirm.html",
            context={
                "token": token,
                "csrf_token": request.cookies.get("csrf_token"),
                "messages": [{"tags": "danger", "message": "Password must be at least 8 characters"}],
            },
            status_code=400
        )

    # 3. Everything OK → reset the password
    reset_password(db, token, new_password)
    return RedirectResponse(url="/login-page", status_code=302)