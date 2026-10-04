# Josh's EQ: Raspberry Pi room-correction DSP

A Raspberry Pi 4 sits between an NVIDIA Shield and a pair of KEF LS50 Wireless
speakers. It receives USB audio from the Shield, applies room-correction EQ with
CamillaDSP, and sends it to the KEFs over USB. A custom touchscreen/phone UI
("Room EQ") controls it.

## Project folder (Windows PC)

`C:\Users\joshi\room-eq\` (on the Pi the UI lives in `~/roomeq-ui/`):

- `ui/`: working copy of `~/roomeq-ui/`. Edit here, then `scp` to the Pi.
- `pi/`: reference copies of Pi files (`pi/camilladsp/room_eq.yml`, later the
  reconnect script and sudoers file).
- `assets/logos/`: logo candidates (plain and `_transparent` PNGs) and the
  active `joshs_eq.png`; `assets/backgrounds/`: generated backgrounds.
- `scripts/`: PC-side helpers (`make_background.py`, run with any Python that
  has Pillow).
- `archive/`: older page versions and the original `roomeq-ui.zip`.
- `measurements/umik1/`: UMIK-1 calibration files, serial 7079072 (`7079072.txt`
  0 degrees, `7079072_90deg.txt` 90 degrees, mic pointing at the ceiling).
  Copies also stay in Downloads. REW measurements and exported filters go in
  `measurements/`.

## REW measurement setup (2026-10-03)

- Plug the PC into the splitter's USB port in place of the Shield: Windows sees
  the Pi gadget as a sound card, so REW plays through CamillaDSP to the KEFs.
  Use rear USB 2.0 ports, the UMIK-1 and the Pi on separate ports. Afterwards
  move the cable back to the Shield and press Reconnect if it does not send.
- Measure in Flat mode, sub on, KEF settings unchanged, 5-7 positions averaged.
  Correct below ~300 Hz, mostly cuts, boosts at most +3 dB, 5-8 filters.
- Scripts (run with `.venv\Scripts\python.exe`): `scripts/rew_compare.py`
  compares REW text exports and averages positions; `scripts/design_peq.py`
  fits cut-only peaking filters to an average (scipy least squares).
- rew_v1 (2026-10-03): 4 cuts, 20.9 Hz -2.8, 39.6 Hz -4.7, 50.1 Hz -3.8,
  66.7 Hz -6.9 dB, all Q 5, preamp 0. File `~/camilladsp/configs/rew_v1.yml`
  (copy in `pi/camilladsp/`). Data in `measurements/2026-10-03_*`.
- REW filter export goes into a new preset (e.g. `rew_v1.yml`) next to
  `room_eq.yml`, with the preamp covering the largest boost.

## miniDSP 2x4 HD / DDRC-24 (side issue, 2026-10-03)

The user's old miniDSP (2x4 HD upgraded to DDRC-24 with Dirac) had UMIK-2
firmware flashed onto its XMOS by mistake: it shows as UMIK-2 v2.06, VID 0x2752
PID 0x002B. miniDSPUAC2Dfu fails at "Entering upgrade mode" (0xEE000003); the
Toolbox loader sends the firmware with no reply; holding the board's reset
button at power-up changes nothing. The XMOS flash is an Adesto AT45DB321E
(SPI DataFlash, 3.3 V) next to the XMOS chip. Plan: with a CH341A plus 3.3 V
adapter (ordered), read the flash twice as a backup, inspect it for a factory
image plus the UMIK-2 upgrade image, and only then erase the upgrade image.
Not needed for the Pi chain; its value is resale or a car install.

## Git

- GitHub: `git@github.com:tosandeepjoshi-max/room-eq.git` (private), branch `main`.
- Pushing needs the dedicated key, set per repo (already done here):
  `git config core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe -i C:/Users/joshi/gitpub"`.
  Plain `ssh` has no default key, so GitHub answers "Permission denied (publickey)".
- `.gitattributes` keeps LF line endings (files are copied to the Pi).

## Access

