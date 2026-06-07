import pytest
from django.urls import reverse

from campaigns.models import Campaign, CampaignStatus
from clients.models import Client, ClientIndustry


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(username="operator", is_staff=True)


@pytest.mark.django_db
def test_client_list_requires_staff(client, django_user_model):
    normal_user = django_user_model.objects.create_user(username="normal")
    client.force_login(normal_user)

    response = client.get(reverse("operator-client-list"))

    assert response.status_code == 302
    assert response.url.startswith("/operator/login/")


@pytest.mark.django_db
def test_staff_can_create_edit_deactivate_and_soft_delete_client(client, staff_user):
    client.force_login(staff_user)
    create_response = client.post(
        reverse("operator-client-create"),
        {
            "name": "Nairobi Retail",
            "slug": "nairobi-retail",
            "industry": ClientIndustry.RETAIL,
            "is_active": "on",
        },
    )
    client_record = Client.objects.get(slug="nairobi-retail")

    assert create_response.status_code == 302
    assert create_response.url == reverse("operator-client-detail", args=[client_record.slug])

    edit_response = client.post(
        reverse("operator-client-edit", args=[client_record.slug]),
        {
            "name": "Nairobi Retail Updated",
            "slug": "nairobi-retail",
            "industry": ClientIndustry.RETAIL,
            "is_active": "on",
        },
    )
    client_record.refresh_from_db()

    assert edit_response.status_code == 302
    assert client_record.name == "Nairobi Retail Updated"

    deactivate_response = client.post(
        reverse("operator-client-deactivate", args=[client_record.slug])
    )
    client_record.refresh_from_db()

    assert deactivate_response.status_code == 302
    assert not client_record.is_active

    delete_response = client.post(reverse("operator-client-delete", args=[client_record.slug]))
    client_record.refresh_from_db()

    assert delete_response.status_code == 302
    assert client_record.deleted_at is not None
    detail_response = client.get(reverse("operator-client-detail", args=[client_record.slug]))
    assert detail_response.status_code == 404


@pytest.mark.django_db
def test_client_deactivation_rejects_get(client, staff_user):
    client.force_login(staff_user)
    client_record = Client.objects.create(
        name="Do Not Deactivate",
        slug="do-not-deactivate",
        industry=ClientIndustry.OTHER,
    )

    response = client.get(reverse("operator-client-deactivate", args=[client_record.slug]))

    assert response.status_code == 405
    client_record.refresh_from_db()
    assert client_record.is_active


@pytest.mark.django_db
def test_staff_can_create_edit_and_archive_campaign(client, staff_user):
    client.force_login(staff_user)
    client_record = Client.objects.create(
        name="Campaign Client",
        slug="campaign-client",
        industry=ClientIndustry.EVENTS,
    )
    create_response = client.post(
        reverse("operator-campaign-create"),
        {
            "client": client_record.pk,
            "name": "Launch Week",
            "description": "Launch content",
            "start_date": "2026-06-01",
            "end_date": "2026-06-07",
            "status": CampaignStatus.ACTIVE,
            "color": "#4f46e5",
        },
    )
    campaign = Campaign.objects.get(name="Launch Week")

    assert create_response.status_code == 302
    assert create_response.url == reverse("operator-campaign-detail", args=[campaign.pk])

    edit_response = client.post(
        reverse("operator-campaign-edit", args=[campaign.pk]),
        {
            "client": client_record.pk,
            "name": "Launch Week Updated",
            "description": "Updated launch content",
            "start_date": "2026-06-01",
            "end_date": "2026-06-08",
            "status": CampaignStatus.ACTIVE,
            "color": "#4338ca",
        },
    )
    campaign.refresh_from_db()

    assert edit_response.status_code == 302
    assert campaign.name == "Launch Week Updated"

    archive_response = client.post(reverse("operator-campaign-archive", args=[campaign.pk]))
    campaign.refresh_from_db()

    assert archive_response.status_code == 302
    assert campaign.status == CampaignStatus.ARCHIVED


@pytest.mark.django_db
def test_campaign_end_date_cannot_precede_start_date(client, staff_user):
    client.force_login(staff_user)
    client_record = Client.objects.create(
        name="Date Client",
        slug="date-client",
        industry=ClientIndustry.OTHER,
    )

    response = client.post(
        reverse("operator-campaign-create"),
        {
            "client": client_record.pk,
            "name": "Invalid Dates",
            "start_date": "2026-06-10",
            "end_date": "2026-06-01",
            "status": CampaignStatus.ACTIVE,
            "color": "#4f46e5",
        },
    )

    assert response.status_code == 200
    assert b"End date cannot be before the start date." in response.content
    assert not Campaign.objects.filter(name="Invalid Dates").exists()


@pytest.mark.django_db
def test_campaign_form_excludes_inactive_clients(client, staff_user):
    client.force_login(staff_user)
    Client.objects.create(
        name="Inactive Client",
        slug="inactive-client",
        industry=ClientIndustry.OTHER,
        is_active=False,
    )

    response = client.get(reverse("operator-campaign-create"))

    assert response.status_code == 200
    assert b"Inactive Client" not in response.content


@pytest.mark.django_db
def test_existing_campaign_for_inactive_client_remains_editable(client, staff_user):
    client.force_login(staff_user)
    client_record = Client.objects.create(
        name="Paused Client",
        slug="paused-client",
        industry=ClientIndustry.OTHER,
        is_active=False,
    )
    campaign = Campaign.objects.create(client=client_record, name="Historical Campaign")

    response = client.get(reverse("operator-campaign-edit", args=[campaign.pk]))

    assert response.status_code == 200
    assert b"Paused Client" in response.content
