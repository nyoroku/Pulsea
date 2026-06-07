import json
import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from time import sleep
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from django.conf import settings

from integrations.models import Platform
from media.image_processing import normalize_instagram_feed_image_file
from media.models import MediaType
from media.storage import get_private_storage

from .models import PostTarget


@dataclass(frozen=True)
class PublishResult:
    success: bool
    retryable: bool = False
    platform_post_id: str = ""
    platform_url: str = ""
    error_message: str = ""


class PlatformPublisher(Protocol):
    def publish(self, target: PostTarget) -> PublishResult:
        ...


class FakePublisher:
    def publish(self, target: PostTarget) -> PublishResult:
        config = getattr(target, "platform_config", None)
        config_json = config.config_json if config else {}
        behavior = config_json.get("fake_behavior", "success")
        failures_before_success = config_json.get("failures_before_success", 1)
        if behavior == "permanent_failure":
            return PublishResult(success=False, error_message="Fake permanent publishing failure.")
        if behavior == "temporary_failure" and target.retry_count < failures_before_success:
            return PublishResult(
                success=False,
                retryable=True,
                error_message="Fake retryable publishing failure.",
            )
        return PublishResult(
            success=True,
            platform_post_id=f"fake-{target.pk}",
            platform_url=f"https://example.invalid/{target.platform.lower()}/fake-{target.pk}",
        )


class FacebookPublisher:
    def publish(self, target: PostTarget) -> PublishResult:
        account = target.social_account
        page_id = account.page_id or account.platform_account_id
        if not page_id or not account.access_token:
            return PublishResult(
                success=False,
                error_message="Reconnect this Facebook Page before publishing.",
            )
        attachments = list(target.post.media_attachments.select_related("media"))
        images = [
            attachment.media
            for attachment in attachments
            if attachment.media.media_type == MediaType.IMAGE
        ]
        videos = [
            attachment.media
            for attachment in attachments
            if attachment.media.media_type == MediaType.VIDEO
        ]
        if images and videos:
            return PublishResult(
                success=False,
                error_message="Facebook posts cannot mix images and videos.",
            )
        if len(videos) > 1:
            return PublishResult(
                success=False,
                error_message="Facebook multiple-video publishing is not enabled yet.",
            )
        if len(images) > 1:
            return self._publish_images(target, page_id, images)
        if attachments:
            media = attachments[0].media
            if media.media_type == MediaType.VIDEO:
                return self._publish_video(target, page_id, media)
            return self._publish_image(target, page_id, media)
        return self._publish_text(target, page_id)

    def _publish_text(self, target: PostTarget, page_id: str) -> PublishResult:
        if not target.post.body.strip():
            return PublishResult(
                success=False,
                error_message="Facebook text posts require a message.",
            )

        try:
            response = _graph_post(
                f"{page_id}/feed",
                {
                    "access_token": target.social_account.access_token,
                    "message": target.post.body,
                },
            )
        except FacebookAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )
        return _facebook_publish_result(response)

    def _publish_image(self, target: PostTarget, page_id: str, media) -> PublishResult:
        storage = get_private_storage()
        try:
            with storage.open(media.file_key, "rb") as media_file:
                response = _graph_post_multipart(
                    f"{page_id}/photos",
                    {
                        "access_token": target.social_account.access_token,
                        "caption": target.post.body,
                    },
                    filename=PurePosixPath(media.file_key).name,
                    content=media_file.read(),
                )
        except FacebookAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )
        except OSError:
            return PublishResult(
                success=False,
                error_message="The attached media file could not be read.",
            )
        return _facebook_publish_result(response)

    def _publish_images(self, target: PostTarget, page_id: str, images: list) -> PublishResult:
        storage = get_private_storage()
        attached_media = []
        try:
            for media in images:
                with storage.open(media.file_key, "rb") as media_file:
                    response = _graph_post_multipart(
                        f"{page_id}/photos",
                        {
                            "access_token": target.social_account.access_token,
                            "published": "false",
                        },
                        filename=PurePosixPath(media.file_key).name,
                        content=media_file.read(),
                    )
                media_id = response.get("id", "")
                if not media_id:
                    return PublishResult(
                        success=False,
                        error_message="Facebook accepted an image without returning its media ID.",
                    )
                attached_media.append(json.dumps({"media_fbid": media_id}))
            response = _graph_post(
                f"{page_id}/feed",
                {
                    "access_token": target.social_account.access_token,
                    "message": target.post.body,
                    "attached_media": attached_media,
                },
            )
        except FacebookAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )
        except OSError:
            return PublishResult(
                success=False,
                error_message="An attached media file could not be read.",
            )
        return _facebook_publish_result(response)

    def _publish_video(self, target: PostTarget, page_id: str, media) -> PublishResult:
        storage = get_private_storage()
        try:
            with storage.open(media.file_key, "rb") as media_file:
                response = _graph_post_multipart(
                    f"{page_id}/videos",
                    {
                        "access_token": target.social_account.access_token,
                        "description": target.post.body,
                        "title": target.post.title,
                    },
                    filename=PurePosixPath(media.file_key).name,
                    content=media_file.read(),
                )
        except FacebookAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )
        except OSError:
            return PublishResult(
                success=False,
                error_message="The attached media file could not be read.",
            )
        return _facebook_publish_result(response)


