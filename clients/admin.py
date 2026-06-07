from django.contrib import admin

from .models import Client, ClientUser


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "is_active", "created_at")
    list_filter = ("industry", "is_active")
    search_fields = ("name", "slug")


@admin.register(ClientUser)
class ClientUserAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "client__name")
