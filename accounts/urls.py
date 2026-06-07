from django.urls import path

from .views import (
    OperatorLoginView,
    PortalLoginView,
    operator_dashboard,
    operator_logout,
    portal_dashboard,
    portal_logout,
    privacy_policy,
    public_home,
    terms_of_service,
)

urlpatterns = [
    path("", public_home, name="home"),
    path("privacy/", privacy_policy, name="privacy-policy"),
    path("terms/", terms_of_service, name="terms-of-service"),
    path("operator/login/", OperatorLoginView.as_view(), name="operator-login"),
    path("operator/logout/", operator_logout, name="operator-logout"),
    path("operator/", operator_dashboard, name="operator-dashboard"),
    path("portal/login/", PortalLoginView.as_view(), name="portal-login"),
    path("portal/logout/", portal_logout, name="portal-logout"),
    path("portal/", portal_dashboard, name="portal-dashboard"),
]
