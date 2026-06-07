from django import forms
from django.db.models import Q

from clients.models import Client

from .models import Campaign


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ("client", "name", "description", "start_date", "end_date", "status", "color")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_clients = Q(is_active=True, deleted_at__isnull=True)
        if self.instance.pk:
            allowed_clients |= Q(pk=self.instance.client_id)
        self.fields["client"].queryset = Client.objects.filter(allowed_clients)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before the start date.")
        return cleaned_data
