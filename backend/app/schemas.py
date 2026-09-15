from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    login: str
    password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    role: str
    login: str
    display_name: str
    status: str
    expires_at: datetime | None = None
    extra_douyin_account_quota: int = 0
    subscription_plan_id: int | None = None

    model_config = {"from_attributes": True}


class AdminCustomerCreate(BaseModel):
    login: str = Field(min_length=3, max_length=190)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class AdminCustomerUpdate(BaseModel):
    login: str | None = Field(default=None, min_length=3, max_length=190)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    extra_douyin_account_quota: int | None = Field(default=None, ge=0, le=1000)


class AdminCustomerStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class AdminCustomerPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminCustomerResponse(BaseModel):
    id: int
    login: str
    display_name: str
    status: str
    last_login_at: datetime | None = None
    expires_at: datetime | None = None
    extra_douyin_account_quota: int = 0
    subscription_plan_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    content: str = Field(min_length=1, max_length=500)
    weight: int = Field(default=1, ge=1, le=100)


class ScriptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    content: str | None = Field(default=None, min_length=1, max_length=500)
    weight: int | None = Field(default=None, ge=1, le=100)


class ScriptBulkCreate(BaseModel):
    contents: list[str] = Field(min_length=1, max_length=1000)


class ScriptResponse(ScriptCreate):
    id: int
    status: str
    review_reason: str | None = None

    model_config = {"from_attributes": True}


class AdminScriptResponse(BaseModel):
    id: int
    customer_id: int
    customer_login: str
    customer_name: str
    title: str
    content: str
    weight: int
    status: str
    review_reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ScriptBatchReviewRequest(BaseModel):
    script_ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_review(self):
        if len(set(self.script_ids)) != len(self.script_ids):
            raise ValueError("话术不能重复选择")
        if self.action == "reject" and not (self.reason or "").strip():
            raise ValueError("批量拒绝时必须填写原因")
        return self


class TaskCreate(BaseModel):
    live_share_text: str = Field(min_length=1, max_length=2000)
    script_ids: list[int] = Field(min_length=1)
    min_interval_seconds: int = Field(default=20, ge=5, le=3600)
    max_interval_seconds: int = Field(default=50, ge=5, le=3600)
    account_source: str = Field(default="platform", pattern="^(platform|customer)$")
    account_ids: list[int] = Field(default_factory=list, max_length=100)
    script_order_mode: str = Field(default="random", pattern="^(random|sequential)$")


class TaskResponse(BaseModel):
    id: int
    customer_id: int
    live_url: str
    status: str
    target_account_count: int
    account_source: str
    script_order_mode: str
    min_interval_seconds: int
    max_interval_seconds: int
    started_at: datetime | None = None
    paused_at: datetime | None = None
    stopped_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentLogResponse(BaseModel):
    id: int
    task_id: int
    account_id: int
    live_url: str
    content: str
    result: str
    failure_code: str | None = None
    sensitive_word: str | None = None
    sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskAccountResponse(BaseModel):
    id: int
    task_id: int
    account_id: int
    status: str
    assigned_at: datetime
    removed_at: datetime | None = None
    last_error: str | None = None

    model_config = {"from_attributes": True}


class SensitiveWordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=255)
    match_type: str = Field(default="contains", pattern="^(contains|exact|regex)$")


class SensitiveWordUpdate(BaseModel):
    word: str | None = Field(default=None, min_length=1, max_length=255)
    match_type: str | None = Field(default=None, pattern="^(contains|exact|regex)$")


class SensitiveWordResponse(SensitiveWordCreate):
    id: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountResponse(BaseModel):
    id: int
    display_name: str
    account_uid: str | None = None
    ownership_type: str = "platform"
    owner_customer_id: int | None = None
    status: str
    enabled: bool
    last_login_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    current_worker_id: int | None = None
    risk_code: str | None = None
    risk_message: str | None = None
    last_error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DouyinAccountUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class AccountLogResponse(BaseModel):
    id: int
    account_id: int
    worker_id: int | None = None
    event_type: str
    detail: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginVerificationOption(BaseModel):
    id: str
    label: str
    description: str | None = None


