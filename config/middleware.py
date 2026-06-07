import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class RequestIdMiddleware:
    header_name = "HTTP_X_REQUEST_ID"
    response_header = "X-Request-ID"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.request_id = request.META.get(self.header_name) or str(uuid.uuid4())
        response = self.get_response(request)
        response[self.response_header] = request.request_id
        return response