class InstagramPublisher:
    def publish(self, target: PostTarget) -> PublishResult:
        account = target.social_account
        instagram_id = account.instagram_business_account_id or account.platform_account_id
        if not instagram_id or not account.access_token:
            return PublishResult(
                success=False,
                error_message="Reconnect this Instagram account before publishing.",
            )
        attachments = list(target.post.media_attachments.select_related("media"))
        if not attachments:
            return PublishResult(
                success=False,
                error_message="Instagram posts require at least one image or video.",
            )
        if len(attachments) > 10:
            return PublishResult(
                success=False,
                error_message="Instagram carousel posts support up to 10 media files.",
            )
        storage = get_private_storage()
        try:
            media_urls = _instagram_media_urls(storage, target, attachments)
        except ValueError as exc:
            return PublishResult(success=False, error_message=str(exc))

        if len(attachments) == 1:
            return self._publish_single(target, instagram_id, attachments[0].media, media_urls[0])
        return self._publish_carousel(target, instagram_id, attachments, media_urls)

    def _publish_single(self, target: PostTarget, instagram_id: str, media, media_url: str):
        payload = {
            "access_token": target.social_account.access_token,
            "caption": target.post.body,
        }
        if media.media_type == MediaType.VIDEO:
            payload.update({"video_url": media_url, "media_type": "REELS"})
        else:
            payload["image_url"] = media_url
        try:
            response = _instagram_graph_post(f"{instagram_id}/media", payload)
            container_id = response.get("id", "")
            if not container_id:
                return PublishResult(
                    success=False,
                    error_message="Instagram accepted the media without returning a container ID.",
                )
            _wait_for_instagram_container(
                container_id,
                target.social_account.access_token,
            )
            return _publish_instagram_container(target, instagram_id, container_id)
        except InstagramAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )

    def _publish_carousel(
        self,
        target: PostTarget,
        instagram_id: str,
        attachments: list,
        media_urls: list[str],
    ) -> PublishResult:
        access_token = target.social_account.access_token
        children = []
        try:
            for attachment, media_url in zip(attachments, media_urls, strict=True):
                media = attachment.media
                payload = {
                    "access_token": access_token,
                    "is_carousel_item": "true",
                }
                if media.media_type == MediaType.VIDEO:
                    payload.update({"video_url": media_url, "media_type": "VIDEO"})
                else:
                    payload["image_url"] = media_url
                response = _instagram_graph_post(f"{instagram_id}/media", payload)
                child_id = response.get("id", "")
                if not child_id:
                    return PublishResult(
                        success=False,
                        error_message=(
                            "Instagram accepted carousel media without returning a container ID."
                        ),
                    )
                _wait_for_instagram_container(child_id, access_token)
                children.append(child_id)
            response = _instagram_graph_post(
                f"{instagram_id}/media",
                {
                    "access_token": access_token,
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": target.post.body,
                },
            )
            carousel_id = response.get("id", "")
            if not carousel_id:
                return PublishResult(
                    success=False,
                    error_message="Instagram did not return a carousel container ID.",
                )
            return _publish_instagram_container(target, instagram_id, carousel_id)
        except InstagramAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )


