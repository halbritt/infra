import asyncio
from pathlib import Path
import sys
import time
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.google_home_faces.const import FACE_EVENT
from custom_components.google_home_faces.matching import Trigger, iso, matching_faces, parse_trigger
from custom_components.google_home_faces.runtime import FaceLookup

DEVICE = 'nest-device'
RESOURCE = 'device@camera'


def camera_history(now):
    return {'entries': {'entries': [{
        'eventId': 'visit-1', 'resourceId': RESOURCE,
        'event': {'eventType': 'CameraHistory.HistoryItem', 'event': {'eventTracks': [
            {'eventTypes': ['EVENT_TYPE_DOORBELL'], 'startTimestampMillis': str((now-5)*1000),
             'endTimestampMillis': str(now*1000)},
            {'eventTypes': ['EVENT_TYPE_PERSON', 'EVENT_TYPE_FAMILIAR_FACE'],
             'startTimestampMillis': str((now-15)*1000), 'endTimestampMillis': str((now-1)*1000),
             'face': {'category': 'FACE_CATEGORY_KNOWN', 'faceId': 'face-1', 'name': 'Myra'}},
        ]}},
    }]}}


def entry():
    return ConfigEntry(domain='google_home_faces', title='Face test', version=1, minor_version=1,
                       source='user', unique_id=RESOURCE, options={}, discovery_keys=MappingProxyType({}),
                       subentries_data=[], data={'device_id': DEVICE, 'resource_id': RESOURCE})


@pytest.mark.parametrize('change', ['wrong_device', 'wrong_type', 'stale', 'future', 'missing_id'])
def test_rejects_untrusted_or_old_trigger(change):
    now = time.time()
    event = {'device_id': DEVICE, 'type': 'doorbell_chime', 'timestamp': iso(now), 'nest_event_id': 'id'}
    if change == 'wrong_device': event['device_id'] = 'other'
    if change == 'wrong_type': event['type'] = 'camera_motion'
    if change == 'stale': event['timestamp'] = iso(now-31)
    if change == 'future': event['timestamp'] = iso(now+6)
    if change == 'missing_id': event.pop('nest_event_id')
    assert parse_trigger(event, DEVICE, now) is None


@pytest.mark.parametrize('change', ['camera', 'ring', 'unknown_face', 'stale_face', 'future_face', 'stale_trigger'])
def test_history_must_correlate_to_fresh_known_face(change):
    now = time.time(); payload = camera_history(now); trigger = Trigger('id', 'doorbell_chime', now-5)
    row = payload['entries']['entries'][0]; tracks = row['event']['event']['eventTracks']
    if change == 'camera': row['resourceId'] = 'device@other'
    if change == 'ring': tracks[0]['startTimestampMillis'] = str((now-20)*1000)
    if change == 'unknown_face': tracks[1]['face']['category'] = 'FACE_CATEGORY_UNKNOWN'
    if change == 'stale_face':
        tracks[1]['startTimestampMillis'] = str((now-90)*1000)
        tracks[1]['endTimestampMillis'] = str((now-70)*1000)
    if change == 'future_face': tracks[1]['endTimestampMillis'] = str((now+10)*1000)
    if change == 'stale_trigger': trigger = Trigger('id', 'doorbell_chime', now-61)
    assert matching_faces(payload, trigger, RESOURCE, now) == []


def test_correlated_face_has_only_safe_fields():
    now = time.time(); payload = camera_history(now)
    payload['entries']['entries'][0]['event']['event']['eventTracks'][1]['face']['faceInstance'] = {'url':'private-signed-url'}
    matches = matching_faces(payload, Trigger('id','doorbell_chime',now-5),RESOURCE,now)
    assert [m['name'] for m in matches] == ['Myra']
    assert matches[0]['recognition_id'] == 'visit-1:face-1'
    assert 'private-signed-url' not in str(matches)


@pytest.mark.asyncio
async def test_duplicate_tracks_and_restart_publish_only_once(tmp_path):
    hass = HomeAssistant(str(tmp_path)); config = entry(); lookup = FaceLookup(hass, config)
    await lookup.start(); events = []
    hass.bus.async_listen(FACE_EVENT, lambda event: events.append(event.data))
    now = time.time(); matches = matching_faces(camera_history(now),Trigger('id','doorbell_chime',now-5),RESOURCE,now)
    await lookup.publish(matches + matches)
    await hass.async_block_till_done()
    assert len(events) == 1 and events[0]['name'] == 'Myra'
    # New HA and runtime instances read the actual saved ledger from disk.
    restarted = HomeAssistant(str(tmp_path)); second = FaceLookup(restarted, config)
    await second.start(); replayed = []
    restarted.bus.async_listen(FACE_EVENT, lambda event: replayed.append(event.data))
    await second.publish(matches)
    await restarted.async_block_till_done()
    assert replayed == []
    assert second.status['status'] == 'duplicate'
    await hass.async_stop(); await restarted.async_stop()


@pytest.mark.asyncio
async def test_storage_failure_never_publishes(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path)); lookup = FaceLookup(hass, entry()); events=[]
    hass.bus.async_listen(FACE_EVENT, lambda event: events.append(event.data))
    async def disk_failure(*args): raise OSError('disk full')
    monkeypatch.setattr(lookup.store, 'async_save', disk_failure)  # Filesystem boundary.
    now=time.time(); matches=matching_faces(camera_history(now),Trigger('id','doorbell_chime',now-5),RESOURCE,now)
    with pytest.raises(OSError): await lookup.publish(matches)
    await hass.async_block_till_done()
    assert not events and not lookup.claims
    await hass.async_stop()


