from __future__ import annotations

import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = os.environ.get("TAILSCALE_INDEX_HOST", "127.0.0.1")
PORT = int(os.environ.get("TAILSCALE_INDEX_PORT", "3012"))
SITE_DIR = Path(os.environ.get("TAILSCALE_INDEX_SITE_DIR", Path(__file__).parent / "site"))


class NoIndexStaticHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive, noimageindex, nosnippet")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    handler = partial(NoIndexStaticHandler, directory=str(SITE_DIR))
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
