#!/usr/bin/env python3
"""
Tests for Crawl4AI-inspired clean web scraper (squad_engine/crawler.py).
"""

import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from squad_engine.crawler import ReadabilityHTMLParser, crawl_url_to_markdown


class TestCrawler(unittest.TestCase):

    def test_parser_strips_noise_and_converts_markdown(self):
        html = """
        <html>
          <head>
            <title>My API Documentation</title>
            <script>console.log("noisy tracking script");</script>
            <style>body { background: red; }</style>
          </head>
          <body>
            <header><nav><a href="/home">Home</a></nav></header>
            <div class="sidebar">Sidebar ads and links</div>
            <article>
              <h1>API Endpoint: /api/v1/auth</h1>
              <p>This endpoint authenticates users using <code>JWT</code> tokens.</p>
              <pre>POST /api/v1/auth HTTP/1.1</pre>
              <ul>
                <li>Parameter 1: username</li>
                <li>Parameter 2: password</li>
              </ul>
              <a href="https://example.com/docs">Read more</a>
            </article>
            <footer class="footer-bottom">Copyright 2026</footer>
          </body>
        </html>
        """
        parser = ReadabilityHTMLParser()
        parser.feed(html)
        md = parser.get_markdown()

        self.assertIn("# API Endpoint: /api/v1/auth", md)
        self.assertIn("This endpoint authenticates users using `JWT` tokens.", md)
        self.assertIn("POST /api/v1/auth HTTP/1.1", md)
        self.assertIn("- Parameter 1: username", md)
        self.assertIn("[Read more](https://example.com/docs)", md)
        # Noise should be stripped
        self.assertNotIn("noisy tracking script", md)
        self.assertNotIn("Sidebar ads", md)
        self.assertNotIn("Copyright 2026", md)

    def test_crawl_url_caching_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_html = "<html><head><title>Test Lib</title></head><body><p>" + ("long text " * 100) + "</p></body></html>"
            mock_resp = MagicMock()
            mock_resp.read.return_value = sample_html.encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp

            with patch("urllib.request.urlopen", return_value=mock_resp):
                # 1. First fetch
                res1 = crawl_url_to_markdown("https://example.com/lib", max_tokens=50, cache_dir=tmpdir)
                self.assertEqual(res1["status"], "success")
                self.assertTrue(res1["truncated"])
                self.assertTrue(Path(res1["cache_file"]).exists())

                # 2. Second fetch hits cache
                res2 = crawl_url_to_markdown("https://example.com/lib", max_tokens=50, cache_dir=tmpdir)
                self.assertEqual(res2["status"], "cached")


if __name__ == "__main__":
    unittest.main()
