from django.db import models

from integrations.models import Platform


class TrendSource(models.TextChoices):
    GOOGLE_TRENDS_KE = "GOOGLE_TRENDS_KE", "Google Trends Kenya"
    TWITTER_TRENDING_KE = "TWITTER_TRENDING_KE", "X trends Kenya"
    NEWS_KE = "NEWS_KE", "Kenyan news"
    OPERATOR_MANUAL = "OPERATOR_MANUAL", "Operator manual"


class SuggestionType(models.TextChoices):
    TREND_BASED = "TREND_BASED", "Trend based"
    EVERGREEN = "EVERGREEN", "Evergreen"
    CAMPAIGN_IDEA = "CAMPAIGN_IDEA", "Campaign idea"
    CAPTION_VARIANT = "CAPTION_VARIANT", "Caption variant"
    HASHTAG_SET = "HASHTAG_SET", "Hashtag set"


class TrendSignal(models.Model):
    topic = models.CharField(max_length=500)
    normalized_topic = models.CharField(max_length=500, db_index=True)
    source = models.CharField(max_length=32, choices=TrendSource.choices)
    source_url = models.URLField(max_length=1000, blank=True)
    popularity_score = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    fetched_at = models.DateTimeField(db_index=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fetched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_topic", "source", "fetched_at"],
                name="uniq_trend_signal_per_source_time",
            ),
        ]

    def __str__(self) -> str:
        return self.topic


class AITrendSuggestion(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="ai_suggestions",
    )
    trend_signal = models.ForeignKey(
        TrendSignal,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )
    trend_topic = models.CharField(max_length=500)
    trend_source = models.CharField(max_length=32, choices=TrendSource.choices)
    suggestion_type = models.CharField(max_length=32, choices=SuggestionType.choices)
    suggested_caption = models.TextField(blank=True)
    suggested_hashtags = models.JSONField(default=list, blank=True)
    suggested_platforms = models.JSONField(default=list, blank=True)
    rationale = models.TextField(blank=True)
    content_angle = models.TextField(blank=True)
    relevance_score = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    fetched_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fetched_at", "-relevance_score"]
        indexes = [
            models.Index(fields=["client", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.client}: {self.trend_topic}"

    def supports_platform(self, platform: Platform) -> bool:
        return platform in self.suggested_platforms
