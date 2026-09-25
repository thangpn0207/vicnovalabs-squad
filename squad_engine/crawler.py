#!/usr/bin/env python3
"""
Crawl4AI-Inspired Intelligent Web & Docs Scraper.
Extracts clean, noise-free Markdown from web documentation, pub.dev, npm, and GitHub pages.
Strips headers, footers, scripts, and ads to optimize LLM token budget.
"""

import ipaddress
import os
import re
import socket
import ssl
import hashlib
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# SSRF Protection — Block list for private/internal IP ranges
# ---------------------------------------------------------------------------
_SSRF_BLOCKED_HOSTS = {
    "localhost", "0.0.0.0",
}

_SSRF_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback
    ipaddress.ip_network("10.0.0.0/8"),     # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.168.0.0/16"), # Private Class C
    ipaddress.ip_network("169.254.0.0/16"), # Link-local / AWS metadata
    ipaddress.ip_network("::1/128"),        # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),       # IPv6 ULA
]


def _is_ssrf_blocked(url: str) -> bool:
    """Returns True if the URL resolves to a private/internal address."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return True
        if host.lower() in _SSRF_BLOCKED_HOSTS:
            return True
        # Resolve hostname to IP and check network ranges
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            try:
                resolved = socket.gethostbyname(host)
                addr = ipaddress.ip_address(resolved)
            except Exception:
                return False  # Cannot resolve — allow (fail-open for DNS errors)
        for network in _SSRF_BLOCKED_NETWORKS:
            if addr in network:
                return True
        return False
    except Exception:
        return False


class ReadabilityHTMLParser(HTMLParser):
    """Strips noisy HTML tags and converts article body into clean Markdown."""

    IGNORED_TAGS = {
        "script", "style", "nav", "footer", "header", "aside",
        "svg", "noscript", "iframe", "form", "button", "input"
    }

    BLOCK_TAGS = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}

    def __init__(self):
        super().__init__()
        self.ignored_stack = []
        self.in_pre = False
        self.in_link = False
        self.link_href = ""
        self.link_text = []
        self.title = ""
        self.in_title = False
        self.output_parts = []
        self.current_heading_level = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        classes = attrs_dict.get("class", "").lower()
        elem_id = attrs_dict.get("id", "").lower()
        is_noise = any(noise in classes or noise in elem_id for noise in ["footer", "cookie", "banner", "sidebar", "nav", "ad-"])

        if tag_lower in self.IGNORED_TAGS or is_noise or self.ignored_stack:
            self.ignored_stack.append(tag_lower)
            return

        if tag_lower == "title":
            self.in_title = True
        elif tag_lower in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            self.current_heading_level = int(tag_lower[1])
            self.output_parts.append(f"\n\n{'#' * self.current_heading_level} ")
        elif tag_lower == "pre":
            self.in_pre = True
            self.output_parts.append("\n```\n")
        elif tag_lower == "code" and not self.in_pre:
            self.output_parts.append("`")
        elif tag_lower == "a":
            self.in_link = True
            self.link_href = attrs_dict.get("href", "")
            self.link_text = []
        elif tag_lower in ["p", "div", "section", "article"]:
            self.output_parts.append("\n\n")
        elif tag_lower == "li":
            self.output_parts.append("\n- ")
        elif tag_lower == "br":
            self.output_parts.append("\n")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()

        if self.ignored_stack:
            if tag_lower in self.ignored_stack:
                while self.ignored_stack:
                    popped = self.ignored_stack.pop()
                    if popped == tag_lower:
                        break
            return

        if tag_lower == "title":
            self.in_title = False
        elif tag_lower in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            self.current_heading_level = 0
            self.output_parts.append("\n")
        elif tag_lower == "pre":
            self.in_pre = False
            self.output_parts.append("\n```\n")
        elif tag_lower == "code" and not self.in_pre:
            self.output_parts.append("`")
        elif tag_lower == "a":
            self.in_link = False
            text = "".join(self.link_text).strip()
            if text and self.link_href and not self.link_href.startswith("javascript:"):
                self.output_parts.append(f"[{text}]({self.link_href})")
            elif text:
                self.output_parts.append(text)
            self.link_text = []

    def handle_data(self, data):
        if self.ignored_stack:
            return

        if self.in_title:
            self.title += data
            return

        if self.in_link:
            self.link_text.append(data)
            return

        if self.in_pre:
            self.output_parts.append(data)
        else:
            # Normalize whitespace
            clean = re.sub(r"[ \t]+", " ", data)
            self.output_parts.append(clean)

    def get_markdown(self) -> str:
        raw = "".join(self.output_parts)
        # Collapse multiple empty lines into at most two
        collapsed = re.sub(r"\n{3,}", "\n\n", raw)
        return collapsed.strip()


def crawl_url_to_markdown(
    url: str,
    max_tokens: int = 1500,
    cache_dir: Optional[str] = None,
    timeout: int = 15,
    verify_tls: bool = True
) -> Dict[str, Any]:
    """
    Fetches URL and converts into clean, noise-free Markdown.
    Caches results locally to guarantee 0 token waste on repeated lookups.

    Args:
        url: Target URL to crawl.
        max_tokens: Maximum output token budget (default 1500).
        cache_dir: Local cache directory (default .squad/cache/docs).
        timeout: HTTP request timeout in seconds.
        verify_tls: Verify TLS certificate (default True). Set False only in local dev.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # P1-A: SSRF Protection Gate — block internal/private network requests
    if _is_ssrf_blocked(url):
        return {
            "status": "blocked",
            "url": url,
            "error": "SSRF_PROTECTION: URL resolves to a private/internal address. Crawling internal endpoints is prohibited.",
            "markdown": ""
        }

    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    c_dir = Path(cache_dir) if cache_dir else Path(".squad/cache/docs")
    c_dir.mkdir(parents=True, exist_ok=True)
    cache_file = c_dir / f"{url_hash}.md"

    if cache_file.exists():
        cached_content = cache_file.read_text(encoding="utf-8")
        return {
            "status": "cached",
            "url": url,
            "cache_file": str(cache_file),
            "markdown": cached_content,
            "estimated_tokens": len(cached_content) // 4
        }

    # Fetch webpage
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    req = urllib.request.Request(url, headers=headers)

    # P1-B: TLS verification — enabled by default, opt-out only for local dev
    if verify_tls:
        ctx = ssl.create_default_context()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            raw_html = response.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {
            "status": "error",
            "url": url,
            "error": str(e),
            "markdown": ""
        }

    parser = ReadabilityHTMLParser()
    try:
        parser.feed(raw_html)
        markdown = parser.get_markdown()
    except Exception as parse_err:
        return {
            "status": "error",
            "url": url,
            "error": f"Parse error: {str(parse_err)}",
            "markdown": ""
        }

    title = parser.title.strip() or url
    max_chars = max_tokens * 4
    truncated = False
    if len(markdown) > max_chars:
        markdown = markdown[:max_chars] + f"\n\n... *(Content truncated to fit token budget of {max_tokens} tokens)*"
        truncated = True

    header = f"# {title}\n*Source: {url}*\n\n---\n\n"
    final_output = header + markdown
    cache_file.write_text(final_output, encoding="utf-8")

    return {
        "status": "success",
        "url": url,
        "title": title,
        "cache_file": str(cache_file),
        "markdown": final_output,
        "char_count": len(final_output),
        "estimated_tokens": len(final_output) // 4,
        "truncated": truncated
    }
