#!/usr/bin/env bash
# Sourced by ae-ci-exec; uses its validated CI pins, STATE, prog and die().
# Required inputs, acquired as ci-run.sh does, owned by the caller (the runtime user).
fetch_inputs() {
  local store=$STATE/inputs/fome-mc-$FOME_MC_COMMIT
  g() { GIT_TERMINAL_PROMPT=0 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -c safe.directory='*' "$@"; }
  if [ ! -d "$store/.git" ]; then
    echo "$prog: cloning fome-mc at $FOME_MC_COMMIT" >&2
    rm -rf "$store.partial"
    g -c credential.helper= -c http.extraheader= clone --quiet --no-checkout https://github.com/halbritt/fome-mc "$store.partial"
    g -C "$store.partial" checkout --quiet --detach "$FOME_MC_COMMIT"
    mv "$store.partial" "$store"
  fi
  [ "$(g -C "$store" rev-parse --verify 'HEAD^{commit}')" = "$FOME_MC_COMMIT" ] || die "fome-mc store $store is not at $FOME_MC_COMMIT"
  ! g -C "$store" config --local --get-regexp '^(http\..*\.extraheader|credential\.)' >/dev/null || die "credentials persisted in $store"
  [ "$(stat -c %u "$store")" = "$(id -u)" ] || die "fome-mc store $store is not owned by $(id -un)"
  local j1=$STATE/inputs/te-776228-1.pdf
  if [ ! -f "$j1" ]; then
    echo "$prog: fetching the J1 drawing" >&2
    curl --fail --silent --show-error --location --proto '=https' --retry 2 \
      --max-time 90 --max-filesize 10000000 --user-agent 'Mozilla/5.0 (X11; Linux x86_64)' \
      "$J1_DRAWING_URL" --output "$j1.partial"
    printf '%s  %s\n' "$J1_DRAWING_SHA256" "$j1.partial" | sha256sum --check --strict --quiet ||
      { rm -f "$j1.partial"; die "J1 drawing hash mismatch"; }
    chmod 0444 "$j1.partial"; mv "$j1.partial" "$j1"
  fi
  printf '%s  %s\n' "$J1_DRAWING_SHA256" "$j1" | sha256sum --check --strict --quiet || die "J1 drawing $j1 hash mismatch"
}

required_input_mounts() {
  REQUIRED_INPUT_MOUNTS=(-v "$STATE/inputs/fome-mc-$FOME_MC_COMMIT:/opt/fome-mc:ro"
                         -v "$STATE/inputs/te-776228-1.pdf:/opt/j1/te-776228-1.pdf:ro")
}
