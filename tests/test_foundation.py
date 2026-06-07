import logging
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from config.logging import RedactSecretsFilter, redact
from media.storage import LocalPrivateStorage, S3PrivateStorage, client_media_key
from publishing.tasks import foundation_heartbeat


def test_healthcheck_returns_request_id(client):
    response = client.get(reverse("healthcheck"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_healthcheck_preserves_supplied_request_id(client):
    response = client.get(reverse("healthcheck"), HTTP_X_REQUEST_ID="trace-123")

    assert response.headers["X-Request-ID"] == "trace-123"


def test_home_is_public_website(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Social publishing workspace" in response.content
    assert reverse("privacy-policy").encode() in response.content


def test_privacy_policy_is_public(client):
    response = client.get(reverse("privacy-policy"))

    assert response.status_code == 200
    assert b"Pulsea Privacy Policy" in response.content
    assert b"Third-Party Platforms" in response.content


def test_terms_of_service_is_public(client):
    response = client.get(reverse("terms-of-service"))

    assert response.status_code == 200
    assert b"Terms of Service" in response.content


def test_foundation_heartbeat_is_registered_in_beat_schedule(settings):
    assert settings.CELERY_BEAT_SCHEDULE["foundation-heartbeat"]["task"] == (
        "publishing.tasks.foundation_heartbeat"
    )
    assert foundation_heartbeat.delay().get() == "ok"


def test_redact_hides_sensitive_values():
    assert redact({"access_token": "secret", "safe": "visible"}) == {
        "access_token": "[REDACTED]",
        "safe": "visible",
    }
    assert redact("token=abc password:xyz keep=this") == (
        "token=[REDACTED] password:[REDACTED] keep=this"
    )


def test_logging_filter_redacts_structured_arguments():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="payload=%s",
        args=({"client_secret": "raw-value"},),
        exc_info=None,
    )

    assert RedactSecretsFilter().filter(record)
    assert record.args == {"client_secret": "[REDACTED]"}


@pytest.mark.parametrize("filename", ["../../unsafe name.png", "..\\..\\unsafe name.png"])
def test_client_media_key_is_scoped_and_sanitized(filename):
    key = client_media_key("42", filename)

    assert key.startswith("clients/42/media/")
    assert key.endswith("-unsafe_name.png")
    assert ".." not in key


def test_local_private_storage_saves_without_public_url(tmp_path):
    storage = LocalPrivateStorage(tmp_path)
    upload = SimpleUploadedFile("example.png", b"image-bytes", content_type="image/png")

    key = storage.save_for_client("client-1", upload.name, upload)

    assert (tmp_path / key).read_bytes() == b"image-bytes"
    with storage.open(key) as stored_file:
        assert stored_file.read() == b"image-bytes"
    with pytest.raises(ValueError, match="does not expose public URLs"):
        storage.url(key)


def test_s3_private_storage_requires_bucket_name():
    with pytest.raises(ValueError, match="AWS_STORAGE_BUCKET_NAME"):
        S3PrivateStorage("")


def test_s3_private_storage_accepts_custom_endpoint(settings):
    settings.AWS_S3_ENDPOINT_URL = "https://account-id.r2.cloudflarestorage.com"
    settings.AWS_S3_REGION_NAME = "auto"
    settings.AWS_ACCESS_KEY_ID = "access-key"
    settings.AWS_SECRET_ACCESS_KEY = "secret-key"

    with patch("storages.backends.s3.S3Storage") as storage_class:
        storage = S3PrivateStorage("pulsea-media")

    assert storage.storage == storage_class.return_value
    storage_class.assert_called_once_with(
        bucket_name="pulsea-media",
        default_acl="private",
        file_overwrite=False,
        querystring_auth=True,
        endpoint_url="https://account-id.r2.cloudflarestorage.com",
        region_name="auto",
        access_key="access-key",
        secret_key="secret-key",
    )