- Pi hostname `joshis-pi`, user `joshi`.
- From the Windows PC, `ssh joshis-pi` logs in with the key `~/pi_access`
  (entry in `C:\Users\joshi\.ssh\config`). No password prompt.
- Copy files with `scp <file> joshis-pi:~/roomeq-ui/`.
- `sudo` on the Pi asks for the user's password, except for
  `/usr/local/bin/roomeq-reconnect` (see below). Ask the user before running
  other sudo commands.

## Hardware

- Raspberry Pi 4, Raspberry Pi OS 64-bit desktop (Debian Trixie base,
  kernel 6.18), labwc (Wayland), booting from an SD card.
- Touchscreen on DSI: `wlr-randr` reports **800 x 480**, scale 1.
- Power and data through a USB-C power/data splitter (ports labelled RPI4,
  USB, PWR): RPI4 -> Pi USB-C, USB -> Shield, PWR -> Pi power supply.
- NVIDIA Shield is the USB host / source. It sees the Pi as "Linux USB gadget".
- KEF LS50 Wireless (gen 1) on a blue USB 3 port of the Pi. Subwoofer is fed
  from the KEF's sub out (RCA), so any filter in CamillaDSP also affects the sub.
- Measurement kit: REW 5.31.3 (no API in this build) + UMIK-1 serial 7079072.
- Subwoofer: Rythmik L12 (servo, sealed), fixed position, fed from the KEF sub
  out into LINE IN "L" (not LFE: on LFE the phase and crossover knobs do
  nothing). Settings 2026-10-03: delay/phase 0, crossover max (120), LPF slope
  12 dB, PEQ off, bass extension Low-HT, volume set by ear (user prefers subtle,
  textured bass). Phase 0 beat 90/180 in REW (smooth 75-95 Hz, no notch).

## Audio chain

Shield -> USB gadget (UAC2) -> CamillaDSP -> KEF USB

| Side | ALSA device | Format | Rate | Channels |
|---|---|---|---|---|
| Capture (gadget) | `hw:CARD=UAC2Gadget,DEV=0` | `S32_LE` (only option) | 192000 (only option) | 2 |
| Playback (KEF) | `hw:CARD=Speaker,DEV=0` | `S24_3_LE` (also offers S16_LE) | 44.1k to 192k | 2 |

Gadget setup:
- `/boot/firmware/config.txt`, under `[all]`: `dtoverlay=dwc2,dr_mode=peripheral`
  (the `[cm4]`/`[cm5]`/`[pi5]` sections above it do not apply to a Pi 4).
- `/etc/modules`: `dwc2` and `g_audio`.
- `/etc/modprobe.d/usb_g_audio.conf`:
  `options g_audio c_srate=192000 c_ssize=4 c_chmask=3 p_chmask=0`
- Gadget max buffer is 8192 frames, so keep chunksize at 1024.
- Connection state: `cat /sys/class/udc/*/state` (`configured` = Shield attached).
- Is the Shield sending? `amixer -c UAC2Gadget cget iface=PCM,name='Capture Rate'`
  (192000 = audio arriving, 0 = not sending).

## CamillaDSP

- Version 4.1.3, binary `/usr/local/bin/camilladsp`.
- Service `camilladsp.service`:
  `camilladsp -s ~/camilladsp/statefile.yml -w -p 1234 -o ~/camilladsp/camilladsp.log`
  (runs as `joshi`, FIFO priority 10).
- Configs in `~/camilladsp/configs/`. Active: `room_eq.yml` (v4 format).
- Devices: samplerate 192000, chunksize 1024, rate adjust on, no resampler
  (fixed 2026-10-03).
- Current filters (placeholders until REW measurements). Names contain spaces:
  - `preamp`: Gain
  - `bass`: Biquad Lowshelf, 100 Hz, slope 6
  - `peq low` / `peq mid` / `peq high`: Biquad Peaking, 50 / 100 / 200 Hz, Q 2
  - `treble`: Biquad Highshelf, 5 kHz, slope 6
  - One Filter pipeline step on channels [0, 1].
