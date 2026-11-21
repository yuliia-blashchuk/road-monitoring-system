"""Фото заявки (KAN-57, DQ-04): формат за вмістом, розмір, кількість, видалення EXIF."""

from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.modules.reports import photos as photos_module
from app.modules.reports.models import Photo, Request
from tests.factories import LVIV, auth, make_driver

URL = "/api/v1/reports"
FORM = {"problem_type": "pothole", **LVIV}
MODEL_TAG, ORIENTATION_TAG = 0x0110, 0x0112


def image_bytes(fmt: str = "JPEG", size=(40, 20), exif: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    out = BytesIO()
    if exif:
        tags = Image.Exif()
        tags[MODEL_TAG] = "Phone X"
        tags[ORIENTATION_TAG] = 6  # повернути на 90°
        image.save(out, fmt, exif=tags.tobytes())
    else:
        image.save(out, fmt)
    return out.getvalue()


def upload(*files: tuple[str, bytes, str]) -> list:
    return [("photos", f) for f in files]


async def count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_photo_saved_without_exif(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-01: EXIF у збереженому фото видалено, поворот застосовано."""
    driver = await make_driver(db)
    raw = image_bytes(exif=True)
    assert Image.open(BytesIO(raw)).getexif()[MODEL_TAG] == "Phone X"

    response = await client.post(
        URL, data=FORM, files=upload(("photo1.jpg", raw, "image/jpeg")), headers=auth(driver)
    )
    assert response.status_code == 201, response.text
    assert response.json()["photos_count"] == 1

    photo = await db.scalar(select(Photo))
    assert photo.mime_type == "image/jpeg" and photo.kind == "before"
    assert photo.uploaded_by == driver.id
    stored = Image.open(BytesIO(get_storage().read(photo.storage_key)))
    assert dict(stored.getexif()) == {}
    assert stored.size == (20, 40)  # 40×20 після повороту з EXIF


@pytest.mark.parametrize(("fmt", "mime"), [("PNG", "image/png"), ("WEBP", "image/webp")])
async def test_png_and_webp_accepted(
    client: AsyncClient, db: AsyncSession, fmt: str, mime: str
) -> None:
    driver = await make_driver(db)
    files = upload((f"photo.{fmt.lower()}", image_bytes(fmt), mime))
    response = await client.post(URL, data=FORM, files=files, headers=auth(driver))
    assert response.status_code == 201
    assert (await db.scalar(select(Photo))).mime_type == mime


async def test_three_photos_ok_fourth_rejected(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-06: 3 фото - можна, 4 - 422, заявку не створено."""
    driver = await make_driver(db)
    three = upload(*[(f"p{i}.jpg", image_bytes(), "image/jpeg") for i in range(3)])
    assert (await client.post(URL, data=FORM, files=three, headers=auth(driver))).status_code == 201

    four = upload(*[(f"p{i}.jpg", image_bytes(), "image/jpeg") for i in range(4)])
    response = await client.post(URL, data=FORM, files=four, headers=auth(driver))
    assert response.status_code == 422
    assert "не більше 3 фото" in str(response.json())
    assert await count(db, Request) == 1


async def test_too_big_photo_rejected_with_filename(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-05: файл понад 5 МБ - 422 з назвою файлу."""
    driver = await make_driver(db)
    big = b"\xff\xd8" + b"0" * (5 * 1024 * 1024)
    files = upload(("big.jpg", big, "image/jpeg"))
    response = await client.post(URL, data=FORM, files=files, headers=auth(driver))
    assert response.status_code == 422
    assert "big.jpg" in str(response.json())
    assert await count(db, Request) == 0


async def test_fake_extension_rejected(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-05: PDF, перейменований на .jpg, визначається за вмістом."""
    driver = await make_driver(db)
    files = upload(("photo.jpg", b"%PDF-1.7\n%fake pdf content", "image/jpeg"))
    response = await client.post(URL, data=FORM, files=files, headers=auth(driver))
    assert response.status_code == 422
    assert "photo.jpg" in str(response.json())


async def test_gif_rejected(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    files = upload(("anim.gif", image_bytes("GIF"), "image/gif"))
    response = await client.post(URL, data=FORM, files=files, headers=auth(driver))
    assert response.status_code == 422


async def test_files_removed_if_saving_fails(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Або все, або нічого: якщо БД відхилила запис, файлів на диску не лишається."""
    driver = await make_driver(db)
    # Тип, який забороняє CHECK-обмеження таблиці photo, - commit не вдасться.
    monkeypatch.setitem(photos_module.FORMATS, "JPEG", ("image/gif", "jpg"))
    storage = get_storage()
    before = set(storage.root.rglob("*")) if storage.root.exists() else set()

    with pytest.raises(Exception):  # noqa: B017 - помилка БД доходить до тесту
        await client.post(
            URL,
            data=FORM,
            files=upload(("p.jpg", image_bytes(), "image/jpeg")),
            headers=auth(driver),
        )
    after = {p for p in storage.root.rglob("*") if p.is_file()} if storage.root.exists() else set()
    assert {p for p in before if p.is_file()} == after
    assert await count(db, Request) == 0
