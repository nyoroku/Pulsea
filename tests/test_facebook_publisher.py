from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from clients.models import Client, ClientIndustry
from integrations.models import Platform, SocialAccount
from media.models import PostMedia
from media.services import upload_media
from publishing.adapters import (
    FacebookAPIError,
    FacebookPublisher,
    UnsupportedPublisher,
    get_publisher,
)
from publishing.models import Post, PostTarget


@pytest.fixture
def facebook_target():
    client = Client.objects.create(
        name="Facebook Client",
        slug="facebook-client",
        industry=ClientIndustry.OTHER,
    )
    account = SocialAccount.objects.create(
        client=client,
        platform=Platform.FACEBOOK,
        account_name="Facebook Client Page",
        platform_account_id="page-123",
        page_id="page-123",
        access_token="page-secret",
    )
    post = Post.objects.create(
        client=client,
        title="Facebook post",
        body="Hello from Pulsea.",
    )
    return PostTarget.objects.create(
        post=post,
        social_account=account,
        platform=Platform.FACEBOOK,
    )


@pytest.mark.django_db
def test_live_facebook_publisher_posts_message_to_page_feed(facebook_target, settings):
    settings.PUBLISHING_ADAPTER_MODE = "live"

    with patch("publishing.adapters._graph_post", return_value={"id": "page-123_post-456"}) as post:
        result = get_publisher(facebook_target).publish(facebook_target)

    assert result.success
    assert result.platform_post_id == "page-123_post-456"
    assert result.platform_url == "https://www.facebook.com/page-123_post-456"
    post.assert_called_once_with(
        "page-123/feed",
        {
            "access_token": "page-secret",
            "message": "Hello from Pulsea.",
        },
    )


@pytest.mark.django_db
def test_live_facebook_publisher_requires_connected_page_token(facebook_target):
    facebook_target.social_account.access_token = ""

    result = FacebookPublisher().publish(facebook_target)

    assert not result.success
    assert result.error_message == "Reconnect this Facebook Page before publishing."


@pytest.mark.django_db
def test_live_facebook_publisher_marks_transient_api_errors_retryable(facebook_target):
    with patch(
        "publishing.adapters._graph_post",
        side_effect=FacebookAPIError("Facebook unavailable.", retryable=True),
    ):
        result = FacebookPublisher().publish(facebook_target)

    assert not result.success
    assert result.retryable
    assert result.error_message == "Facebook unavailable."


@pytest.mark.django_db
def test_live_mode_reports_unsupported_platform(facebook_target, settings):
    settings.PUBLISHING_ADAPTER_MODE = "live"
    facebook_target.platform = Platform.TIKTOK

    publisher = get_publisher(facebook_target)

    assert isinstance(publisher, UnsupportedPublisher)
    assert not publisher.publish(facebook_target).success


@pytest.mark.django_db
def test_live_facebook_publisher_uploads_single_image(facebook_target, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    media = upload_media(
        client=facebook_target.post.client,
        uploaded_file=SimpleUploadedFile(
            "lake.png",
            b"\x89PNG\r\n\x1a\nimage-bytes",
            content_type="image/png",
        ),
    )
    PostMedia.objects.create(post=facebook_target.post, media=media)

    with patch(
        "publishing.adapters._graph_post_multipart",
        return_value={"post_id": "page-123_photo-456"},
    ) as post:
        result = FacebookPublisher().publish(facebook_target)

    assert result.success
    assert result.platform_post_id == "page-123_photo-456"
    post.assert_called_once_with(
        "page-123/photos",
        {
            "access_token": "page-secret",
            "caption": "Hello from Pulsea.",
        },
        filename=media.file_key.split("/")[-1],
        content=b"\x89PNG\r\n\x1a\nimage-bytes",
    )


@pytest.mark.django_db
def test_live_facebook_publisher_uploads_single_video(facebook_target, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    media = upload_media(
        client=facebook_target.post.client,
        uploaded_file=SimpleUploadedFile(
            "lake.mp4",
            b"\x00\x00\x00\x14ftypmp42video",
            content_type="video/mp4",
        ),
    )
    PostMedia.objects.create(post=facebook_target.post, media=media)

    with patch(
        "publishing.adapters._graph_post_multipart",
        return_value={"id": "video-456"},
    ) as post:
        result = FacebookPublisher().publish(facebook_target)

    assert result.success
    assert result.platform_post_id == "video-456"
    post.assert_called_once_with(
        "page-123/videos",
        {
            "access_token": "page-secret",
            "description": "Hello from Pulsea.",
            "title": "Facebook post",
        },
        filename=media.file_key.split("/")[-1],
        content=b"\x00\x00\x00\x14ftypmp42video",
    )


@pytest.mark.django_db
def test_live_facebook_publisher_uploads_multiple_images(facebook_target, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    for filename in ("lake.png", "boat.png"):
        media = upload_media(
            client=facebook_target.post.client,
            uploaded_file=SimpleUploadedFile(
                filename,
                b"\x89PNG\r\n\x1a\nimage-bytes",
                content_type="image/png",
            ),
        )
        PostMedia.objects.create(post=facebook_target.post, media=media)

    with patch(
        "publishing.adapters._graph_post_multipart",
        side_effect=[{"id": "photo-1"}, {"id": "photo-2"}],
    ) as upload:
        with patch(
            "publishing.adapters._graph_post",
            return_value={"id": "page-123_post-456"},
        ) as publish:
            result = FacebookPublisher().publish(facebook_target)

    assert result.success
    assert upload.call_count == 2
    publish.assert_called_once_with(
        "page-123/feed",
        {
            "access_token": "page-secret",
            "message": "Hello from Pulsea.",
            "attached_media": [
                '{"media_fbid": "photo-1"}',
                '{"media_fbid": "photo-2"}',
            ],
        },
    )


@pytest.mark.django_db
def test_live_facebook_publisher_rejects_multiple_videos(facebook_target, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    for filename in ("lake.mp4", "boat.mp4"):
        media = upload_media(
            client=facebook_target.post.client,
            uploaded_file=SimpleUploadedFile(
                filename,
                b"\x00\x00\x00\x14ftypmp42video",
                content_type="video/mp4",
            ),
        )
        PostMedia.objects.create(post=facebook_target.post, media=media)

    result = FacebookPublisher().publish(facebook_target)

    assert not result.success
    assert result.error_message == "Facebook multiple-video publishing is not enabled yet."


@pytest.mark.django_db
def test_live_facebook_publisher_rejects_mixed_media(facebook_target, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    uploads = [
        SimpleUploadedFile(
            "lake.png",
            b"\x89PNG\r\n\x1a\nimage-bytes",
            content_type="image/png",
        ),
        SimpleUploadedFile(
            "boat.mp4",
            b"\x00\x00\x00\x14ftypmp42video",
            content_type="video/mp4",
        ),
    ]
    for uploaded_file in uploads:
        media = upload_media(
            client=facebook_target.post.client,
            uploaded_file=uploaded_file,
        )
        PostMedia.objects.create(post=facebook_target.post, media=media)

    result = FacebookPublisher().publish(facebook_target)

    assert not result.success
    assert result.error_message == "Facebook posts cannot mix images and videos."
