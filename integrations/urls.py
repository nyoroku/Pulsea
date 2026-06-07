from django.urls import path

from . import views

urlpatterns = [
    path("", views.social_account_list, name="operator-social-account-list"),
    path("test/new/", views.social_account_create_test, name="operator-social-account-create-test"),
    path("meta/start/", views.meta_oauth_start, name="operator-meta-oauth-start"),
    path("meta/callback/", views.meta_oauth_callback, name="operator-meta-oauth-callback"),
    path(
        "instagram/start/",
        views.instagram_oauth_start,
        name="operator-instagram-oauth-start",
    ),
    path(
        "instagram/callback/",
        views.instagram_oauth_callback,
        name="operator-instagram-oauth-callback",
    ),
    path(
        "instagram/webhook/",
        views.instagram_webhook,
        name="operator-instagram-webhook",
    ),
    path(
        "pinterest/start/",
        views.pinterest_oauth_start,
        name="operator-pinterest-oauth-start",
    ),
    path(
        "pinterest/callback/",
        views.pinterest_oauth_callback,
        name="operator-pinterest-oauth-callback",
    ),
    path(
        "<int:pk>/disconnect/",
        views.social_account_disconnect,
        name="operator-social-account-disconnect",
    ),
]
