"""Match a fresh Nest trigger to named tracks from the same camera visit."""
from dataclasses import dataclass
from datetime import datetime, UTC
import math

from .const import FUTURE_SKEW, MAX_AGE, TRIGGER_MAX_AGE


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Expected a timezone-aware event timestamp')
    return value.timestamp()


def iso(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def interval(track):
    start = float(track['startTimestampMillis']) / 1000
    end = float(track['endTimestampMillis']) / 1000
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ValueError('Invalid camera track interval')
    return start, end


@dataclass(frozen=True)
class Trigger:
    key: str
    kind: str
    occurred: float


def parse_trigger(event, device_id, now):
    if event.get('device_id') != device_id:
        return None
    kind = event.get('type')
    if kind not in ('doorbell_chime', 'camera_person'):
        return None
    key = event.get('nest_event_id')
    if not isinstance(key, str) or not key:
        return None
    occurred = timestamp(event['timestamp'])
    if not -FUTURE_SKEW <= now - occurred <= TRIGGER_MAX_AGE:
        return None
    return Trigger(key + ':' + kind, kind, occurred)


def matching_faces(payload, trigger, resource_id, now):
    if not -FUTURE_SKEW <= now - trigger.occurred <= MAX_AGE:
        return []
    matches = []
    for entry in payload.get('entries', {}).get('entries', []):
        if entry.get('resourceId') != resource_id or not entry.get('eventId'):
            continue
        event = entry.get('event', {})
        if event.get('eventType') != 'CameraHistory.HistoryItem':
            continue
        tracks = event['event'].get('eventTracks', [])
        anchor_type = ('EVENT_TYPE_DOORBELL' if trigger.kind == 'doorbell_chime'
                       else 'EVENT_TYPE_PERSON')
        anchors = [interval(t) for t in tracks if anchor_type in t.get('eventTypes', [])]
        if trigger.kind == 'doorbell_chime':
            correlated = any(abs(start - trigger.occurred) <= 5 for start, _ in anchors)
        else:
            correlated = any(start - 5 <= trigger.occurred <= end + 5 for start, end in anchors)
        if not correlated:
            continue
        for track in tracks:
            face = track.get('face', {})
            name = face.get('name')
            if ('EVENT_TYPE_FAMILIAR_FACE' not in track.get('eventTypes', [])
                    or face.get('category') != 'FACE_CATEGORY_KNOWN'
                    or not isinstance(name, str) or not name.strip()):
                continue
            start, end = interval(track)
            if (end < trigger.occurred - 30 or start > trigger.occurred + 30
                    or end > now + FUTURE_SKEW or now - end > MAX_AGE):
                continue
            matches.append({
                'recognition_id': entry['eventId'] + ':' + str(face.get('faceId', name)),
                'history_event_id': entry['eventId'], 'name': name.strip(),
                'resource_id': resource_id, 'face_last_seen': iso(end),
                'trigger_timestamp': iso(trigger.occurred),
                'trigger_type': trigger.kind, 'observed_at': iso(now),
            })
    return matches
