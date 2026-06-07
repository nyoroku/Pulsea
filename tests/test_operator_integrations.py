from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.db import connection
from django.urls import reverse

from clients.models import Client, ClientIndustry
from integrations.instagram import InstagramToken
from integrations.meta import MetaConnectionResult
from integrations.models import ConnectionHealth, Platform, SocialAccount
from integrations.pinterest import PinterestConnectionResult, PinterestToken


@pytest.fixture
def integration_staff_user(django_user_model):
    return django_user_model.objects.create_user(username="connection-operator", is_staff=True)


@pytest.fixture
def integration_client():
    return Client.objects.create(
        name="Connection Client",
        slug="connection-client",
        industry=ClientIndustry.RETAIL,
    )


@pytest.mark.django_db
def test_connections_list_requires_staff(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="connection-normal"))

    response = client.get(reverse("operator-social-account-list"))

    assert response.status_code == 302
    assert response.url.startswith("/operator/login/")


@pytest.mark.django_db
def test_staff_can_create_local_test_connection(client, integration_staff_user, integration_client):
    client.force_login(integration_staff_user)

    response = client.post(
        reverse("operator-social-account-create-test"),
        {
            "client": integration_client.pk,
            "platform": Platform.FACEBOOK,
            "account_name": "Connection Client Page",
            "platform_account_id": "",
        },
    )
    social_account = SocialAccount.objects.get()

    assert response.status_code == 302
    assert response.url == reverse("operator-social-account-list")
    assert social_account.client == integration_client
    assert social_account.platform == Platform.FACEBOOK
    assert social_account.platform_account_id.startswith("test-")
    assert social_account.connection_health == ConnectionHealth.CONNECTED


@pytest.mark.django_db
def test_staff_can_disconnect_social_account(client, integration_staff_user, integration_client):
    social_account = SocialAccount.objects.create(
        client=integration_client,
        platform=Platform.INSTAGRAM,
        account_name="Connection Client Instagram",
        platform_account_id="test-instagram",
    )
    client.force_login(integration_staff_user)

    response = client.post(reverse("operator-social-account-disconnect", args=[social_account.pk]))
    social_account.refresh_from_db()

    assert response.status_code == 302
    assert not social_account.is_active
    assert social_account.connection_health == ConnectionHealth.DISCONNECTED


@pytest.mark.django_db
def test_test_connection_creation_is_hidden_outside_fake_mode(
    client,
    integration_staff_user,
    integration_client,
    settings,
):
    settings.PUBLISHING_ADAPTER_MODE = "real"
    client.force_login(integration_staff_user)

    response = client.post(
        reverse("operator-social-account-create-test"),
        {
            "client": integration_client.pk,
            "platform": Platform.FACEBOOK,
            "account_name": "Should not exist",
        },
    )

    assert response.status_code == 302
    assert not SocialAccount.objects.exists()


@pytest.mark.django_db
def test_meta_oauth_start_redirects_with_selected_client_and_state(
    client,
    integration_staff_user,
    integration_client,
    settings,
):
    settings.META_APP_ID = "meta-app-id"
    settings.META_APP_SECRET = "meta-app-secret"
    settings.META_OAUTH_REDIRECT_URI = "http://localhost:8000/operator/connections/meta/callback/"
    client.force_login(integration_staff_user)

    response = client.get(reverse("operator-meta-oauth-start"), {"client": integration_client.pk})
    query = parse_qs(urlparse(response.url).query)

    assert response.status_code == 302
    assert response.url.startswith("https://www.facebook.com/")
    assert query["client_id"] == ["meta-app-id"]
    assert query["redirect_uri"] == [settings.META_OAUTH_REDIRECT_URI]
    assert query["state"] == [client.session["meta_oauth"]["state"]]
    assert "instagram_basic" not in query["scope"][0]
    assert "instagram_business_basic" not in query["scope"][0]
    assert client.session["meta_oauth"]["client_id"] == integration_client.pk


