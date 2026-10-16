# room-eq to-dos

- [x] Move to-dos into TODO.md
- [x] Migration 2026-10-06: new .venv, path fix, CLAUDE.md header, .gitignore

## Open items

Paused 2026-10-03. Next: miniDSP flash backup when the CH341A arrives; the
user plans a Pi heatsink and a closed case (watch CPU temp, ~56 C open).

- [ ] miniDSP flash backup when the CH341A arrives (see CLAUDE.md, "miniDSP 2x4 HD / DDRC-24").
- [ ] Pi heatsink and closed case (watch CPU temp, ~56 C open).
- [x] Auto mode switch: Vocal 23:00, Room EQ 09:00 Eastern, once per time (2026-10-11).
- [x] Make the auto mode switch and the 2026-10-04 Vocal/Night retune permanent on the Pi: saved to the SD card 2026-10-15; overlay on again, code checked after reboot.
- [x] Shield no-audio hint: status line shows "No audio from Shield" / "Shield not connected"; 20 s after Reconnect, still no audio -> toast "restart the Shield" (2026-10-15).
- [x] Restart Shield over ADB: code done and deployed to RAM (2026-10-16).
- [~] Boot splash: own Plymouth theme `joshs-eq` (logo on black, 800x480, aspect kept). Files staged in `~/plymouth-joshs-eq` on the Pi; user runs the sudo install (2026-10-16).
- [ ] Set up Restart Shield on the Pi (overlay off): `sudo apt install adb`, Shield Network debugging on, accept the key on the TV, add `shield_mac` to settings.json, test. Also saves the Shield hint. Then overlay on.

- [x] 1. Compact layout on the 800 x 480 screen: done 2026-10-03 (new fader
   layout deployed, kiosk restarted, checked live at 800 x 480).
- [x] 2. Fix devices config: done 2026-10-03. Both presets now have
   `enable_rate_adjust: true` and no resampler (backups `*.pre-rateadjust`).
   Load fell to ~3.4 %, rate adjust ~1.0001, buffer converging; the "needless
   1:1 sample rate conversion" warning is gone. Earlier underruns (16:09,
   16:14) were before the change.
- [x] 3. Reconnect feature: done 2026-10-03. The user installed the helper and the
   sudoers rule; a test through the server took 3.7 s, then Running at 192 kHz.
- [x] 3b. Auto-recover after a KEF USB dropout: deployed 2026-10-03, confirmed
   working live by the user 2026-10-05. The KEF's power saving switches it off (it leaves USB) regularly;
   CamillaDSP then stops with a PlaybackError and stays Inactive. The server's
   status loop (`auto_recover`) waits while a configured card is missing from
   `/proc/asound/`, then re-applies the effective config once both are back
   and shows "Speakers back: audio restarted". Failed attempts back off 5-30 s.
- [x] 4. Room measurement with REW + UMIK-1: done 2026-10-03. Result is preset
   `rew_v1.yml` (4 room cuts + tone bank), active on the Pi (checked 2026-10-09).
   `room_eq.yml` keeps the old placeholder filters as a spare preset.
- [x] 5. Larger logo area: done 2026-10-03 (title removed, header 68 px / 56 px on
   the touchscreen, transparent cropped logo).
- [x] 6. Overlay (read-only) file system: **ON since 2026-10-03** (the user chose to
   accept losing manual slider tweaks at reboot). Turn it OFF before deploying
   code or presets that must persist, then back on. With it on, nothing is
   written to the SD card and all changes (presets saved, settings.json mode
   tones / brightness, uploads, deployed code) vanish at reboot, so it must be
   OFF while changing things. Check: `findmnt -n -o FSTYPE /` (overlay = on,
   ext4 = off). On: `ssh -t joshis-pi "sudo raspi-config nonint
   enable_overlayfs && sudo reboot"`. Off: same with `disable_overlayfs`.
   Boot-partition write protection (enable_bootro) optional, not needed.
   After any reboot: wait ~30 s, press Reconnect if the Shield does not play.
