from django.urls import path

from . import views

urlpatterns = [
    path("", views.campaign_list, name="operator-campaign-list"),
    path("new/", views.campaign_create, name="operator-campaign-create"),
    path("<int:pk>/", views.campaign_detail, name="operator-campaign-detail"),
    path("<int:pk>/edit/", views.campaign_edit, name="operator-campaign-edit"),
    path("<int:pk>/archive/", views.campaign_archive, name="operator-campaign-archive"),
]
