from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas import UserCreate, UserOut
from ..crud import create_user
from app.routers.auth_routes import get_current_user, require_roles
from app.models import User
import os

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.post("/users")
def create_new_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
):
    return create_user(db, user)

@router.get("/me")
def read_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role
    }

@router.get("/admin/users", response_model=list[UserOut])
def list_all_users(
    current_user: User = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db)
):
    return db.query(User).all()

@router.get("/admin/users-page", response_class=HTMLResponse)
def admin_users_page(
    request: Request,
    current_user: User = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db)
):
    users = db.query(User).all()
    return templates.TemplateResponse(request, "admin_users.html", {
        "request": request,
        "users": users,
        "current_user": current_user,
        "csrf_token": request.cookies.get("csrf_token")
    })

@router.post("/admin/users/{user_id}/toggle", response_class=HTMLResponse)
def toggle_user_active(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    return templates.TemplateResponse(
        request,
        "partials/user_row.html",
        {
            "request": request,
            "user": user,
            "current_user": current_user,
            "csrf_token": request.cookies.get("csrf_token"),
        }
    )

@router.delete("/admin/users/{user_id}", response_class=HTMLResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")

    db.delete(user)
    db.commit()

    # Return empty response → HTMX removes the row
    return HTMLResponse(content="")