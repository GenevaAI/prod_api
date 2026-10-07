from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..config import settings
from ..schemas import UserUpdate
from ..crud import update_user
from .auth_routes import get_current_user
from ..security import verify_password, hash_password
import uuid
import boto3
from botocore.client import Config
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(tags=["Profile"])

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)

# ---------- R2 helper ----------
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",          # R2 requires "auto"
    )

def upload_to_r2(file: UploadFile, object_key: str) -> str:
    """Upload a file to R2 and return the public URL."""
    client = get_r2_client()

    # Read the file content
    content = file.file.read()          # or await file.read() if you prefer

    client.put_object(
        Bucket=settings.R2_BUCKET,
        Key=object_key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
        # ACL is not needed for R2 public buckets / custom domains
    )

    # Return the public URL
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{object_key}"

# ---------- Profile routes ----------

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, current_user: User = Depends(get_current_user)):
    csrf_token = request.cookies.get("csrf_token")

    if csrf_token is None:
        import secrets
        csrf_token = secrets.token_hex(32)

    response = templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": current_user,
            "csrf_token": csrf_token
        }
    )

    is_production = settings.ENVIRONMENT == "production"

    if request.cookies.get("csrf_token") is None:
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=is_production,
            samesite="lax",
            max_age=3600
        )

    return response

@router.post("/profile")
async def update_profile(
    request: Request,
    email: str = Form(None),
    password: str = Form(None),
    profile_picture: UploadFile = File(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    update_data = UserUpdate(email=email, password=password if password else None)

    # ---------- Handle profile picture (now to R2) ----------
    if profile_picture and profile_picture.filename:
        ext = profile_picture.filename.split(".")[-1].lower()
        # Optional: validate allowed extensions
        allowed = {"jpg", "jpeg", "png", "webp", "gif"}
        if ext not in allowed:
            raise HTTPException(status_code=400, detail="Invalid image type")

        object_key = f"profile_pictures/{current_user.id}_{uuid.uuid4().hex}.{ext}"

        # Upload to R2 and get the public URL
        public_url = upload_to_r2(profile_picture, object_key)

        # Store the full public URL in the database
        current_user.profile_picture = public_url

    update_user(db, current_user, update_data)
    return RedirectResponse(url="/profile", status_code=302)

# ---------- Password Change ----------

@router.get("/password-change")
def password_change_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request,                          # ← Request first
        "password_change.html",
        {
            "user": current_user,
            "csrf_token": request.cookies.get("csrf_token"),
            "messages": []
        }
    )

@router.post("/password-change")
async def password_change(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Check that the two new passwords match
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,                          # ← Request first
            "password_change.html",
            {
                "user": current_user,
                "csrf_token": request.cookies.get("csrf_token"),
                "messages": [{"tags": "danger", "message": "New passwords do not match"}]
            },
            status_code=400
        )

    # 2. Verify the current password
    if not verify_password(current_password, current_user.password):
        return templates.TemplateResponse(
            request,                          # ← Request first
            "password_change.html",
            {
                "user": current_user,
                "csrf_token": request.cookies.get("csrf_token"),
                "messages": [{"tags": "danger", "message": "Current password is incorrect"}]
            },
            status_code=400
        )
        
    # 3. Update the password
    update_data = UserUpdate(password=new_password)
    update_user(db, current_user, update_data)

    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)