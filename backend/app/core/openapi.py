"""Опис відповідей з помилками для документації API (/docs, KAN-113).

API повертає помилки в трьох форматах:

- ``{"detail": "текст"}`` - 401, 403, 404, 409, 429;
- ``{"detail": [{"loc": ["body", "поле"], "msg": "текст"}]}`` - 422, помилка в полі запиту;
- ``{"detail": {"message": "текст", "missing_consents": [...]}}`` - 403, бракує згоди водія.

Тут зібрано типові описи цих відповідей, щоб роутери підключали їх одним рядком:
``APIRouter(..., responses=errors(401, 403))``. Опис конкретного маршруту
(``responses=`` у декораторі) має пріоритет над описом роутера.

``install(app)`` доповнює схему: кожна відповідь 4xx без опису тіла отримує схему
ErrorOut (422 - ValidationErrorOut), щоб у /docs було видно, що саме прийде у відповіді.
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field


class ErrorOut(BaseModel):
    """Помилка з одним повідомленням для користувача."""

    detail: str = Field(examples=["Недостатньо прав для цієї дії"])


class ValidationIssue(BaseModel):
    loc: list[str | int] = Field(examples=[["body", "latitude"]])
    msg: str = Field(examples=["Ділянка не обслуговується"])


class ValidationErrorOut(BaseModel):
    """422: помилка в полях запиту; loc вказує поле, яке треба підсвітити."""

    detail: list[ValidationIssue]


class ConsentMissingDetail(BaseModel):
    message: str = Field(examples=["Для цієї дії потрібна згода водія"])
    missing_consents: list[str] = Field(examples=[["contact"]])


class ConsentMissingOut(BaseModel):
    """403: водій не надав потрібну згоду (KAN-65)."""

    detail: ConsentMissingDetail


DESCRIPTIONS: dict[int, str] = {
    401: "Потрібен вхід: токена немає, він недійсний або прострочений",
    403: "Недостатньо прав для цієї дії (відмова записується в журнал аудиту як ACCESS_DENIED)",
    404: "Запис не знайдено",
    409: "Дію не можна виконати в поточному стані запису",
    429: "Забагато запитів, спробуйте пізніше",
}


def errors(*codes: int, **descriptions: str) -> dict[int | str, dict[str, Any]]:
    """Описи помилок для ``responses=``.

    Свій текст для коду передається як ``e404="Заявку не знайдено"``.
    """
    return {
        code: {
            "model": ErrorOut,
            "description": descriptions.get(f"e{code}", DESCRIPTIONS[code]),
        }
        for code in codes
    }


def consent_or_access_denied(description: str) -> dict[str, Any]:
    """403, коли причиною може бути і роль, і відсутня згода водія."""
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorOut"},
                        {"$ref": "#/components/schemas/ConsentMissingOut"},
                    ]
                }
            }
        },
    }


ERROR_MODELS = (ErrorOut, ValidationErrorOut, ConsentMissingOut)


def _fill_error_schemas(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in ERROR_MODELS:
        model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(model_schema.pop("$defs", {}))
        components.setdefault(model.__name__, model_schema)

    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            for code, response in operation.get("responses", {}).items():
                if not code.startswith("4") or "content" in response:
                    continue
                name = "ValidationErrorOut" if code == "422" else "ErrorOut"
                response["content"] = {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}
                }


def install(app: FastAPI) -> None:
    """Підміняє app.openapi так, щоб схема містила описи тіл помилок."""
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = build()
            _fill_error_schemas(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
