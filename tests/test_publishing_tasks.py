from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from clients.models import Client, ClientIndustry
from integrations.models import Platform, SocialAccount
from publishing.models import (
    Post,
    PostAuditEvent,
    PostPlatformConfig,
    PostStatus,
    PostTarget,
    PostTargetStatus,
)
from publishing.tasks import (
    dispatch_post,
    enqueue_due_posts,
    manual_retry_failed_targets,
    publish_target,
    retry_target,
)


@pytest.fixture
def publishing_client():
    return Client.objects.create(
        name="Publishing Client",
        slug="publishing-client",
        industry=ClientIndustry.OTHER,
    )


def make_target(post, *, platform, account_id, behavior="success"):
    social_account = SocialAccount.objects.create(
        client=post.client,
        platform=platform,
        account_name=f"{platform} account",
        platform_account_id=account_id,
    )
    target = PostTarget.objects.create(
        post=post,
        social_account=social_account,
        platform=platform,
    )
    PostPlatformConfig.objects.create(
        post_target=target,
        config_json={"fake_behavior": behavior},
    )
    return target


@pytest.mark.django_db
def test_enqueue_due_posts_queues_due_scheduled_posts(publishing_client):
    due_post = Post.objects.create(
        client=publishing_client,
        title="Due post",
        status=PostStatus.SCHEDULED,
        scheduled_at=timezone.now(),
    )
    future_post = Post.objects.create(
        client=publishing_client,
        title="Future post",
        status=PostStatus.SCHEDULED,
        scheduled_at=timezone.now() + timedelta(hours=1),
    )

    with patch("publishing.tasks.dispatch_post.delay") as dispatch_delay:
        assert enqueue_due_posts() == [due_post.pk]

    due_post.refresh_from_db()
    future_post.refresh_from_db()
    assert due_post.status == PostStatus.QUEUED
    assert future_post.status == PostStatus.SCHEDULED
    dispatch_delay.assert_called_once_with(due_post.pk)


@pytest.mark.django_db
def test_fake_publisher_marks_successful_post_published(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Publish me",
        status=PostStatus.QUEUED,
    )
    target = make_target(
        post,
        platform=Platform.FACEBOOK,
        account_id="facebook-success",
    )

    assert dispatch_post(post.pk) == PostStatus.PUBLISHED

    post.refresh_from_db()
    target.refresh_from_db()
    assert post.published_at is not None
    assert target.status == PostTargetStatus.PUBLISHED
    assert target.platform_post_id == f"fake-{target.pk}"


@pytest.mark.django_db
def test_fake_retryable_failure_can_recover(publishing_client):
    post = Post.objects.create(client=publishing_client, title="Retry me", status=PostStatus.QUEUED)
    target = make_target(
        post,
        platform=Platform.INSTAGRAM,
        account_id="instagram-retry",
        behavior="temporary_failure",
    )

    assert dispatch_post(post.pk) == PostStatus.PUBLISHING

    target.refresh_from_db()
    assert target.status == PostTargetStatus.PENDING
    assert target.retry_count == 1
    assert target.next_retry_at is not None

    assert retry_target(target.pk) == PostTargetStatus.PUBLISHED

    post.refresh_from_db()
    target.refresh_from_db()
    assert post.status == PostStatus.PUBLISHED
    assert target.next_retry_at is None


@pytest.mark.django_db
def test_fake_permanent_failure_marks_post_failed(publishing_client):
    post = Post.objects.create(client=publishing_client, title="Fail me", status=PostStatus.QUEUED)
    target = make_target(
        post,
        platform=Platform.TIKTOK,
        account_id="tiktok-failure",
        behavior="permanent_failure",
    )

    assert dispatch_post(post.pk) == PostStatus.FAILED

    target.refresh_from_db()
    assert target.status == PostTargetStatus.FAILED
    assert target.error_message == "Fake permanent publishing failure."


