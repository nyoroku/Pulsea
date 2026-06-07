from django.core.exceptions import PermissionDenied


class ClientRequiredMixin:
    request = None

    def dispatch(self, request, *args, **kwargs):
        if request.client is None:
            raise PermissionDenied("An active client account is required.")
        return super().dispatch(request, *args, **kwargs)

    def filter_client_queryset(self, queryset):
        if self.request is None or self.request.client is None:
            raise PermissionDenied("An active client account is required.")
        return queryset.filter(client=self.request.client)
