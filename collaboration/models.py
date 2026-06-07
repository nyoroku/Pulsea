from django.conf import settings
from django.db import models

from integrations.models import Platform


class PostComment(models.Model):
    post = models.ForeignKey("publishing.Post", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="post_comments",
    )
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.author} on {self.post}"


class ContentRequestStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    DONE = "DONE", "Done"
    CANCELLED = "CANCELLED", "Cancelled"


class ContentRequest(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="content_requests",
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="content_requests",
    )
    title = models.CharField(max_length=240)
    post_type = models.CharField(max_length=80)
    brief = models.TextField()
    reference_media = models.ManyToManyField(
        "media.Media",
        blank=True,
        related_name="content_requests",
    )
    deadline = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=ContentRequestStatus.choices,
        default=ContentRequestStatus.RECEIVED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_content_requests",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assigned_content_requests",
    )
    linked_post = models.ForeignKey(
        "publishing.Post",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="content_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.client}: {self.title}"


class ContentRequestTarget(models.Model):
    content_request = models.ForeignKey(
        ContentRequest,
        on_delete=models.CASCADE,
        related_name="targets",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["content_request", "platform"],
                name="uniq_platform_per_content_request",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.content_request}: {self.get_platform_display()}"


class ContentRequestComment(models.Model):
    content_request = models.ForeignKey(
        ContentRequest,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="content_request_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.author} on {self.content_request}"


class ContentRequestStatusEvent(models.Model):
    content_request = models.ForeignKey(
        ContentRequest,
        on_delete=models.CASCADE,
        related_name="status_events",
    )
    status = models.CharField(max_length=16, choices=ContentRequestStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="content_request_status_events",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.content_request}: {self.get_status_display()}"


class UnifiedComment(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="unified_comments",
    )
    post_target = models.ForeignKey(
        "publishing.PostTarget",
        on_delete=models.CASCADE,
        related_name="unified_comments",
    )
    platform_comment_id = models.CharField(max_length=255)
    author_name = models.CharField(max_length=255)
    body = models.TextField()
    remote_created_at = models.DateTimeField()
    is_read = models.BooleanField(default=False)
    is_replied = models.BooleanField(default=False)
    reply_body = models.TextField(blank=True)
    is_hidden = models.BooleanField(default=False)
    is_spam_suspected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-remote_created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post_target", "platform_comment_id"],
                name="uniq_remote_comment_per_target",
            ),
        ]
        indexes = [
            models.Index(fields=["client", "is_read"]),
        ]

    def __str__(self) -> str:
        return f"{self.author_name} on {self.post_target}"
