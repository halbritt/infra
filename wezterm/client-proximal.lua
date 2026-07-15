local wezterm = require 'wezterm'

local config = wezterm.config_builder()

config.font = wezterm.font_with_fallback {
  'JetBrains Mono',
  'Cascadia Mono',
  'Menlo',
}
config.font_size = 14.0
config.scrollback_lines = 100000
config.enable_scroll_bar = true
config.hide_tab_bar_if_only_one_tab = false
config.check_for_updates = false

config.ssh_domains = {
  {
    name = 'proximal',
    remote_address = 'proximal',
    username = 'halbritt',
    remote_wezterm_path = '/home/halbritt/.local/bin/wezterm',
    multiplexing = 'WezTerm',
    assume_shell = 'Posix',
    local_echo_threshold_ms = 20,
  },
}

config.default_gui_startup_args = { 'connect', 'proximal' }

return config
