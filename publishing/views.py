from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clients.models import Client
from integrations.models import Platform
from media.image_processing import normalize_instagram_feed_image_upload
from media.models import MediaSource, MediaType, PostMedia
from media.services import upload_media
from media.storage import get_private_storage

from .forms import PostComposerForm
from .models import (
    Post,
    PostAuditEntry,
    PostAuditEvent,
    PostStatus,
    PostTarget,
    PostTargetStatus,
)
from .tasks import dispatch_post, manual_retry_failed_targets


@staff_member_required(login_url="operator-login")
def post_list(request):
    posts = Post.objects.select_related("client", "campaign").prefetch_related("targets")
    selected_status = request.GET.get("status", "")
    selected_client = request.GET.get("client", "")
    if selected_status:
        posts = posts.filter(status=selected_status)
    if selected_client:
        posts = posts.filter(client_id=selected_client)
    context = {
        "posts": posts,
        "clients": Client.objects.filter(deleted_at__isnull=True),
        "post_statuses": PostStatus.choices,
        "selected_client": selected_client,
        "selected_status": selected_status,
    }
    return render(request, "operator/posts/list.html", context)


@staff_member_required(login_url="operator-login")
def post_compose(request):
    form = PostComposerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "draft")
        if action == "schedule" and not form.cleaned_data["scheduled_at"]:
            form.add_error("scheduled_at", "Choose a schedule time before scheduling this post.")
        elif action not in {"draft", "schedule", "publish_now"}:
            form.add_error(None, "Unknown composer action.")
        elif action != "draft" and not _validate_publish_readiness(form):
            pass
        else:
            uploaded_media_items = []
            try:
                with transaction.atomic():
                    post = form.save(commit=False)
                    post.created_by = request.user
                    if action == "schedule":
                        post.status = PostStatus.SCHEDULED
                    elif action == "publish_now":
                        post.status = PostStatus.QUEUED
                    post.save()
                    media_items = list(form.cleaned_data["existing_media"])
                    media_uploads = _prepare_media_uploads_for_targets(form)
                    for media_upload in media_uploads:
                        uploaded_media = upload_media(
                            client=post.client,
                            uploaded_file=media_upload,
                            source=MediaSource.OPERATOR,
                            uploaded_by=request.user,
                            label=media_upload.name,
                        )
                        media_items.append(uploaded_media)
                        uploaded_media_items.append(uploaded_media)
                    for position, media_item in enumerate(media_items):
                        PostMedia.objects.create(
                            post=post,
                            media=media_item,
                            position=position,
                        )
                    for social_account in form.cleaned_data["social_accounts"]:
                        PostTarget.objects.create(
                            post=post,
                            social_account=social_account,
                            platform=social_account.platform,
                        )
                    PostAuditEntry.objects.create(
                        post=post,
                        actor=request.user,
                        event_type=PostAuditEvent.CREATED,
                        new_status=post.status,
                        metadata_json={"source": "operator_composer"},
                    )
                    if action == "publish_now":
                        transaction.on_commit(lambda: dispatch_post.delay(post.pk))
            except Exception:
                storage = get_private_storage()
                for uploaded_media in uploaded_media_items:
                    storage.delete(uploaded_media.file_key)
                raise
            return redirect("operator-post-detail", pk=post.pk)
    return render(request, "operator/posts/compose.html", {"form": form})


def _validate_publish_readiness(form: PostComposerForm) -> bool:
    social_accounts = form.cleaned_data["social_accounts"]
    existing_media = list(form.cleaned_data["existing_media"])
    media_uploads = form.cleaned_data["media_uploads"]
    media_types = _selected_media_types(existing_media, media_uploads)
    media_count = len(existing_media) + len(media_uploads)

    if any(account.platform == Platform.FACEBOOK for account in social_accounts):
        if MediaType.IMAGE in media_types and MediaType.VIDEO in media_types:
            form.add_error("media_uploads", "Facebook posts cannot mix images and videos.")
            return False
        if sum(1 for media_type in media_types if media_type == MediaType.VIDEO) > 1:
            form.add_error(
                "media_uploads",
                "Facebook multiple-video publishing is not enabled yet.",
            )
            return False

    if any(account.platform == Platform.PINTEREST for account in social_accounts):
        if media_count == 0:
            form.add_error("media_uploads", "Pinterest posts require one image.")
            return False
        if media_count != 1 or MediaType.VIDEO in media_types:
            form.add_error(
                "media_uploads",
                "Pinterest publishing currently supports exactly one image.",
            )
            return False
        if settings.PUBLISHING_ADAPTER_MODE == "live" and settings.PRIVATE_STORAGE_BACKEND != "s3":
            form.add_error(
                "media_uploads",
                "Pinterest live publishing requires public S3 media storage.",
            )
            return False

    if not any(account.platform == Platform.INSTAGRAM for account in social_accounts):
        return True

    if not existing_media and not media_uploads:
        form.add_error(
            "media_uploads",
            "Instagram posts require at least one image or video.",
        )
        return False

    if settings.PUBLISHING_ADAPTER_MODE == "live" and settings.PRIVATE_STORAGE_BACKEND != "s3":
        form.add_error(
            "media_uploads",
            "Instagram live publishing requires public S3 media storage.",
        )
        return False

    if media_count > 10:
        form.add_error("media_uploads", "Instagram carousel posts support up to 10 media files.")
        return False

    return True


