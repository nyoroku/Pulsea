from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from campaigns.models import Campaign
from clients.mixins import ClientRequiredMixin
from clients.models import Client, ClientIndustry, ClientUser


@pytest.fixture
def portal_client_record():
    return Client.objects.create(
        name="Portal Client",
        slug="portal-client",
        industry=ClientIndustry.RETAIL,
    )


@pytest.mark.django_db
def test_portal_login_is_public(client):
    response = client.get(reverse("portal-login"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_operator_login_is_public(client):
    response = client.get(reverse("operator-login"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_operator_login_rejects_non_staff_account(client, django_user_model):
    django_user_model.objects.create_user(username="not-operator", password="password")

    response = client.post(
        reverse("operator-login"),
        {"username": "not-operator", "password": "password"},
    )

    assert response.status_code == 200
    assert b"This account does not have operator access." in response.content


@pytest.mark.django_db
def test_anonymous_portal_dashboard_redirects_to_portal_login(client):
    response = client.get(reverse("portal-dashboard"))

    assert response.status_code == 302
    assert response.url == "/portal/login/?next=/portal/"


@pytest.mark.django_db
def test_unmapped_user_cannot_open_portal(client, django_user_model):
    user = django_user_model.objects.create_user(username="unmapped")
    client.force_login(user)

    response = client.get(reverse("portal-dashboard"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_client_user_cannot_open_portal(client, django_user_model, portal_client_record):
    user = django_user_model.objects.create_user(username="inactive")
    ClientUser.objects.create(user=user, client=portal_client_record, is_active=False)
    client.force_login(user)

    response = client.get(reverse("portal-dashboard"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_active_client_user_sees_scoped_portal(client, django_user_model, portal_client_record):
    user = django_user_model.objects.create_user(username="active")
    ClientUser.objects.create(user=user, client=portal_client_record)
    client.force_login(user)

    response = client.get(reverse("portal-dashboard"))

    assert response.status_code == 200
    assert portal_client_record.name.encode() in response.content


@pytest.mark.django_db
def test_operator_dashboard_requires_staff(client, django_user_model):
    normal_user = django_user_model.objects.create_user(username="normal")
    client.force_login(normal_user)

    response = client.get(reverse("operator-dashboard"))

    assert response.status_code == 302
    assert response.url.startswith("/operator/login/")


@pytest.mark.django_db
def test_operator_dashboard_allows_staff(client, django_user_model):
    staff_user = django_user_model.objects.create_user(username="staff", is_staff=True)
    client.force_login(staff_user)

    response = client.get(reverse("operator-dashboard"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_client_queryset_mixin_filters_as_first_tenant_operation():
    alpha = Client.objects.create(name="Alpha", slug="alpha", industry=ClientIndustry.OTHER)
    beta = Client.objects.create(name="Beta", slug="beta", industry=ClientIndustry.OTHER)
    Campaign.objects.create(client=alpha, name="Alpha Campaign")
    Campaign.objects.create(client=beta, name="Beta Campaign")
    view = ClientRequiredMixin()
    view.request = SimpleNamespace(client=alpha)

    scoped_campaigns = view.filter_client_queryset(Campaign.objects.all())

    assert list(scoped_campaigns.values_list("name", flat=True)) == ["Alpha Campaign"]


def test_client_queryset_mixin_rejects_missing_client():
    view = ClientRequiredMixin()
    view.request = SimpleNamespace(client=None)

    with pytest.raises(PermissionDenied, match="active client"):
        view.filter_client_queryset(Campaign.objects.all())