@pytest.mark.django_db
def test_meta_oauth_callback_rejects_invalid_state(
    client,
    integration_staff_user,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["meta_oauth"] = {"client_id": 999, "state": "expected"}
    session.save()

    response = client.get(reverse("operator-meta-oauth-callback"), {"state": "forged"})

    assert response.status_code == 302
    assert not SocialAccount.objects.exists()


@pytest.mark.django_db
def test_meta_oauth_callback_saves_discovered_page_and_instagram_account(
    client,
    integration_staff_user,
    integration_client,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["meta_oauth"] = {"client_id": integration_client.pk, "state": "expected"}
    session.save()
    pages = [
        {
            "id": "page-123",
            "name": "Connection Client Page",
            "access_token": "page-secret",
            "instagram_business_account": {"id": "instagram-123", "username": "connection-client"},
        }
    ]

    with patch("integrations.views.exchange_meta_code", return_value="user-secret"):
        with patch("integrations.views.discover_meta_pages", return_value=pages):
            response = client.get(
                reverse("operator-meta-oauth-callback"),
                {"state": "expected", "code": "authorization-code"},
            )

    assert response.status_code == 302
    assert SocialAccount.objects.filter(
        client=integration_client,
        platform=Platform.FACEBOOK,
        platform_account_id="page-123",
    ).exists()
    assert SocialAccount.objects.filter(
        client=integration_client,
        platform=Platform.INSTAGRAM,
        platform_account_id="instagram-123",
    ).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT access_token FROM integrations_socialaccount WHERE platform_account_id = %s",
            ["page-123"],
        )
        raw_access_token = cursor.fetchone()[0]
    assert raw_access_token.startswith("fernet$")
    assert "page-secret" not in raw_access_token


@pytest.mark.django_db
def test_meta_oauth_callback_reports_discovery_counts(
    client,
    integration_staff_user,
    integration_client,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["meta_oauth"] = {"client_id": integration_client.pk, "state": "expected"}
    session.save()

    with patch("integrations.views.exchange_meta_code", return_value="user-secret"):
        with patch("integrations.views.discover_meta_pages", return_value=[]):
            with patch(
                "integrations.views.save_meta_accounts",
                return_value=MetaConnectionResult(facebook_pages=2, instagram_accounts=1),
            ):
                response = client.get(
                    reverse("operator-meta-oauth-callback"),
                    {"state": "expected", "code": "authorization-code"},
                    follow=True,
                )

    assert b"Connected 2 Facebook Page(s) and 1 Instagram account(s)" in response.content


@pytest.mark.django_db
def test_instagram_oauth_start_redirects_with_direct_instagram_scopes(
    client,
    integration_staff_user,
    integration_client,
    settings,
):
    settings.INSTAGRAM_APP_ID = "instagram-app-id"
    settings.INSTAGRAM_APP_SECRET = "instagram-app-secret"
    settings.INSTAGRAM_OAUTH_REDIRECT_URI = (
        "http://localhost:8000/operator/connections/instagram/callback/"
    )
    client.force_login(integration_staff_user)

    response = client.get(
        reverse("operator-instagram-oauth-start"),
        {"client": integration_client.pk},
    )
    query = parse_qs(urlparse(response.url).query)

    assert response.status_code == 302
    assert response.url.startswith("https://www.instagram.com/oauth/authorize")
    assert query["client_id"] == ["instagram-app-id"]
    assert query["redirect_uri"] == [settings.INSTAGRAM_OAUTH_REDIRECT_URI]
    assert query["state"] == [client.session["instagram_oauth"]["state"]]
    assert "instagram_business_basic" in query["scope"][0]
    assert "instagram_business_content_publish" in query["scope"][0]
    assert client.session["instagram_oauth"]["client_id"] == integration_client.pk


@pytest.mark.django_db
def test_instagram_oauth_callback_saves_direct_account(
    client,
    integration_staff_user,
    integration_client,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["instagram_oauth"] = {"client_id": integration_client.pk, "state": "expected"}
    session.save()

    with patch(
        "integrations.views.exchange_instagram_code",
        return_value=InstagramToken(access_token="instagram-secret", expires_in=3600),
    ):
        with patch(
            "integrations.views.discover_instagram_account",
            return_value={
                "user_id": "instagram-456",
                "username": "connection.client",
                "account_type": "BUSINESS",
            },
        ):
            response = client.get(
                reverse("operator-instagram-oauth-callback"),
                {"state": "expected", "code": "authorization-code"},
                follow=True,
            )

    social_account = SocialAccount.objects.get(
        client=integration_client,
        platform=Platform.INSTAGRAM,
        platform_account_id="instagram-456",
    )
    assert response.status_code == 200
    assert social_account.account_name == "connection.client"
    assert social_account.access_token == "instagram-secret"
    assert social_account.token_expires_at is not None
    assert b"Connected Instagram account @connection.client" in response.content


@pytest.mark.django_db
def test_instagram_oauth_callback_rejects_invalid_state(
    client,
    integration_staff_user,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["instagram_oauth"] = {"client_id": 999, "state": "expected"}
    session.save()

    response = client.get(reverse("operator-instagram-oauth-callback"), {"state": "forged"})

    assert response.status_code == 302
    assert not SocialAccount.objects.exists()


@pytest.mark.django_db
def test_pinterest_oauth_start_redirects_with_board_and_pin_scopes(
    client,
    integration_staff_user,
    integration_client,
    settings,
):
    settings.PINTEREST_APP_ID = "pinterest-app-id"
    settings.PINTEREST_APP_SECRET = "pinterest-app-secret"
    settings.PINTEREST_OAUTH_REDIRECT_URI = (
        "http://localhost:8000/operator/connections/pinterest/callback/"
    )
    client.force_login(integration_staff_user)

    response = client.get(
        reverse("operator-pinterest-oauth-start"),
        {"client": integration_client.pk},
    )
    query = parse_qs(urlparse(response.url).query)

    assert response.status_code == 302
    assert response.url.startswith("https://www.pinterest.com/oauth/")
    assert query["client_id"] == ["pinterest-app-id"]
    assert query["redirect_uri"] == [settings.PINTEREST_OAUTH_REDIRECT_URI]
    assert query["state"] == [client.session["pinterest_oauth"]["state"]]
    assert "boards:read" in query["scope"][0]
    assert "pins:write" in query["scope"][0]
    assert client.session["pinterest_oauth"]["client_id"] == integration_client.pk


@pytest.mark.django_db
def test_pinterest_oauth_callback_saves_discovered_boards(
    client,
    integration_staff_user,
    integration_client,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["pinterest_oauth"] = {"client_id": integration_client.pk, "state": "expected"}
    session.save()

    with patch(
        "integrations.views.exchange_pinterest_code",
        return_value=PinterestToken(
            access_token="pinterest-secret",
            refresh_token="pinterest-refresh",
            expires_in=3600,
        ),
    ):
        with patch(
            "integrations.views.discover_pinterest_boards",
            return_value=[{"id": "board-123", "name": "Travel ideas"}],
        ):
            response = client.get(
                reverse("operator-pinterest-oauth-callback"),
                {"state": "expected", "code": "authorization-code"},
                follow=True,
            )

    social_account = SocialAccount.objects.get(
        client=integration_client,
        platform=Platform.PINTEREST,
        platform_account_id="board-123",
    )
    assert response.status_code == 200
    assert social_account.account_name == "Travel ideas"
    assert social_account.access_token == "pinterest-secret"
    assert social_account.refresh_token == "pinterest-refresh"
    assert social_account.token_expires_at is not None
    assert b"Connected 1 Pinterest board(s)" in response.content


@pytest.mark.django_db
def test_pinterest_oauth_callback_reports_discovery_counts(
    client,
    integration_staff_user,
    integration_client,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["pinterest_oauth"] = {"client_id": integration_client.pk, "state": "expected"}
    session.save()

    with patch("integrations.views.exchange_pinterest_code"):
        with patch("integrations.views.discover_pinterest_boards", return_value=[]):
            with patch(
                "integrations.views.save_pinterest_boards",
                return_value=PinterestConnectionResult(boards=3),
            ):
                response = client.get(
                    reverse("operator-pinterest-oauth-callback"),
                    {"state": "expected", "code": "authorization-code"},
                    follow=True,
                )

    assert b"Connected 3 Pinterest board(s)" in response.content


@pytest.mark.django_db
def test_pinterest_oauth_callback_rejects_invalid_state(
    client,
    integration_staff_user,
):
    client.force_login(integration_staff_user)
    session = client.session
    session["pinterest_oauth"] = {"client_id": 999, "state": "expected"}
    session.save()

    response = client.get(reverse("operator-pinterest-oauth-callback"), {"state": "forged"})

    assert response.status_code == 302
    assert not SocialAccount.objects.exists()


def test_instagram_webhook_verification_returns_challenge(client, settings):
    settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN = "verify-me"

    response = client.get(
        reverse("operator-instagram-webhook"),
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "123456",
        },
    )

    assert response.status_code == 200
    assert response.content == b"123456"


def test_instagram_webhook_verification_rejects_wrong_token(client, settings):
    settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN = "verify-me"

    response = client.get(
        reverse("operator-instagram-webhook"),
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "123456",
        },
    )

    assert response.status_code == 403
