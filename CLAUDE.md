# room-eq

Category: personal
Path: Projects/personal/room-eq   (use paths relative to this folder)
Purpose: Raspberry Pi room-correction DSP (CamillaDSP) with a custom touchscreen UI, plus PC-side REW scripts.
Run: .venv\Scripts\python scripts\<script>.py   (PC helpers; the UI runs on the Pi, see "Room EQ UI")
Python: 3.12.9, .venv in the project root

# Josh's EQ: Raspberry Pi room-correction DSP

A Raspberry Pi 4 sits between an NVIDIA Shield and a pair of KEF LS50 Wireless
speakers. It receives USB audio from the Shield, applies room-correction EQ with
CamillaDSP, and sends it to the KEFs over USB. A custom touchscreen/phone UI
("Room EQ") controls it.

## Project folder (Windows PC)

`C:\Users\joshi\Projects\personal\room-eq\` (on the Pi the UI lives in `~/roomeq-ui/`):

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

## Josh's EQ Pocket: phone measurement page (2026-10-19)

- `web/phone_eq.html`, published as a private Artifact:
  https://claude.ai/artifact/V94Xsx2MX7YdWrJaj4FXBM (republish the same file path to update).
- Plays an 8 s log sweep (18 Hz-20 kHz, 0.5 s before, 2 s after), analyses WAV recordings
  (deconvolution, 300 ms IR window, UMIK-1 7079072 calibration built in: "Mic points" switch,
  90 degrees = up at the roof (default) or 0 degrees = at the speakers; switching re-bases stored
  positions; `pocket_analyse.py` also defaults to 90 degrees), averages positions and
  fits PEQ filters with a JS port of `design_peq.py`. Exports APO/AutoEq text (Poweramp EQ),
  Wavelet GraphicEQ (Wavelet's fixed 127 frequencies only), CamillaDSP, plain list.
- Artifact pages cannot use the microphone: record with a recorder app (USB Audio Recorder PRO
  or similar, WAV 48 kHz) and add the file. "Save measurements" moves data to the PC as JSON.
- PC check: `scripts/pocket_analyse.py <folder of WAVs>` does the same analysis and writes
  REW-style text files plus `average.txt` for `design_peq.py`. Both reject a recording where
  the full sweep is missing.
- 2026-10-21/22 car tests: no recording held a full sweep. The user stayed on the page until
  "Done"; the files are short and the sweep ends at a splice click 1-2 s before the end, so the
  recorder app pauses in the background (no foreground service). Confirmed 2026-10-23 by the user:
  USB Audio Recorder PRO records about 12 s after it leaves the screen, then pauses, also after
  a quick switch back. Its Output (monitor) was set to 8000 Hz: set 48000 Hz, MON off.
  Working method (user, 2026-10-23): recorder and the page in Android split screen, so neither
  pauses; the page's Play sweep then works. Fallback: keep the recorder in front
  and play `web/pocket_sweep_48k.wav` (3 s silence + the page's sweep, made by
  `pocket_analyse.py --write-sweep`) from a car USB stick or a music player.
- Phone over wireless adb (2026-10-23): platform-tools installed with winget; phone vivo V2562
  paired (guid `adb-10AG5L1NLF002QS`; the Shield also shows in `adb mdns services`, never use
  it). `scripts/phone.py status | push <files> --to Download/x | pull-recordings YYYY_MM_DD`.
  Recordings: `/sdcard/Documents/USBAudioRecorderPRO/Recordings/`.
- car_v1 (2026-10-23, 5 full sweeps): `scripts/design_full.py` (target = 500 Hz-2 kHz level +
  bass shelf below 60 Hz + -1 dB/oct above 2 kHz; 4 kHz high shelf + cut-only PEQs).
  Versions normal (+8 dB bass), gentle (+11), bass (+14) in `measurements/2026-10-23_car/`,
  pushed to the phone's `Download/car_eq_wavelet/`. Car: +15 dB at 40-70 Hz, +10 dB at
  150-250 Hz, treble 5-6 dB low.
- car_bass_v1 (2026-10-22, 5 positions, bass part only, 30-250 Hz, +6 dB lift): 42 Hz -3 Q 6,
  50 Hz -3 Q 3.5, 66 Hz -3 Q 4. Files in `measurements/2026-10-22_car/partial/`.

## Room check from the Pi (2026-10-27)

- `scripts/pi_sweep.py` runs on the Pi with the UMIK-1 on a Pi USB port: switches the UI to each mode,
  swaps CamillaDSP's capture for a WAV of the Pocket sweep (192 kHz, -10 dBFS used, played twice:
  the first wakes everything, the analysis picks the second), records with arecord, restores the mode.
  `scp scripts/pi_sweep.py joshis-pi:/tmp/ && ssh joshis-pi python3 /tmp/pi_sweep.py --level=-10 flat room`,
  then `scp joshis-pi:/tmp/pi_sweep/*.wav`, `scripts/pocket_analyse.py` (90 degree cal) and
  `scripts/compare_room.py flat.txt room.txt --png` (target as in design_peq; `--align` for runs at
  different volumes).
- Do not record the UMIK-1 on the PC with ffmpeg/dshow: Windows 11 "Voice clarity" (and other mic
  enhancements) removes steady sounds, so the slow low end of a sweep and test tones vanished.
  REW avoided it with WASAPI exclusive mode. The KEF and sub were fine.
- Result, one position, sub on, normal volume (`measurements/2026-10-27_room/`): above 80 Hz on target
  in both modes; rew_v1 cuts the 40/50/67 Hz peaks by 3-7 dB as designed, but the whole 18-80 Hz range
  sits +6..+8 dB above target (Flat +8..+12): the sub is about 5 dB louder vs the speakers than on
  2026-10-03. Narrow null at 105 Hz (-9 dB, sub/speaker overlap). RMS error 18-300 Hz: Flat 8.4 dB,
  Room EQ 6.0 dB.

## Speaker chirp from the display (2026-10-05)

A faint chirp/beep in the KEF stops when the backlight is off (brightness 0)
and is the same at 255, 150 and 60. CamillaDSP was clean at the time (silent
input, steady buffer, no clipping). It stayed with the KEF USB cable unplugged
and came only from the right speaker, next to the Pi, so it is radiated
interference, not a USB/ground path. It faded out a few minutes after boot, with
the chirps getting slower, which fits Wi-Fi/boot activity settling. If it comes
back: test more distance between the Pi and the right speaker, and Wi-Fi off.

## miniDSP 2x4 HD / DDRC-24 (side issue, 2026-10-03)

The user's old miniDSP (2x4 HD upgraded to DDRC-24 with Dirac) had UMIK-2
firmware flashed onto its XMOS by mistake: it shows as UMIK-2 v2.06, VID 0x2752
PID 0x002B. miniDSPUAC2Dfu fails at "Entering upgrade mode" (0xEE000003); the
Toolbox loader sends the firmware with no reply; holding the board's reset
button at power-up changes nothing. (Early belief, proven wrong 2026-10-29: the AT45DB321E is
NOT the XMOS flash; it is the SHARC DSP's flash. The XMOS firmware is inside the XMOS chip.)
Not needed for the Pi chain; its value is resale or a car install.

Status 2026-10-29: XMOS still runs UMIK-2 2.06. DSP side intact, AT45 backed up and resoldered.
Only route left: XMOS XTAG-4 on the 2x4 pin header next to the XMOS (JTAG), read the internal
flash with xflash, look for a factory image. Ask miniDSP support as a parallel option.

Tried and failed (do not repeat):

| Date | What | Result |
|---|---|---|
| 10-03/05 | miniDSPUAC2Dfu with the correct 2x4 HD / DDRC-24 firmware, AMD and Intel PCs, rear USB 2.0 ports, after power cycles | "Entering upgrade mode", then TUSBAUDIO_GetDfuStatus 0xEE000003 (TIMEOUT); device detaches, never re-enumerates in DFU mode |
| 10-05 | Hold the reset button during power-up (forum tip) | No change, still UMIK-2 |
| 10-05 | miniDSP factory/Toolbox loader tool | Sends the firmware, no reply |
| 10-05 | Pi as SPI programmer on the AT45 in-circuit (SOIC8 clip, flashrom), Pi-powered | All 0xFF, Pi undervoltage, back-feeds the board's 3.3 V rail. Never power the board from the Pi |
| 10-05 | Same, board self-powered, wake-up command 0xAB, reset held | RDID still 0xFF; in-circuit read impossible |
| 10-29 | AT45 desoldered, read off-board with the Pico (worked) | Holds DSP code, presets, Dirac data, not the XMOS firmware. Writing it cannot fix the USB side |
| 10-29 | Board search for an external XMOS flash | None (only op-amps, codec, regulators, resistor arrays); XMOS has internal flash |
| 10-29 | Driver API `TUSBAUDIO_StartDfuRevertToFactoryImage` | 0xEE000047 INVALID_INDEX |
| 10-29 | Driver API `ClassVendorRequestOut`, XMOS revert 0xF1 and DFU detach, all argument combinations | REJECTED (driver blocks the DFU interface) or TIMEOUT; device unchanged after power cycle |
| 10-29 | WinUSB via Zadig on the whole device + pyusb: DFU GETSTATUS / detach on interface 2 | Times out on a freshly powered device, then EP0 stalls. Every DFU request hangs (UMIK-2 audio core stuck on this hardware). USB route closed |

Lesson: in Zadig pick the entry whose current driver is `miniDSPUAC2` (whole device), not
"USB Input Device (Interface 3)" (the HID part).

2026-10-05 attempt with the Pi as programmer (flashrom linux_spi, SOIC8 clip):
- The clip's ribbon does not follow chip numbering. Measured map, IDC holes face
  you with the red stripe left (T = top row, B = bottom row, L/R = clip jaws
  from the top, wires down, red on the left jaw, XMOS at the board's top left):
  T1-L4 T2-L3 T3-L2 T4-L1, B1-R4 B2-R3 B3-R2 B4-R1. Wires used: T1 brown (CS),
  T2 orange (RESET), T3 purple (SCK), T4 blue (SI), B2 red (VCC), B3 white
  (GND), B4 green (SO), B1 empty (WP).
- With the Pi supplying 3.3 V, every probe read 0xFF, the Pi logged
  undervoltage, and the IDC connector got warm: the Pi back-feeds the whole
  board's 3.3 V rail. Do not power the chip from the Pi again. The board still
  enumerated as UMIK-2 afterwards (no damage); it needs its own power supply.
- Self-powered try (no red/orange wires, board on its own supply, grounds joined
  through white): chip VCC 3.2 V, RESET high, MISO idles high, but RDID still
  reads 0xFF, also after the 0xAB wake-up command and with the reset button held
  from power-up. In-circuit read failed; likely the XMOS keeps the SPI lines or a
  signal tooth has no contact. Options: desolder the chip and read it off-board,
  or ship the board to miniDSP.

2026-10-29 off-board read (chip desoldered, in a SOIC-8 socket adapter, wired to the Pico;
`scripts/minidsp_flash.py`): chip VCC (adapter wire gray) on Pico 3V3 OUT pin 36, RESET and WP
left open (internal pull-ups). ID `1f 27 01`, status 0xB4 (528-byte pages). Two reads identical:
`measurements/minidsp/at45_backup_2026-10-29.bin` (4,325,376 bytes = 8192 x 528).
- Used: pages 0-189 (~100 KB, XMOS code, no readable strings), four 69-page blocks plus one page
  each at pages 400, 625, 826, 1028 (likely the 4 presets' data), pages 8184-8191 with the user's
  preset names ("default dirac new", "flat filters", "high mids"). Rest is 0xFF.
- Analysis 2026-10-29: no USB strings at all (no "UMIK", "miniDSP", "XMOS", ASCII or UTF-16,
  also bit-reversed or byte-swapped). So this chip is NOT the XMOS firmware flash: it holds the
  DSP/MCU side (likely the DSP program in pages 0-189, the Dirac/preset data, preset names, and a
  device-unique string "27AcOcjkWu2SjYh" at 0x41fea0, possibly the Dirac licence ID). Do not erase
  it; resolder it unchanged. The UMIK-2 firmware must sit in the XMOS's own flash (an XUF part
  has it inside) or in another chip.
- Board photos 2026-10-29 (miniDSP 2x4 HD-V2 R1.0, Dec 2020): DSP = ADSP-21489 SHARC, codec
  PCM3168A, XMOS marked U11692C20 (TQFP-128, likely XUF216 = flash inside). The AT45 sits on the
  back (empty SOIC-8 pads) and is the SHARC's boot/preset flash. No external XMOS flash found.
  2x7 header next to the SHARC (its JTAG), 2x4 pin header next to the XMOS (likely XMOS JTAG).
- Plan (steps 1-2 done, both failed or done, see table above): (1) resolder the AT45 unchanged; (2) try the XMOS DFU "revert to factory" request
  (XMOS_DFU_REVERTFACTORY 0xF1, as `xmosdfu --revertfactory` in XMOS sw_usb_audio) from the PC
  over USB: it erases the upgrade image, so the XMOS boots its factory image again (likely the
  original miniDSP firmware). Needs the WinUSB driver on the DFU interface (Zadig, done by the user).
  (3) Fallback: XMOS xTAG on the 2x4 header, read the internal flash, erase only the upgrade image.
- USB attempts 2026-10-29 (all failed, device unchanged, still UMIK-2 2.06):
  - miniDSP driver API (`miniDSPUAC2api_x64.dll`, Thesycon TUSBAUDIO API 5.11) works from Python
    ctypes. `TUSBAUDIO_StartDfuRevertToFactoryImage(handle, flags)` returns 0xEE000047 INVALID_INDEX.
    `TUSBAUDIO_ClassVendorRequestOut` (10 args) to the DFU interface: REJECTED or TIMEOUT.
  - Device descriptor: IF0 audio control, IF1 audio in (3 alts), IF2 DFU runtime (DFU 1.1,
    attrs 0x07, detach 250 ms), IF3 HID.
  - With WinUSB on the whole device (Zadig, `USB\VID_2752&PID_002B`): standard requests work,
    but DFU GETSTATUS on IF2 times out (3 s) on a freshly powered device, then EP0 stalls.
  - Conclusion: every DFU request hangs. In XMOS lib_xua each DFU request first stops the audio
    core and waits for its handshake; the UMIK-2 build's audio core is likely stuck on the miniDSP
    hardware. This also explains the old 0xEE000003 timeout. The USB route is closed; use an XTAG-4.
  - Undo: Device Manager > the UMIK-2 / USB device > Uninstall device, tick "delete the driver",
    replug; the miniDSPUAC2 driver comes back (also for the HID part, MI_03, set to WinUSB first).

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
  `options g_audio c_srate=192000 c_ssize=4 c_chmask=3 p_chmask=0 iManufacturer=JoshEQ iProduct="JoshEQ DSP"`
  (name added 2026-10-29: the Shield lists "USB-Audio - JoshEQ DSP" instead of "Linux USB Audio
  Gadget"; the Pi-side ALSA card stays `UAC2Gadget`. Applied with roomeq-reconnect.)
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
- Dim stage and Screen off (2026-10-29): after `dim_minutes` (default 2; choices 0/1/2/5) of no
  touch the kiosk page sends `screen` {on: true, dim: true}; the server sets the backlight to
  `DIM_PCT` (8 % = 20 of 255) and a transparent cover swallows the waking touch. Off after
  `sleep_minutes` (default now 10). Moon button in the header: on the kiosk it goes dark at once;
  on a phone it sends `screen_off`, which the server broadcasts, and the kiosk page goes dark.
  Settings: "Dim after" and "Off after". Tested on the Pi: dim 20, awake 255, screen_off 0.
  Saved on the SD card 2026-10-29 (overlay off): code + settings sleep 10 / dim 2.

How it works:
- CamillaDSP client fix (2026-10-22): a call cancelled after sending (the
  debounced apply while dragging a fader) left its reply unread, so every later
  call read the previous call's answer until a server restart. Status fields
  came out shuffled, and `auto_recover` never saw `Inactive`, so the audio
  stayed off after a KEF USB dropout until a manual Reconnect. `Camilla.call`
  now skips replies whose key is not its command, and drops the connection
  when cancelled.
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
  10 ms, release 0.6 s, makeup +8 dB. Saved on the Pi 2026-10-15 (overlay off).
  Room bands are never changed by modes.
  Bypass button = Flat; "Sub off" button = 80 Hz low cut on its own.
- Auto mode switch (2026-10-11): Vocal at 23:00, Room EQ at 09:00, US Eastern
  (`MODE_SCHEDULE` in server.py, `schedule_loop`, checked every 20 s). Each
  time fires once; a mode the user picks afterwards stays. Every start or
  restart (2026-10-16, user's rule) uses the scheduled mode for the time of day,
  whatever was chosen before (reboot at 1 AM -> Vocal). The start waits for
  `/run/systemd/timesync/synchronized` (max 180 s), since the Pi has no RTC.
  While running, a switch more than 10 min late is skipped. On/off:
  gear > Schedule (setting `auto_mode`, default on).
- Bass slider (2026-10-27): meter panel, under Bypass / Sub off. Low shelf `__roomeq_bass`
  (80 Hz, Q 0.707), -12..+6 dB in 0.5 dB steps, setting `bass_db`; command `bass` {value, save}
  (live while dragging, saved on release; double-click resets to 0). Replaces the sub's own knob for
  the speaker/sub balance. Off in Flat. Auto preamp covers a boost. The 2026-10-27 room check
  suggests about -5 dB at mid volume.
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
- 2026-10-15: after an overlay reboot the link was `configured` but capture
  rate stayed 0, also after Reconnect. Restarting the Shield fixed it. The
  Shield sometimes stops routing sound to the USB output. Order to try:
  Reconnect, then restart the Shield, then replug the USB cable.
- Shield hint (2026-10-15): status carries `link` (`/sys/class/udc/*/state`).
  The status line shows "Shield not connected" (link not configured) or "No
  audio from Shield" (CamillaDSP state Stalled; also normal while nothing
  plays). 20 s after a Reconnect, if still Stalled with the link up, a toast
  says to restart the Shield (`shield_hint`, `SHIELD_HINT_DELAY`).

Restart Shield over ADB (2026-10-16):
- Gear > Shield > Restart Shield, and the button in the "Still no audio" toast.
  Command `restart_shield`: `adb connect <ip>:5555`, `get-state` must be
  `device`, then `adb reboot`. Shown only when `adb` is installed and
  `settings.json` has `shield_mac`.
- Shield MAC `00:04:4b:74:5f:62` (NVIDIA), IP `192.168.110.211` on 2026-10-15.
  The server finds the IP by MAC (`ip neigh`, ping sweep of the /24 if needed)
  and stores it as `shield_host`.
- Shield side: Developer options > Network debugging on; the Pi's ADB key is
  accepted once on the TV ("Always allow"). The key is `~/.android/adbkey` on
  the Pi: create it with the overlay off, or it is lost at reboot.
- 2026-10-27: the Pi's key was rejected again ("unauthorized"; likely lost to the
  overlay). The PC key is accepted: `adb connect 192.168.110.211:5555` from the PC.

Shield setup (debloat, Projectivy as the only Home, Sleep Home app, restore after a factory
reset): moved to its own project `Projects/personal/shield` on 2026-10-29 (completed).

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

## Boot splash (2026-10-16)

- Plymouth theme `joshs-eq` (stock theme was `pix`, a 1024x768 image from
  package `rpd-plym-splash`; left untouched). Source in `pi/plymouth/joshs-eq/`;
  `splash.png` made by `scripts/make_splash.py` (logo cropped, 80 % of the
  height, centred on black at 800x480). The script fits the image with its
  aspect ratio kept.
- Installed in `/usr/share/plymouth/themes/joshs-eq/`, set with
  `sudo plymouth-set-default-theme -R joshs-eq` (`-R` rebuilds the initramfs,
  which holds the theme). Back to stock: same command with `pix`.

## Health checks

- `systemctl status camilladsp camillagui roomeq-ui`
- `tail -20 ~/camilladsp/camilladsp.log`
- `aplay -l` (KEF = `Speaker`), `arecord -l` (gadget = `UAC2Gadget`)
- `vcgencmd get_throttled` (want `0x0`), `vcgencmd measure_temp` (~56 C normal)
- Pi status at handover: throttled 0x0, 56 C.

## Open items

To-dos: see TODO.md.

## Working rules

- Shut down with `sudo shutdown now` or `sudo reboot`; never pull power while
  running (an interrupted first boot already corrupted the card once).
- Keep chunksize 1024 and the 192 kHz / S32_LE gadget settings unless the user
  asks otherwise.
- Overlay file system is ON: turn it off before you deploy (how-to: TODO.md, item 6).
- Explain changes in plain language; the user is comfortable with the terminal
  but new to Linux audio.