class LoginSessionResponse(BaseModel):
    id: int
    account_id: int
    status: str
    expires_at: datetime
    qr_payload: str | None = None
    failure_reason: str | None = None
    verification_options: list[LoginVerificationOption] = Field(default_factory=list)
    selected_verification_method: LoginVerificationOption | None = None

    model_config = {"from_attributes": True}


class LoginVerificationCodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class LoginPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=50)


class LoginVerificationMethodRequest(BaseModel):
    method_id: str = Field(pattern=r"^method-\d+$")


class ServiceStatus(BaseModel):
    name: str
    status: str
    latency_ms: float | None = None
    last_heartbeat_at: datetime | None = None


class ServerStatusResponse(BaseModel):
    collected_at: datetime
    hostname: str
    platform: str
    python_version: str
    uptime_seconds: int
    cpu_percent: float
    cpu_count: int
    load_average: list[float]
    memory_total: int
    memory_used: int
    memory_percent: float
    disk_total: int
    disk_used: int
    disk_percent: float
    services: list[ServiceStatus]


class PlatformSettingsResponse(BaseModel):
    comment_min_interval_seconds: int
    comment_max_interval_seconds: int
    script_bulk_import_limit: int
    qr_expire_minutes: int
    worker_heartbeat_timeout_seconds: int
    account_reclaim_seconds: int
    extra_account_quota_price_cents: int


class PlatformSettingsUpdate(PlatformSettingsResponse):
    comment_min_interval_seconds: int = Field(ge=5, le=3600)
    comment_max_interval_seconds: int = Field(ge=5, le=3600)
    script_bulk_import_limit: int = Field(ge=1, le=1000)
    qr_expire_minutes: int = Field(ge=1, le=30)
    worker_heartbeat_timeout_seconds: int = Field(ge=10, le=300)
    account_reclaim_seconds: int = Field(ge=30, le=1800)
    extra_account_quota_price_cents: int = Field(ge=0, le=100000000)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.comment_max_interval_seconds < self.comment_min_interval_seconds:
            raise ValueError("评论最大间隔不能小于最小间隔")
        if self.account_reclaim_seconds < self.worker_heartbeat_timeout_seconds:
            raise ValueError("账号回收时间不能小于 Worker 心跳超时")
        return self


class SubscriptionPlanResponse(BaseModel):
    id: int
    code: str
    name: str
    tier_level: int
    duration_days: int
    base_douyin_account_quota: int
    platform_account_count: int
    max_active_tasks: int
    max_scripts_per_task: int
    price_cents: int | None = None
    features: list | None = None
    enabled: bool

    model_config = {"from_attributes": True}


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    base_douyin_account_quota: int | None = Field(default=None, ge=0, le=1000)
    platform_account_count: int | None = Field(default=None, ge=1, le=100)
    max_active_tasks: int | None = Field(default=None, ge=1, le=20)
    max_scripts_per_task: int | None = Field(default=None, ge=1, le=500)
    price_cents: int | None = Field(default=None, ge=0, le=100000000)
    enabled: bool | None = None


class CustomerSubscriptionResponse(BaseModel):
    plan: SubscriptionPlanResponse
    expires_at: datetime | None = None
    extra_account_quota: int
    total_account_quota: int


class PurchaseOrderCreate(BaseModel):
    order_type: str = Field(pattern="^(plan_upgrade|account_quota)$")
    plan_id: int | None = None
    quota_quantity: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_order(self):
        if self.order_type == "plan_upgrade" and self.plan_id is None:
            raise ValueError("升级套餐必须选择套餐")
        if self.order_type == "account_quota" and self.quota_quantity is None:
            raise ValueError("购买账号额度必须填写数量")
        return self


class PurchaseOrderResponse(BaseModel):
    id: int
    order_no: str
    customer_id: int
    order_type: str
    plan_id: int | None = None
    quota_quantity: int | None = None
    amount_cents: int | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
