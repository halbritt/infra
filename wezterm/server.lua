local wezterm = require 'wezterm'

local config = wezterm.config_builder()

config.default_prog = { '/bin/bash', '-l' }
config.scrollback_lines = 100000
config.check_for_updates = false

return config
