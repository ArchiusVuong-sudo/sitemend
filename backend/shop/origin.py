"""The synthetic shop: static HTML files plus a redirect chain and missing pages.

The files are never edited by the app. The edge reads them through
``fetch_origin`` and rewrites a copy in memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SHOP_DIR = Path(__file__).resolve().parent
SITE_DIR = SHOP_DIR / "site"

# A two-hop chain: an old marketing path that moved twice.
REDIRECTS: dict[str, str] = {
    "/shop/mugs": "/mugs",
    "/mugs": "/collections/mugs",
}

NOT_FOUND_HTML = (
    b"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<title>Page not found</title>\n</head>\n"
    b"<body>\n<h1>Page not found</h1>\n</body>\n</html>\n"
)


@dataclass(frozen=True)
class OriginResponse:
    status: int
    body: bytes
    location: str | None = None


def normalize_path(path: str) -> str:
    path = "/" + path.strip("/")
    return path


def _file_for(path: str) -> Path:
    name = "index" if path == "/" else path.strip("/")
    candidate = (SITE_DIR / f"{name}.html").resolve()
    if SITE_DIR.resolve() not in candidate.parents:
        raise ValueError("path escapes the site folder")
    return candidate


def fetch_origin(path: str) -> OriginResponse:
    path = normalize_path(path)
    if path in REDIRECTS:
        return OriginResponse(status=301, body=b"", location=REDIRECTS[path])
    try:
        file = _file_for(path)
    except ValueError:
        return OriginResponse(status=404, body=NOT_FOUND_HTML)
    if not file.is_file():
        return OriginResponse(status=404, body=NOT_FOUND_HTML)
    return OriginResponse(status=200, body=file.read_bytes())


def all_page_paths() -> list[str]:
    paths = []
    for file in sorted(SITE_DIR.rglob("*.html")):
        rel = file.relative_to(SITE_DIR).with_suffix("").as_posix()
        paths.append("/" if rel == "index" else f"/{rel}")
    return paths


@cache
def search_data() -> dict[str, dict]:
    """Synthetic 28-day search performance per page (labelled synthetic in the UI)."""
    return json.loads((SHOP_DIR / "search_data.json").read_text())["pages"]


@cache
def planted_issues() -> list[dict]:
    """The manifest of issues planted in the synthetic site. Tests match scans to it exactly."""
    return json.loads((SHOP_DIR / "manifest.json").read_text())["issues"]
