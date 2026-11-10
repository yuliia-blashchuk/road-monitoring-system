from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_db(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/db")
    assert response.status_code == 200
    assert response.json()["postgis"].startswith("3.")


async def test_docs_available(client: AsyncClient) -> None:
    assert (await client.get("/docs")).status_code == 200
