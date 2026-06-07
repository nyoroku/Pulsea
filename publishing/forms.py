from django import forms

from campaigns.models import Campaign
from clients.models import Client
from integrations.models import SocialAccount
from media.models import Media

from .models import Post


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)] if data else []


class PostComposerForm(forms.ModelForm):
    social_accounts = forms.ModelMultipleChoiceField(
        queryset=SocialAccount.objects.none(),
        help_text="Select one or more connected accounts for delivery.",
    )
    existing_media = forms.ModelMultipleChoiceField(
        queryset=Media.objects.none(),
        required=False,
        help_text="Optional: reuse an existing client asset.",
    )
    media_uploads = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "accept": "image/jpeg,image/png,image/webp,video/mp4,video/quicktime",
            },
        ),
        help_text="Optional: upload JPEG, PNG, WebP, MP4, or MOV assets.",
    )
    scheduled_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Post
        fields = (
            "client",
            "campaign",
            "title",
            "body",
            "social_accounts",
            "scheduled_at",
            "existing_media",
            "media_uploads",
        )
        widgets = {
            "body": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        self.fields["campaign"].queryset = Campaign.objects.select_related("client")
        self.fields["social_accounts"].queryset = SocialAccount.objects.filter(
            client__is_active=True,
            client__deleted_at__isnull=True,
            is_active=True,
        ).select_related("client")
        self.fields["existing_media"].queryset = Media.objects.filter(
            client__is_active=True,
            client__deleted_at__isnull=True,
            deleted_at__isnull=True,
        ).select_related("client")

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        campaign = cleaned_data.get("campaign")
        social_accounts = cleaned_data.get("social_accounts")
        existing_media = cleaned_data.get("existing_media")
        if client and campaign and campaign.client_id != client.pk:
            self.add_error("campaign", "Campaign must belong to the selected client.")
        if client and social_accounts:
            invalid_accounts = social_accounts.exclude(client=client)
            if invalid_accounts.exists():
                self.add_error(
                    "social_accounts",
                    "Every social account must belong to the selected client.",
                )
        if client and existing_media:
            invalid_media = existing_media.exclude(client=client)
            if invalid_media.exists():
                self.add_error(
                    "existing_media",
                    "Every selected asset must belong to the selected client.",
                )
        return cleaned_data
