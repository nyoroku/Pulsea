from django.contrib import admin

from .models import (
    BulkImport,
    BulkImportRow,
    Post,
    PostAuditEntry,
    PostLabel,
    PostPlatformConfig,
    PostQueue,
    PostTarget,
    PostTargetMetricSnapshot,
)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "campaign", "status", "scheduled_at", "published_at")
    list_filter = ("status", "client", "campaign")
    search_fields = ("title", "body")
    filter_horizontal = ("labels",)


@admin.register(PostTarget)
class PostTargetAdmin(admin.ModelAdmin):
    list_display = ("post", "platform", "social_account", "status", "retry_count")
    list_filter = ("platform", "status")
    search_fields = ("post__title", "platform_post_id")


admin.site.register(PostLabel)
admin.site.register(PostQueue)
admin.site.register(PostPlatformConfig)
admin.site.register(PostTargetMetricSnapshot)
admin.site.register(PostAuditEntry)
admin.site.register(BulkImport)
admin.site.register(BulkImportRow)