@pytest.mark.django_db
def test_publish_target_marks_missing_media_failed(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Missing media",
        status=PostStatus.PUBLISHING,
    )
    target = make_target(
        post,
        platform=Platform.INSTAGRAM,
        account_id="instagram-missing-media",
    )

    with patch("publishing.tasks.get_publisher") as get_publisher:
        get_publisher.return_value.publish.side_effect = FileNotFoundError("missing")
        assert publish_target(target.pk) == PostTargetStatus.FAILED

    target.refresh_from_db()
    assert target.status == PostTargetStatus.FAILED
    assert target.error_message == (
        "The selected media file is no longer available in storage. "
        "Reupload it before retrying."
    )


@pytest.mark.django_db
def test_fake_partial_success_marks_post_published(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Partly publish me",
        status=PostStatus.QUEUED,
    )
    successful_target = make_target(
        post,
        platform=Platform.FACEBOOK,
        account_id="facebook-partial",
    )
    failed_target = make_target(
        post,
        platform=Platform.TIKTOK,
        account_id="tiktok-partial",
        behavior="permanent_failure",
    )

    assert dispatch_post(post.pk) == PostStatus.PUBLISHED

    successful_target.refresh_from_db()
    failed_target.refresh_from_db()
    assert successful_target.status == PostTargetStatus.PUBLISHED
    assert failed_target.status == PostTargetStatus.FAILED


@pytest.mark.django_db
def test_fake_retryable_failure_stops_after_three_auto_retries(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Eventually fail",
        status=PostStatus.QUEUED,
    )
    target = make_target(
        post,
        platform=Platform.INSTAGRAM,
        account_id="instagram-exhaust",
        behavior="temporary_failure",
    )
    target.platform_config.config_json["failures_before_success"] = 4
    target.platform_config.save(update_fields=["config_json"])

    assert dispatch_post(post.pk) == PostStatus.PUBLISHING
    assert retry_target(target.pk) == PostTargetStatus.PENDING
    assert retry_target(target.pk) == PostTargetStatus.PENDING
    assert retry_target(target.pk) == PostTargetStatus.FAILED

    post.refresh_from_db()
    target.refresh_from_db()
    assert post.status == PostStatus.FAILED
    assert target.retry_count == 3
    assert target.next_retry_at is None


@pytest.mark.django_db
def test_manual_retry_requeues_fully_failed_post(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Manual retry",
        status=PostStatus.FAILED,
    )
    target = make_target(
        post,
        platform=Platform.FACEBOOK,
        account_id="facebook-manual-retry",
    )
    target.status = PostTargetStatus.FAILED
    target.error_message = "Previous failure."
    target.save(update_fields=["status", "error_message", "updated_at"])

    assert manual_retry_failed_targets(post.pk) == [target.pk]

    post.refresh_from_db()
    target.refresh_from_db()
    assert post.status == PostStatus.QUEUED
    assert target.status == PostTargetStatus.PENDING
    assert post.audit_entries.filter(event_type=PostAuditEvent.RETRIED).exists()

    assert dispatch_post(post.pk) == PostStatus.PUBLISHED


@pytest.mark.django_db
def test_manual_retry_can_recover_failed_target_on_partial_publish(publishing_client):
    post = Post.objects.create(
        client=publishing_client,
        title="Partial manual retry",
        status=PostStatus.PUBLISHED,
    )
    target = make_target(
        post,
        platform=Platform.INSTAGRAM,
        account_id="instagram-partial-manual-retry",
    )
    target.status = PostTargetStatus.FAILED
    target.error_message = "Previous failure."
    target.save(update_fields=["status", "error_message", "updated_at"])

    assert manual_retry_failed_targets(post.pk) == [target.pk]
    assert retry_target(target.pk, allow_published_post=True) == PostTargetStatus.PUBLISHED

    post.refresh_from_db()
    target.refresh_from_db()
    assert post.status == PostStatus.PUBLISHED
    assert target.status == PostTargetStatus.PUBLISHED
