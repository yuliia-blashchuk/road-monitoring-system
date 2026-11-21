"""Сховище файлів (фото заявок).

Модулі працюють лише через інтерфейс FileStorage: save / delete. У прототипі файли
лежать у локальній папці MEDIA_DIR; за архітектурою (п. 4.1) у продуктиві це MinIO,
і для переходу достатньо додати клас S3Storage з тими самими методами.
"""

from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class FileStorage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:  # ключ не може вийти за межі папки
            raise ValueError(f"Недопустимий ключ файлу: {key}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().media_dir)
