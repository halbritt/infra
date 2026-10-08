"""Read Google Home camera history with the separate familiar-face OAuth grant."""
import asyncio
from datetime import timedelta
import json
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .matching import iso

ENDPOINT = 'https://home.googleapis.com/mcp'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'


class HistoryClient:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._token = None
        self._expires = 0

    async def access_token(self):
        if self._token and self._expires > time.monotonic() + 60:
            return self._token
        config = self.entry.data
        async with asyncio.timeout(10):
            async with async_get_clientsession(self.hass).post(TOKEN_ENDPOINT, data={
                'grant_type': 'refresh_token', 'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'refresh_token': config['refresh_token'],
            }) as response:
                body = await response.json()
                if response.status in (400, 401):
                    raise ConfigEntryAuthFailed('Google Home authorization must be renewed')
                response.raise_for_status()
        self._token = body['access_token']
        self._expires = time.monotonic() + float(body['expires_in'])
        if body.get('refresh_token'):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**config, 'refresh_token': body['refresh_token']})
        return self._token

    async def history(self, occurred):
        async with asyncio.timeout(15):
            token = await self.access_token()
            config = self.entry.data
            arguments = {
                'structureId': config['structure_id'],
                'filter': {'resourceIds': [config['resource_id']]},
                'startTime': iso(occurred - 35),
                'endTime': iso(occurred + 60),
                'includeMediaUrls': False, 'pageSize': 100,
            }
            async with streamablehttp_client(
                ENDPOINT, headers={'Authorization': 'Bearer ' + token},
                timeout=10, sse_read_timeout=10,
            ) as streams:
                async with ClientSession(streams[0], streams[1],
                                         read_timeout_seconds=timedelta(seconds=10)) as session:
                    await session.initialize()
                    response = await session.call_tool('list_home_history', arguments)
            if response.isError:
                raise RuntimeError('Google Home history returned an error')
            payload = response.structuredContent
            if payload is None:
                payload = json.loads(next(c.text for c in response.content if c.type == 'text'))
            if payload.get('nextPageToken'):
                raise RuntimeError('History window exceeded one page; refusing incomplete matching')
            return payload
