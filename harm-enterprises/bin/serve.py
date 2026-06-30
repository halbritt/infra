#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


ROOT = Path("/home/halbritt/sites/harm-enterprises/public")
HOST = "127.0.0.1"
PORT = 18888


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive, noimageindex, nosnippet")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
        super().end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
