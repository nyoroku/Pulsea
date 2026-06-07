from django.contrib import admin

from .models import AITrendSuggestion, TrendSignal


@admin.register(TrendSignal)
class TrendSignalAdmin(admin.ModelAdmin):
    list_display = ("topic", "source", "popularity_score", "fetched_at")
    list_filter = ("source",)
    search_fields = ("topic", "normalized_topic")


@admin.register(AITrendSuggestion)
class AITrendSuggestionAdmin(admin.ModelAdmin):
    list_display = ("trend_topic", "client", "trend_source", "relevance_score", "expires_at")
    list_filter = ("trend_source", "suggestion_type", "is_used", "is_dismissed")
    search_fields = ("trend_topic", "suggested_caption", "client__name")
