from django.conf import settings
from django.db import models


class MediaType(models.TextChoices):
    IMAGE = "IMAGE", "Image"
    VIDEO = "VIDEO", "Video"


class MediaSource(models.TextChoices):
    OPERATOR = "OPERATOR", "Operator"
    CLIENT = "CLIENT", "Client"


class Media(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="media")
    post = models.ForeignKey(
        "publishing.Post",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="media",
    )
    file_key = models.CharField(max_length=1000)
    media_type = models.CharField(max_length=16, choices=MediaType.choices)
    width = models.PositiveIntegerField(blank=True, null=True)
    height = models.PositiveIntegerField(blank=True, null=True)
    duration_seconds = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_media",
    )
    source = models.CharField(max_length=16, choices=MediaSource.choices)
    label = models.CharField(max_length=180, blank=True)
    note = models.TextField(blank=True)
    thumbnail_key = models.CharField(max_length=1000, blank=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "media_type"]),
            models.Index(fields=["client", "source"]),
        ]

    def __str__(self) -> str:
        return self.label or self.file_key


class PostMedia(models.Model):
    post = models.ForeignKey(
        "publishing.Post",
        on_delete=models.CASCADE,
        related_name="media_attachments",
    )
    media = models.ForeignKey(Media, on_delete=models.PROTECT, related_name="post_attachments")
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "media"],
                name="uniq_media_attachment_per_post",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.post}: {self.media}"
