from django.conf import settings
from django.db import models


class ClientIndustry(models.TextChoices):
    RESTAURANT = "RESTAURANT", "Restaurant"
    RETAIL = "RETAIL", "Retail"
    HOSPITALITY = "HOSPITALITY", "Hospitality"
    HEALTHCARE = "HEALTHCARE", "Healthcare"
    REAL_ESTATE = "REAL_ESTATE", "Real estate"
    EDUCATION = "EDUCATION", "Education"
    BEAUTY = "BEAUTY", "Beauty"
    FINANCE = "FINANCE", "Finance"
    NGO = "NGO", "NGO"
    EVENTS = "EVENTS", "Events"
    OTHER = "OTHER", "Other"


class Client(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True)
    logo_key = models.CharField(max_length=500, blank=True)
    industry = models.CharField(max_length=32, choices=ClientIndustry.choices)
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClientUser(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="portal_users")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client", "user__email"]

    def __str__(self) -> str:
        return f"{self.user} ({self.client})"
