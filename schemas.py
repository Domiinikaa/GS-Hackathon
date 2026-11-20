from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# --- Department Schemas ---

class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, example="Engineering")
    description: Optional[str] = Field(None, max_length=255, example="Software engineering and infrastructure")


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=255)


class DepartmentResponse(DepartmentBase):
    id: int
    created_at: datetime
    user_count: Optional[int] = 0

    class Config:
        from_attributes = True


# --- User & Auth Schemas ---

class UserRegister(BaseModel):
    uname: str = Field(..., min_length=3, max_length=50, example="j_smith")
    email: EmailStr = Field(..., example="jsmith@goldmansachs.com")
    password: str = Field(..., min_length=6, max_length=128, example="SuperSecret123!")
    invite_code: str = Field(..., min_length=4, max_length=64, example="GS-7F8A-9B2C")
    nrtel: Optional[str] = Field(None, example="+1 (212) 555-0199")
    dzial: Optional[str] = Field(None, example="Finance")


class UserLogin(BaseModel):
    uname_or_email: str = Field(..., example="j_smith")
    password: str = Field(..., example="SuperSecret123!")


class UserUpdate(BaseModel):
    nrtel: Optional[str] = None
    dzial: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    uname: str
    email: str
    nrtel: Optional[str] = None
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

class InviteCodeCreateRequest(BaseModel):
    is_admin: bool = Field(False, description="Whether registering with this code grants Administrator privileges")


class InviteCodeResponse(BaseModel):
    id: int
    code: str
    is_used: bool
    is_admin_invite: bool = False
    created_at: datetime
    used_at: Optional[datetime] = None
    created_by_uname: Optional[str] = None
    used_by_uname: Optional[str] = None

    class Config:
        from_attributes = True


class InviteCodeCreateResponse(BaseModel):
    code: str
    is_admin_invite: bool = False
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
