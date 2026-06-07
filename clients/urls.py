from django.urls import path

from . import views

urlpatterns = [
    path("", views.client_list, name="operator-client-list"),
    path("new/", views.client_create, name="operator-client-create"),
    path("<slug:slug>/", views.client_detail, name="operator-client-detail"),
    path("<slug:slug>/edit/", views.client_edit, name="operator-client-edit"),
    path("<slug:slug>/deactivate/", views.client_deactivate, name="operator-client-deactivate"),
    path("<slug:slug>/delete/", views.client_soft_delete, name="operator-client-delete"),
]
