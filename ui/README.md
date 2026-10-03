# Room EQ UI

A touchscreen and phone remote for CamillaDSP: EQ curve with draggable bands,
filter cards, in/out meters, presets, Bypass, Sub off (80 Hz low cut),
custom logo and background.

## Install on the Pi

1. On Windows, unzip `roomeq-ui.zip`, then in PowerShell from the folder that
   contains `roomeq-ui`:

       scp -r roomeq-ui joshi@joshis-pi:~/

2. On the Pi, install the two libraries it needs:

       sudo apt install -y python3-aiohttp python3-yaml

3. Try it once by hand:

       python3 ~/roomeq-ui/server.py

   Open `http://joshis-pi:8080` on your computer or phone. Press Ctrl+C to stop.

4. Run it automatically at boot:

       sudo cp ~/roomeq-ui/roomeq-ui.service /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now roomeq-ui

5. Point the touchscreen at it: edit `~/.config/autostart/camillagui.desktop`
   and change `http://localhost:5005` to `http://localhost:8080`, then reboot.

6. On your Android phone, open `http://joshis-pi:8080` in Chrome, then
   menu > Add to Home screen.

## Using it

- Drag a node on the curve to change that band's frequency and gain.
  Drag knobs up and down; double-tap a knob to reset it.
- Changes play immediately. The save button (dot = unsaved changes) writes
  them to the active config file and keeps the previous version as `.bak`.
- Flat / Bypass and Night / Sub off are live switches and are never written
  into the config file. Cards switched off with their power button are
  remembered per preset.
- Presets are the config files in `~/camilladsp/configs`.
- If you edit the config in CamillaGUI while this is running, re-select the
  preset here so it reloads the file.

## Files

- `server.py` talks to CamillaDSP (port 1234) and serves the page on port 8080
- `index.html` the interface
- Logo, background and settings are stored in `~/camilladsp/roomeq_ui/`
