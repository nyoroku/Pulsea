from django.contrib import admin

from .models import Campaign


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "status", "start_date", "end_date")
    list_filter = ("status", "client")
    search_fields = ("name", "client__name")