class PinterestPublisher:
    def publish(self, target: PostTarget) -> PublishResult:
        account = target.social_account
        if not account.platform_account_id or not account.access_token:
            return PublishResult(
                success=False,
                error_message="Reconnect this Pinterest board before publishing.",
            )
        attachments = list(target.post.media_attachments.select_related("media"))
        if not attachments:
            return PublishResult(success=False, error_message="Pinterest posts require one image.")
        if len(attachments) != 1 or attachments[0].media.media_type != MediaType.IMAGE:
            return PublishResult(
                success=False,
                error_message="Pinterest publishing currently supports exactly one image.",
            )
        storage = get_private_storage()
        try:
            media_url = _instagram_media_url(storage, attachments[0].media.file_key)
            response = _pinterest_api_post(
                "pins",
                account.access_token,
                {
                    "board_id": account.platform_account_id,
                    "title": target.post.title,
                    "description": target.post.body,
                    "media_source": {
                        "source_type": "image_url",
                        "url": media_url,
                    },
                },
            )
        except ValueError as exc:
            return PublishResult(success=False, error_message=str(exc))
        except PinterestAPIError as exc:
            return PublishResult(
                success=False,
                retryable=exc.retryable,
                error_message=str(exc),
            )
        pin_id = str(response.get("id") or "")
        if not pin_id:
            return PublishResult(
                success=False,
                error_message="Pinterest accepted the request without returning a Pin ID.",
            )
        return PublishResult(
            success=True,
            platform_post_id=pin_id,
            platform_url=response.get("link") or f"https://www.pinterest.com/pin/{pin_id}/",
        )


class UnsupportedPublisher:
    def publish(self, target: PostTarget) -> PublishResult:
        return PublishResult(
            success=False,
            error_message=f"Live publishing is not configured for {target.get_platform_display()}.",
        )


