from collections.abc import Callable

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from .models import ClientUser


class ClientMiddleware:
    portal_prefix = "/portal/"
    public_paths = {"/portal/login/", "/portal/logout/"}

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.client = None
        if not request.path.startswith(self.portal_prefix) or request.path in self.public_paths:
            return self.get_response(request)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), "/portal/login/")
        try:
            client_user = request.user.clientuser
        except ClientUser.DoesNotExist as exc:
            raise PermissionDenied("Portal access requires an active client account.") from exc
        if (
            not client_user.is_active
            or not client_user.client.is_active
            or client_user.client.deleted_at is not None
        ):
            raise PermissionDenied("Portal access requires an active client account.")
        request.client = client_user.client
        return self.get_response(request)