@pytest.mark.asyncio
async def test_retry_stops_after_name_arrives_and_has_no_idle_requests(tmp_path, monkeypatch):
    hass=HomeAssistant(str(tmp_path)); lookup=FaceLookup(hass,entry()); await lookup.start()
    now=time.time(); responses=iter([{},camera_history(now)])
    async def google_history(occurred): return next(responses)
    monkeypatch.setattr(lookup.client,'history',google_history)  # Google network boundary.
    monkeypatch.setattr('custom_components.google_home_faces.runtime.RETRY_DELAYS',(0,0,0))
    await hass.async_block_till_done()
    assert lookup.status['requests'] == 0
    await lookup.lookup(Trigger('id','doorbell_chime',now-5))
    assert lookup.status['requests'] == 2 and lookup.status['status'] == 'matched'
    await hass.async_block_till_done()
    assert lookup.status['requests'] == 2
    await hass.async_stop()


@pytest.mark.asyncio
async def test_unload_cancels_network_wait_without_publication(tmp_path, monkeypatch):
    hass=HomeAssistant(str(tmp_path)); lookup=FaceLookup(hass,entry()); await lookup.start()
    entered=asyncio.Event(); events=[]
    hass.bus.async_listen(FACE_EVENT,lambda event:events.append(event.data))
    async def google_history(occurred):
        entered.set(); await asyncio.Event().wait()
    monkeypatch.setattr(lookup.client,'history',google_history)
    lookup.pending.append(Trigger('id','doorbell_chime',time.time()))
    lookup.worker=asyncio.create_task(lookup.run())
    await entered.wait(); await lookup.stop(); await hass.async_block_till_done()
    assert not events and lookup.worker.done() and not lookup.pending
    await hass.async_stop()


def test_person_push_must_overlap_person_track():
    now = time.time()
    payload = camera_history(now)
    assert matching_faces(payload, Trigger('person', 'camera_person', now-10), RESOURCE, now)
    assert not matching_faces(payload, Trigger('person', 'camera_person', now-30), RESOURCE, now)


@pytest.mark.asyncio
async def test_no_match_exhausts_budget_without_publication(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path)); lookup = FaceLookup(hass, entry()); events = []
    hass.bus.async_listen(FACE_EVENT, lambda event: events.append(event.data))
    async def no_history(occurred): return {}
    monkeypatch.setattr(lookup.client, 'history', no_history)
    monkeypatch.setattr('custom_components.google_home_faces.runtime.RETRY_DELAYS', (0, 0, 0))
    await lookup.lookup(Trigger('ring', 'doorbell_chime', time.time()))
    await hass.async_block_till_done()
    assert lookup.status['status'] == 'no_fresh_match'
    assert lookup.status['requests'] == 3 and events == []
    await hass.async_stop()


@pytest.mark.asyncio
async def test_auth_failure_requests_reauth_and_emits_nothing(tmp_path, monkeypatch):
    from homeassistant.exceptions import ConfigEntryAuthFailed
    hass = HomeAssistant(str(tmp_path)); config = entry(); lookup = FaceLookup(hass, config)
    events = []; reauth = []
    hass.bus.async_listen(FACE_EVENT, lambda event: events.append(event.data))
    async def expired(occurred): raise ConfigEntryAuthFailed('expired')
    monkeypatch.setattr(lookup.client, 'history', expired)
    monkeypatch.setattr(ConfigEntry, 'async_start_reauth', lambda self, hass: reauth.append(self.entry_id))
    lookup.pending.append(Trigger('ring', 'doorbell_chime', time.time()))
    await lookup.run(); await hass.async_block_till_done()
    assert reauth == [config.entry_id] and events == []
    assert lookup.status['status'] == 'authorization_required'
    await hass.async_stop()


@pytest.mark.asyncio
async def test_sdk_transport_group_retries_within_existing_budget(tmp_path, monkeypatch):
    from httpx import ReadError
    hass = HomeAssistant(str(tmp_path)); lookup = FaceLookup(hass, entry())
    now = time.time(); calls = []
    async def google_history(occurred):
        calls.append(occurred)
        if len(calls) == 1:
            raise ExceptionGroup('SDK', [ReadError('private transport context')])
        return camera_history(now)
    monkeypatch.setattr(lookup.client, 'history', google_history)
    monkeypatch.setattr('custom_components.google_home_faces.runtime.RETRY_DELAYS', (0, 0, 0))
    await lookup.lookup(Trigger('ring', 'doorbell_chime', now-5))
    assert len(calls) == 2 and lookup.status['status'] == 'matched'
    assert lookup.status['last_error'] is None
    await hass.async_stop()


@pytest.mark.asyncio
async def test_persistent_transport_failure_is_error_not_empty_history(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path)); lookup = FaceLookup(hass, entry()); events = []
    hass.bus.async_listen(FACE_EVENT, lambda event: events.append(event.data))
    async def unavailable(occurred): raise TimeoutError()
    monkeypatch.setattr(lookup.client, 'history', unavailable)
    monkeypatch.setattr('custom_components.google_home_faces.runtime.RETRY_DELAYS', (0, 0))
    await lookup.lookup(Trigger('ring', 'doorbell_chime', time.time()))
    await hass.async_block_till_done()
    assert lookup.status['requests'] == 2 and lookup.status['status'] == 'error'
    assert events == []
    await hass.async_stop()
