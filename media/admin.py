from django.contrib import admin

from .models import Media, PostMedia


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ("label", "client", "media_type", "source", "size_bytes", "created_at")
    list_filter = ("media_type", "source", "client")
    search_fields = ("label", "file_key", "client__name")


admin.site.register(PostMedia)
