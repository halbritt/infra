#!/bin/bash
# Install canonical files and existing credential copies; do not start a job.
set -euo pipefail
update_bot_source=$(cd -- "$(dirname -- "$0")" && pwd)
sudo install -d -m 0755 /usr/local/lib/update-bot /etc/update-bot
sudo install -m 0755 "$update_bot_source/update_bot.py" "$update_bot_source/cairn-mcp" /usr/local/lib/update-bot/
sudo install -m 0644 "$update_bot_source/policy.md" "$update_bot_source/role.md" "$update_bot_source/hermes.yaml" "$update_bot_source/settings.json" /etc/update-bot/
sudo install -m 0644 "$update_bot_source/"*.service "$update_bot_source/"*.timer /etc/systemd/system/
sudo /home/halbritt/.hermes/hermes-agent/venv/bin/python - <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import os
values = dotenv_values('/home/halbritt/.hermes/.env')
for source, name in [('OPENROUTER_API_KEY', 'openrouter'), ('SLACK_BOT_TOKEN', 'slack')]:
    value = values.get(source)
    if not value:
        raise SystemExit('Missing existing credential: ' + source)
    path = Path('/etc/update-bot') / (name + '.key')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value + '\n')
print('Existing provider and Slack credentials installed without displaying values')
PY
sudo systemctl daemon-reload
