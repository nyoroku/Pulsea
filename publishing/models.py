from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from integrations.models import Platform


class PostStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SCHEDULED = "SCHEDULED", "Scheduled"
    QUEUED = "QUEUED", "Queued"
    PUBLISHING = "PUBLISHING", "Publishing"
    PUBLISHED = "PUBLISHED", "Published"
    FAILED = "FAILED", "Failed"
    ARCHIVED = "ARCHIVED", "Archived"


class PostTargetStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PUBLISHING = "PUBLISHING", "Publishing"
    PUBLISHED = "PUBLISHED", "Published"
    FAILED = "FAILED", "Failed"


class FirstCommentStatus(models.TextChoices):
    NOT_REQUESTED = "NOT_REQUESTED", "Not requested"
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class PostLabel(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="post_labels",
    )
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=7, default="#64748b")

    class Meta:
        ordering = ["client", "name"]
        constraints = [
            models.UniqueConstraint(fields=["client", "name"], name="uniq_post_label_per_client"),
        ]

    def __str__(self) -> str:
        return f"{self.client}: {self.name}"


class PostQueue(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="queue_slots",
    )
    social_account = models.ForeignKey(
        "integrations.SocialAccount",
        on_delete=models.CASCADE,
        related_name="queue_slots",
    )
    day_of_week = models.PositiveSmallIntegerField()
    time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["client", "social_account", "day_of_week", "time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(day_of_week__gte=0, day_of_week__lte=6),
                name="queue_day_of_week_between_0_and_6",
            ),
            models.UniqueConstraint(
                fields=["social_account", "day_of_week", "time"],
                name="uniq_queue_slot_per_social_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.social_account} day={self.day_of_week} at {self.time}"


class Post(models.Model):
    ALLOWED_TRANSITIONS = {
        PostStatus.DRAFT: {PostStatus.SCHEDULED, PostStatus.QUEUED, PostStatus.ARCHIVED},
        PostStatus.SCHEDULED: {PostStatus.QUEUED, PostStatus.ARCHIVED},
        PostStatus.QUEUED: {PostStatus.PUBLISHING, PostStatus.ARCHIVED},
        PostStatus.PUBLISHING: {PostStatus.PUBLISHED, PostStatus.FAILED, PostStatus.ARCHIVED},
        PostStatus.PUBLISHED: {PostStatus.ARCHIVED},
        PostStatus.FAILED: {PostStatus.QUEUED, PostStatus.ARCHIVED},
        PostStatus.ARCHIVED: set(),
    }

    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="posts")
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="posts",
    )
    title = models.CharField(max_length=240)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=PostStatus.choices, default=PostStatus.DRAFT)
    scheduled_at = models.DateTimeField(blank=True, null=True, db_index=True)
    published_at = models.DateTimeField(blank=True, null=True)
    labels = models.ManyToManyField(PostLabel, blank=True, related_name="posts")
    first_comment_body = models.TextField(blank=True)
    queue_slot = models.ForeignKey(
        PostQueue,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="posts",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_posts",
    )
    is_clone_of = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="clones",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "status"]),
            models.Index(fields=["status", "scheduled_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def transition_to(self, new_status: str, *, actor=None, metadata: dict | None = None) -> None:
        if new_status == self.status:
            return
        if new_status not in self.ALLOWED_TRANSITIONS[self.status]:
            raise ValidationError(f"Post cannot transition from {self.status} to {new_status}.")
        previous_status = self.status
        self.status = new_status
        update_fields = ["status", "updated_at"]
        if new_status == PostStatus.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            update_fields.append("published_at")
        self.save(update_fields=update_fields)
        PostAuditEntry.objects.create(
            post=self,
            actor=actor,
            event_type=PostAuditEvent.STATUS_CHANGED,
            previous_status=previous_status,
            new_status=new_status,
            metadata_json=metadata or {},
        )

    def recalculate_terminal_status(self, *, actor=None) -> str:
        statuses = list(self.targets.values_list("status", flat=True))
        if not statuses or any(
            status in {PostTargetStatus.PENDING, PostTargetStatus.PUBLISHING} for status in statuses
        ):
            return self.status
        terminal_status = (
            PostStatus.PUBLISHED if PostTargetStatus.PUBLISHED in statuses else PostStatus.FAILED
        )
        self.transition_to(terminal_status, actor=actor)
        return terminal_status


class PostTarget(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="targets")
    social_account = models.ForeignKey(
        "integrations.SocialAccount",
        on_delete=models.PROTECT,
        related_name="post_targets",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)
    status = models.CharField(
        max_length=16,
        choices=PostTargetStatus.choices,
        default=PostTargetStatus.PENDING,
    )
    platform_post_id = models.CharField(max_length=255, blank=True)
    platform_url = models.URLField(max_length=1000, blank=True)
    published_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(blank=True, null=True)
    first_comment_status = models.CharField(
        max_length=16,
        choices=FirstCommentStatus.choices,
        default=FirstCommentStatus.NOT_REQUESTED,
    )
    first_comment_error = models.TextField(blank=True)
    first_comment_platform_id = models.CharField(max_length=255, blank=True)
    first_comment_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["post", "platform"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "social_account"],
                name="uniq_social_account_target_per_post",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.post}: {self.get_platform_display()}"


class PostPlatformConfig(models.Model):
    post_target = models.OneToOneField(
        PostTarget,
        on_delete=models.CASCADE,
        related_name="platform_config",
    )
    config_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Config for {self.post_target}"


class PostTargetMetricSnapshot(models.Model):
    post_target = models.ForeignKey(PostTarget, on_delete=models.CASCADE, related_name="metrics")
    metrics_json = models.JSONField(default=dict)
    collected_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-collected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post_target", "collected_at"],
                name="uniq_metric_snapshot_per_target_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.post_target} metrics at {self.collected_at}"


class PostAuditEvent(models.TextChoices):
    CREATED = "CREATED", "Created"
    UPDATED = "UPDATED", "Updated"
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"
    RETRIED = "RETRIED", "Retried"


class PostAuditEntry(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="audit_entries")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="post_audit_entries",
    )
    event_type = models.CharField(max_length=32, choices=PostAuditEvent.choices)
    previous_status = models.CharField(max_length=16, choices=PostStatus.choices, blank=True)
    new_status = models.CharField(max_length=16, choices=PostStatus.choices, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.post}: {self.get_event_type_display()}"


class BulkImportStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    VALIDATED = "VALIDATED", "Validated"
    IMPORTED = "IMPORTED", "Imported"
    FAILED = "FAILED", "Failed"


class BulkImport(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="bulk_imports",
    )
    source_file_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16,
        choices=BulkImportStatus.choices,
        default=BulkImportStatus.UPLOADED,
    )
    row_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="bulk_imports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.client}: {self.source_file_name}"


class BulkImportRow(models.Model):
    bulk_import = models.ForeignKey(BulkImport, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    data_json = models.JSONField(default=dict)
    errors_json = models.JSONField(default=list, blank=True)
    imported_post = models.ForeignKey(
        Post,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="bulk_import_rows",
    )

    class Meta:
        ordering = ["bulk_import", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["bulk_import", "row_number"],
                name="uniq_bulk_import_row_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bulk_import} row {self.row_number}"
