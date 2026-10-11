from django.http import HttpRequest, HttpResponse

from .origin import fetch_origin


def origin_page(request: HttpRequest, path: str = "") -> HttpResponse:
    """Serves the untouched synthetic shop, as its own web server would."""
    res = fetch_origin(path)
    if res.status in (301, 302):
        response = HttpResponse(status=res.status)
        response["Location"] = res.location or "/"
        return response
    return HttpResponse(res.body, status=res.status, content_type="text/html; charset=utf-8")
