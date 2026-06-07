from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    POST_PUBLISHED = "POST_PUBLISHED", "Post published"
    POST_FAILED = "POST_FAILED", "Post failed"
    POST_COMMENT = "POST_COMMENT", "Post comment"
    ASSET_UPLOADED = "ASSET_UPLOADED", "Asset uploaded"
    REQUEST_RECEIVED = "REQUEST_RECEIVED", "Request received"
    REQUEST_STATUS_CHANGED = "REQUEST_STATUS_CHANGED", "Request status changed"
    REQUEST_COMMENT = "REQUEST_COMMENT", "Request comment"
    TOKEN_EXPIRING = "TOKEN_EXPIRING", "Token expiring"
    UNIFIED_COMMENT_NEW = "UNIFIED_COMMENT_NEW", "New unified comment"
    AI_SUGGESTIONS_READY = "AI_SUGGESTIONS_READY", "AI suggestions ready"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=32, choices=NotificationType.choices)
    title = models.CharField(max_length=240)
    body = models.TextField()
    link = models.CharField(max_length=1000, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self) -> str:
        return f"{self.recipient}: {self.title}"


class NotificationPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    type = models.CharField(max_length=32, choices=NotificationType.choices)
    email_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type"],
                name="uniq_notification_preference_per_user_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user}: {self.get_type_display()}"
