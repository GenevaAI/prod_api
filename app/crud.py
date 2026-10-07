from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime, timedelta
import secrets
from . import models, schemas
from .models import User
from .security import hash_password, get_password_hash   # or just hash_password

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user):
    if get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if get_user_by_username(db, user.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    db_user = User(
        username=user.username,
        email=user.email,
        password=hash_password(user.password),
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user: models.User, user_update: schemas.UserUpdate):
    if user_update.email:
        existing = get_user_by_email(db, user_update.email)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = user_update.email

    if user_update.password:
        user.password = hash_password(user_update.password)   # fixed

    db.commit()
    db.refresh(user)
    return user

def create_reset_token(db: Session, email: str):
    user = get_user_by_email(db, email)
    if not user:
        return None

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
    db.commit()
    return token

def reset_password(db: Session, token: str, new_password: str):
    user = db.query(models.User).filter(
        models.User.reset_token == token,
        models.User.reset_token_expires > datetime.utcnow()
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.password = hash_password(new_password)   # fixed
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return user