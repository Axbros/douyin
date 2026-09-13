from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    role: str
    login: str
    display_name: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    content: str = Field(min_length=1, max_length=500)
    weight: int = Field(default=1, ge=1, le=100)


class ScriptResponse(ScriptCreate):
    id: int
    status: str
    review_reason: str | None = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    room_id: str = Field(min_length=1, max_length=100)
    script_ids: list[int] = Field(min_length=1)
    target_account_count: int = Field(default=3, ge=1, le=100)
    min_interval_seconds: int = Field(default=20, ge=5, le=3600)
    max_interval_seconds: int = Field(default=50, ge=5, le=3600)


class TaskResponse(BaseModel):
    id: int
    room_id: str
    status: str
    target_account_count: int
    min_interval_seconds: int
    max_interval_seconds: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountResponse(BaseModel):
    id: int
    display_name: str
    account_uid: str | None = None
    status: str
    enabled: bool
    last_login_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    current_worker_id: int | None = None
    risk_code: str | None = None
    risk_message: str | None = None

    model_config = {"from_attributes": True}


class LoginSessionResponse(BaseModel):
    id: int
    account_id: int
    status: str
    expires_at: datetime
    qr_payload: str | None = None

    model_config = {"from_attributes": True}
