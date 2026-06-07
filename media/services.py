from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Media, MediaSource, MediaType
from .storage import PrivateStorage, get_private_storage


@dataclass(frozen=True)
class UploadFormat:
    media_type: str
    content_types: frozenset[str]


UPLOAD_FORMATS = {
    ".jpg": UploadFormat(MediaType.IMAGE, frozenset({"image/jpeg"})),
    ".jpeg": UploadFormat(MediaType.IMAGE, frozenset({"image/jpeg"})),
    ".png": UploadFormat(MediaType.IMAGE, frozenset({"image/png"})),
    ".webp": UploadFormat(MediaType.IMAGE, frozenset({"image/webp"})),
    ".mp4": UploadFormat(MediaType.VIDEO, frozenset({"video/mp4"})),
    ".mov": UploadFormat(MediaType.VIDEO, frozenset({"video/quicktime"})),
}


def upload_media(
    *,
    client,
    uploaded_file: BinaryIO,
    source: str = MediaSource.OPERATOR,
    uploaded_by=None,
    label: str = "",
    note: str = "",
    storage: PrivateStorage | None = None,
) -> Media:
    upload_format = validate_media_upload(uploaded_file)
    storage = storage or get_private_storage()
    file_key = storage.save_for_client(client.pk, uploaded_file.name, uploaded_file)
    try:
        with transaction.atomic():
            return Media.objects.create(
                client=client,
                file_key=file_key,
                media_type=upload_format.media_type,
                size_bytes=uploaded_file.size,
                uploaded_by=uploaded_by,
                source=source,
                label=label.strip(),
                note=note.strip(),
            )
    except Exception:
        storage.delete(file_key)
        raise


def validate_media_upload(uploaded_file: BinaryIO) -> UploadFormat:
    filename = PurePosixPath(str(uploaded_file.name).replace("\\", "/")).name
    extension = PurePosixPath(filename).suffix.lower()
    upload_format = UPLOAD_FORMATS.get(extension)
    if upload_format is None:
        raise ValidationError("Upload a JPEG, PNG, WebP, MP4, or MOV file.")

    content_type = getattr(uploaded_file, "content_type", "")
    if content_type not in upload_format.content_types:
        raise ValidationError("The file type does not match its extension.")

    size_bytes = getattr(uploaded_file, "size", 0)
    if not size_bytes:
        raise ValidationError("The uploaded file is empty.")

    size_limit = (
        settings.MEDIA_MAX_IMAGE_UPLOAD_BYTES
        if upload_format.media_type == MediaType.IMAGE
        else settings.MEDIA_MAX_VIDEO_UPLOAD_BYTES
    )
    if size_bytes > size_limit:
        raise ValidationError(f"The uploaded file exceeds the {size_limit}-byte size limit.")

    header = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not _matches_signature(extension, header):
        raise ValidationError("The uploaded file content is not a valid supported media type.")
    return upload_format


def _matches_signature(extension: str, header: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return len(header) >= 12 and header[4:8] == b"ftyp"
