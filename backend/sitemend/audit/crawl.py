"""Breadth-first crawl of one site through a fetch function.

The crawler does not follow redirects on its own: it records each hop so the
redirect rule can say how long a chain is. Each URL is fetched once.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .html import ParsedPage
from .rules import LinkStatus

MAX_PAGES = 200
MAX_HOPS = 5
REDIRECT_CODES = (301, 302, 307, 308)


@dataclass(frozen=True)
class Fetched:
    path: str
    status: int
    body: str
    location: str | None = None
    release: str | None = None


Fetch = Callable[[str], Fetched]
Progress = Callable[[int, int], None]


@dataclass
class CrawlResult:
    pages: list[ParsedPage] = field(default_factory=list)
    links: dict[str, LinkStatus] = field(default_factory=dict)
    fetches: int = 0
    release: str | None = None


def crawl(fetch: Fetch, start: str = "/", on_progress: Progress | None = None) -> CrawlResult:
    result = CrawlResult()
    cache: dict[str, Fetched] = {}

    def get(path: str) -> Fetched:
        if path not in cache:
            cache[path] = fetch(path)
            result.fetches += 1
        return cache[path]

    def resolve(path: str) -> LinkStatus:
        chain: list[str] = []
        current = path
        for _ in range(MAX_HOPS):
            got = get(current)
            if got.status in REDIRECT_CODES and got.location:
                chain.append(got.location)
                current = got.location
                continue
            if chain and got.status == 200:
                return LinkStatus(status=301, chain=tuple(chain), final=current)
            return LinkStatus(status=got.status, chain=tuple(chain), final=current)
        return LinkStatus(status=508, chain=tuple(chain), final=current)  # loop or too many hops

    queue: deque[str] = deque([start])
    queued = {start}
    result.links[start] = resolve(start)
    while queue and len(result.pages) < MAX_PAGES:
        path = queue.popleft()
        got = get(path)
        if got.release:
            result.release = got.release
        if got.status != 200:
            continue
        page = ParsedPage.parse(path, got.status, got.body)
        result.pages.append(page)
        for target, _node in page.links():
            if target not in result.links:
                result.links[target] = resolve(target)
            link = result.links[target]
            final = link.final or target
            if link.status in (200, 301) and final not in queued:
                queued.add(final)
                queue.append(final)
        if on_progress:
            on_progress(len(result.pages), len(result.pages) + len(queue))
    return result
