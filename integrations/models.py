from django.db import models

from .fields import EncryptedTextField


class Platform(models.TextChoices):
    GBP = "GBP", "Google Business Profile"
    FACEBOOK = "FACEBOOK", "Facebook"
    TIKTOK = "TIKTOK", "TikTok"
    INSTAGRAM = "INSTAGRAM", "Instagram"
    PINTEREST = "PINTEREST", "Pinterest"
    YOUTUBE = "YOUTUBE", "YouTube"
    LINKEDIN = "LINKEDIN", "LinkedIn"
    TWITTER = "TWITTER", "X / Twitter"


class ConnectionHealth(models.TextChoices):
    CONNECTED = "CONNECTED", "Connected"
    EXPIRING = "EXPIRING", "Token expiring soon"
    DISCONNECTED = "DISCONNECTED", "Disconnected"
    ERROR = "ERROR", "Error"


class SocialAccount(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)
    account_name = models.CharField(max_length=180)
    access_token = EncryptedTextField(blank=True)
    refresh_token = EncryptedTextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    platform_account_id = models.CharField(max_length=255, blank=True)
    location_id = models.CharField(max_length=255, blank=True)
    page_id = models.CharField(max_length=255, blank=True)
    channel_id = models.CharField(max_length=255, blank=True)
    instagram_business_account_id = models.CharField(max_length=255, blank=True)
    connection_health = models.CharField(
        max_length=16,
        choices=ConnectionHealth.choices,
        default=ConnectionHealth.CONNECTED,
    )
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client", "platform", "account_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "platform", "platform_account_id"],
                condition=~models.Q(platform_account_id=""),
                name="uniq_remote_social_account_per_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client}: {self.get_platform_display()} - {self.account_name}"
