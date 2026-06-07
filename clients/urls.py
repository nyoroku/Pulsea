from django.urls import path

from campaigns import views as campaign_views
from integrations import views as integration_views
from publishing import views as publishing_views

from . import views

urlpatterns = [
    path("", views.client_list, name="operator-client-list"),
    path("new/", views.client_create, name="operator-client-create"),
    path("<slug:slug>/posts/", publishing_views.client_post_list, name="operator-client-post-list"),
    path(
        "<slug:slug>/posts/calendar/",
        publishing_views.client_post_calendar,
        name="operator-client-post-calendar",
    ),
    path(
        "<slug:slug>/posts/compose/",
        publishing_views.client_post_compose,
        name="operator-client-post-compose",
    ),
    path(
        "<slug:slug>/posts/<int:pk>/",
        publishing_views.client_post_detail,
        name="operator-client-post-detail",
    ),
    path(
        "<slug:slug>/posts/<int:pk>/retry/",
        publishing_views.client_post_retry,
        name="operator-client-post-retry",
    ),
    path(
        "<slug:slug>/campaigns/new/",
        campaign_views.client_campaign_create,
        name="operator-client-campaign-create",
    ),
    path(
        "<slug:slug>/campaigns/<int:pk>/",
        campaign_views.client_campaign_detail,
        name="operator-client-campaign-detail",
    ),
    path(
        "<slug:slug>/campaigns/<int:pk>/edit/",
        campaign_views.client_campaign_edit,
        name="operator-client-campaign-edit",
    ),
    path(
        "<slug:slug>/campaigns/<int:pk>/archive/",
        campaign_views.client_campaign_archive,
        name="operator-client-campaign-archive",
    ),
    path(
        "<slug:slug>/connections/",
        integration_views.client_social_account_list,
        name="operator-client-social-account-list",
    ),
    path(
        "<slug:slug>/connections/meta/start/",
        integration_views.client_meta_oauth_start,
        name="operator-client-meta-oauth-start",
    ),
    path(
        "<slug:slug>/connections/instagram/start/",
        integration_views.client_instagram_oauth_start,
        name="operator-client-instagram-oauth-start",
    ),
    path(
        "<slug:slug>/connections/pinterest/start/",
        integration_views.client_pinterest_oauth_start,
        name="operator-client-pinterest-oauth-start",
    ),
    path(
        "<slug:slug>/connections/<int:pk>/disconnect/",
        integration_views.client_social_account_disconnect,
        name="operator-client-social-account-disconnect",
    ),
    path("<slug:slug>/", views.client_detail, name="operator-client-detail"),
    path("<slug:slug>/edit/", views.client_edit, name="operator-client-edit"),
    path("<slug:slug>/deactivate/", views.client_deactivate, name="operator-client-deactivate"),
    path("<slug:slug>/delete/", views.client_soft_delete, name="operator-client-delete"),
]
