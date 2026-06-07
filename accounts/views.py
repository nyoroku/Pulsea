from email.utils import parseaddr

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import OperatorAuthenticationForm


def public_home(request):
    return render(request, "public/home.html", _public_context(request))


def privacy_policy(request):
    return render(request, "public/privacy.html", _public_context(request))


def terms_of_service(request):
    return render(request, "public/terms.html", _public_context(request))


@staff_member_required(login_url="operator-login")
def operator_dashboard(request):
    return render(request, "operator/dashboard.html")


class OperatorLoginView(LoginView):
    authentication_form = OperatorAuthenticationForm
    template_name = "accounts/operator_login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("operator-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self) -> str:
        return "/operator/"


@require_POST
def operator_logout(request):
    logout(request)
    return redirect("operator-login")


class PortalLoginView(LoginView):
    template_name = "accounts/portal_login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        return "/portal/"


@login_required
@require_POST
def portal_logout(request):
    logout(request)
    return redirect("portal-login")


@login_required
def portal_dashboard(request):
    return render(request, "portal/dashboard.html", {"client": request.client})


def _public_context(request) -> dict:
    contact_name, contact_address = parseaddr(settings.PUBLIC_CONTACT_EMAIL)
    contact_email = contact_address or settings.PUBLIC_CONTACT_EMAIL
    return {
        "contact_email": contact_email,
        "contact_label": contact_name or contact_email,
        "site_url": request.build_absolute_uri("/").rstrip("/"),
    }
