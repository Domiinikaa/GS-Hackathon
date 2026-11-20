import secrets
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import User, InviteCode, Department
from schemas import (
    InviteCodeResponse,
    InviteCodeCreateResponse,
    UserResponse,
    DepartmentResponse,
    DepartmentCreate,
    DepartmentUpdate
)
from routers.deps import get_current_admin_user

router = APIRouter(tags=["Admin & Departments"])


# --- PUBLIC DEPARTMENTS DIRECTORY ---

@router.get("/api/departments", response_model=List[DepartmentResponse])
def get_public_departments(db: Session = Depends(get_db)):
    """Retrieves all active company departments (available for registration and profile forms)."""
    departments = db.query(Department).order_by(Department.name.asc()).all()
    results = []
    for d in departments:
        user_count = db.query(func.count(User.id)).filter(User.dzial == d.name).scalar() or 0
        results.append({
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "created_at": d.created_at,
            "user_count": user_count
        })
    return results


# --- DEPARTMENT MANAGEMENT (ADMIN ONLY) ---

@router.post("/api/admin/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Creates a new company department. Administrator only."""
    dept_name = payload.name.strip()
    existing = db.query(Department).filter(
        func.lower(Department.name) == dept_name.lower()
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Department '{dept_name}' already exists."
        )

    new_dept = Department(
        name=dept_name,
        description=payload.description.strip() if payload.description else None
    )
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)

    return {
        "id": new_dept.id,
        "name": new_dept.name,
        "description": new_dept.description,
        "created_at": new_dept.created_at,
        "user_count": 0
    }


@router.delete("/api/admin/departments/{dept_id}", status_code=status.HTTP_200_OK)
def delete_department(
    dept_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Deletes a department. Employees in this department are preserved (department reset to null)."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")

    # Reset users referencing this department name
    db.query(User).filter(User.dzial == dept.name).update({User.dzial: None})

    db.delete(dept)
    db.commit()
    return {"message": f"Department '{dept.name}' was successfully deleted."}


@router.put("/api/admin/departments/{dept_id}", response_model=DepartmentResponse)
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Updates department name or description."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")

    old_name = dept.name
    if payload.name:
        new_name = payload.name.strip()
        conflict = db.query(Department).filter(
            func.lower(Department.name) == new_name.lower(),
            Department.id != dept_id
        ).first()
        if conflict:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department '{new_name}' already exists.")
        dept.name = new_name

        # Cascade name update to users
        db.query(User).filter(User.dzial == old_name).update({User.dzial: new_name})

    if payload.description is not None:
        dept.description = payload.description.strip() if payload.description else None

    db.commit()
    db.refresh(dept)

    user_count = db.query(func.count(User.id)).filter(User.dzial == dept.name).scalar() or 0
    return {
        "id": dept.id,
        "name": dept.name,
        "description": dept.description,
        "created_at": dept.created_at,
        "user_count": user_count
    }


# --- INVITE CODES & USER ROSTER (ADMIN ONLY) ---

def generate_unique_code(db: Session) -> str:
    """Generates a secure, human-readable code e.g. GS-9B2F-4A7C."""
    while True:
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        code = f"GS-{part1}-{part2}"
        if not db.query(InviteCode).filter(InviteCode.code == code).first():
            return code


@router.post("/api/admin/invites", response_model=InviteCodeCreateResponse, status_code=status.HTTP_201_CREATED)
def create_invite_code(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Generates a new single-use registration invite code for a team member."""
    code_str = generate_unique_code(db)
    invite = InviteCode(
        code=code_str,
        is_used=False,
        created_by_id=admin.id
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return {
        "code": invite.code,
        "message": "Single-use invite code generated successfully."
    }


@router.get("/api/admin/invites", response_model=List[InviteCodeResponse])
def list_invite_codes(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Returns all invite codes with their status (active vs used) and timestamps."""
    invites = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    results = []
    for inv in invites:
        results.append({
            "id": inv.id,
            "code": inv.code,
            "is_used": inv.is_used,
            "created_at": inv.created_at,
            "used_at": inv.used_at,
            "created_by_uname": inv.created_by.uname if inv.created_by else None,
            "used_by_uname": inv.used_by.uname if inv.used_by else None,
        })
    return results


@router.get("/api/admin/users", response_model=List[UserResponse])
def list_company_users(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Returns the roster of registered users and their departments."""
    return db.query(User).order_by(User.created_at.desc()).all()
