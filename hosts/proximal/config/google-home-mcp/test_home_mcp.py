import asyncio
import contextlib
from http.server import HTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from google.oauth2.credentials import Credentials

import home_mcp as home


class HomeAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.auth = home.Authorization(self.directory)
        self.auth.state = 'expected-state'
        self.auth.started = time.monotonic()
        self.auth.flow = Mock()
        self.auth.flow.credentials = Credentials(
            token='fixture', refresh_token='fixture',
            token_uri='https://oauth2.googleapis.com/token',
            client_id='fixture', client_secret='fixture', scopes=[home.SCOPE])

    def test_wrong_missing_and_expired_state_do_not_exchange_code(self):
        for state in [[], ['wrong'], ['expected-state', 'expected-state']]:
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.auth.finish({'state': state, 'code': ['code']})
        self.auth.started -= 601
        with self.assertRaises(ValueError):
            self.auth.finish({'state': ['expected-state'], 'code': ['code']})
        self.auth.flow.fetch_token.assert_not_called()
        self.assertFalse((self.directory / 'token.json').exists())

    def test_denied_consent_never_exchanges_code(self):
        with self.assertRaises(ValueError):
            self.auth.finish({'state': ['expected-state'], 'error': ['access_denied']})
        self.auth.flow.fetch_token.assert_not_called()
        self.assertIsNone(self.auth.state)

    def test_success_saves_private_token_and_rejects_replay(self):
        query = {'state': ['expected-state'], 'code': ['code']}
        self.auth.finish(query)
        token = self.directory / 'token.json'
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(token.read_text())['refresh_token'], 'fixture')
        self.assertTrue(self.auth.complete)
        with self.assertRaises(ValueError):
            self.auth.finish(query)
        self.auth.flow.fetch_token.assert_called_once()

    def test_missing_refresh_grant_does_not_replace_existing_token(self):
        token = self.directory / 'token.json'
        home.private_write(token, '{"previous":"working"}')
        self.auth.flow.credentials = Credentials(token='fixture', scopes=[home.SCOPE])
        with self.assertRaises(ValueError):
            self.auth.finish({'state': ['expected-state'], 'code': ['code']})
        self.assertEqual(json.loads(token.read_text()), {'previous': 'working'})
        self.assertFalse(self.auth.complete)

    def test_control_tool_is_rejected_before_loading_credentials(self):
        # No credential file exists: rejection must precede any credential I/O.
        with self.assertRaisesRegex(ValueError, 'Only read-only'):
            asyncio.run(home.read_home(self.directory, 'run_home_actions', {}))

    def test_browser_callback_requires_owner_and_redacts_exchange_error(self):
        self.auth.flow.fetch_token.side_effect = RuntimeError('secret-auth-code')
        server = HTTPServer(('127.0.0.1', 0), home.auth_handler(self.auth))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/oauth/callback?state=expected-state&code=secret-auth-code'
            with self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            self.auth.flow.fetch_token.assert_not_called()
            request = Request(url, headers={'Tailscale-User-Login': 'halbritt@gmail.com'})
            log = io.StringIO()
            with contextlib.redirect_stdout(log), self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)
            self.assertNotIn('secret-auth-code', error.exception.read().decode())
            error.exception.close()
            self.assertNotIn('secret-auth-code', log.getvalue())
        finally:
            server.shutdown()
            worker.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
