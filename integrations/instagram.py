import json
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import ConnectionHealth, Platform, SocialAccount

INSTAGRAM_SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)


class InstagramAPIError(Exception):
    pass


@dataclass(frozen=True)
class InstagramToken:
    access_token: str
    expires_in: int


def instagram_is_configured() -> bool:
    return bool(settings.INSTAGRAM_APP_ID and settings.INSTAGRAM_APP_SECRET)


def build_instagram_authorization_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.INSTAGRAM_APP_ID,
            "redirect_uri": settings.INSTAGRAM_OAUTH_REDIRECT_URI,
            "state": state,
            "scope": ",".join(INSTAGRAM_SCOPES),
            "response_type": "code",
            "enable_fb_login": "0",
            "force_authentication": "1",
        }
    )
    return f"https://www.instagram.com/oauth/authorize?{query}"


def exchange_instagram_code(code: str) -> InstagramToken:
    short_lived = _request_json(
        "https://api.instagram.com/oauth/access_token",
        method="POST",
        data={
            "client_id": settings.INSTAGRAM_APP_ID,
            "client_secret": settings.INSTAGRAM_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": settings.INSTAGRAM_OAUTH_REDIRECT_URI,
            "code": code,
        },
    )
    short_token = short_lived.get("access_token", "")
    if not short_token:
        raise InstagramAPIError("Instagram did not return an access token.")

    long_lived = _request_json(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": settings.INSTAGRAM_APP_SECRET,
            "access_token": short_token,
        },
    )
    return InstagramToken(
        access_token=long_lived.get("access_token") or short_token,
        expires_in=int(long_lived.get("expires_in") or 3600),
    )


def discover_instagram_account(access_token: str) -> dict:
    return _request_json(
        f"https://graph.instagram.com/{settings.INSTAGRAM_API_VERSION}/me",
        params={
            "fields": "user_id,username,account_type",
            "access_token": access_token,
        },
    )


def save_instagram_account(client, profile: dict, token: InstagramToken) -> SocialAccount:
    instagram_id = str(profile.get("user_id") or profile.get("id") or "")
    if not instagram_id:
        raise InstagramAPIError("Instagram did not return an account ID.")
    username = profile.get("username") or f"Instagram {instagram_id}"
    social_account, _ = SocialAccount.objects.update_or_create(
        client=client,
        platform=Platform.INSTAGRAM,
        platform_account_id=instagram_id,
        defaults={
            "account_name": username,
            "access_token": token.access_token,
            "token_expires_at": timezone.now() + timedelta(seconds=token.expires_in),
            "instagram_business_account_id": instagram_id,
            "connection_health": ConnectionHealth.CONNECTED,
            "is_active": True,
        },
    )
    return social_account


def _request_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(
        url,
        data=urlencode(data).encode("utf-8") if data else None,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise InstagramAPIError(f"Instagram rejected the request: {details}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise InstagramAPIError(
            "Instagram could not be reached or returned an invalid response."
        ) from exc
