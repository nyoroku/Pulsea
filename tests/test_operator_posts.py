from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from campaigns.models import Campaign
from clients.models import Client, ClientIndustry
from integrations.models import Platform, SocialAccount
from media.image_processing import (
    instagram_image_ratio_is_unsupported,
    jpeg_dimensions_from_bytes,
)
from media.models import Media, MediaType, PostMedia
from publishing.models import Post, PostAuditEvent, PostStatus, PostTargetStatus


@pytest.fixture
def post_staff_user(django_user_model):
    return django_user_model.objects.create_user(username="post-operator", is_staff=True)


@pytest.fixture
def post_client_record():
    return Client.objects.create(
        name="Post Client",
        slug="post-client",
        industry=ClientIndustry.RETAIL,
    )


@pytest.fixture
def post_social_account(post_client_record):
    return SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.FACEBOOK,
        account_name="Post Client Page",
        platform_account_id="post-client-page",
    )


@pytest.mark.django_db
def test_post_list_requires_staff(client, django_user_model):
    normal_user = django_user_model.objects.create_user(username="post-normal")
    client.force_login(normal_user)

    response = client.get(reverse("operator-post-list"))

    assert response.status_code == 302
    assert response.url.startswith("/operator/login/")


@pytest.mark.django_db
def test_staff_can_save_post_draft(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Draft announcement",
            "body": "A useful draft.",
            "social_accounts": [post_social_account.pk],
            "action": "draft",
        },
    )
    post = Post.objects.get(title="Draft announcement")

    assert response.status_code == 302
    assert response.url == reverse("operator-post-detail", args=[post.pk])
    assert post.status == PostStatus.DRAFT
    assert post.targets.get().social_account == post_social_account
    assert post.audit_entries.get().event_type == PostAuditEvent.CREATED


@pytest.mark.django_db
def test_publish_now_dispatches_fake_delivery(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
    django_capture_on_commit_callbacks,
):
    client.force_login(post_staff_user)

    with patch("publishing.views.dispatch_post.delay") as dispatch_delay:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("operator-post-compose"),
                {
                    "client": post_client_record.pk,
                    "title": "Publish now",
                    "body": "Send this immediately.",
                    "social_accounts": [post_social_account.pk],
                    "action": "publish_now",
                },
            )
    post = Post.objects.get(title="Publish now")

    assert response.status_code == 302
    assert post.status == PostStatus.QUEUED
    dispatch_delay.assert_called_once_with(post.pk)


@pytest.mark.django_db
def test_schedule_action_requires_time(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Missing schedule",
            "body": "This should not save.",
            "social_accounts": [post_social_account.pk],
            "action": "schedule",
        },
    )

    assert response.status_code == 200
    assert b"Choose a schedule time before scheduling this post." in response.content
    assert not Post.objects.filter(title="Missing schedule").exists()


@pytest.mark.django_db
def test_composer_prefills_client_and_campaign_from_campaign_link(
    client,
    post_staff_user,
    post_client_record,
):
    campaign = Campaign.objects.create(client=post_client_record, name="Prefilled Campaign")
    client.force_login(post_staff_user)

    response = client.get(reverse("operator-post-compose"), {"campaign": campaign.pk})

    assert response.status_code == 200
    assert b"Prefilled Campaign" in response.content
    assert b"Post Client" in response.content
    assert f'value="{campaign.pk}" selected'.encode() in response.content


@pytest.mark.django_db
def test_composer_rejects_cross_client_campaign(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    other_client = Client.objects.create(
        name="Other Client",
        slug="other-client",
        industry=ClientIndustry.OTHER,
    )
    campaign = Campaign.objects.create(client=other_client, name="Other Campaign")
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "campaign": campaign.pk,
            "title": "Wrong campaign",
            "social_accounts": [post_social_account.pk],
            "action": "draft",
        },
    )

    assert response.status_code == 200
    assert b"Campaign must belong to the selected client." in response.content
    assert not Post.objects.filter(title="Wrong campaign").exists()


@pytest.mark.django_db
def test_composer_rejects_cross_client_account(client, post_staff_user, post_client_record):
    other_client = Client.objects.create(
        name="Other Account Client",
        slug="other-account-client",
        industry=ClientIndustry.OTHER,
    )
    other_account = SocialAccount.objects.create(
        client=other_client,
        platform=Platform.INSTAGRAM,
        account_name="Other Instagram",
        platform_account_id="other-instagram",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Wrong account",
            "social_accounts": [other_account.pk],
            "action": "draft",
        },
    )

    assert response.status_code == 200
    assert b"Every social account must belong to the selected client." in response.content
    assert not Post.objects.filter(title="Wrong account").exists()


