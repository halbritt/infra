#!/bin/bash
# Idempotent toolchain provisioning for the WSL Ubuntu build node on peecee.
# Run as halbritt (passwordless sudo) over `ssh peecee-wsl`:
#   bash provision-toolchains.sh
# Mirrors the toolchains proximal's ~/git repos use: python (uv), node 24, go,
# rust, cmake/ninja, docker, gh, rg/jq/tmux, claude/codex CLIs, git-wt/git-land.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
S="sudo -n"

$S apt-get update -q
$S apt-get install -y -q \
  build-essential cmake ninja-build pkg-config ccache gdb \
  python3 python3-venv python3-pip python3-dev \
  git git-lfs curl wget ca-certificates gnupg unzip zip \
  ripgrep jq tmux shellcheck sqlite3 \
  libssl-dev libffi-dev libpq-dev zlib1g-dev libsqlite3-dev \
  postgresql-client docker.io docker-compose-v2 gh \
  bubblewrap slirp4netns uidmap binutils

# docker group for the agent user
$S usermod -aG docker halbritt
$S systemctl enable --now docker

# node 24 via NodeSource
if ! command -v node >/dev/null || [[ "$(node -v)" != v24.* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | $S -E bash - >/dev/null
  $S apt-get install -y -q nodejs
fi
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global

# go: latest stable to /usr/local/go
GO_VER="$(curl -fsSL 'https://go.dev/VERSION?m=text' | head -1)"
if [ ! -x /usr/local/go/bin/go ] || [ "$(/usr/local/go/bin/go version | awk '{print $3}')" != "$GO_VER" ]; then
  curl -fsSL "https://go.dev/dl/${GO_VER}.linux-amd64.tar.gz" -o /tmp/go.tgz
  $S rm -rf /usr/local/go && $S tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz
fi

# rust via rustup
if [ ! -x ~/.cargo/bin/rustc ]; then
  curl -fsSL https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal >/dev/null
fi

# uv
if [ ! -x ~/.local/bin/uv ]; then
  curl -fsSL https://astral.sh/uv/install.sh | sh >/dev/null
fi

# PATH for login + non-login shells
cat > ~/.profile.d-toolchains.sh <<'P'
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/.cargo/bin:/usr/local/go/bin:$HOME/go/bin:$PATH"
P
grep -q profile.d-toolchains ~/.bashrc || echo '. ~/.profile.d-toolchains.sh' >> ~/.bashrc
grep -q profile.d-toolchains ~/.profile || echo '. ~/.profile.d-toolchains.sh' >> ~/.profile
# non-interactive `ssh peecee-wsl <cmd>` sources neither; sshd applies /etc/environment via PAM
$S tee /etc/environment >/dev/null <<'ENV'
PATH="/home/halbritt/.local/bin:/home/halbritt/.npm-global/bin:/home/halbritt/.cargo/bin:/usr/local/go/bin:/home/halbritt/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV
. ~/.profile.d-toolchains.sh

# agent CLIs (user-scope)
npm install -g --silent @anthropic-ai/claude-code @openai/codex opencode-ai

# git identity + trunk tools (git-wt / git-land wrap cairn's git_trunk_tools.py)
git config --global user.name halbritt
git config --global user.email halbritt@gmail.com
git config --global safe.directory '*'
git config --global init.defaultBranch main
mkdir -p ~/git ~/.cache/agent-worktrees
[ -d ~/git/cairn ] || git clone -q https://github.com/halbritt/cairn ~/git/cairn
for t in wt land; do
  printf '#!/usr/bin/env bash\nexec /usr/bin/python3 %s/git/cairn/scripts/git_trunk_tools.py %s "$@"\n' "$HOME" "$t" > ~/.local/bin/git-$t
  chmod +x ~/.local/bin/git-$t
done

echo "=== versions ==="
gcc --version | head -1; cmake --version | head -1; python3 --version; uv --version
node -v; npm -v; go version; rustc --version; cargo --version
docker --version; docker compose version; gh --version | head -1
claude --version 2>/dev/null || echo "claude: installed, not authenticated"
codex --version 2>/dev/null | head -1
git-wt --help 2>&1 | head -1
