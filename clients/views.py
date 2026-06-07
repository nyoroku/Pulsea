from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClientForm
from .models import Client


def active_clients():
    return Client.objects.filter(deleted_at__isnull=True)


@staff_member_required(login_url="operator-login")
def client_list(request):
    return render(request, "operator/clients/list.html", {"clients": active_clients()})


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
    return render(request, "operator/clients/detail.html", {"client_record": client_record})


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
