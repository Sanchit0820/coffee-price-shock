"""Tests for the cached, robots-aware fetcher. The network is faked."""
import pytest

from src import config, http_client


class FakeResponse:
    def __init__(self, url, status=200, text=""):
        self.url = url
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": "text/html"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture
def fake_web(tmp_path, monkeypatch):
    """Serve a robots.txt that blocks /private, and record every request."""
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse(url, text="User-agent: *\nDisallow: /private\n")
        return FakeResponse(url, text=f"<html>{url}</html>")

    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(http_client._session, "get", fake_get)
    monkeypatch.setattr(http_client._limiter, "min_interval", 0)
    monkeypatch.setattr(config, "SCRAPE_DELAY_SECONDS", 0)
    http_client._robots.clear()
    http_client._robots_status.clear()
    return requested


def test_second_fetch_uses_cache(fake_web):
    url = "https://roaster.example/products/beans"
    assert http_client.fetch(url) == http_client.fetch(url)
    page_requests = [u for u in fake_web if not u.endswith("robots.txt")]
    assert page_requests == [url]  # fetched from the web only once


def test_robots_disallow_is_respected(fake_web):
    with pytest.raises(http_client.DisallowedByRobots):
        http_client.fetch("https://roaster.example/private/prices")


def test_robots_check_reports_status_without_fetching_page(fake_web):
    assert http_client.robots_check("https://roaster.example/shop") == (True, "found")
    assert http_client.robots_check("https://roaster.example/private/x") == (False, "found")
    assert all(u.endswith("robots.txt") for u in fake_web)


def test_refresh_bypasses_cache(fake_web):
    url = "https://roaster.example/products/beans"
    http_client.fetch(url)
    http_client.fetch(url, refresh=True)
    page_requests = [u for u in fake_web if not u.endswith("robots.txt")]
    assert page_requests == [url, url]
