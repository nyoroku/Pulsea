from io import BytesIO
from unittest.mock import Mock, call, patch

import pytest
from PIL import Image

from clients.models import Client, ClientIndustry
from integrations.models import Platform, SocialAccount
from media.models import Media, MediaSource, MediaType, PostMedia
from publishing.adapters import InstagramPublisher, get_publisher
from publishing.models import Post, PostTarget


@pytest.fixture
def instagram_target():
    client = Client.objects.create(
        name="Instagram Client",
        slug="instagram-client",
        industry=ClientIndustry.OTHER,
    )
    account = SocialAccount.objects.create(
        client=client,
        platform=Platform.INSTAGRAM,
        account_name="instagram.client",
        platform_account_id="ig-123",
        instagram_business_account_id="ig-123",
        access_token="instagram-secret",
    )
    post = Post.objects.create(
        client=client,
        title="Instagram post",
        body="Hello from Pulsea.",
    )
    return PostTarget.objects.create(
        post=post,
        social_account=account,
        platform=Platform.INSTAGRAM,
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


def instagram_storage_mock(*, image_count: int = 1):
    storage = Mock()
    storage.open.side_effect = [
        BytesIO(_image_bytes(width=720, height=188)) for _ in range(image_count)
    ]
    storage.save_for_client.side_effect = [
        f"clients/1/media/normalized-{index}.jpg" for index in range(image_count)
    ]
    storage.url.side_effect = lambda key: f"https://media.example.com/{key}"
    return storage


@pytest.mark.django_db
def test_live_instagram_publisher_uploads_single_image(instagram_target, settings):
    settings.PUBLISHING_ADAPTER_MODE = "live"
    attach_media(instagram_target, "lake.jpg", MediaType.IMAGE)
    storage = instagram_storage_mock()

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        with patch(
            "publishing.adapters._instagram_graph_post",
            side_effect=[{"id": "container-1"}, {"id": "media-1"}],
        ) as post:
            with patch(
                "publishing.adapters._instagram_graph_get",
                side_effect=[
                    {"status_code": "FINISHED"},
                    {"permalink": "https://www.instagram.com/p/shortcode/"},
                ],
            ):
                result = get_publisher(instagram_target).publish(instagram_target)

    assert result.success
    assert result.platform_post_id == "media-1"
    assert result.platform_url == "https://www.instagram.com/p/shortcode/"
    assert post.call_args_list == [
        call(
            "ig-123/media",
            {
                "access_token": "instagram-secret",
                "caption": "Hello from Pulsea.",
                "image_url": "https://media.example.com/clients/1/media/normalized-0.jpg",
            },
        ),
        call(
            "ig-123/media_publish",
            {
                "access_token": "instagram-secret",
                "creation_id": "container-1",
            },
        ),
    ]


@pytest.mark.django_db
def test_live_instagram_publisher_uploads_carousel(instagram_target):
    attach_media(instagram_target, "lake.jpg", MediaType.IMAGE)
    attach_media(instagram_target, "boat.jpg", MediaType.IMAGE)
    storage = instagram_storage_mock(image_count=2)

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        with patch(
            "publishing.adapters._instagram_graph_post",
            side_effect=[
                {"id": "child-1"},
                {"id": "child-2"},
                {"id": "carousel-1"},
                {"id": "media-1"},
            ],
        ) as post:
            with patch(
                "publishing.adapters._instagram_graph_get",
                side_effect=[
                    {"status_code": "FINISHED"},
                    {"status_code": "FINISHED"},
                    {"permalink": "https://www.instagram.com/p/carousel/"},
                ],
            ):
                result = InstagramPublisher().publish(instagram_target)

    assert result.success
    assert post.call_args_list[2] == call(
        "ig-123/media",
        {
            "access_token": "instagram-secret",
            "media_type": "CAROUSEL",
            "children": "child-1,child-2",
            "caption": "Hello from Pulsea.",
        },
    )


@pytest.mark.django_db
def test_live_instagram_publisher_uploads_video_as_reel(instagram_target):
    attach_media(instagram_target, "boat.mp4", MediaType.VIDEO)
    storage = Mock()
    storage.url.return_value = "https://media.example.com/boat.mp4"

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        with patch(
            "publishing.adapters._instagram_graph_post",
            side_effect=[{"id": "container-1"}, {"id": "media-1"}],
        ) as post:
            with patch("publishing.adapters._wait_for_instagram_container") as wait:
                with patch(
                    "publishing.adapters._instagram_graph_get",
                    return_value={"permalink": "https://www.instagram.com/reel/shortcode/"},
                ):
                    result = InstagramPublisher().publish(instagram_target)

    assert result.success
    assert post.call_args_list[0] == call(
        "ig-123/media",
        {
            "access_token": "instagram-secret",
            "caption": "Hello from Pulsea.",
            "video_url": "https://media.example.com/boat.mp4",
            "media_type": "REELS",
        },
    )
    wait.assert_called_once_with("container-1", "instagram-secret")


@pytest.mark.django_db
def test_live_instagram_publisher_requires_public_media_url(instagram_target):
    attach_media(instagram_target, "lake.jpg", MediaType.IMAGE)
    storage = instagram_storage_mock()
    storage.url.side_effect = ValueError("Private local media does not expose public URLs.")

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        result = InstagramPublisher().publish(instagram_target)

    assert not result.success
    assert result.error_message == (
        "Instagram publishing requires public media URLs. "
        "Configure S3 storage before publishing from Pulsea."
    )


@pytest.mark.django_db
def test_live_instagram_publisher_normalizes_non_jpeg_images(instagram_target):
    attach_media(instagram_target, "lake.png", MediaType.IMAGE)
    storage = instagram_storage_mock()

    with patch("publishing.adapters.get_private_storage", return_value=storage):
        with patch(
            "publishing.adapters._instagram_graph_post",
            side_effect=[{"id": "container-1"}, {"id": "media-1"}],
        ):
            with patch(
                "publishing.adapters._instagram_graph_get",
                side_effect=[
                    {"status_code": "FINISHED"},
                    {"permalink": "https://www.instagram.com/p/shortcode/"},
                ],
            ):
                result = InstagramPublisher().publish(instagram_target)

    assert result.success
    assert storage.save_for_client.call_args.args[1] == "lake.png"


@pytest.mark.django_db
def test_live_instagram_publisher_rejects_text_only_post(instagram_target):
    result = InstagramPublisher().publish(instagram_target)

    assert not result.success
    assert result.error_message == "Instagram posts require at least one image or video."


def _image_bytes(*, width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="JPEG")
    return output.getvalue()
