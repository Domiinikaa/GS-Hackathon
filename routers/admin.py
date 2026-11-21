import secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Alert, InviteCode, Person, Rule, Source, Team, User
from routers.deps import get_current_admin_user
from schemas import (
    InviteCodeCreateRequest,
    InviteCodeCreateResponse,
    InviteCodeResponse,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
    UserResponse,
    UserRoleUpdate,
)

router = APIRouter(tags=["Admin & Teams"])


def _serialize_team(db: Session, team: Team) -> dict:
    user_count = db.query(func.count(User.id)).filter(User.dzial == team.name).scalar() or 0
    people_count = db.query(func.count(Person.id)).filter(Person.team == team.name).scalar() or 0
    rules_count = db.query(func.count(Rule.id)).filter(Rule.team == team.name).scalar() or 0
    sources_count = db.query(func.count(Source.id)).filter(Source.team == team.name).scalar() or 0
    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at,
        "user_count": user_count,
        "people_count": people_count,
        "rules_count": rules_count,
        "sources_count": sources_count,
    }


# --- PUBLIC TEAMS DIRECTORY ---

@router.get("/api/teams", response_model=List[TeamResponse])
@router.get("/api/departments", response_model=List[TeamResponse], include_in_schema=False)
def get_public_teams(db: Session = Depends(get_db)):
    """Retrieves all active teams (used by Registration, Alerts, People, Rules, Sources, and Admin)."""
    teams = db.query(Team).order_by(Team.name.asc()).all()
    return [_serialize_team(db, t) for t in teams]


# --- TEAM MANAGEMENT (ADMIN ONLY) ---

@router.post("/api/admin/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/admin/departments", response_model=TeamResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_team(
    payload: TeamCreate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Creates a new team. Administrator only."""
    team_name_clean = payload.name.strip()
    existing = db.query(Team).filter(
        func.lower(Team.name) == team_name_clean.lower()
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Team '{team_name_clean}' already exists."
        )

    new_team = Team(
        name=team_name_clean,
        description=payload.description.strip() if payload.description else None
    )
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return _serialize_team(db, new_team)


@router.delete("/api/admin/teams/{team_id}", status_code=status.HTTP_200_OK)
@router.delete("/api/admin/departments/{team_id}", status_code=status.HTTP_200_OK, include_in_schema=False)
def delete_team(
    team_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Deletes a team once no People or Rules reference it."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    people_count = db.query(func.count(Person.id)).filter(Person.team == team.name).scalar() or 0
    rules_count = db.query(func.count(Rule.id)).filter(Rule.team == team.name).scalar() or 0
    if people_count > 0 or rules_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete team '{team.name}' while it still has {people_count} people "
                f"and {rules_count} rules. Reassign or remove them first."
            ),
        )

    # Unlink users and shared sources referencing this team name
    db.query(User).filter(User.dzial == team.name).update({User.dzial: None})
    db.query(Source).filter(Source.team == team.name).update({Source.team: "All"})

    db.delete(team)
    db.commit()
    return {"message": f"Team '{team.name}' was successfully deleted."}


@router.put("/api/admin/teams/{team_id}", response_model=TeamResponse)
@router.put("/api/admin/departments/{team_id}", response_model=TeamResponse, include_in_schema=False)
def update_team(
    team_id: int,
    payload: TeamUpdate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Updates team name or description and cascades rename across users, people, rules, sources, and alerts."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    old_name = team.name
    if payload.name:
        new_name = payload.name.strip()
        conflict = db.query(Team).filter(
            func.lower(Team.name) == new_name.lower(),
            Team.id != team_id
        ).first()
        if conflict:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Team '{new_name}' already exists.")
        team.name = new_name

        # Cascade name update across users and all alerting entities
        db.query(User).filter(User.dzial == old_name).update({User.dzial: new_name})
        db.query(Person).filter(Person.team == old_name).update({Person.team: new_name})
        db.query(Rule).filter(Rule.team == old_name).update({Rule.team: new_name})
        db.query(Source).filter(Source.team == old_name).update({Source.team: new_name})
        db.query(Alert).filter(Alert.team == old_name).update({Alert.team: new_name})

    if payload.description is not None:
        team.description = payload.description.strip() if payload.description else None

    db.commit()
    db.refresh(team)
    return _serialize_team(db, team)


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
    payload: Optional[InviteCodeCreateRequest] = None,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Generates a new single-use registration invite code for a team member or administrator."""
    is_admin = payload.is_admin if payload else False
    code_str = generate_unique_code(db)
    invite = InviteCode(
        code=code_str,
        is_used=False,
        is_admin_invite=is_admin,
        created_by_id=admin.id
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    role_desc = "Administrator" if is_admin else "Standard User"
    return {
        "code": invite.code,
        "is_admin_invite": invite.is_admin_invite,
        "message": f"Single-use invite code for {role_desc} generated successfully."
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
            "is_admin_invite": getattr(inv, "is_admin_invite", False),
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
    """Returns the roster of registered users and their teams."""
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/api/admin/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Promotes or demotes a user to/from Administrator role. Administrator only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.id == admin.id and not payload.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot demote their own account to prevent lockout."
        )

    user.is_admin = payload.is_admin
    db.commit()
    db.refresh(user)
    return user
