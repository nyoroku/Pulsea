from django.contrib import admin

from .models import SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ("account_name", "client", "platform", "connection_health", "is_active")
    list_filter = ("platform", "connection_health", "is_active")
    search_fields = ("account_name", "client__name", "platform_account_id")
    exclude = ("access_token", "refresh_token")
