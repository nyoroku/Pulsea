from django.contrib import admin
from django.urls import include, path

from .views import healthcheck

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("operator/clients/", include("clients.urls")),
    path("operator/campaigns/", include("campaigns.urls")),
    path("operator/posts/", include("publishing.urls")),
    path("operator/connections/", include("integrations.urls")),
    path("", include("accounts.urls")),
]