@pytest.mark.django_db
def test_post_detail_shows_failed_target_and_retry_action(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    post = Post.objects.create(
        client=post_client_record,
        title="Failed detail",
        status=PostStatus.FAILED,
    )
    post.targets.create(
        social_account=post_social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.FAILED,
        error_message="Remote API unavailable.",
    )
    client.force_login(post_staff_user)

    response = client.get(reverse("operator-post-detail", args=[post.pk]))

    assert response.status_code == 200
    assert b"Remote API unavailable." in response.content
    assert b"Retry failed targets" in response.content


@pytest.mark.django_db
def test_post_detail_shows_platform_link_and_processing_note(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    post = Post.objects.create(
        client=post_client_record,
        title="Mixed detail",
        status=PostStatus.PUBLISHING,
    )
    post.targets.create(
        social_account=post_social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.PUBLISHED,
        platform_url="https://www.facebook.com/example-post",
    )
    instagram = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.INSTAGRAM,
        account_name="Post Client Instagram",
        platform_account_id="instagram-client",
    )
    post.targets.create(
        social_account=instagram,
        platform=Platform.INSTAGRAM,
        status=PostTargetStatus.PUBLISHING,
    )
    client.force_login(post_staff_user)

    response = client.get(reverse("operator-post-detail", args=[post.pk]))

    assert response.status_code == 200
    assert b"Open on Facebook" in response.content
    assert b"https://www.facebook.com/example-post" in response.content
    assert b"Instagram media can take about a minute." in response.content


@pytest.mark.django_db
def test_post_detail_shows_video_preview_link(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    post = Post.objects.create(
        client=post_client_record,
        title="Video detail",
        status=PostStatus.PUBLISHING,
    )
    post.targets.create(
        social_account=post_social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.PUBLISHING,
    )
    media = Media.objects.create(
        client=post_client_record,
        file_key="clients/1/media/clip.mp4",
        media_type=MediaType.VIDEO,
        size_bytes=1024,
        source="OPERATOR",
        label="clip.mp4",
    )
    PostMedia.objects.create(post=post, media=media)
    client.force_login(post_staff_user)

    storage = type("Storage", (), {"url": lambda self, key: f"https://media.example.com/{key}"})()
    with patch("publishing.views.get_private_storage", return_value=storage):
        response = client.get(reverse("operator-post-detail", args=[post.pk]))

    assert response.status_code == 200
    assert b"<video controls" in response.content
    assert b"Open video file" in response.content
    assert b"Instagram Reels can take a few minutes." in response.content


@pytest.mark.django_db
def test_post_retry_endpoint_dispatches_task(
    client,
    post_staff_user,
    post_client_record,
):
    post = Post.objects.create(
        client=post_client_record,
        title="Retry endpoint",
        status=PostStatus.FAILED,
    )
    client.force_login(post_staff_user)

    with patch("publishing.views.manual_retry_failed_targets.delay") as retry_delay:
        response = client.post(reverse("operator-post-retry", args=[post.pk]))

    assert response.status_code == 302
    retry_delay.assert_called_once_with(post.pk, post_staff_user.pk)


@pytest.mark.django_db
def test_composer_uploads_and_attaches_client_media(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
    settings,
    tmp_path,
):
    settings.PRIVATE_STORAGE_BACKEND = "local"
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Image announcement",
            "body": "A post with an image.",
            "social_accounts": [post_social_account.pk],
            "action": "draft",
            "media_uploads": SimpleUploadedFile(
                "campaign.png",
                b"\x89PNG\r\n\x1a\nimage-bytes",
                content_type="image/png",
            ),
        },
    )
    post = Post.objects.get(title="Image announcement")
    attachment = PostMedia.objects.get(post=post)

    assert response.status_code == 302
    assert attachment.media.client == post_client_record
    assert attachment.media.uploaded_by == post_staff_user
    assert (tmp_path / attachment.media.file_key).exists()


@pytest.mark.django_db
def test_composer_uploads_and_attaches_multiple_media_files(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
    settings,
    tmp_path,
):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Carousel announcement",
            "body": "A post with two images.",
            "social_accounts": [post_social_account.pk],
            "action": "draft",
            "media_uploads": [
                SimpleUploadedFile(
                    "campaign-one.png",
                    b"\x89PNG\r\n\x1a\nimage-one",
                    content_type="image/png",
                ),
                SimpleUploadedFile(
                    "campaign-two.png",
                    b"\x89PNG\r\n\x1a\nimage-two",
                    content_type="image/png",
                ),
            ],
        },
    )
    post = Post.objects.get(title="Carousel announcement")

    assert response.status_code == 302
    assert post.media_attachments.count() == 2


