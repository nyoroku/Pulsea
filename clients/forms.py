from django import forms

from .models import Client


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name", "slug", "logo_key", "industry", "is_active")
