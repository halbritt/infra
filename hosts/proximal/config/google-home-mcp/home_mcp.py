"""Authorize and inspect Google Home events; never issue device actions."""
import argparse
import asyncio
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SCOPE = 'https://www.googleapis.com/auth/home.platform.v2'
ENDPOINT = 'https://home.googleapis.com/mcp'
CALLBACK = 'https://proximal.tail0ecc2e.ts.net:8797/oauth/callback'
CONFIG = Path.home() / '.config/google-home-mcp'
READ_TOOLS = ('list_homes', 'list_home_resources', 'list_home_states', 'list_home_history')


def private_write(path, contents):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def client_config(directory):
    config = json.loads((directory / 'client.json').read_text())
    web = config['web']
    if web['project_id'] != 'heath-stuff':
        raise ValueError('OAuth client must belong to heath-stuff')
    if CALLBACK not in web['redirect_uris']:
        raise ValueError('OAuth client is missing the configured redirect URI')
    if web['auth_uri'] != 'https://accounts.google.com/o/oauth2/auth':
        raise ValueError('Unexpected authorization endpoint')
    if web['token_uri'] != 'https://oauth2.googleapis.com/token':
        raise ValueError('Unexpected token endpoint')
    return config


class Authorization:
    def __init__(self, directory):
        self.directory = directory
        self.flow = None
        self.state = None
        self.started = 0
        self.complete = False

    def begin(self):
        self.flow = Flow.from_client_config(client_config(self.directory),
                                           scopes=[SCOPE], redirect_uri=CALLBACK)
        url, self.state = self.flow.authorization_url(
            access_type='offline', prompt='consent')
        self.started = time.monotonic()
        return url

    def finish(self, query):
        states = query.get('state', [])
        if (len(states) != 1 or not self.state
                or not secrets.compare_digest(states[0], self.state)
                or time.monotonic() - self.started > 600):
            raise ValueError('Invalid or expired OAuth state')
        self.state = None  # A callback can be consumed only once, even on failure.
        if query.get('error'):
            raise ValueError('Google authorization was declined')
        codes = query.get('code', [])
        if len(codes) != 1 or not codes[0]:
            raise ValueError('Missing authorization code')
        self.flow.fetch_token(code=codes[0], timeout=30)
        credentials = self.flow.credentials
        if not credentials.refresh_token or not credentials.has_scopes([SCOPE]):
            raise ValueError('Google did not grant persistent Home API access')
        private_write(self.directory / 'token.json', credentials.to_json())
        self.complete = True


def auth_handler(auth):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback queries contain authorization codes.

        def respond(self, status, body):
            encoded = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            route = urlsplit(self.path)
            if route.path == '/health':
                ready = (auth.directory / 'client.json').is_file()
                self.respond(200, json.dumps({'client_present': ready,
                                              'authorized': auth.complete}))
                return
            if self.headers.get('Tailscale-User-Login') != 'halbritt@gmail.com':
                self.respond(403, 'Open this page through the owner Tailscale account.')
                return
            try:
                if route.path == '/login':
                    url = auth.begin()
                    self.send_response(302)
                    self.send_header('Location', url)
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.end_headers()
                elif route.path == '/oauth/callback':
                    auth.finish(parse_qs(route.query))
                    self.respond(200, 'Google Home access saved. You can close this page.')
                else:
                    self.respond(404, 'Not found')
            except FileNotFoundError:
                self.respond(503, 'Save the Google OAuth client JSON on proximal first.')
            except Exception as error:
                # OAuth exceptions can include codes/tokens; expose only their class.
                print('OAuth failed: ' + type(error).__name__, flush=True)
                self.respond(400, 'Authorization failed. Reopen /login to try again.')
    return Handler


def authorize(directory, seconds):
    auth = Authorization(directory)
    with HTTPServer(('127.0.0.1', 8797), auth_handler(auth)) as server:
        server.timeout = 1
        deadline = time.monotonic() + seconds
        print('Open https://proximal.tail0ecc2e.ts.net:8797/login', flush=True)
        while not auth.complete and time.monotonic() < deadline:
            server.handle_request()
    if not auth.complete:
        raise TimeoutError('Authorization window expired')
    print('Google Home OAuth saved; familiar-face consent is still separate.')


def access_token(directory):
    credentials = Credentials.from_authorized_user_file(directory / 'token.json')
    if not credentials.has_scopes([SCOPE]):
        raise ValueError('Stored token lacks Home API scope')
    if not credentials.valid:
        credentials.refresh(Request())
        private_write(directory / 'token.json', credentials.to_json())
    return credentials.token


async def read_home(directory, tool, arguments):
    if tool is not None and tool not in READ_TOOLS:
        raise ValueError('Only read-only Home tools are permitted')
    token = access_token(directory)
    async with streamablehttp_client(ENDPOINT, headers={'Authorization': 'Bearer ' + token},
                                     timeout=30, sse_read_timeout=45) as streams:
        async with ClientSession(streams[0], streams[1],
                                 read_timeout_seconds=timedelta(seconds=45)) as session:
            await session.initialize()
            if tool is None:
                result = await session.list_tools()
            else:
                result = await session.call_tool(tool, arguments)
            return result.model_dump(mode='json', by_alias=True, exclude_none=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=CONFIG)
    commands = parser.add_subparsers(dest='command', required=True)
    auth = commands.add_parser('auth')
    auth.add_argument('--seconds', type=int, default=1200)
    tools = commands.add_parser('tools')
    tools.add_argument('--output', type=Path, required=True)
    call = commands.add_parser('call')
    call.add_argument('tool', choices=READ_TOOLS)
    call.add_argument('--arguments', type=Path)
    call.add_argument('--output', type=Path, required=True)
    consent = commands.add_parser('face-consent')
    consent.add_argument('structure_id', help='Exact structure ID returned by list_homes')
    args = parser.parse_args()
    # SDK HTTP diagnostics may contain personal event details or callback codes.
    logging.disable(logging.CRITICAL)
    try:
        if args.command == 'auth':
            if not 1 <= args.seconds <= 3600:
                raise ValueError('Authorization window must be 1-3600 seconds')
            authorize(args.config_dir, args.seconds)
        elif args.command == 'face-consent':
            client = client_config(args.config_dir)['web']['client_id']
            print('https://home.google.com/connections/feature_consent?' + urlencode({
                'client_id': client, 'structure_id': args.structure_id,
                'features': '1', 'continue': 'https://home.google.com'}))
        else:
            tool = args.tool if args.command == 'call' else None
            arguments = json.loads(args.arguments.read_text()) if tool and args.arguments else {}
            result = asyncio.run(read_home(args.config_dir, tool, arguments))
            private_write(args.output, json.dumps(result, indent=2) + '\n')
            if result.get('isError'):
                print('Google Home returned an error; private response saved to ' + str(args.output))
                return 1
            print('Saved Google Home response to ' + str(args.output))
    except Exception as error:
        # Failure remains a nonzero exit; do not dump token-bearing SDK exceptions.
        print('Failed: ' + type(error).__name__ + '. Check client setup, consent and access.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