@pytest.mark.django_db
def test_composer_blocks_live_instagram_posts_without_public_storage(
    client,
    post_staff_user,
    post_client_record,
    settings,
):
    settings.PUBLISHING_ADAPTER_MODE = "live"
    settings.PRIVATE_STORAGE_BACKEND = "local"
    instagram = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.INSTAGRAM,
        account_name="Post Client Instagram",
        platform_account_id="instagram-client",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Instagram local storage",
            "body": "This should not queue.",
            "social_accounts": [instagram.pk],
            "action": "publish_now",
            "media_uploads": SimpleUploadedFile(
                "campaign.jpg",
                b"\xff\xd8\xffimage-bytes",
                content_type="image/jpeg",
            ),
        },
    )

    assert response.status_code == 200
    assert b"Instagram live publishing requires public S3 media storage." in response.content
    assert not Post.objects.filter(title="Instagram local storage").exists()


@pytest.mark.django_db
def test_composer_blocks_facebook_mixed_image_and_video_publish(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Facebook mixed media",
            "body": "This should not queue.",
            "social_accounts": [post_social_account.pk],
            "action": "publish_now",
            "media_uploads": [
                SimpleUploadedFile(
                    "campaign.png",
                    b"\x89PNG\r\n\x1a\nimage-bytes",
                    content_type="image/png",
                ),
                SimpleUploadedFile(
                    "clip.mp4",
                    b"\x00\x00\x00\x14ftypmp42video",
                    content_type="video/mp4",
                ),
            ],
        },
    )

    assert response.status_code == 200
    assert b"Facebook posts cannot mix images and videos." in response.content
    assert not Post.objects.filter(title="Facebook mixed media").exists()


@pytest.mark.django_db
def test_composer_blocks_facebook_multiple_video_publish(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Facebook multiple videos",
            "body": "This should not queue.",
            "social_accounts": [post_social_account.pk],
            "action": "publish_now",
            "media_uploads": [
                SimpleUploadedFile(
                    "clip-one.mp4",
                    b"\x00\x00\x00\x14ftypmp42video",
                    content_type="video/mp4",
                ),
                SimpleUploadedFile(
                    "clip-two.mp4",
                    b"\x00\x00\x00\x14ftypmp42video",
                    content_type="video/mp4",
                ),
            ],
        },
    )

    assert response.status_code == 200
    assert b"Facebook multiple-video publishing is not enabled yet." in response.content
    assert not Post.objects.filter(title="Facebook multiple videos").exists()


@pytest.mark.django_db
def test_composer_blocks_instagram_carousel_over_ten_items(
    client,
    post_staff_user,
    post_client_record,
    settings,
):
    settings.PUBLISHING_ADAPTER_MODE = "fake"
    instagram = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.INSTAGRAM,
        account_name="Post Client Instagram",
        platform_account_id="instagram-client",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Instagram too many media",
            "body": "This should not queue.",
            "social_accounts": [instagram.pk],
            "action": "publish_now",
            "media_uploads": [
                SimpleUploadedFile(
                    f"campaign-{index}.png",
                    b"\x89PNG\r\n\x1a\nimage-bytes",
                    content_type="image/png",
                )
                for index in range(11)
            ],
        },
    )

    assert response.status_code == 200
    assert b"Instagram carousel posts support up to 10 media files." in response.content
    assert not Post.objects.filter(title="Instagram too many media").exists()


@pytest.mark.django_db
def test_composer_blocks_pinterest_video_publish(
    client,
    post_staff_user,
    post_client_record,
    settings,
):
    settings.PUBLISHING_ADAPTER_MODE = "fake"
    pinterest = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.PINTEREST,
        account_name="Post Client Pinterest",
        platform_account_id="board-123",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Pinterest video",
            "body": "This should not queue.",
            "social_accounts": [pinterest.pk],
            "action": "publish_now",
            "media_uploads": SimpleUploadedFile(
                "clip.mp4",
                b"\x00\x00\x00\x14ftypmp42video",
                content_type="video/mp4",
            ),
        },
    )

    assert response.status_code == 200
    assert b"Pinterest publishing currently supports exactly one image." in response.content
    assert not Post.objects.filter(title="Pinterest video").exists()


