from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .adapters import get_publisher
from .models import Post, PostAuditEntry, PostAuditEvent, PostStatus, PostTarget, PostTargetStatus

MAX_AUTO_RETRIES = 3
RETRY_DELAYS_SECONDS = (300, 1200, 3600)

@shared_task
def foundation_heartbeat() -> str:
    return "ok"


@shared_task
def enqueue_due_posts() -> list[int]:
    cutoff = timezone.now() + timedelta(minutes=5)
    post_ids = []
    with transaction.atomic():
        posts = (
            Post.objects.select_for_update(skip_locked=True)
            .filter(status=PostStatus.SCHEDULED, scheduled_at__lte=cutoff)
            .order_by("scheduled_at")
        )
        for post in posts:
            post.transition_to(PostStatus.QUEUED, metadata={"source": "enqueue_due_posts"})
            post_ids.append(post.pk)
    for post_id in post_ids:
        dispatch_post.delay(post_id)
    return post_ids


@shared_task
def dispatch_post(post_id: int) -> str:
    with transaction.atomic():
        post = Post.objects.select_for_update().get(pk=post_id)
        if post.status in {PostStatus.PUBLISHED, PostStatus.FAILED, PostStatus.ARCHIVED}:
            return post.status
        if post.status == PostStatus.QUEUED:
            post.transition_to(PostStatus.PUBLISHING, metadata={"source": "dispatch_post"})
        elif post.status != PostStatus.PUBLISHING:
            return post.status
        target_ids = list(
            post.targets.filter(status=PostTargetStatus.PENDING).values_list("pk", flat=True)
        )
    for target_id in target_ids:
        publish_target(target_id)
    post.refresh_from_db()
    return post.status


@shared_task
def retry_target(target_id: int, allow_published_post: bool = False) -> str:
    return publish_target(target_id, allow_published_post=allow_published_post)


@shared_task
def manual_retry_failed_targets(post_id: int, actor_id: int | None = None) -> list[int]:
    with transaction.atomic():
        post = Post.objects.select_for_update().get(pk=post_id)
        target_ids = list(
            post.targets.filter(status=PostTargetStatus.FAILED).values_list("pk", flat=True)
        )
        if not target_ids:
            return []
        post.targets.filter(pk__in=target_ids).update(
            status=PostTargetStatus.PENDING,
            error_message="",
            next_retry_at=None,
        )
        PostAuditEntry.objects.create(
            post=post,
            actor_id=actor_id,
            event_type=PostAuditEvent.RETRIED,
            previous_status=post.status,
            new_status=post.status,
            metadata_json={"target_ids": target_ids},
        )
        if post.status == PostStatus.FAILED:
            post.transition_to(
                PostStatus.QUEUED,
                metadata={"source": "manual_retry"},
            )
            transaction.on_commit(lambda: dispatch_post.delay(post.pk))
        else:
            transaction.on_commit(
                lambda: [
                    retry_target.delay(target_id, allow_published_post=True)
                    for target_id in target_ids
                ]
            )
        return target_ids


def publish_target(target_id: int, *, allow_published_post: bool = False) -> str:
    with transaction.atomic():
        target = PostTarget.objects.select_for_update().select_related("post").get(pk=target_id)
        if target.status == PostTargetStatus.PUBLISHED:
            return target.status
        can_publish = target.post.status == PostStatus.PUBLISHING
        can_retry_partial = allow_published_post and target.post.status == PostStatus.PUBLISHED
        if not can_publish and not can_retry_partial:
            return target.status
        target.status = PostTargetStatus.PUBLISHING
        target.save(update_fields=["status", "updated_at"])

    try:
        result = get_publisher(target).publish(target)
    except FileNotFoundError:
        result = _publish_result(
            "The selected media file is no longer available in storage. "
            "Reupload it before retrying."
        )
    except Exception:
        result = _publish_result(
            "Publishing failed unexpectedly. Check the worker logs before retrying."
        )

    with transaction.atomic():
        target = PostTarget.objects.select_for_update().select_related("post").get(pk=target_id)
        target.error_message = result.error_message
        target.next_retry_at = None
        if result.success:
            target.status = PostTargetStatus.PUBLISHED
            target.platform_post_id = result.platform_post_id
            target.platform_url = result.platform_url
            target.published_at = timezone.now()
        elif result.retryable and target.retry_count < MAX_AUTO_RETRIES:
            delay_seconds = RETRY_DELAYS_SECONDS[target.retry_count]
            target.retry_count += 1
            target.status = PostTargetStatus.PENDING
            target.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
            transaction.on_commit(
                lambda: retry_target.apply_async(
                    args=[target_id, allow_published_post],
                    countdown=delay_seconds,
                )
            )
        else:
            target.status = PostTargetStatus.FAILED
        target.save(
            update_fields=[
                "status",
                "platform_post_id",
                "platform_url",
                "published_at",
                "error_message",
                "retry_count",
                "next_retry_at",
                "updated_at",
            ]
        )
        target.post.recalculate_terminal_status()
        return target.status


def _publish_result(error_message: str):
    from .adapters import PublishResult

    return PublishResult(success=False, error_message=error_message)