def _prepare_media_uploads_for_targets(form: PostComposerForm):
    media_uploads = form.cleaned_data["media_uploads"]
    social_accounts = form.cleaned_data["social_accounts"]
    if not any(account.platform == Platform.INSTAGRAM for account in social_accounts):
        return media_uploads
    return [normalize_instagram_feed_image_upload(media_upload) for media_upload in media_uploads]


def _selected_media_types(existing_media, media_uploads) -> list[str]:
    return [
        *[media_item.media_type for media_item in existing_media],
        *[_upload_media_type(media_upload.name) for media_upload in media_uploads],
    ]


def _upload_media_type(filename: str) -> str:
    suffix = PurePosixPath(str(filename).replace("\\", "/")).suffix.lower()
    if suffix in {".mp4", ".mov"}:
        return MediaType.VIDEO
    return MediaType.IMAGE


@staff_member_required(login_url="operator-login")
def post_detail(request, pk):
    post = get_object_or_404(
        Post.objects.select_related("client", "campaign").prefetch_related(
            "targets",
            "targets__social_account",
            "media_attachments__media",
        ),
        pk=pk,
    )
    return render(
        request,
        "operator/posts/detail.html",
        {
            "post": post,
            "has_failed_targets": post.targets.filter(status=PostTargetStatus.FAILED).exists(),
            "media_previews": _media_previews(post),
            "target_cards": [_target_card(target) for target in post.targets.all()],
            "post_badge_class": _post_badge_class(post.status),
        },
    )


@staff_member_required(login_url="operator-login")
@require_POST
def post_retry(request, pk):
    post = get_object_or_404(Post, pk=pk)
    manual_retry_failed_targets.delay(post.pk, request.user.pk)
    return redirect("operator-post-detail", pk=post.pk)


def _media_previews(post: Post) -> list[dict]:
    storage = None
    previews = []
    for attachment in post.media_attachments.all():
        media = attachment.media
        preview_url = ""
        try:
            storage = storage or get_private_storage()
            preview_url = storage.url(media.file_key)
        except Exception:
            preview_url = ""
        previews.append(
            {
                "media": media,
                "preview_url": preview_url,
                "filename": media.label or media.file_key.rsplit("/", 1)[-1],
                "is_missing": not preview_url,
            }
        )
    return previews


def _target_card(target: PostTarget) -> dict:
    return {
        "target": target,
        "badge_class": _target_badge_class(target.status),
        "note": _target_note(target),
        "action_label": f"Open on {target.get_platform_display()}" if target.platform_url else "",
    }


def _target_badge_class(status: str) -> str:
    if status == PostTargetStatus.PUBLISHED:
        return "badge-good"
    if status == PostTargetStatus.FAILED:
        return "badge-bad"
    if status in {PostTargetStatus.PENDING, PostTargetStatus.PUBLISHING}:
        return "badge-warn"
    return "badge-muted"


def _post_badge_class(status: str) -> str:
    if status == PostStatus.PUBLISHED:
        return "badge-good"
    if status == PostStatus.FAILED:
        return "badge-bad"
    if status in {PostStatus.QUEUED, PostStatus.PUBLISHING, PostStatus.SCHEDULED}:
        return "badge-warn"
    return "badge-muted"


def _target_note(target: PostTarget) -> str:
    if target.error_message:
        return target.error_message
    if target.status == PostTargetStatus.PUBLISHED:
        return "Published successfully. Use the link to confirm it on the platform."
    if target.status == PostTargetStatus.PUBLISHING:
        if any(
            attachment.media.media_type == MediaType.VIDEO
            for attachment in target.post.media_attachments.all()
        ):
            return (
                "Pulsea is uploading or waiting for platform video processing. "
                "Instagram Reels can take a few minutes."
            )
        return (
            "Pulsea is uploading or waiting for platform processing. "
            "Instagram media can take about a minute."
        )
    if target.status == PostTargetStatus.PENDING and target.next_retry_at:
        return f"Retry scheduled for {target.next_retry_at}."
    if target.status == PostTargetStatus.PENDING:
        return "Waiting in the publishing queue."
    return "No issues reported."
