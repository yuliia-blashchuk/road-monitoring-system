"""Схеми API довідників і політик доступу."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AccessScope, Priority


class ProblemTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    icon: str
    color: str


class ProblemTypeCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$", examples=["open_manhole"])
    name: str = Field(min_length=2, max_length=100, examples=["Відкритий люк"])
    icon: str = Field(min_length=1, max_length=50, examples=["manhole"])
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$", examples=["#8D6E63"])


class RoutingRuleOut(BaseModel):
    id: int
    problem_type: str
    service: str
    copy_service: str | None
    initial_priority: Priority
    is_active: bool


class AccessPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    resource: str
    action: str
    scope: AccessScope
    log_access: bool
