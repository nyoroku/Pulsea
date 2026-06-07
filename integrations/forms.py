from django import forms

from clients.models import Client

from .models import Platform, SocialAccount


class TestSocialAccountForm(forms.ModelForm):
    class Meta:
        model = SocialAccount
        fields = ("client", "platform", "account_name", "platform_account_id")
        help_texts = {
            "platform_account_id": "Optional test identifier. Pulsea creates one when left blank.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        self.fields["platform"].choices = [
            (Platform.GBP, Platform.GBP.label),
            (Platform.FACEBOOK, Platform.FACEBOOK.label),
            (Platform.INSTAGRAM, Platform.INSTAGRAM.label),
            (Platform.TIKTOK, Platform.TIKTOK.label),
            (Platform.YOUTUBE, Platform.YOUTUBE.label),
        ]

