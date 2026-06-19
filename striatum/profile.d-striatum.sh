# /etc/profile.d/striatum.sh — point interactive shells at the system striatumd.
#
# striatumd moved from a per-user systemd unit (socket under the login-session
# runtime dir /run/user/1000/striatum) to a system unit that keeps its runtime
# state in /run/striatum. The `striatum` CLI resolves the daemon socket as
# STRIATUM_DAEMON_SOCKET -> else $XDG_RUNTIME_DIR/striatum/daemon-go.sock, and the
# MCP/discovery files via STRIATUM_DAEMON_RUNTIME_DIR -> else $XDG_RUNTIME_DIR/striatum.
# Interactive shells still have XDG_RUNTIME_DIR=/run/user/1000, so without these
# exports the CLI would look in the old, now-empty location. Export both so every
# halbritt shell reaches the system daemon.
#
# /run/striatum is mode 0700 owned by halbritt; only halbritt (the daemon user)
# can read these paths, which is the intended posture.
# The RPC socket is nested in rpc/ (see striatumd.service for the lane-ACL reason);
# the runtime/discovery files stay in /run/striatum.
export STRIATUM_DAEMON_RUNTIME_DIR=/run/striatum
export STRIATUM_DAEMON_SOCKET=/run/striatum/rpc/daemon-go.sock
