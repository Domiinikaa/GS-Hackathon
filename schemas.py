from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, EmailStr, Field


# --- Team Schemas ---

class TeamBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="Payments")
    description: Optional[str] = Field(None, max_length=255, example="Payments API reliability and failover")


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=255)


class TeamResponse(TeamBase):
    id: int
    created_at: datetime
    user_count: int = 0
    people_count: int = 0
    rules_count: int = 0
    sources_count: int = 0

    class Config:
        from_attributes = True


# Backwards-compatible aliases
DepartmentBase = TeamBase
DepartmentCreate = TeamCreate
DepartmentUpdate = TeamUpdate
DepartmentResponse = TeamResponse


# --- User & Auth Schemas ---

class UserRegister(BaseModel):
    uname: str = Field(..., min_length=3, max_length=50, example="j_smith")
    email: EmailStr = Field(..., example="jsmith@goldmansachs.com")
    password: str = Field(..., min_length=6, max_length=128, example="SuperSecret123!")
    confirm_password: Optional[str] = Field(None, min_length=6, max_length=128, example="SuperSecret123!")
    invite_code: str = Field(..., min_length=4, max_length=64, example="GS-7F8A-9B2C")
    nrtel: Optional[str] = Field(None, example="+1 (212) 555-0199")
    team: Optional[str] = Field(None, example="Payments")
    dzial: Optional[str] = Field(None, example="Payments")


class UserLogin(BaseModel):
    uname_or_email: str = Field(..., example="j_smith")
    password: str = Field(..., example="SuperSecret123!")


class UserUpdate(BaseModel):
    nrtel: Optional[str] = None
    team: Optional[str] = None
    dzial: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    uname: str
    email: str
    nrtel: Optional[str] = None
    team: Optional[str] = None
    dzial: Optional[str] = None
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserRoleUpdate(BaseModel):
    is_admin: bool = Field(..., description="Set user administrator status")


# --- Invite Code Schemas ---

InviteRole = Literal["member", "lead"]


class InviteCodeCreateRequest(BaseModel):
    role: Optional[InviteRole] = Field(None, description="Role assigned to the new user ('member' or 'lead')")
    is_admin: Optional[bool] = Field(None, description="Legacy flag: True sets role='lead'")
    team: Optional[str] = Field(None, description="Optional team/department assigned to the new user")
    dzial: Optional[str] = Field(None, description="Alias for team")

    def resolved_role(self) -> InviteRole:
        if self.role is not None:
            return self.role
        if self.is_admin:
            return "lead"
        return "member"


class InviteCodeResponse(BaseModel):
    id: int
    code: str
    is_used: bool
    is_admin_invite: bool = False
    role: InviteRole = "member"
    team: Optional[str] = None
    created_at: datetime
    used_at: Optional[datetime] = None
    created_by_uname: Optional[str] = None
    used_by_uname: Optional[str] = None

    class Config:
        from_attributes = True


class InviteCodeCreateResponse(BaseModel):
    code: str
    is_admin_invite: bool = False
    role: InviteRole = "member"
    team: Optional[str] = None
    message: str


# --- Panel Item Schemas ---

class ItemBase(BaseModel):
    title: str = Field(..., example="Goldman Sachs Group (GS)")
    category: Optional[str] = Field("Equity", example="Equity")
    value: Optional[float] = Field(0.0, example=475.50)
    description: Optional[str] = Field(None, example="Core portfolio holding")


class ItemCreate(ItemBase):
    pass


class ItemResponse(ItemBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
