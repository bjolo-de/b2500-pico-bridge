# Setup guide

End‑to‑end: from a fresh Pico W / Pico 2 W in its bag to a working
bridge plugged into your router. About 15 minutes.

## 1. Install Thonny on your computer

Thonny is the easiest way to upload MicroPython code to a Pico.
Download from <https://thonny.org/>. It's free and runs on macOS,
Windows, and Linux.

## 2. Flash MicroPython onto the Pico

1. Download the latest MicroPython UF2 firmware for your board:
   - **Pico W**: <https://micropython.org/download/RPI_PICO_W/>
   - **Pico 2 W**: <https://micropython.org/download/RPI_PICO2_W/>

   Take the latest stable release (`.uf2` file).

2. Hold down the **BOOTSEL** button on the Pico while plugging it into
   your computer's USB port. A drive named `RPI-RP2` (or `RP2350` for
   the Pico 2 W) appears.

3. Drag the `.uf2` file onto that drive. The Pico reboots automatically
   after flashing — the drive disappears, and the device is now running
   MicroPython.

## 3. Configure the bridge

1. Copy `src/config.py.example` to `src/config.py`.
2. Open `src/config.py` and fill in:
   - Your **WiFi SSID** and **password** (2.4 GHz network)
   - The **IP** of your real Shelly 3EM
   - A **fake src** value starting with `shellypro3em-` (the suffix can
     be any 12 hex characters; using the real Shelly's MAC works well)

## 4. Upload the code to the Pico

1. Open Thonny. In the bottom right, switch the interpreter to
   **MicroPython (Raspberry Pi Pico)**.
2. In Thonny's file pane: open `src/boot.py`, then File → Save as →
   Raspberry Pi Pico → name it `boot.py`.
3. Repeat for `main.py` and `config.py`.
4. Hit the green Play button or press F5. You should see logs in
   Thonny's shell:

   ```
   Bridge starting in 3s. Ctrl+C for REPL.
   WiFi: your-ssid @ 192.168.x.x (RSSI -45 dBm)
   Shelly OK (98 W)
   Listening on UDP 1010
   Listening on UDP 2220
   Pretending to be shellypro3em-...
   ```

   After this the bridge prints a heartbeat once per minute
   (`[hb] pkts=N errs=M`) and otherwise stays quiet.

## 5. Move to the router

1. Stop the program in Thonny (red Stop button).
2. Unplug the Pico from your computer.
3. Plug it into your router's USB port using a short Micro‑USB cable.
4. The Pico boots in ~5 seconds (3 s startup grace + WiFi
   association), runs `boot.py` then `main.py` automatically, and
   starts serving the B2500.

To verify it's running, check from your computer:

```bash
echo '{"id":1,"method":"EM.GetStatus","params":{"id":0}}' \
  | nc -u -w2 <pico-ip> 2220
```

You should get back a JSON response with `a_act_power`, `b_act_power`,
`c_act_power` and `total_act_power`.

## 6. Connect the B2500

1. In the Marstek app, **disconnect any active Bluetooth connection**
   to the B2500 (close the app or leave the device).
2. In the app: **Auto Mode → Third-party CT devices → Shelly Pro 3EM**.
3. Within 30–60 seconds the per-phase power values should start
   flowing in the B2500 stream view, and within another minute or two
   the storage should engage and regulate towards net-zero at the
   grid connection.

If you previously had a different bridge (laptop script, container,
another Pico) on a different IP, the B2500 may need a hard
power-cycle (unplug for 30 s) before it accepts the new bridge.

## Troubleshooting

**Pico's USB port not detected by the router**
Some router USB ports only deliver power when a "valid" USB device is
present. The Pico is a valid device, but if your router rejects it,
use any wall USB charger instead — same result. Or test with a
smartphone first: if it charges from the router USB, the Pico will
work.

**WiFi never connects**
The Pico W only supports 2.4 GHz. If your router uses combined
2.4/5 GHz with a single SSID, the Pico will pick whichever the AP
allows. If WiFi connection times out, double‑check SSID/password and
that the network is 2.4 GHz‑capable.

**B2500 doesn't find the meter**
Check the bridge logs (plug back into your computer, run via Thonny)
to see if `EM.GetStatus` requests are arriving. If yes, the data path
works — check the Marstek app for a stale meter status (cache lag of
several minutes is normal).

**Bridge crashes silently**
The watchdog reboots the Pico every 8 seconds if the main loop hangs.
If the device keeps rebooting, plug into your computer and watch the
Thonny shell for the actual error.

## Power consumption

The Pico W draws ~50 mA average, ~150 mA peak. At 5 V that's
~0.25–0.75 W, or ~6 kWh per year — about €1.80 at typical German
electricity prices.
