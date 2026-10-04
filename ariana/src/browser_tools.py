from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from urllib.parse import quote_plus, urlparse

from livekit.agents import RunContext
from livekit.agents.llm import ToolError, Toolset, function_tool
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    async_playwright,
)

DEFAULT_TIMEOUT_MS = 15_000
MAX_TEXT_LENGTH = 8_000
MAX_LINKS = 30
BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


class BrowserToolset(Toolset):
    """Session-scoped, read-only browser tools backed by Playwright WebKit."""

    def __init__(self, *, headless: bool | None = None) -> None:
        super().__init__(id="browser")
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._page_lock = asyncio.Lock()
        self._timeout_ms = _env_int("ARIANA_BROWSER_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)
        self._max_text_length = _env_int(
            "ARIANA_BROWSER_MAX_TEXT_LENGTH", MAX_TEXT_LENGTH
        )
        self._allowed_hosts = _env_hosts("ARIANA_BROWSER_ALLOWED_HOSTS")

    async def setup(self) -> BrowserToolset:
        await super().setup()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.webkit.launch(
            headless=(
                self._headless
                if self._headless is not None
                else _env_bool("ARIANA_BROWSER_HEADLESS", False)
            )
        )
        self._context = await self._browser.new_context()
        await self._context.route("**/*", self._route_request)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        return self

    async def aclose(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            await super().aclose()

    @function_tool
    async def browser_search(
        self, context: RunContext, query: str
    ) -> dict[str, str | int]:
        """Open a visible web search page for the user's query."""
        query = query.strip()
        if not query:
            raise ToolError("Tell me what you want to search for.")

        page = self._require_page()
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        async with self._page_lock:
            await self._validate_url(search_url)
            try:
                response = await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout_ms,
                )
                await self._validate_url(page.url)
                summary = await self._page_summary(
                    page, response.status if response else 0
                )
                summary["query"] = query
                return summary
            except Exception as error:
                raise ToolError(f"Could not open the search page: {error}") from error

    @function_tool
    async def browser_open(self, context: RunContext, url: str) -> dict[str, str | int]:
        """Open a public HTTP(S) page and return its title and a short text preview."""
        page = self._require_page()
        async with self._page_lock:
            await self._validate_url(url)
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout_ms,
                )
                await self._validate_url(page.url)
                return await self._page_summary(
                    page, response.status if response else 0
                )
            except Exception as error:
                raise ToolError(f"Could not open that page: {error}") from error

    @function_tool
    async def browser_read(self, context: RunContext) -> dict[str, str | int]:
        """Read the current page title, URL, and bounded visible text."""
        page = self._require_page()
        async with self._page_lock:
            return await self._page_summary(page)

    @function_tool
    async def browser_links(self, context: RunContext) -> list[dict[str, str]]:
        """List the first useful links from the current page."""
        page = self._require_page()
        async with self._page_lock:
            links = await page.locator("a").evaluate_all(
                """
                (elements, maxLinks) => elements
                    .map((element) => ({
                        text: (element.innerText || element.getAttribute('aria-label') || '').trim(),
                        href: element.href || ''
                    }))
                    .filter((link) => link.text && link.href)
                    .slice(0, maxLinks)
                """,
                MAX_LINKS,
            )
            return [
                {"text": link["text"][:200], "href": link["href"]}
                for link in links
                if _is_http_url(link["href"])
            ]

    @function_tool
    async def browser_current_page(self, context: RunContext) -> dict[str, str]:
        """Return the current page URL and title without reading page content."""
        page = self._require_page()
        async with self._page_lock:
            return {"url": page.url, "title": await page.title()}

    async def _page_summary(
        self, page: Page, status: int | None = None
    ) -> dict[str, str | int]:
        text = await page.locator("body").inner_text(timeout=self._timeout_ms)
        summary: dict[str, str | int] = {
            "url": page.url,
            "title": await page.title(),
            "text": _clean_text(text)[: self._max_text_length],
        }
        if status:
            summary["status"] = status
        return summary

    async def _route_request(self, route: Route) -> None:
        try:
            await self._validate_url(route.request.url)
            await route.continue_()
        except ToolError:
            await route.abort("blockedbyclient")

    async def _validate_url(self, raw_url: str) -> None:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ToolError("Only public HTTP and HTTPS pages are allowed.")
        if parsed.username or parsed.password:
            raise ToolError("URLs containing usernames or passwords are not allowed.")

        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in BLOCKED_HOSTS or hostname.endswith(".local"):
            raise ToolError("Local and internal hosts are blocked.")
        if self._allowed_hosts and not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in self._allowed_hosts
        ):
            raise ToolError("That host is not on the browser allowlist.")

        addresses = await asyncio.get_running_loop().run_in_executor(
            None, _resolve_addresses, hostname
        )
        if any(_is_private_address(address) for address in addresses):
            raise ToolError("Private and internal network addresses are blocked.")

    def _require_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise ToolError(
                "The browser is not ready. Start a new session and try again."
            )
        return self._page


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _env_hosts(name: str) -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in os.environ.get(name, "").split(",")
        if host.strip()
    }


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def _resolve_addresses(hostname: str) -> list[str]:
    try:
        return list(
            {
                result[4][0]
                for result in socket.getaddrinfo(
                    hostname, None, type=socket.SOCK_STREAM
                )
            }
        )
    except socket.gaierror as error:
        raise ToolError(f"Could not resolve that host: {hostname}") from error


def _is_private_address(address: str) -> bool:
    parsed = ipaddress.ip_address(address)
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_unspecified
        or parsed.is_multicast
    )


def _is_http_url(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}


def _clean_text(text: str) -> str:
    return " ".join(text.split())
