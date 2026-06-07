from django.urls import path

from . import views

urlpatterns = [
    path("", views.post_list, name="operator-post-list"),
    path("compose/", views.post_compose, name="operator-post-compose"),
    path("<int:pk>/", views.post_detail, name="operator-post-detail"),
    path("<int:pk>/retry/", views.post_retry, name="operator-post-retry"),
]