@pytest.mark.django_db
def test_composer_blocks_live_pinterest_posts_without_public_storage(
    client,
    post_staff_user,
    post_client_record,
    settings,
):
    settings.PUBLISHING_ADAPTER_MODE = "live"
    settings.PRIVATE_STORAGE_BACKEND = "local"
    pinterest = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.PINTEREST,
        account_name="Post Client Pinterest",
        platform_account_id="board-123",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Pinterest local storage",
            "body": "This should not queue.",
            "social_accounts": [pinterest.pk],
            "action": "publish_now",
            "media_uploads": SimpleUploadedFile(
                "campaign.jpg",
                b"\xff\xd8\xffimage-bytes",
                content_type="image/jpeg",
            ),
        },
    )

    assert response.status_code == 200
    assert b"Pinterest live publishing requires public S3 media storage." in response.content
    assert not Post.objects.filter(title="Pinterest local storage").exists()


@pytest.mark.django_db
def test_composer_converts_png_images_for_instagram_upload(
    client,
    post_staff_user,
    post_client_record,
    settings,
    tmp_path,
):
    settings.PUBLISHING_ADAPTER_MODE = "fake"
    settings.PRIVATE_STORAGE_BACKEND = "local"
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    instagram = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.INSTAGRAM,
        account_name="Post Client Instagram",
        platform_account_id="instagram-client",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Instagram PNG",
            "body": "This should not queue.",
            "social_accounts": [instagram.pk],
            "action": "draft",
            "media_uploads": SimpleUploadedFile(
                "campaign.png",
                _image_bytes(width=800, height=800, image_format="PNG"),
                content_type="image/png",
            ),
        },
    )
    post = Post.objects.get(title="Instagram PNG")
    attachment = PostMedia.objects.get(post=post)
    stored_file = tmp_path / attachment.media.file_key

    assert response.status_code == 302
    assert attachment.media.file_key.endswith(".jpg")
    assert stored_file.read_bytes().startswith(b"\xff\xd8")


@pytest.mark.django_db
def test_composer_queues_wide_jpeg_images_for_instagram_publish(
    client,
    post_staff_user,
    post_client_record,
    settings,
    tmp_path,
):
    settings.PUBLISHING_ADAPTER_MODE = "fake"
    settings.PRIVATE_STORAGE_BACKEND = "local"
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    instagram = SocialAccount.objects.create(
        client=post_client_record,
        platform=Platform.INSTAGRAM,
        account_name="Post Client Instagram",
        platform_account_id="instagram-client",
    )
    client.force_login(post_staff_user)

    with patch("publishing.views.dispatch_post.delay"):
        response = client.post(
            reverse("operator-post-compose"),
            {
                "client": post_client_record.pk,
                "title": "Instagram wide image",
                "body": "This should queue.",
                "social_accounts": [instagram.pk],
                "action": "publish_now",
                "media_uploads": SimpleUploadedFile(
                    "campaign.jpg",
                    _image_bytes(width=720, height=188, image_format="JPEG"),
                    content_type="image/jpeg",
                ),
            },
        )
    post = Post.objects.get(title="Instagram wide image")
    attachment = PostMedia.objects.get(post=post)
    stored_file = tmp_path / attachment.media.file_key
    dimensions = jpeg_dimensions_from_bytes(stored_file.read_bytes())

    assert response.status_code == 302
    assert post.status == PostStatus.QUEUED
    assert dimensions == (720, 377)
    assert not instagram_image_ratio_is_unsupported(dimensions)


@pytest.mark.django_db
def test_composer_rejects_cross_client_existing_media(
    client,
    post_staff_user,
    post_client_record,
    post_social_account,
):
    other_client = Client.objects.create(
        name="Other Media Client",
        slug="other-media-client",
        industry=ClientIndustry.OTHER,
    )
    other_media = Media.objects.create(
        client=other_client,
        file_key="clients/other/media/asset.png",
        media_type="IMAGE",
        size_bytes=10,
        source="OPERATOR",
    )
    client.force_login(post_staff_user)

    response = client.post(
        reverse("operator-post-compose"),
        {
            "client": post_client_record.pk,
            "title": "Wrong media",
            "body": "This should not save.",
            "social_accounts": [post_social_account.pk],
            "existing_media": [other_media.pk],
            "action": "draft",
        },
    )

    assert response.status_code == 200
    assert b"Every selected asset must belong to the selected client." in response.content
    assert not Post.objects.filter(title="Wrong media").exists()


def _image_bytes(*, width: int, height: int, image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format=image_format)
    return output.getvalue()
