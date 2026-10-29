# room-eq to-dos

- [x] Move to-dos into TODO.md
- [x] Migration 2026-10-06: new .venv, path fix, CLAUDE.md header, .gitignore

## Open items

Paused 2026-10-03. Next: analyse the miniDSP flash backup (taken 2026-10-29); the
user plans a Pi heatsink and a closed case (watch CPU temp, ~56 C open).

- [x] miniDSP flash backup: chip desoldered, read off-board with the Pico 2026-10-29 (two identical reads), `measurements/minidsp/at45_backup_2026-10-29.bin`.
- [x] User: desolder the flash chip and wire it off-board to the Pico (done 2026-10-29).
- [x] miniDSP: image analysed 2026-10-29: the AT45 holds DSP/preset data, not the XMOS firmware (no USB strings). Keep it unchanged.
- [x] User: XMOS marking and board photos (2026-10-29): no external XMOS flash; flash is inside the XMOS.
- [ ] miniDSP: after the AT45 is back, plug the miniDSP into the PC and try the XMOS DFU revert-to-factory request over USB (see CLAUDE.md).
- [x] User: resolder the AT45 unchanged (done 2026-10-29; no bridges, all legs beep, VCC-GND 170 ohm = board load)
- [x] DSP left-row legs ~7-8 joined: user judges it a deliberate factory joint, left as is (2026-10-29)
- [ ] User: if the Shield wakes by itself again, do not unplug it; ask Claude to read `~/shield-wakelog/wakes.log` on the Pi #you
- [ ] Shield sleep = Home + sleep without the Pi: today `pi/bin/shield-sleephome` (run by the Pi wake logger) does it and stops on a Pi reboot. Options: re-enable tvlauncher + tvrecommendations and turn on Projectivy's "Override current launcher", or an automation app on the Shield (screen off -> Home).
- [x] Room check from the Pi: scripts/pi_sweep.py + compare_room.py; Flat vs Room EQ measured 2026-10-27.
- [ ] User: KEF volume test (Flat sweep at a clearly lower KEF volume) to see whether the sub follows the KEF volume #you
- [x] Bass slider on the Pi UI (low shelf under 80 Hz, -12..+6 dB), deployed to RAM 2026-10-27.
- [x] Bass slider set to -5 dB by the user (2026-10-27).
- [x] Bass slider saved on the SD card (2026-10-27, overlay off).
- [x] Overlay on again (2026-10-27); bass -5 dB and rew_v1 confirmed after reboot.
- [ ] Optional: second filter round for 37/46 Hz after the bass level is set; try sub phase against the 105 Hz null.
- [ ] Pi heatsink and closed case (watch CPU temp, ~56 C open).
- [x] Phone EQ page: sweep + UMIK-1 measurement and PEQ design in Chrome on Android (car tuning), exports for Poweramp EQ / Equalizer314 / Wavelet / CamillaDSP. Source `web/phone_eq.html`. Published: https://claude.ai/artifact/V94Xsx2MX7YdWrJaj4FXBM
- [x] User: first real measurement with the phone, a recorder app and the UMIK-1 (car): done 2026-10-23 (split screen, 5 full sweeps); car_v1 normal/gentle/bass pushed to the phone.
- [ ] User: try car_v1 normal / gentle / bass in Wavelet while driving and say which fits #you
- [ ] Pocket page: bring in the full-range design of `scripts/design_full.py` (bass-shelf target, treble shelf, clear before/after chart); the user found the page's bass-only result hard to read.
- [x] Auto mode switch: Vocal 23:00, Room EQ 09:00 Eastern, once per time (2026-10-11).
- [x] Make the auto mode switch and the 2026-10-04 Vocal/Night retune permanent on the Pi: saved to the SD card 2026-10-15; overlay on again, code checked after reboot.
- [x] Shield no-audio hint: status line shows "No audio from Shield" / "Shield not connected"; 20 s after Reconnect, still no audio -> toast "restart the Shield" (2026-10-15).
- [x] Restart Shield over ADB: code done and deployed to RAM (2026-10-16).
- [x] Boot splash: Plymouth theme `joshs-eq` installed (2026-10-16); colour square off (`disable_splash=1`). User confirmed it looks right.
- [x] Overlay on again 2026-10-16. Splash and disable_splash checked by the user on boot.
- [x] Every start/restart uses the scheduled mode for the time of day (2026-10-16).
- [x] Save the startup-mode fix on the SD card: saved 2026-10-16; overlay on, real reboot at 01:22 started in Vocal.
- [x] Fix: audio not restarting after a KEF dropout (CamillaDSP replies out of step, auto-recover blind). Deployed to RAM 2026-10-22.
- [x] CamillaDSP reply fix saved on the SD card (2026-10-27, overlay was off).
- [ ] User: turn the overlay on again (off since 2026-10-27) #you
- [x] Set up Restart Shield on the Pi: adb installed, key accepted on the Shield, `shield_mac` saved, code on the SD card; real restart tested 2026-10-16 (Shield back in ~45 s, key still accepted).

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
