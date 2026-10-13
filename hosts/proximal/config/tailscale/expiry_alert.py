#!/usr/bin/env python3
"""Warn the owner by SMS before proximal's live Tailscale key expires."""

import argparse
import fcntl
import json
import logging
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

STATE = Path.home() / '.local/state/tailscale-expiry-alert'


class NotSent(RuntimeError):
    """A preflight or explicit rejection proves no SMS was queued."""


def notice(status, now):
    if status['BackendState'] != 'Running':
        return 'offline:' + now.date().isoformat(), (
            'Tailscale on proximal is offline. Check tailscale status; '
            'use wezterm connect proximal-local on the home network.'
        )
    expiry_text = status['Self']['KeyExpiry']
    if expiry_text is None:
        return None  # Tailscale reports null when key expiry is disabled.
    expiry = datetime.fromisoformat(expiry_text.replace('Z', '+00:00'))
    if expiry.tzinfo is None:
        raise ValueError('Key expiry lacks timezone')
    days = math.ceil((expiry - now).total_seconds() / 86400)
    if days > 14:
        return None
    if days > 7:
        bucket = '14-days'
    elif days > 3:
        bucket = '7-days'
    else:
        bucket = now.date().isoformat()
    label = expiry.strftime('%b %d, %Y at %H:%M UTC')
    timing = f'in {days} days' if days > 0 else 'now or already expired'
    return expiry.isoformat() + ':' + bucket, (
        f'Tailscale on proximal: key expiry {timing} ({label}). '
        'Run tailscale up --force-reauth on proximal and complete sign-in. '
        'LAN backup: wezterm connect proximal-local.'
    )


def live_status():
    completed = subprocess.run(
        ['/usr/bin/tailscale', 'status', '--json'], check=True,
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(completed.stdout)


def send_sms(message, now):
    from urllib.request import urlopen
    from praxis.android_sms import android_sms_carrier_from_env, gateway_post
    from praxis.delivery import AttemptOutcome, DeliveryMode, DeliveryRequest, Stakes
    from praxis.trust import Authority

    def post(url, body, headers):
        status, raw = gateway_post(url, body, headers)
        if status in (400, 401, 404, 413):
            raise NotSent(f'SMS rejected before queue insertion: HTTP {status}')
        if status not in (200, 201, 202):
            raise RuntimeError('SMS transport outcome unknown')
        return status, raw

    carrier = android_sms_carrier_from_env(http_post=post)
    if carrier is None:
        raise NotSent('SMS configuration missing')
    try:
        with urlopen(carrier.base_url.rstrip('/') + '/health', timeout=5) as response:
            health = json.load(response)
    except (OSError, ValueError) as error:
        raise NotSent('SMS health check failed') from error
    if health.get('state') != 'ready':
        raise NotSent('SMS modem not ready')
    request = DeliveryRequest(
        request_id='tailscale-expiry-' + now.date().isoformat(),
        source_ref='proximal tailscale status --json', message=message,
        authority=Authority.AGENT_INFERRED, stakes=Stakes.MED,
        confidence=1.0, horizon=now, preferred_channels=('sms',),
    )
    receipt = carrier.deliver(request, DeliveryMode.INTERRUPT, now)
    if receipt.outcome != AttemptOutcome.DELIVERED:
        raise NotSent('SMS egress gate rejected message')
    if not receipt.payload_ref:
        raise RuntimeError('SMS response missing gateway ID')
    return receipt.payload_ref


def save(path, receipts):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(receipts, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def check(status, now, state_dir=STATE, send=send_sms):
    warning = notice(status, now)
    if warning is None:
        return 'outside-warning-window'
    key, message = warning
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / 'check.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = state_dir / 'receipts.json'
        receipts = json.loads(path.read_text()) if path.exists() else {}
        previous = receipts.get(key)
        if previous and previous['status'] == 'accepted':
            return 'already-alerted'
        if previous and previous['status'] == 'pending':
            raise RuntimeError('Previous SMS outcome unknown; inspect gateway journal')
        receipts[key] = {'status': 'pending', 'at': now.isoformat()}
        save(path, receipts)
        try:
            gateway_id = send(message, now)
        except NotSent:
            receipts[key]['status'] = 'rejected'
            save(path, receipts)
            raise
        # An uncertain send keeps pending across restarts: never silently resend.
        receipts[key].update(status='accepted', gateway_id=gateway_id)
        save(path, receipts)
        return 'accepted-by-gateway'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    now = datetime.now(timezone.utc)
    try:
        status = live_status()
        if args.dry_run:
            print(json.dumps({'state': status['BackendState'],
                              'expiry': status.get('Self', {}).get('KeyExpiry'),
                              'notice': notice(status, now)}))
        else:
            logging.info('%s', check(status, now))
    except Exception as error:
        # Preserve failure status, but keep provider payloads and credentials out of logs.
        logging.error('Expiry check failed (%s); no successful delivery claimed', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
