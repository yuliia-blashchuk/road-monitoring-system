"""Схеми API модуля users: що приймає реєстрація і що повертають вхід і профіль."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import REQUIRED_CONSENTS, ConsentType


class RegisterRequest(BaseModel):
    """Реєстрація водія. Працівників служб і підрядників створює адміністратор."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Щонайменше 8 символів")
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{10,15}$")
    consents: list[ConsentType] = Field(
        description="Надані згоди. Обов'язкові: terms і personal_data (табл. 15)",
        examples=[["terms", "personal_data", "email_notifications"]],
    )

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Пароль має містити літери й цифри")
        return v

    @field_validator("consents")
    @classmethod
    def _required_consents(cls, v: list[ConsentType]) -> list[ConsentType]:
        missing = REQUIRED_CONSENTS - set(v)
        if missing:
            names = ", ".join(sorted(m.value for m in missing))
            raise ValueError(f"Без обов'язкових згод реєстрація неможлива: {names}")
        return sorted(set(v))


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: ConsentType
    version: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    phone: str | None
    role: str
    service_id: int | None
    contractor_id: int | None
    consents: list[ConsentOut]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Строк дії токена, с")
    role: str
