from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clients.models import Client

from .forms import CampaignForm
from .models import Campaign, CampaignStatus


@staff_member_required(login_url="operator-login")
def campaign_list(request):
    campaigns = Campaign.objects.select_related("client")
    return render(request, "operator/campaigns/list.html", {"campaigns": campaigns})


@staff_member_required(login_url="operator-login")
def campaign_create(request):
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        return redirect("operator-campaign-detail", pk=campaign.pk)
    return render(request, "operator/campaigns/form.html", {"form": form, "campaign": None})


@staff_member_required(login_url="operator-login")
def client_campaign_create(request, slug):
    client_record = _active_client(slug)
    form = CampaignForm(request.POST or None, client_context=client_record)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        return redirect(
            "operator-client-campaign-detail",
            slug=client_record.slug,
            pk=campaign.pk,
        )
    return render(
        request,
        "operator/campaigns/form.html",
        {
            "form": form,
            "campaign": None,
            "client_record": client_record,
        },
    )


@staff_member_required(login_url="operator-login")
def campaign_detail(request, pk):
    campaign = get_object_or_404(
        Campaign.objects.select_related("client").annotate(post_count=Count("posts")),
        pk=pk,
    )
    posts = campaign.posts.select_related("client").prefetch_related("targets").order_by(
        "-created_at"
    )
    return render(
        request,
        "operator/campaigns/detail.html",
        {
            "campaign": campaign,
            "posts": posts,
        },
    )


@staff_member_required(login_url="operator-login")
def client_campaign_detail(request, slug, pk):
    client_record = _active_client(slug)
    campaign = get_object_or_404(
        Campaign.objects.select_related("client").annotate(post_count=Count("posts")),
        pk=pk,
        client=client_record,
    )
    posts = campaign.posts.select_related("client").prefetch_related("targets").order_by(
        "-created_at"
    )
    return render(
        request,
        "operator/campaigns/detail.html",
        {
            "campaign": campaign,
            "posts": posts,
            "client_record": client_record,
        },
    )


@staff_member_required(login_url="operator-login")
def campaign_edit(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    form = CampaignForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        return redirect("operator-campaign-detail", pk=campaign.pk)
    return render(request, "operator/campaigns/form.html", {"form": form, "campaign": campaign})


@staff_member_required(login_url="operator-login")
def client_campaign_edit(request, slug, pk):
    client_record = _active_client(slug)
    campaign = get_object_or_404(Campaign, pk=pk, client=client_record)
    form = CampaignForm(request.POST or None, instance=campaign, client_context=client_record)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        return redirect(
            "operator-client-campaign-detail",
            slug=client_record.slug,
            pk=campaign.pk,
        )
    return render(
        request,
        "operator/campaigns/form.html",
        {
            "form": form,
            "campaign": campaign,
            "client_record": client_record,
        },
    )


@staff_member_required(login_url="operator-login")
@require_POST
def campaign_archive(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    campaign.status = CampaignStatus.ARCHIVED
    campaign.save(update_fields=["status", "updated_at"])
    return redirect("operator-campaign-detail", pk=campaign.pk)


@staff_member_required(login_url="operator-login")
@require_POST
def client_campaign_archive(request, slug, pk):
    client_record = _active_client(slug)
    campaign = get_object_or_404(Campaign, pk=pk, client=client_record)
    campaign.status = CampaignStatus.ARCHIVED
    campaign.save(update_fields=["status", "updated_at"])
    return redirect("operator-client-campaign-detail", slug=client_record.slug, pk=campaign.pk)


def _active_client(slug):
    return get_object_or_404(
        Client,
        slug=slug,
        is_active=True,
        deleted_at__isnull=True,
    )
