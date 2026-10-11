from django.http import HttpRequest, HttpResponse

from shop.origin import fetch_origin

from ..models import Release, Site
from ..releases import ops_for_path
from .rewriter import rewrite_bytes


def render_edge(path: str) -> tuple[int, bytes, str | None, str]:
    """What the edge serves for a path: origin HTML with the active release applied."""
    res = fetch_origin(path)
    site = Site.objects.select_related("active_release").order_by("id").first()
    release: Release | None = site.active_release if site else None
    label = release.label if release else "none"
    if res.status != 200:
        return res.status, res.body, res.location, label
    norm = "/" + path.strip("/")
    return 200, rewrite_bytes(res.body, ops_for_path(release, norm), norm), None, label


def edge_page(request: HttpRequest, path: str = "") -> HttpResponse:
    status, body, location, label = render_edge(path)
    if location:
        response = HttpResponse(status=status)
        response["Location"] = location
    else:
        response = HttpResponse(body, status=status, content_type="text/html; charset=utf-8")
    response["X-Sitemend-Release"] = label
    response["Cache-Control"] = "no-store"
    return response