- v4 format names: `S16_LE`, `S24_3_LE`, `S24_4_LE`, `S32_LE`, `F32_LE`.
  Shelves take `slope` (dB/oct) or `q`. FO variants (`LowshelfFO`) are first order.
- Log meaning: "Capture device is stalled" = no audio from the Shield.

## CamillaGUI (stock web GUI)

- Bundle in `/opt/camillagui_backend`, service `camillagui.service`, port **5005**.
- Slider shortcuts in `/opt/camillagui_backend/_internal/config/gui-config.yml`,
  using the `config_elements: [{path: [...], reverse: false}]` format.
  Backup: `~/camilladsp/gui-config_backup.yml`.
- Still used from the PC for detailed work, e.g. entering REW filters.

## Room EQ UI (custom)

- Code in `~/roomeq-ui/` on the Pi: `server.py`, `index.html`, `manifest.json`,
  `icon.svg`, `roomeq-ui.service`, `README.md`.
- Service `roomeq-ui.service`, port **8080**: `python3 ~/roomeq-ui/server.py`.
  Needs `python3-aiohttp` and `python3-yaml` (apt).
- Data in `~/camilladsp/roomeq_ui/`: `settings.json` and `uploads/` (logo and
  background images).
- `index.html` is read fresh on each request, so page changes only need a
  browser reload. `server.py` changes need a service restart. No sudo needed:
  the service runs as `joshi` with `Restart=always`, so
  `kill $(systemctl show -p MainPID --value roomeq-ui)` restarts it (allow a
  few seconds; the first SIGTERM can take a while). Screens reconnect by
  themselves; audio is not affected.

Screen sleep and brightness (2026-10-03):
- Settings popover (gear), "Screen" section: Brightness 10-100 % and
  "Sleep after" (Never, 1, 2, 5, 10, 15, 30, 60 min; default 5), stored in
  `settings.json` as `brightness` and `sleep_minutes`.
- Only the kiosk page (opened as `localhost`) sleeps; phones never do. After
  the idle time it shows a black cover and sends `screen` `on:false`; the
  server writes 0 to `/sys/class/backlight/10-0045/brightness` (group `video`,
  so no sudo). The first touch only wakes it: the cover swallows that touch.
- Commands: `screen` {on}, `brightness` {value, save}. If the page that put the
  screen to sleep disconnects, the server turns the backlight back on.

How it works:
- The server talks to CamillaDSP's websocket on 1234 and serves the page and a
  websocket at `/ws` for the screens. It pushes `state`, `levels` (~14/s),
  `status` (1/s: state, load, capture rate, clipped, rate adjust, CPU temp),
  `notice` and `selected` messages.
- It keeps a **base** config (loaded from the active YAML file, edited by the
  user) and sends an **effective** config with `SetConfigJson`. Effective =
  base, minus switched-off filters, minus all Filter steps when bypassed, plus
  `__roomeq_lowcut` (BiquadCombo ButterworthHighpass, order 4, 80 Hz) when
  Sub off / Night is on. Bypass, low cut and switched-off filters are never
  written to the YAML.
- Save writes base back to the active YAML with PyYAML (comments are lost) and
  keeps a `.bak` copy.
- Commands from the page: `set_param`, `toggle_filter`, `add_band`,
  `remove_filter`, `set_mode` (room / flat / night), `set_bypass`,
  `set_lowcut`, `preset`, `save`, `undo`, `settings`, `reconnect`.
- Modes (2026-10-03): Room EQ = the preset's own fader values; Flat = bypass;
  Vocal and Night = their own tone-fader values (DEFAULT_MODE_TONES in
  server.py, then remembered per mode in settings.json "mode_tones"). Switching
  mode moves the tone faders; gain changes made in Vocal/Night go to that mode,
  not the preset (no dirty flag). Night also adds a compressor. Retuned
  2026-10-04 from dialogue-EQ and night-mode guidance: Vocal 31 -6, 63 -4,
  125 -1, 250 -2, 500 -1, 2k +3, 4k +2.5; Night 31 -12, 63 -6, 125 -2, 250 -1,
  2k +2, 4k +1, 8k -2, 16k -4; compressor threshold -35 dB, ratio 4, attack
  10 ms, release 0.6 s, makeup +8 dB. Deployed with the overlay ON, so on the
  Pi it lasts until reboot: turn the overlay off and redeploy server.py (and
  re-apply the mode values) to make it permanent. Room bands are never changed by modes.
  Bypass button = Flat; "Sub off" button = 80 Hz low cut on its own.
