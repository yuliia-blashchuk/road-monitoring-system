"""HTTP-ендпоінти довідників: публічний список типів проблем і адмін-розділ.

Права перевіряє AccessControl (require): reference.manage - лише адміністратор,
access_policy.view - адміністратор і Data Governance (табл. 14).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access_control import AccessContext, require
from app.modules.admin import repository as repo
from app.modules.admin.models import ProblemType
from app.modules.admin.schemas import (
    AccessPolicyOut,
    ProblemTypeCreate,
    ProblemTypeOut,
    RoutingRuleOut,
)
from app.modules.users.dependencies import SessionDep

# Публічні довідники - потрібні карті й формі заявки без входу.
public_router = APIRouter(tags=["reference"])

router = APIRouter(prefix="/admin", tags=["admin"])

ManageReference = Annotated[AccessContext, Depends(require("reference", "manage"))]
ViewPolicies = Annotated[AccessContext, Depends(require("access_policy", "view"))]


@public_router.get(
    "/problem-types", response_model=list[ProblemTypeOut], summary="Типи проблем (публічно)"
)
async def list_problem_types(session: SessionDep) -> list[ProblemType]:
    return await repo.active_problem_types(session)


@router.post(
    "/problem-types",
    response_model=ProblemTypeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Додати тип проблеми (адміністратор)",
)
async def create_problem_type(
    data: ProblemTypeCreate, session: SessionDep, _: ManageReference
) -> ProblemType:
    if await repo.problem_type_by_code(session, data.code):
        raise HTTPException(status.HTTP_409_CONFLICT, "Тип з таким кодом уже існує")
    item = await repo.add_problem_type(session, ProblemType(**data.model_dump()))
    await session.commit()
    return item


@router.get(
    "/routing-rules",
    response_model=list[RoutingRuleOut],
    summary="Правила маршрутизації з пріоритетами (адміністратор)",
)
async def list_routing_rules(session: SessionDep, _: ManageReference) -> list:
    return await repo.routing_rules(session)


@router.get(
    "/access-policies",
    response_model=list[AccessPolicyOut],
    summary="Політики доступу RBAC (адміністратор, Data Governance)",
)
async def list_access_policies(session: SessionDep, _: ViewPolicies) -> list:
    return await repo.access_policies(session)
