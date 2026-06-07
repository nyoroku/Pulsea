from unittest.mock import Mock, patch

import pytest

from clients.models import Client, ClientIndustry
from integrations.models import Platform, SocialAccount
from media.models import Media, MediaSource, MediaType, PostMedia
from publishing.adapters import PinterestPublisher, get_publisher
from publishing.models import Post, PostTarget


@pytest.fixture
def pinterest_target():
    client = Client.objects.create(
        name="Pinterest Client",
        slug="pinterest-client",
        industry=ClientIndustry.OTHER,
    )
    account = SocialAccount.objects.create(
        client=client,
        platform=Platform.PINTEREST,
        account_name="Travel ideas",
        platform_account_id="board-123",
        access_token="pinterest-secret",
    )
    post = Post.objects.create(
        client=client,
        title="Lake Naivasha",
        body="A calm day on the lake.",
    )
    return PostTarget.objects.create(
        post=post,
        social_account=account,
        platform=Platform.PINTEREST,
    )


def attach_media(target, filename: str, media_type: str):
    media = Media.objects.create(
        client=target.post.client,
        file_key=f"clients/1/media/{filename}",
        media_type=media_type,
        size_bytes=100,
        source=MediaSource.OPERATOR,
    )
    PostMedia.objects.create(post=target.post, media=media)
    return media


@pytest.mark.django_db
def test_live_pinterest_publisher_creates_image_pin(pinterest_target, settings):
    settings.PUBLISHING_ADAPTER_MODE = "live"
    attach_media(pinterest_target, "lake.jpg", MediaType.IMAGE)
    storage = Mock()
    storage.url.return_value = "https://media.example.com/lake.jpg"

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        with patch(
            "publishing.adapters._pinterest_api_post",
            return_value={"id": "pin-123"},
        ) as post:
            result = get_publisher(pinterest_target).publish(pinterest_target)

    assert result.success
    assert result.platform_post_id == "pin-123"
    assert result.platform_url == "https://www.pinterest.com/pin/pin-123/"
    post.assert_called_once_with(
        "pins",
        "pinterest-secret",
        {
            "board_id": "board-123",
            "title": "Lake Naivasha",
            "description": "A calm day on the lake.",
            "media_source": {
                "source_type": "image_url",
                "url": "https://media.example.com/lake.jpg",
            },
        },
    )


@pytest.mark.django_db
def test_live_pinterest_publisher_rejects_video(pinterest_target):
    attach_media(pinterest_target, "lake.mp4", MediaType.VIDEO)

    result = PinterestPublisher().publish(pinterest_target)

    assert not result.success
    assert result.error_message == "Pinterest publishing currently supports exactly one image."


@pytest.mark.django_db
def test_live_pinterest_publisher_requires_media(pinterest_target):
    result = PinterestPublisher().publish(pinterest_target)

    assert not result.success
    assert result.error_message == "Pinterest posts require one image."
