"""Bounded event-driven lookups and durable recognition deduplication."""
import asyncio
from collections import deque
import logging
import time

from aiohttp import ClientError
from httpx import HTTPError

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .client import HistoryClient
from .const import DOMAIN, FACE_EVENT, MAX_AGE, RETRY_DELAYS
from .matching import iso, matching_faces, parse_trigger, timestamp

_LOGGER = logging.getLogger(__name__)


def network_failure(error):
    """Recognize SDK task-group transport errors without logging private bodies."""
    if isinstance(error, ExceptionGroup):
        return bool(error.exceptions) and all(network_failure(e) for e in error.exceptions)
    return isinstance(error, (TimeoutError, ConnectionError, ClientError, HTTPError))


class FaceLookup:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.client = HistoryClient(hass, entry)
        self.store = Store(hass, 1, DOMAIN + '.' + entry.entry_id, private=True, atomic_writes=True)
        self.claims = {}
        self.seen_triggers = {}
        self.pending = deque()
        self.worker = None
        self.signal = DOMAIN + '.' + entry.entry_id
        self.status = {'status': 'idle', 'requests': 0}
        self.last_name = None

    async def start(self):
        stored = await self.store.async_load()
        if stored is not None:
            self.claims = stored['claims']
        self.prune(time.time())

    def prune(self, now):
        self.claims = {key: value for key, value in self.claims.items() if now - value < 3600}
        self.seen_triggers = {key: value for key, value in self.seen_triggers.items()
                              if now - value < 3600}

    @callback
    def update(self, **changes):
        self.status.update(changes)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def accept(self, event):
        try:
            trigger = parse_trigger(event.data, self.entry.data['device_id'], time.time())
        except (KeyError, TypeError, ValueError):
            self.update(status='invalid_trigger')
            return
        if trigger is None:
            return
        self.prune(time.time())
        if trigger.key in self.seen_triggers:
            return
        if len(self.pending) >= 4:
            self.update(status='queue_full')
            return
        self.seen_triggers[trigger.key] = time.time()
        self.pending.append(trigger)
        if self.worker is None or self.worker.done():
            self.worker = self.entry.async_create_background_task(
                self.hass, self.run(), 'Google Home face lookup')

    async def run(self):
        while self.pending:
            trigger = self.pending.popleft()
            self.update(status='looking_up', trigger_timestamp=iso(trigger.occurred),
                        trigger_type=trigger.kind, last_error=None)
            try:
                await self.lookup(trigger)
            except ConfigEntryAuthFailed:
                self.update(status='authorization_required', last_error='ConfigEntryAuthFailed')
                self.pending.clear()
                self.entry.async_start_reauth(self.hass)
                _LOGGER.error('Google Home face authorization must be renewed')
                return
            except Exception as error:
                # No actuation is possible on failure. SDK errors can contain private
                # event bodies or credentials: expose only the class, never a traceback.
                self.update(status='error', last_error=type(error).__name__)
                _LOGGER.error('Google Home face lookup failed (%s)', type(error).__name__)

    async def lookup(self, trigger):
        last_failed = False
        for delay in RETRY_DELAYS:
            if time.time() + delay - trigger.occurred > MAX_AGE:
                break
            if delay:
                await asyncio.sleep(delay)
            self.update(requests=self.status['requests'] + 1)
            try:
                payload = await self.client.history(trigger.occurred)
            except Exception as error:
                if not network_failure(error):
                    raise
                last_failed = True
                self.update(status='retrying', last_error=type(error).__name__)
                continue
            last_failed = False
            self.update(last_error=None)
            matches = matching_faces(payload, trigger, self.entry.data['resource_id'], time.time())
            if matches:
                await self.publish(matches)
                return
        self.update(status='error' if last_failed else 'no_fresh_match')

    async def publish(self, matches):
        fresh = list({match['recognition_id']: match for match in matches
                      if match['recognition_id'] not in self.claims}.values())
        if not fresh:
            self.update(status='duplicate')
            return
        # Commit the claim before publishing: a crash can lose a notification, but
        # restart or redelivery must never repeat a recognized visit's action.
        updated = {**self.claims, **{match['recognition_id']: time.time() for match in fresh}}
        await self.store.async_save({'claims': updated})
        self.claims = updated
        for match in fresh:
            if time.time() - timestamp(match['trigger_timestamp']) > MAX_AGE:
                continue
            self.last_name = match['name']
            self.update(status='matched', last_recognition=match)
            self.hass.bus.async_fire(FACE_EVENT, {'device_id': self.entry.data['device_id'], **match})

    async def stop(self):
        self.pending.clear()
        if self.worker is not None and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