- Auto preamp (setting `auto_preamp`, default on): the effective preamp is
  minus the largest boost of all active filters (+0.1 dB margin), so boosts
  never clip; the preamp fader shows "auto" and cannot be dragged.
- Faders: no chip row any more; each fader has a light-bulb on/off button at
  its foot and "+" at the end of the tone bank adds a band. Filters named
  "room ..." are room correction, shown behind a ROOM toggle (amber caps); the
  rest are the tone bank. rew_v1 has a 10-band tone
  bank (31 Hz-16 kHz, Q 1.41, 0 dB) in front of the 4 room cuts.
- If the YAML is edited elsewhere (CamillaGUI) while Room EQ runs, re-select
  the preset in Room EQ, or its next change will overwrite those edits.

Layout:
- Design: slate panels (`#232a35` at adjustable opacity), coral accent
  `#ff7a72`, cyan switches `#3ccfe0`, Manrope + JetBrains Mono.
  Header (logo with a small "CamillaDSP" caption under it, no "Room EQ" title;
  mode pill, preset bar, undo / save / gear; reconnect planned), a row of filter chips (on/off switch, name, short info such as
  "LS · 100 Hz"; scrolls sideways; "+ Band" at the end), then
  [slim EQ curve preview above the fader bank] | in/out meters. The curve is
  only a preview (160 px tall; 96 px with no title bar on the touchscreen).
- Fader bank (2026-10-03, replaced the cards and knobs): one vertical fader per
  filter, styled like a hardware EQ, preamp first with a cyan cap line. Drag
  moves the cap relative to the touch point (it never jumps); double-click
  resets to 0 dB. Below the bank: Freq and Q (or Slope) sliders and Remove for
  the selected band.
- Preview without the Pi: open `index.html?demo` (made-up data, commands applied
  in the page only). Serve `ui/` with a local static server; port 8765 is taken
  by the journaling app, so use another port such as 8791.
- Breakpoints: full layout above 700 px wide; a compact variant for small
  landscape screens (`min-width: 701px and max-height: 560px`) targets the
  800 x 480 touchscreen; phone layout at 700 px and below.
- Appearance popover: backgrounds (carbon, plain, walnut, uploaded photo),
  panel opacity, logo upload/remove. Tapping the logo opens it.
- Active branding (2026-10-03): header logo `assets/logos/joshs_eq_header.png`
  (made from `joshs_eq.png` by `scripts/make_logo.py`: black made transparent,
  margins cropped); background `assets/backgrounds/joshs_eq_dimmed.jpg`, made
  with `scripts/make_background.py` (dimmed, blurred logo on 1920x1080). Upload
  without the page: on the Pi,
  `curl -F file=@<img> http://localhost:8080/upload/background` (or `/logo`).

Reconnect button:
- Fixes the Shield no longer sending after a Pi reboot (reselecting the output
  or restarting the Shield does not help; unplugging the USB cable does).
- `/usr/local/bin/roomeq-reconnect` stops camilladsp, `modprobe -r g_audio`,
  waits, `modprobe g_audio`, starts camilladsp. Allowed without a password by
  `/etc/sudoers.d/roomeq`:
  `joshi ALL=(root) NOPASSWD: /usr/local/bin/roomeq-reconnect`
- The server re-applies the effective config afterwards.

## Touchscreen kiosk

- `~/.config/autostart/camillagui.desktop` (name kept from the CamillaGUI days):
  `Exec=sh -c "sleep 10; chromium --kiosk --noerrdialogs --password-store=basic --force-device-scale-factor=1 http://localhost:8080"`
