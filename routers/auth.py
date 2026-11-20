from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from models import User, InviteCode
from schemas import UserRegister, UserLogin, UserResponse, TokenResponse, UserUpdate
from services.security import hash_password, verify_password, create_access_token
from routers.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication & Profile"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user using a single-use Administrator Invite Code.
    Required: uname, email, password, invite_code.
    Optional: nrtel (phone), dzial (department).
    """
    # 0. Validate password confirmation if provided
    if payload.confirm_password is not None and payload.password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    # 1. Validate invite code (must exist and be unused)
    code_str = payload.invite_code.strip().upper()
    invite = db.query(InviteCode).filter(InviteCode.code == code_str).first()

    if not invite or invite.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already used single-use invite code."
        )

    # 2. Check if username or email already exists
    existing_user = db.query(User).filter(
        or_(User.uname == payload.uname.strip(), User.email == payload.email.lower().strip())
    ).first()

    if existing_user:
        if existing_user.uname.lower() == payload.uname.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{payload.uname}' is already taken."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email address '{payload.email}' is already registered."
            )

    # 3. Hash password and create user record
    hashed_pwd = hash_password(payload.password)
    is_admin = bool(getattr(invite, "is_admin_invite", False))

    new_user = User(
        uname=payload.uname.strip(),
        email=payload.email.lower().strip(),
        hashed_password=hashed_pwd,
        nrtel=payload.nrtel.strip() if payload.nrtel else None,
        dzial=payload.dzial.strip() if payload.dzial else None,
        is_admin=is_admin
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 4. Mark invite code as used
    invite.is_used = True
    invite.used_by_id = new_user.id
    invite.used_at = datetime.utcnow()
    db.commit()

    # 5. Issue JWT access token
    access_token = create_access_token(data={"sub": str(new_user.id), "uname": new_user.uname})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticates user via username OR email and password.
    Returns JWT access token and user profile.
    """
    identifier = payload.uname_or_email.strip()
    user = db.query(User).filter(
        or_(User.uname == identifier, User.email == identifier.lower())
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id), "uname": user.uname})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/token", response_model=dict, include_in_schema=False)
def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 compatibility endpoint for Swagger UI (/docs) Authorize dialog."""
    user = db.query(User).filter(
        or_(User.uname == form_data.username, User.email == form_data.username.lower())
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id), "uname": user.uname})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Returns profile data for the authenticated user."""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Updates profile attributes (phone number, department)."""
    if payload.nrtel is not None:
        current_user.nrtel = payload.nrtel.strip() if payload.nrtel else None
    if payload.dzial is not None:
        current_user.dzial = payload.dzial.strip() if payload.dzial else None

    db.commit()
    db.refresh(current_user)
    return current_user
