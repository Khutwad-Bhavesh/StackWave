from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, Token, UserResponse, UserCreate
from app.security import verify_password, hash_password, create_access_token, get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])

@router.post("/login", response_model=Token)
def login(creds: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == creds.username).first()
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "id": user.id}
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        username=user.username
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(["admin"]))):
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    user = User(
        username=user_in.username,
        password_hash=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
