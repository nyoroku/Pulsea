from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from campaigns.models import Campaign
from integrations.presentation import platform_meta
from publishing.models import Post, PostStatus

from .forms import ClientForm
from .models import Client


def active_clients():
    return Client.objects.filter(deleted_at__isnull=True)


@staff_member_required(login_url="operator-login")
def client_list(request):
    query = request.GET.get("q", "").strip()
    clients = active_clients().annotate(
        post_count=Count("posts", distinct=True),
        campaign_count=Count("campaigns", distinct=True),
        connection_count=Count(
            "social_accounts",
            filter=Q(social_accounts__is_active=True),
            distinct=True,
        ),
    )
    if query:
        clients = clients.filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(industry__icontains=query)
        )
    return render(
        request,
        "operator/clients/list.html",
        {
            "clients": clients,
            "query": query,
        },
    )


@staff_member_required(login_url="operator-login")
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client_record = form.save()
        return redirect("operator-client-detail", slug=client_record.slug)
    return render(request, "operator/clients/form.html", {"form": form, "client_record": None})


@staff_member_required(login_url="operator-login")
def client_detail(request, slug):
    client_record = get_object_or_404(active_clients(), slug=slug)
    social_accounts = [
        {
            "account": account,
            "meta": platform_meta(account.platform),
        }
        for account in client_record.social_accounts.filter(is_active=True)
    ]
    campaigns = Campaign.objects.filter(client=client_record).annotate(
        post_count=Count("posts")
    )[:6]
    recent_posts = (
        Post.objects.filter(client=client_record)
        .select_related("campaign")
        .prefetch_related("targets")
        .order_by("-created_at")[:6]
    )
    stats = {
        "posts": client_record.posts.count(),
        "scheduled": client_record.posts.filter(status=PostStatus.SCHEDULED).count(),
        "campaigns": client_record.campaigns.count(),
        "connections": client_record.social_accounts.filter(is_active=True).count(),
    }
    return render(
        request,
        "operator/clients/detail.html",
        {
            "client_record": client_record,
            "social_accounts": social_accounts,
            "campaigns": campaigns,
            "recent_posts": recent_posts,
            "stats": stats,
        },
    )


@staff_member_required(login_url="operator-login")
def client_edit(request, slug):
    client_record = get_object_or_404(active_clients(), slug=slug)
    form = ClientForm(request.POST or None, instance=client_record)
    if request.method == "POST" and form.is_valid():
        client_record = form.save()
        return redirect("operator-client-detail", slug=client_record.slug)
    return render(
        request,
        "operator/clients/form.html",
        {"form": form, "client_record": client_record},
    )


@staff_member_required(login_url="operator-login")
@require_POST
def client_deactivate(request, slug):
    client_record = get_object_or_404(active_clients(), slug=slug)
    client_record.is_active = False
    client_record.save(update_fields=["is_active", "updated_at"])
    return redirect("operator-client-detail", slug=client_record.slug)


@staff_member_required(login_url="operator-login")
@require_POST
def client_soft_delete(request, slug):
    client_record = get_object_or_404(active_clients(), slug=slug)
    client_record.is_active = False
    client_record.deleted_at = timezone.now()
    client_record.save(update_fields=["is_active", "deleted_at", "updated_at"])
    return redirect("operator-client-list")
