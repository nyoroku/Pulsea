from django.db import models


class CampaignStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    COMPLETED = "COMPLETED", "Completed"
    ARCHIVED = "ARCHIVED", "Archived"


class Campaign(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=CampaignStatus.choices,
        default=CampaignStatus.ACTIVE,
    )
    color = models.CharField(max_length=7, default="#4f46e5")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "name"],
                name="uniq_campaign_name_per_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client}: {self.name}"
