import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from campaigns.models import Campaign
from clients.models import Client, ClientIndustry
from collaboration.models import ContentRequest, ContentRequestTarget
from integrations.models import Platform, SocialAccount
from publishing.models import (
    Post,
    PostAuditEvent,
    PostStatus,
    PostTarget,
    PostTargetStatus,
)


@pytest.fixture
def client_record():
    return Client.objects.create(
        name="Westlands Cafe",
        slug="westlands-cafe",
        industry=ClientIndustry.RESTAURANT,
    )


@pytest.fixture
def social_account(client_record):
    return SocialAccount.objects.create(
        client=client_record,
        platform=Platform.FACEBOOK,
        account_name="Westlands Cafe Page",
        platform_account_id="page-123",
    )


@pytest.mark.django_db
def test_social_account_tokens_are_encrypted_at_rest(client_record):
    account = SocialAccount.objects.create(
        client=client_record,
        platform=Platform.INSTAGRAM,
        account_name="Westlands Cafe Instagram",
        access_token="access-secret",
        refresh_token="refresh-secret",
        platform_account_id="instagram-123",
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT access_token, refresh_token FROM integrations_socialaccount WHERE id = %s",
            [account.pk],
        )
        raw_access_token, raw_refresh_token = cursor.fetchone()

    assert raw_access_token.startswith("fernet$")
    assert raw_refresh_token.startswith("fernet$")
    assert "access-secret" not in raw_access_token
    assert "refresh-secret" not in raw_refresh_token

    reloaded = SocialAccount.objects.get(pk=account.pk)
    assert reloaded.access_token == "access-secret"
    assert reloaded.refresh_token == "refresh-secret"


@pytest.mark.django_db
def test_partial_target_success_marks_post_published(client_record, social_account):
    post = Post.objects.create(
        client=client_record,
        title="Weekend brunch",
        status=PostStatus.PUBLISHING,
    )
    PostTarget.objects.create(
        post=post,
        social_account=social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.PUBLISHED,
    )
    instagram = SocialAccount.objects.create(
        client=client_record,
        platform=Platform.INSTAGRAM,
        account_name="Westlands Cafe Instagram",
        platform_account_id="instagram-123",
    )
    PostTarget.objects.create(
        post=post,
        social_account=instagram,
        platform=Platform.INSTAGRAM,
        status=PostTargetStatus.FAILED,
    )

    assert post.recalculate_terminal_status() == PostStatus.PUBLISHED
    post.refresh_from_db()
    assert post.status == PostStatus.PUBLISHED
    assert post.audit_entries.get().event_type == PostAuditEvent.STATUS_CHANGED


@pytest.mark.django_db
def test_all_target_failures_mark_post_failed(client_record, social_account):
    post = Post.objects.create(
        client=client_record,
        title="Unavailable post",
        status=PostStatus.PUBLISHING,
    )
    PostTarget.objects.create(
        post=post,
        social_account=social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.FAILED,
    )

    assert post.recalculate_terminal_status() == PostStatus.FAILED
    post.refresh_from_db()
    assert post.status == PostStatus.FAILED


@pytest.mark.django_db
def test_pending_target_keeps_post_publishing(client_record, social_account):
    post = Post.objects.create(
        client=client_record,
        title="Still publishing",
        status=PostStatus.PUBLISHING,
    )
    PostTarget.objects.create(
        post=post,
        social_account=social_account,
        platform=Platform.FACEBOOK,
        status=PostTargetStatus.PENDING,
    )

    assert post.recalculate_terminal_status() == PostStatus.PUBLISHING
    assert not post.audit_entries.exists()


@pytest.mark.django_db
def test_invalid_post_transition_is_rejected(client_record):
    post = Post.objects.create(client=client_record, title="Draft post")

    with pytest.raises(ValidationError, match="cannot transition"):
        post.transition_to(PostStatus.PUBLISHED)


@pytest.mark.django_db
def test_content_request_platforms_are_unique(client_record, django_user_model):
    user = django_user_model.objects.create_user(username="operator")
    campaign = Campaign.objects.create(client=client_record, name="Lunch Campaign")
    content_request = ContentRequest.objects.create(
        client=client_record,
        campaign=campaign,
        title="Promote lunch menu",
        post_type="STANDARD",
        brief="Feature the new lunch menu.",
        created_by=user,
    )
    ContentRequestTarget.objects.create(
        content_request=content_request,
        platform=Platform.FACEBOOK,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ContentRequestTarget.objects.create(
            content_request=content_request,
            platform=Platform.FACEBOOK,
        )