- `--password-store=basic` stops the keyring password prompt at boot.
- With the Pi's keyboard: Ctrl+Shift+R hard reload, Ctrl+0 reset zoom,
  Alt+F4 leaves kiosk mode.
- Restart the kiosk browser remotely, no sudo (copy in `pi/bin/`):
  `ssh joshis-pi 'nohup ~/bin/roomeq-kiosk >/dev/null 2>&1 </dev/null'`.
  It needs `--ozone-platform=wayland` when started over SSH. Never use
  `pkill -f chromium...` over SSH: the pattern matches the SSH command itself.
- Prefer this to a reboot: after a reboot the Shield stops sending until the
  USB cable is replugged (until the Reconnect feature exists), and `sudo
  reboot` needs the user's password (SSH key login does not cover sudo).

## Health checks

- `systemctl status camilladsp camillagui roomeq-ui`
- `tail -20 ~/camilladsp/camilladsp.log`
- `aplay -l` (KEF = `Speaker`), `arecord -l` (gadget = `UAC2Gadget`)
- `vcgencmd get_throttled` (want `0x0`), `vcgencmd measure_temp` (~56 C normal)
- Pi status at handover: throttled 0x0, 56 C.

## Open items

Paused 2026-10-03. Next: miniDSP flash backup when the CH341A arrives; the
user plans a Pi heatsink and a closed case (watch CPU temp, ~56 C open).


1. ~~Compact layout on the 800 x 480 screen~~: done 2026-10-03 (new fader
   layout deployed, kiosk restarted, checked live at 800 x 480).
2. ~~Fix devices config~~: done 2026-10-03. Both presets now have
   `enable_rate_adjust: true` and no resampler (backups `*.pre-rateadjust`).
   Load fell to ~3.4 %, rate adjust ~1.0001, buffer converging; the "needless
   1:1 sample rate conversion" warning is gone. Earlier underruns (16:09,
   16:14) were before the change.
3. ~~Reconnect feature~~: done 2026-10-03. The user installed the helper and the
   sudoers rule; a test through the server took 3.7 s, then Running at 192 kHz.
3b. Auto-recover after a KEF USB dropout: deployed 2026-10-03, not yet seen
   live. The KEF's power saving switches it off (it leaves USB) regularly;
   CamillaDSP then stops with a PlaybackError and stays Inactive. The server's
   status loop (`auto_recover`) waits while a configured card is missing from
   `/proc/asound/`, then re-applies the effective config once both are back
   and shows "Speakers back: audio restarted". Failed attempts back off 5-30 s.
4. Room measurement with REW + UMIK-1 at the listening position, filters at
   0 dB, sub running, then replace the placeholder filters.
5. Larger logo area: done 2026-10-03 (title removed, header 68 px / 56 px on
   the touchscreen, transparent cropped logo).
6. Overlay (read-only) file system: **ON since 2026-10-03** (the user chose to
   accept losing manual slider tweaks at reboot). Turn it OFF before deploying
   code or presets that must persist, then back on. With it on, nothing is
   written to the SD card and all changes (presets saved, settings.json mode
   tones / brightness, uploads, deployed code) vanish at reboot, so it must be
   OFF while changing things. Check: `findmnt -n -o FSTYPE /` (overlay = on,
   ext4 = off). On: `ssh -t joshis-pi "sudo raspi-config nonint
   enable_overlayfs && sudo reboot"`. Off: same with `disable_overlayfs`.
   Boot-partition write protection (enable_bootro) optional, not needed.
   After any reboot: wait ~30 s, press Reconnect if the Shield does not play.

## Working rules

- Shut down with `sudo shutdown now` or `sudo reboot`; never pull power while
  running (an interrupted first boot already corrupted the card once).
- Keep chunksize 1024 and the 192 kHz / S32_LE gadget settings unless the user
  asks otherwise.
- Explain changes in plain language; the user is comfortable with the terminal
  but new to Linux audio.
