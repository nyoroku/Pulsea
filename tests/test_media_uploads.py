from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from clients.models import Client, ClientIndustry
from media.models import Media, MediaSource, MediaType
from media.services import upload_media
from media.storage import LocalPrivateStorage


@pytest.fixture
def media_client():
    return Client.objects.create(
        name="Media Client",
        slug="media-client",
        industry=ClientIndustry.OTHER,
    )


@pytest.mark.django_db
def test_upload_media_saves_client_scoped_private_image(media_client, tmp_path):
    uploaded_file = SimpleUploadedFile(
        "../../campaign image.png",
        b"\x89PNG\r\n\x1a\nimage-bytes",
        content_type="image/png",
    )

    media = upload_media(
        client=media_client,
        uploaded_file=uploaded_file,
        label=" Campaign image ",
        storage=LocalPrivateStorage(tmp_path),
    )

    assert media.client == media_client
    assert media.media_type == MediaType.IMAGE
    assert media.source == MediaSource.OPERATOR
    assert media.label == "Campaign image"
    assert media.file_key.startswith(f"clients/{media_client.pk}/media/")
    assert ".." not in media.file_key
    assert (tmp_path / media.file_key).read_bytes() == b"\x89PNG\r\n\x1a\nimage-bytes"


@pytest.mark.django_db
def test_upload_media_accepts_quicktime_video(media_client, tmp_path):
    uploaded_file = SimpleUploadedFile(
        "launch.mov",
        b"\x00\x00\x00\x14ftypqt  video-bytes",
        content_type="video/quicktime",
    )

    media = upload_media(
        client=media_client,
        uploaded_file=uploaded_file,
        storage=LocalPrivateStorage(tmp_path),
    )

    assert media.media_type == MediaType.VIDEO


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_media_type"),
    [
        ("photo.jpg", "image/jpeg", b"\xff\xd8\xffimage-bytes", MediaType.IMAGE),
        ("photo.jpeg", "image/jpeg", b"\xff\xd8\xffimage-bytes", MediaType.IMAGE),
        ("photo.webp", "image/webp", b"RIFF\x00\x00\x00\x00WEBPimage", MediaType.IMAGE),
        ("video.mp4", "video/mp4", b"\x00\x00\x00\x14ftypmp42video", MediaType.VIDEO),
    ],
)
def test_upload_media_accepts_each_supported_format(
    media_client,
    tmp_path,
    filename,
    content_type,
    content,
    expected_media_type,
):
    uploaded_file = SimpleUploadedFile(filename, content, content_type=content_type)

    media = upload_media(
        client=media_client,
        uploaded_file=uploaded_file,
        storage=LocalPrivateStorage(tmp_path),
    )

    assert media.media_type == expected_media_type


@pytest.mark.django_db
def test_upload_media_rejects_spoofed_content(media_client, tmp_path):
    uploaded_file = SimpleUploadedFile(
        "not-really-an-image.png",
        b"plain text",
        content_type="image/png",
    )

    with pytest.raises(ValidationError, match="not a valid supported media type"):
        upload_media(
            client=media_client,
            uploaded_file=uploaded_file,
            storage=LocalPrivateStorage(tmp_path),
        )

    assert not Media.objects.exists()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.django_db
def test_upload_media_rejects_mime_type_that_does_not_match_extension(media_client, tmp_path):
    uploaded_file = SimpleUploadedFile(
        "not-really-an-image.png",
        b"\x89PNG\r\n\x1a\nimage-bytes",
        content_type="image/jpeg",
    )

    with pytest.raises(ValidationError, match="does not match its extension"):
        upload_media(
            client=media_client,
            uploaded_file=uploaded_file,
            storage=LocalPrivateStorage(tmp_path),
        )

    assert not Media.objects.exists()


@pytest.mark.django_db
def test_upload_media_rejects_image_over_size_limit(media_client, tmp_path, settings):
    settings.MEDIA_MAX_IMAGE_UPLOAD_BYTES = 8
    uploaded_file = SimpleUploadedFile(
        "large.png",
        b"\x89PNG\r\n\x1a\nextra",
        content_type="image/png",
    )

    with pytest.raises(ValidationError, match="exceeds the 8-byte size limit"):
        upload_media(
            client=media_client,
            uploaded_file=uploaded_file,
            storage=LocalPrivateStorage(tmp_path),
        )

    assert not Media.objects.exists()


@pytest.mark.django_db
def test_upload_media_deletes_private_object_when_record_creation_fails(media_client, tmp_path):
    uploaded_file = SimpleUploadedFile(
        "campaign.png",
        b"\x89PNG\r\n\x1a\nimage-bytes",
        content_type="image/png",
    )

    with patch("media.services.Media.objects.create", side_effect=RuntimeError("database failed")):
        with pytest.raises(RuntimeError, match="database failed"):
            upload_media(
                client=media_client,
                uploaded_file=uploaded_file,
                storage=LocalPrivateStorage(tmp_path),
            )

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
