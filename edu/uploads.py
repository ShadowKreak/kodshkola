"""Безопасная загрузка обложек курсов."""
import secrets
from pathlib import Path

from flask import current_app

MAX_BYTES = 2 * 1024 * 1024


def _detect(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def save_cover(file_storage) -> str | None:
    """Сохраняет изображение, возвращает имя файла. ValueError — если файл недопустим."""
    if not file_storage or not file_storage.filename:
        return None
    data = file_storage.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Обложка не должна превышать 2 МБ.")
    ext = _detect(data[:16])
    if not ext:
        raise ValueError("Допустимые форматы обложки: PNG, JPG, WEBP.")
    name = secrets.token_hex(12) + ext  # имя генерируется сервером, пользовательское не используется
    (Path(current_app.config["UPLOAD_DIR"]) / name).write_bytes(data)
    return name


def delete_cover(name: str | None):
    if not name:
        return
    path = Path(current_app.config["UPLOAD_DIR"]) / Path(name).name
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
