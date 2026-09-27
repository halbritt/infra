# Terminal (foot)

Omarchy's default terminal on archon is `foot`. Its user config is
`~/.config/foot/foot.ini`, which includes the active Omarchy theme
(`~/.local/state/omarchy/current/theme/foot.ini`).

Owner override (2026-09-26): font size 11 (Omarchy default 9).

```ini
font=JetBrainsMono Nerd Font:size=11
```

foot reads its config at window start, so the change applies to new windows.
Rollback: restore `~/.config/foot/foot.ini.bak-20260926`, or set `size=9`.
`omarchy-font-set` changes the family; recheck the size after using it.
The unused ghostty/alacritty configs still say size 9.
