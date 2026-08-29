from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit

import httpx


_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) POSCO-Market-Sensing/1.0"
_SEARCH_ENDPOINT = "https://lite.duckduckgo.com/lite/"
_MAX_SEARCH_BYTES = 512 * 1024
_MAX_FETCH_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SearchHit:
    rank: int
    title: str
    url: str
    snippet: str
    publisher: str

    def json(self) -> dict[str, object]:
        return asdict(self)


class _DuckParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[dict[str, str]] = []
        self._field: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and classes & {"result-link", "result__a"}:
            self._field, self._parts = "title", []
            self.hits.append({"url": _result_url(values.get("href") or "")})
        elif classes & {"result-snippet", "result__snippet"} and self.hits:
            self._field, self._parts = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._field:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._field and tag in {"a", "td", "div"} and self.hits:
            self.hits[-1][self._field] = " ".join("".join(self._parts).split())
            self._field, self._parts = None, []


class _ReadableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._title = False
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._title = True
        if tag in {"script", "style", "noscript", "svg", "form", "nav"}:
            self._skip += 1
        elif tag in {"p", "li", "h1", "h2", "h3", "tr", "br"} and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title = False
        if tag in {"script", "style", "noscript", "svg", "form", "nav"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._title:
            self.title += data
        if not self._skip:
            self.parts.append(data)


class PublicWeb:
    def __init__(self) -> None:
        timeout = httpx.Timeout(20, connect=10)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "identity"},
        )

    async def search(self, query: str, limit: int = 8) -> dict[str, object]:
        normalized = " ".join(query.split())[:500]
        if not normalized:
            raise ValueError("검색어가 비어 있습니다.")
        response = await self._client.get(
            f"{_SEARCH_ENDPOINT}?q={quote_plus(normalized)}"
        )
        body = response.content[:_MAX_SEARCH_BYTES]
        if response.status_code == 429:
            raise RuntimeError("DuckDuckGo 검색 요청이 제한되었습니다.")
        response.raise_for_status()
        if b"challenge-form" in body or b"captcha" in body.lower():
            raise RuntimeError("DuckDuckGo 확인 절차가 감지되었습니다.")
        parser = _DuckParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        seen: set[str] = set()
        hits: list[SearchHit] = []
        for raw in parser.hits:
            url = raw.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            host = (urlsplit(url).hostname or "").removeprefix("www.")
            hits.append(
                SearchHit(
                    rank=len(hits) + 1,
                    title=raw.get("title", "")[:300],
                    url=url,
                    snippet=raw.get("snippet", "")[:1_000],
                    publisher=host,
                )
            )
            if len(hits) >= max(1, min(limit, 10)):
                break
        return {
            "backend": "duckduckgo_lite",
            "query": normalized,
            "results": [h.json() for h in hits],
        }

    async def fetch(self, url: str) -> dict[str, object]:
        current = url.strip()
        for _ in range(4):
            await _require_public_url(current)
            async with self._client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    if not location:
                        raise RuntimeError("원문 이동 주소가 비어 있습니다.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if content_type not in {
                    "text/html",
                    "text/plain",
                    "application/xhtml+xml",
                }:
                    raise RuntimeError(
                        f"현재 읽을 수 없는 원문 형식입니다: {content_type or 'unknown'}"
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_FETCH_BYTES:
                        raise RuntimeError("원문이 허용된 크기를 초과했습니다.")
                    chunks.append(chunk)
                body = b"".join(chunks)
            text = body.decode("utf-8", errors="replace")
            if content_type == "text/plain":
                title, readable = current, text
            else:
                parser = _ReadableParser()
                parser.feed(text)
                title = " ".join(parser.title.split())
                readable = "\n".join(
                    line
                    for line in (
                        " ".join(part.split())
                        for part in "".join(parser.parts).splitlines()
                    )
                    if line
                )
            readable = readable[:60_000]
            if len(readable) < 80:
                raise RuntimeError("분석할 원문 내용을 확보하지 못했습니다.")
            return {
                "requested_url": url,
                "canonical_url": current,
                "title": title[:300],
                "publisher": (urlsplit(current).hostname or "").removeprefix("www."),
                "content": readable,
                "content_truncated": len(readable) >= 60_000,
            }
        raise RuntimeError("원문 이동 횟수가 허용 범위를 초과했습니다.")

    async def aclose(self) -> None:
        await self._client.aclose()


def _result_url(value: str) -> str:
    absolute = urljoin("https://lite.duckduckgo.com", value)
    parsed = urlsplit(absolute)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return absolute if parsed.scheme in {"http", "https"} else ""


async def _require_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("http 또는 https 공개 주소만 읽을 수 있습니다.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("인증정보가 포함된 주소는 읽을 수 없습니다.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    infos = await asyncio.to_thread(
        socket.getaddrinfo, parsed.hostname, port, type=socket.SOCK_STREAM
    )
    addresses = {item[4][0] for item in infos}
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("공개 인터넷 주소만 읽을 수 있습니다.")
