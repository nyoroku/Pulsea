from secrets import compare_digest, token_urlsafe
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from clients.models import Client

from .forms import TestSocialAccountForm
from .instagram import (
    InstagramAPIError,
    build_instagram_authorization_url,
    discover_instagram_account,
    exchange_instagram_code,
    instagram_is_configured,
    save_instagram_account,
)
from .meta import (
    MetaAPIError,
    build_meta_authorization_url,
    discover_meta_pages,
    exchange_meta_code,
    meta_is_configured,
    save_meta_accounts,
)
from .models import ConnectionHealth, SocialAccount
from .pinterest import (
    PinterestAPIError,
    build_pinterest_authorization_url,
    discover_pinterest_boards,
    exchange_pinterest_code,
    pinterest_is_configured,
    save_pinterest_boards,
)

PROVIDER_GROUPS = [
    {
        "name": "Meta",
        "platforms": "Facebook Pages",
        "description": "Connect a client's managed Facebook Pages through Meta OAuth.",
        "status": "OAuth setup required",
    },
    {
        "name": "Google",
        "platforms": "Business Profile and YouTube",
        "description": (
            "Authorize Google locations and YouTube channels through scoped Google OAuth."
        ),
        "status": "OAuth setup required",
    },
    {
        "name": "Pinterest",
        "platforms": "Pinterest boards",
        "description": "Authorize Pinterest boards for image Pin publishing.",
        "status": "OAuth setup required",
    },
    {
        "name": "TikTok",
        "platforms": "TikTok",
        "description": "Authorize Content Posting access after TikTok app review is approved.",
        "status": "App review required",
    },
]


@staff_member_required(login_url="operator-login")
def social_account_list(request):
    accounts = SocialAccount.objects.select_related("client")
    return render(
        request,
        "operator/integrations/list.html",
        {
            "accounts": accounts,
            "provider_groups": PROVIDER_GROUPS,
            "test_mode": settings.PUBLISHING_ADAPTER_MODE == "fake",
            "meta_configured": meta_is_configured(),
            "meta_callback_url": settings.META_OAUTH_REDIRECT_URI,
            "instagram_configured": instagram_is_configured(),
            "instagram_callback_url": settings.INSTAGRAM_OAUTH_REDIRECT_URI,
            "pinterest_configured": pinterest_is_configured(),
            "pinterest_callback_url": settings.PINTEREST_OAUTH_REDIRECT_URI,
            "clients": Client.objects.filter(is_active=True, deleted_at__isnull=True),
        },
    )


@staff_member_required(login_url="operator-login")
def social_account_create_test(request):
    if settings.PUBLISHING_ADAPTER_MODE != "fake":
        return redirect("operator-social-account-list")
    form = TestSocialAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        social_account = form.save(commit=False)
        if not social_account.platform_account_id:
            social_account.platform_account_id = f"test-{uuid4()}"
        social_account.connection_health = ConnectionHealth.CONNECTED
        social_account.save()
        return redirect("operator-social-account-list")
    return render(request, "operator/integrations/test_form.html", {"form": form})


@staff_member_required(login_url="operator-login")
@require_POST
def social_account_disconnect(request, pk):
    social_account = get_object_or_404(SocialAccount, pk=pk)
    social_account.is_active = False
    social_account.connection_health = ConnectionHealth.DISCONNECTED
    social_account.save(update_fields=["is_active", "connection_health", "updated_at"])
    return redirect("operator-social-account-list")


@staff_member_required(login_url="operator-login")
def meta_oauth_start(request):
    if not meta_is_configured():
        messages.error(request, "Add META_APP_SECRET to .env before connecting Meta.")
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=request.GET.get("client"),
        is_active=True,
        deleted_at__isnull=True,
    )
    state = token_urlsafe(32)
    request.session["meta_oauth"] = {"client_id": client.pk, "state": state}
    return redirect(build_meta_authorization_url(state))