class FacebookAPIError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class InstagramAPIError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class PinterestAPIError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _graph_post(path: str, payload: dict[str, str | list[str]]) -> dict:
    url = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{path}"
    request = Request(
        url,
        data=urlencode(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise FacebookAPIError(
            _facebook_error_message(exc),
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise FacebookAPIError(
            "Facebook could not be reached. Pulsea will retry this delivery.",
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise FacebookAPIError("Facebook returned an invalid response.") from exc


def _graph_post_multipart(
    path: str,
    fields: dict[str, str],
    *,
    filename: str,
    content: bytes,
) -> dict:
    boundary = f"pulsea-{uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="source"; filename="{filename}"\r\n'.encode()
    )
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(content)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    request = Request(
        f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{path}",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise FacebookAPIError(
            _facebook_error_message(exc),
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise FacebookAPIError(
            "Facebook could not be reached. Pulsea will retry this delivery.",
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise FacebookAPIError("Facebook returned an invalid response.") from exc


def _facebook_publish_result(response: dict) -> PublishResult:
    platform_post_id = response.get("post_id") or response.get("id", "")
    if not platform_post_id:
        return PublishResult(
            success=False,
            error_message="Facebook accepted the request without returning a post ID.",
        )
    return PublishResult(
        success=True,
        platform_post_id=platform_post_id,
        platform_url=f"https://www.facebook.com/{platform_post_id}",
    )


def _facebook_error_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("error", {}).get("message", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        message = ""
    return message or f"Facebook rejected this post with HTTP {exc.code}."


def _instagram_graph_post(path: str, payload: dict[str, str]) -> dict:
    request = Request(
        f"https://graph.instagram.com/{settings.INSTAGRAM_API_VERSION}/{path}",
        data=urlencode(payload).encode("utf-8"),
        method="POST",
    )
    return _instagram_request_json(request)


def _instagram_graph_get(path: str, params: dict[str, str]) -> dict:
    query = urlencode(params)
    request = Request(
        f"https://graph.instagram.com/{settings.INSTAGRAM_API_VERSION}/{path}?{query}",
    )
    return _instagram_request_json(request)


def _instagram_request_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise InstagramAPIError(
            _instagram_error_message(exc),
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise InstagramAPIError(
            "Instagram could not be reached. Pulsea will retry this delivery.",
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise InstagramAPIError("Instagram returned an invalid response.") from exc


def _instagram_error_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("error", {}).get("message", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        message = ""
    return message or f"Instagram rejected this post with HTTP {exc.code}."


def _pinterest_api_post(path: str, access_token: str, payload: dict) -> dict:
    request = Request(
        f"https://api.pinterest.com/v5/{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise PinterestAPIError(
            _pinterest_error_message(exc),
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise PinterestAPIError(
            "Pinterest could not be reached. Pulsea will retry this delivery.",
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PinterestAPIError("Pinterest returned an invalid response.") from exc


def _pinterest_error_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("message", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        message = ""
    return message or f"Pinterest rejected this post with HTTP {exc.code}."


def _instagram_media_url(storage, file_key: str) -> str:
    try:
        media_url = storage.url(file_key)
    except ValueError as exc:
        raise ValueError(
            "Instagram publishing requires public media URLs. "
            "Configure S3 storage before publishing from Pulsea."
        ) from exc
    parsed = urlparse(media_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError(
            "Instagram publishing requires a publicly reachable media URL."
        )
    return media_url


def _instagram_media_urls(storage, target: PostTarget, attachments: list) -> list[str]:
    urls = []
    for attachment in attachments:
        media = attachment.media
        file_key = media.file_key
        if media.media_type == MediaType.IMAGE:
            file_key = _instagram_normalized_image_key(storage, target, media)
        urls.append(_instagram_media_url(storage, file_key))
    return urls


def _instagram_normalized_image_key(storage, target: PostTarget, media) -> str:
    with storage.open(media.file_key, "rb") as media_file:
        normalized_file = normalize_instagram_feed_image_file(media_file, media.file_key)
    if normalized_file is None:
        raise ValueError("Instagram image posts require JPEG, PNG, or WebP files.")
    return storage.save_for_client(
        target.post.client_id,
        PurePosixPath(media.file_key).name,
        normalized_file,
    )


def _wait_for_instagram_container(container_id: str, access_token: str) -> None:
    for attempt in range(settings.INSTAGRAM_CONTAINER_POLL_ATTEMPTS):
        response = _instagram_graph_get(
            container_id,
            {
                "fields": "status_code,status",
                "access_token": access_token,
            },
        )
        status_code = response.get("status_code", "")
        if status_code in {"FINISHED", "PUBLISHED"}:
            return
        if status_code in {"ERROR", "EXPIRED"}:
            status = response.get("status", "")
            raise InstagramAPIError(status or "Instagram could not process the media.")
        if attempt + 1 < settings.INSTAGRAM_CONTAINER_POLL_ATTEMPTS:
            sleep(settings.INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS)
    raise InstagramAPIError(
        "Instagram is still processing the media. Pulsea will retry this delivery.",
        retryable=True,
    )


def _publish_instagram_container(
    target: PostTarget,
    instagram_id: str,
    container_id: str,
) -> PublishResult:
    response = _instagram_graph_post(
        f"{instagram_id}/media_publish",
        {
            "access_token": target.social_account.access_token,
            "creation_id": container_id,
        },
    )
    platform_post_id = response.get("id", "")
    if not platform_post_id:
        return PublishResult(
            success=False,
            error_message="Instagram accepted the request without returning a media ID.",
        )
    try:
        media = _instagram_graph_get(
            platform_post_id,
            {
                "fields": "permalink",
                "access_token": target.social_account.access_token,
            },
        )
        platform_url = media.get("permalink", "")
    except InstagramAPIError:
        platform_url = ""
    return PublishResult(
        success=True,
        platform_post_id=platform_post_id,
        platform_url=platform_url,
    )


def get_publisher(target: PostTarget) -> PlatformPublisher:
    if settings.PUBLISHING_ADAPTER_MODE == "fake":
        return FakePublisher()
    if target.platform == Platform.FACEBOOK:
        return FacebookPublisher()
    if target.platform == Platform.INSTAGRAM:
        return InstagramPublisher()
    if target.platform == Platform.PINTEREST:
        return PinterestPublisher()
    return UnsupportedPublisher()
