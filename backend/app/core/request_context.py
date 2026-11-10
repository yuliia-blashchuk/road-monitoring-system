"""Контекст HTTP-запиту: ідентифікатор операції (correlation_id) та IP клієнта.

Middleware присвоює кожному запиту correlation_id (або бере з заголовка X-Request-ID)
і повертає його у відповіді. Журнал аудиту бере ці значення звідси, тому всі записи
одного запиту об'єднані одним correlation_id (п. 3.8).
"""

import ipaddress
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[uuid.UUID | None] = ContextVar("correlation_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)

HEADER = "X-Request-ID"


def _parse_uuid(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value) if value else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def _parse_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = _parse_uuid(request.headers.get(HEADER))
        cid_token = correlation_id_var.set(cid)
        ip_token = client_ip_var.set(_parse_ip(request.client.host if request.client else None))
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(cid_token)
            client_ip_var.reset(ip_token)
        response.headers[HEADER] = str(cid)
        return response
