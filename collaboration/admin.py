from django.contrib import admin

from .models import (
    ContentRequest,
    ContentRequestComment,
    ContentRequestStatusEvent,
    ContentRequestTarget,
    PostComment,
    UnifiedComment,
)


@admin.register(ContentRequest)
class ContentRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "campaign", "status", "deadline", "created_at")
    list_filter = ("status", "client")
    search_fields = ("title", "brief", "client__name")


@admin.register(UnifiedComment)
class UnifiedCommentAdmin(admin.ModelAdmin):
    list_display = ("author_name", "client", "post_target", "is_read", "is_replied", "is_hidden")
    list_filter = ("is_read", "is_replied", "is_hidden", "client")
    search_fields = ("author_name", "body")


admin.site.register(PostComment)
admin.site.register(ContentRequestTarget)
admin.site.register(ContentRequestComment)
admin.site.register(ContentRequestStatusEvent)