@staff_member_required(login_url="operator-login")
def meta_oauth_callback(request):
    expected = request.session.pop("meta_oauth", {})
    returned_state = request.GET.get("state", "")
    if (
        not expected
        or not returned_state
        or not compare_digest(expected.get("state", ""), returned_state)
    ):
        messages.error(request, "Meta connection expired or returned an invalid state. Try again.")
        return redirect("operator-social-account-list")
    if request.GET.get("error"):
        messages.error(request, "Meta authorization was cancelled or denied.")
        return redirect("operator-social-account-list")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "Meta did not return an authorization code.")
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=expected["client_id"],
        is_active=True,
        deleted_at__isnull=True,
    )
    try:
        user_access_token = exchange_meta_code(code)
        pages = discover_meta_pages(user_access_token)
        result = save_meta_accounts(client, pages)
    except MetaAPIError as exc:
        messages.error(request, str(exc))
        return redirect("operator-social-account-list")
    messages.success(
        request,
        (
            f"Connected {result.facebook_pages} Facebook Page(s) and "
            f"{result.instagram_accounts} Instagram account(s) for {client.name}."
        ),
    )
    return redirect("operator-social-account-list")


@staff_member_required(login_url="operator-login")
def instagram_oauth_start(request):
    if not instagram_is_configured():
        messages.error(
            request,
            "Add INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET to .env before connecting Instagram.",
        )
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=request.GET.get("client"),
        is_active=True,
        deleted_at__isnull=True,
    )
    state = token_urlsafe(32)
    request.session["instagram_oauth"] = {"client_id": client.pk, "state": state}
    return redirect(build_instagram_authorization_url(state))


@staff_member_required(login_url="operator-login")
def instagram_oauth_callback(request):
    expected = request.session.pop("instagram_oauth", {})
    returned_state = request.GET.get("state", "")
    if (
        not expected
        or not returned_state
        or not compare_digest(expected.get("state", ""), returned_state)
    ):
        messages.error(
            request,
            "Instagram connection expired or returned an invalid state. Try again.",
        )
        return redirect("operator-social-account-list")
    if request.GET.get("error"):
        messages.error(request, "Instagram authorization was cancelled or denied.")
        return redirect("operator-social-account-list")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "Instagram did not return an authorization code.")
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=expected["client_id"],
        is_active=True,
        deleted_at__isnull=True,
    )
    try:
        token = exchange_instagram_code(code)
        profile = discover_instagram_account(token.access_token)
        social_account = save_instagram_account(client, profile, token)
    except InstagramAPIError as exc:
        messages.error(request, str(exc))
        return redirect("operator-social-account-list")
    messages.success(
        request,
        f"Connected Instagram account @{social_account.account_name} for {client.name}.",
    )
    return redirect("operator-social-account-list")


@staff_member_required(login_url="operator-login")
def pinterest_oauth_start(request):
    if not pinterest_is_configured():
        messages.error(
            request,
            "Add PINTEREST_APP_ID and PINTEREST_APP_SECRET to .env before connecting Pinterest.",
        )
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=request.GET.get("client"),
        is_active=True,
        deleted_at__isnull=True,
    )
    state = token_urlsafe(32)
    request.session["pinterest_oauth"] = {"client_id": client.pk, "state": state}
    return redirect(build_pinterest_authorization_url(state))


@staff_member_required(login_url="operator-login")
def pinterest_oauth_callback(request):
    expected = request.session.pop("pinterest_oauth", {})
    returned_state = request.GET.get("state", "")
    if (
        not expected
        or not returned_state
        or not compare_digest(expected.get("state", ""), returned_state)
    ):
        messages.error(
            request,
            "Pinterest connection expired or returned an invalid state. Try again.",
        )
        return redirect("operator-social-account-list")
    if request.GET.get("error"):
        messages.error(request, "Pinterest authorization was cancelled or denied.")
        return redirect("operator-social-account-list")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "Pinterest did not return an authorization code.")
        return redirect("operator-social-account-list")
    client = get_object_or_404(
        Client,
        pk=expected["client_id"],
        is_active=True,
        deleted_at__isnull=True,
    )
    try:
        token = exchange_pinterest_code(code)
        boards = discover_pinterest_boards(token.access_token)
        result = save_pinterest_boards(client, boards, token)
    except PinterestAPIError as exc:
        messages.error(request, str(exc))
        return redirect("operator-social-account-list")
    messages.success(
        request,
        f"Connected {result.boards} Pinterest board(s) for {client.name}.",
    )
    return redirect("operator-social-account-list")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def instagram_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        if (
            mode == "subscribe"
            and token
            and compare_digest(token, settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN)
        ):
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Webhook verification failed.", status=403)
    return JsonResponse({"status": "ok"})
