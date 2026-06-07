from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol
from uuid import UUID, uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.text import get_valid_filename


def client_media_key(client_id: UUID | str | int, filename: str) -> str:
    basename = PurePosixPath(str(filename).replace("\\", "/")).name
    safe_name = get_valid_filename(basename).lstrip(".") or "upload"
    return str(PurePosixPath("clients", str(client_id), "media", f"{uuid4()}-{safe_name}"))


class PrivateStorage(Protocol):
    def save_for_client(self, client_id: UUID | str | int, filename: str, content: BinaryIO) -> str:
        ...

    def delete(self, key: str) -> None:
        ...

    def open(self, key: str, mode: str = "rb") -> BinaryIO:
        ...

    def url(self, key: str) -> str:
        ...


@dataclass
class LocalPrivateStorage:
    root: Path

    def __post_init__(self) -> None:
        self.storage = FileSystemStorage(location=self.root)

    def save_for_client(self, client_id: UUID | str | int, filename: str, content: BinaryIO) -> str:
        return self.storage.save(client_media_key(client_id, filename), content)

    def delete(self, key: str) -> None:
        self.storage.delete(key)

    def open(self, key: str, mode: str = "rb") -> BinaryIO:
        return self.storage.open(key, mode)

    def url(self, key: str) -> str:
        raise ValueError("Private local media does not expose public URLs.")


@dataclass
class S3PrivateStorage:
    bucket_name: str

    def __post_init__(self) -> None:
        if not self.bucket_name:
            raise ValueError("AWS_STORAGE_BUCKET_NAME is required for private S3 storage.")

        from storages.backends.s3 import S3Storage

        self.storage = S3Storage(
            bucket_name=self.bucket_name,
            default_acl="private",
            file_overwrite=False,
            querystring_auth=True,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
            region_name=settings.AWS_S3_REGION_NAME or None,
            access_key=settings.AWS_ACCESS_KEY_ID or None,
            secret_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

    def save_for_client(self, client_id: UUID | str | int, filename: str, content: BinaryIO) -> str:
        return self.storage.save(client_media_key(client_id, filename), content)

    def delete(self, key: str) -> None:
        self.storage.delete(key)

    def open(self, key: str, mode: str = "rb") -> BinaryIO:
        return self.storage.open(key, mode)

    def url(self, key: str) -> str:
        return self.storage.url(key)


def get_private_storage() -> PrivateStorage:
    if settings.PRIVATE_STORAGE_BACKEND == "local":
        return LocalPrivateStorage(settings.PRIVATE_MEDIA_ROOT)
    if settings.PRIVATE_STORAGE_BACKEND == "s3":
        return S3PrivateStorage(settings.AWS_STORAGE_BUCKET_NAME)
    raise ValueError(f"Unsupported PRIVATE_STORAGE_BACKEND: {settings.PRIVATE_STORAGE_BACKEND}")
