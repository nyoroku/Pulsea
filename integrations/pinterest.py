import json
from base64 import b64encode
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ConnectionHealth, Platform, SocialAccount

PINTEREST_SCOPES = (
    "boards:read",
    "pins:read",
    "pins:write",
    "user_accounts:read",
)
PINTEREST_API_BASE_URL = "https://api.pinterest.com/v5"


class PinterestAPIError(Exception):
    pass


@dataclass(frozen=True)
class PinterestToken:
    access_token: str
    refresh_token: str = ""
    expires_in: int = 2592000


@dataclass(frozen=True)
class PinterestConnectionResult:
    boards: int


def pinterest_is_configured() -> bool:
    return bool(settings.PINTEREST_APP_ID and settings.PINTEREST_APP_SECRET)


def build_pinterest_authorization_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.PINTEREST_APP_ID,
            "redirect_uri": settings.PINTEREST_OAUTH_REDIRECT_URI,
            "state": state,
            "scope": ",".join(PINTEREST_SCOPES),
            "response_type": "code",
        }
    )
    return f"https://www.pinterest.com/oauth/?{query}"


def exchange_pinterest_code(code: str) -> PinterestToken:
    response = _request_json(
        f"{PINTEREST_API_BASE_URL}/oauth/token",
        method="POST",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.PINTEREST_OAUTH_REDIRECT_URI,
        },
        basic_auth=True,
    )
    access_token = response.get("access_token", "")
    if not access_token:
        raise PinterestAPIError("Pinterest did not return an access token.")
    return PinterestToken(
        access_token=access_token,
        refresh_token=response.get("refresh_token", ""),
        expires_in=int(response.get("expires_in") or 2592000),
    )


def discover_pinterest_boards(access_token: str) -> list[dict]:
    response = _request_json(
        f"{PINTEREST_API_BASE_URL}/boards",
        params={"page_size": "100"},
        access_token=access_token,
    )
    return response.get("items", [])


@transaction.atomic
def save_pinterest_boards(
    client,
    boards: list[dict],
    token: PinterestToken,
) -> PinterestConnectionResult:
    count = 0
    expires_at = timezone.now() + timedelta(seconds=token.expires_in)
    for board in boards:
        board_id = str(board.get("id") or "")
        name = board.get("name") or f"Pinterest board {board_id}"
        if not board_id:
            continue
        SocialAccount.objects.update_or_create(
            client=client,
            platform=Platform.PINTEREST,
            platform_account_id=board_id,
            defaults={
                "account_name": name,
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
                "token_expires_at": expires_at,
                "connection_health": ConnectionHealth.CONNECTED,
                "is_active": True,
            },
        )
        count += 1
    return PinterestConnectionResult(boards=count)


def _request_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    access_token: str = "",
    basic_auth: bool = False,
) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {}
    if basic_auth:
        credentials = f"{settings.PINTEREST_APP_ID}:{settings.PINTEREST_APP_SECRET}".encode()
        headers["Authorization"] = f"Basic {b64encode(credentials).decode('ascii')}"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = Request(
        url,
        data=urlencode(data).encode("utf-8") if data else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise PinterestAPIError(f"Pinterest rejected the request: {details}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PinterestAPIError(
            "Pinterest could not be reached or returned an invalid response."
        ) from exc
