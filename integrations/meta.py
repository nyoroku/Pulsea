import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import ConnectionHealth, Platform, SocialAccount

META_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
)


class MetaAPIError(Exception):
    pass


@dataclass(frozen=True)
class MetaConnectionResult:
    facebook_pages: int
    instagram_accounts: int


def meta_is_configured() -> bool:
    return bool(settings.META_APP_ID and settings.META_APP_SECRET)


def build_meta_authorization_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.META_APP_ID,
            "redirect_uri": settings.META_OAUTH_REDIRECT_URI,
            "state": state,
            "scope": ",".join(META_SCOPES),
            "response_type": "code",
        }
    )
    return f"https://www.facebook.com/{settings.META_GRAPH_API_VERSION}/dialog/oauth?{query}"


def exchange_meta_code(code: str) -> str:
    short_lived = _graph_get(
        "oauth/access_token",
        {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_OAUTH_REDIRECT_URI,
            "code": code,
        },
    )
    short_token = short_lived.get("access_token")
    if not short_token:
        raise MetaAPIError("Meta did not return an access token.")

    long_lived = _graph_get(
        "oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": short_token,
        },
    )
    return long_lived.get("access_token") or short_token


def discover_meta_pages(user_access_token: str) -> list[dict]:
    response = _graph_get(
        "me/accounts",
        {
            "access_token": user_access_token,
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "limit": "100",
        },
    )
    return response.get("data", [])


@transaction.atomic
def save_meta_accounts(client, pages: list[dict]) -> MetaConnectionResult:
    facebook_pages = 0
    instagram_accounts = 0
    for page in pages:
        page_id = page.get("id", "")
        page_name = page.get("name", "Facebook Page")
        page_access_token = page.get("access_token", "")
        if not page_id or not page_access_token:
            continue
        _upsert_social_account(
            client=client,
            platform=Platform.FACEBOOK,
            platform_account_id=page_id,
            account_name=page_name,
            access_token=page_access_token,
            page_id=page_id,
        )
        facebook_pages += 1

        instagram = page.get("instagram_business_account") or {}
        instagram_id = instagram.get("id", "")
        if instagram_id:
            _upsert_social_account(
                client=client,
                platform=Platform.INSTAGRAM,
                platform_account_id=instagram_id,
                account_name=instagram.get("username") or f"{page_name} Instagram",
                access_token=page_access_token,
                page_id=page_id,
                instagram_business_account_id=instagram_id,
            )
            instagram_accounts += 1
    return MetaConnectionResult(facebook_pages, instagram_accounts)


def _upsert_social_account(
    *,
    client,
    platform: str,
    platform_account_id: str,
    account_name: str,
    access_token: str,
    page_id: str,
    instagram_business_account_id: str = "",
) -> None:
    SocialAccount.objects.update_or_create(
        client=client,
        platform=platform,
        platform_account_id=platform_account_id,
        defaults={
            "account_name": account_name,
            "access_token": access_token,
            "page_id": page_id,
            "instagram_business_account_id": instagram_business_account_id,
            "connection_health": ConnectionHealth.CONNECTED,
            "is_active": True,
        },
    )


def _graph_get(path: str, params: dict[str, str]) -> dict:
    url = (
        f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{path}"
        f"?{urlencode(params)}"
    )
    try:
        with urlopen(Request(url), timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise MetaAPIError(f"Meta rejected the request: {details}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetaAPIError("Meta could not be reached or returned an invalid response.") from exc
