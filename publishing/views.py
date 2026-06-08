import calendar
from datetime import timedelta
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from campaigns.models import Campaign
from clients.models import Client
from integrations.models import Platform
from integrations.presentation import platform_meta
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
    context = _post_list_context(request)
    return render(request, "operator/posts/list.html", context)


@staff_member_required(login_url="operator-login")
def client_post_list(request, slug):
    client_record = _active_client(slug)
    context = _post_list_context(request, client_record=client_record)
    return render(request, "operator/posts/list.html", context)


def _post_list_context(request, client_record=None):
    posts = Post.objects.select_related("client", "campaign").prefetch_related(
        "targets",
        "targets__social_account",
    )
    selected_status = request.GET.get("status", "")
    selected_client = str(client_record.pk) if client_record else request.GET.get("client", "")
    query = request.GET.get("q", "").strip()
    if selected_status:
        posts = posts.filter(status=selected_status)
    if client_record:
        posts = posts.filter(client=client_record)
    elif selected_client:
        posts = posts.filter(client_id=selected_client)
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(body__icontains=query)
            | Q(client__name__icontains=query)
            | Q(campaign__name__icontains=query)
        )
    context = {
        "post_rows": [_post_row(post) for post in posts],
        "clients": Client.objects.filter(deleted_at__isnull=True),
        "post_statuses": PostStatus.choices,
        "selected_client": selected_client,
        "selected_status": selected_status,
        "query": query,
        "client_record": client_record,
    }
    return context


@staff_member_required(login_url="operator-login")
def post_compose(request):
    return _post_compose(request)


@staff_member_required(login_url="operator-login")
def client_post_compose(request, slug):
    client_record = _active_client(slug)
    return _post_compose(request, client_record=client_record)


def _post_compose(request, client_record=None):
    initial = _compose_initial(request, client_record=client_record)
    form = PostComposerForm(
        request.POST or None,
        request.FILES or None,
        initial=initial,
        client_context=client_record,
    )
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
            if client_record:
                return redirect(
                    "operator-client-post-detail",
                    slug=client_record.slug,
                    pk=post.pk,
                )
            return redirect("operator-post-detail", pk=post.pk)
    return render(
        request,
        "operator/posts/compose.html",
        {
            "form": form,
            "prefill_client": initial.get("client"),
            "prefill_campaign": initial.get("campaign"),
            "client_record": client_record,
            "platform_picker_rows": _platform_picker_rows(form),
        },
    )


@staff_member_required(login_url="operator-login")
def post_calendar(request):
    context = _post_calendar_context(request)
    return render(request, "operator/posts/calendar.html", context)


@staff_member_required(login_url="operator-login")
def client_post_calendar(request, slug):
    client_record = _active_client(slug)
    context = _post_calendar_context(request, client_record=client_record)
    return render(request, "operator/posts/calendar.html", context)


def _post_calendar_context(request, client_record=None):
    today = timezone.localdate()
    selected_client = str(client_record.pk) if client_record else request.GET.get("client", "")
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        month_start = today.replace(year=year, month=month, day=1)
    except ValueError:
        year = today.year
        month = today.month
        month_start = today.replace(day=1)
    month_end = _next_month(month_start)

    posts = Post.objects.select_related("client", "campaign").prefetch_related(
        "targets",
        "targets__social_account",
    )
    posts = posts.filter(
        Q(scheduled_at__date__gte=month_start, scheduled_at__date__lt=month_end)
        | Q(published_at__date__gte=month_start, published_at__date__lt=month_end)
        | Q(created_at__date__gte=month_start, created_at__date__lt=month_end)
    )
    if client_record:
        posts = posts.filter(client=client_record)
    elif selected_client:
        posts = posts.filter(client_id=selected_client)

    posts_by_day = {}
    for post in posts:
        day = _calendar_post_date(post)
        if month_start <= day < month_end:
            posts_by_day.setdefault(day.day, []).append(_post_row(post))

    previous_month = month_start - timedelta(days=1)
    next_month = month_end
    context = {
        "calendar_weeks": _calendar_weeks(month_start, posts_by_day),
        "month_start": month_start,
        "month_label": month_start.strftime("%B %Y"),
        "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "previous_month": previous_month,
        "next_month": next_month,
        "clients": Client.objects.filter(deleted_at__isnull=True),
        "selected_client": selected_client,
        "today": today,
        "client_record": client_record,
    }
    return context


def _compose_initial(request, client_record=None) -> dict:
    initial = {}
    if client_record:
        initial["client"] = client_record
    client_id = request.GET.get("client")
    campaign_id = request.GET.get("campaign")
    if campaign_id:
        campaigns = Campaign.objects.filter(pk=campaign_id).select_related("client")
        if client_record:
            campaigns = campaigns.filter(client=client_record)
        campaign = campaigns.first()
        if campaign:
            initial["campaign"] = campaign
            initial["client"] = campaign.client
            return initial
    if client_record:
        return initial
    if client_id:
        client = Client.objects.filter(pk=client_id, deleted_at__isnull=True).first()
        if client:
            initial["client"] = client
    return initial


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


def _platform_picker_rows(form: PostComposerForm) -> list[dict]:
    selected_values = form["social_accounts"].value() or []
    if isinstance(selected_values, str):
        selected_values = [selected_values]
    selected_ids = {str(value) for value in selected_values}
    return [
        {
            "account": account,
            "meta": platform_meta(account.platform),
            "checked": str(account.pk) in selected_ids,
        }
        for account in form.fields["social_accounts"].queryset
    ]


def _post_row(post: Post) -> dict:
    targets = [
        {
            "target": target,
            "meta": platform_meta(target.platform),
            "badge_class": _target_badge_class(target.status),
        }
        for target in post.targets.all()
    ]
    return {
        "post": post,
        "targets": targets,
        "badge_class": _post_badge_class(post.status),
        "calendar_date": _calendar_post_date(post),
    }


def _calendar_post_date(post: Post):
    timestamp = post.scheduled_at or post.published_at or post.created_at
    return timezone.localtime(timestamp).date()


def _next_month(month_start):
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)


def _calendar_weeks(month_start, posts_by_day: dict[int, list[dict]]) -> list[list[dict]]:
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(
        month_start.year,
        month_start.month,
    ):
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == month_start.month,
                    "posts": (
                        posts_by_day.get(day.day, [])
                        if day.month == month_start.month
                        else []
                    ),
                }
                for day in week
            ]
        )
    return weeks


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
def client_post_detail(request, slug, pk):
    client_record = _active_client(slug)
    post = get_object_or_404(
        Post.objects.select_related("client", "campaign").prefetch_related(
            "targets",
            "targets__social_account",
            "media_attachments__media",
        ),
        pk=pk,
        client=client_record,
    )
    return render(
        request,
        "operator/posts/detail.html",
        {
            "post": post,
            "client_record": client_record,
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


@staff_member_required(login_url="operator-login")
@require_POST
def client_post_retry(request, slug, pk):
    client_record = _active_client(slug)
    post = get_object_or_404(Post, pk=pk, client=client_record)
    manual_retry_failed_targets.delay(post.pk, request.user.pk)
    return redirect("operator-client-post-detail", slug=client_record.slug, pk=post.pk)


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
    meta = platform_meta(target.platform)
    return {
        "target": target,
        "meta": meta,
        "badge_class": _target_badge_class(target.status),
        "note": _target_note(target),
        "action_label": f"Open on {meta['label']}" if target.platform_url else "",
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


def _active_client(slug):
    return get_object_or_404(
        Client,
        slug=slug,
        is_active=True,
        deleted_at__isnull=True,
    )
