# b2500-pico-bridge

A tiny MicroPython bridge that lets a **Marstek B2500** balcony battery
storage system talk to a **Shelly 3EM Gen3** (or any other Shelly EM
that the B2500 doesn't natively support yet).

Runs on a **Raspberry Pi Pico W / Pico 2 W** powered from any USB port —
e.g. a router USB port that's already on 24/7. No Linux, no SD card,
no extra power supply, no Docker.

## Why this exists

The Marstek B2500 firmware only accepts smart meters whose RPC `src`
field starts with one of the prefixes it has whitelisted (e.g.
`shellypro3em-…`, `shellyemg3-…`, `shellyproem50-…`). The newer
**Shelly 3EM Gen3** identifies itself as `shelly3em63g3-…` and is
therefore rejected by the B2500 even though it speaks the same
JSON‑RPC over UDP and returns the exact same data fields.

This bridge sits between the B2500 and the Shelly:

```
B2500 ──UDP──▶ Pico W ──HTTP──▶ Shelly 3EM Gen3
        ◀──UDP──        ◀──HTTP──
        (rewritten src)
```

It listens for the B2500's `EM.GetStatus` requests, fetches the actual
power data from the Shelly via HTTP RPC, and replies pretending to be
a Shelly Pro 3EM by setting `src` to a `shellypro3em-…` value the B2500
accepts.

## Hardware

| Item | Cost | Notes |
|---|---:|---|
| Raspberry Pi Pico W or Pico 2 W | ~7–8 € | 2.4 GHz WiFi required |
| Micro‑USB‑B cable, ~30 cm | ~3 € | data + power, not charge‑only |
| USB power source | 0 € | any 5 V port: router, wall plug, TV, NAS |

The Pico draws ~50–150 mA, well under any USB 2.0 spec. Powering it
from the Vodafone Station USB port works (data is locked, power is
not) — see [docs/setup.md](docs/setup.md) for details.

## Quick start

1. Flash MicroPython onto the Pico — see [docs/setup.md](docs/setup.md).
2. Copy `src/config.py.example` to `src/config.py` and fill in your
   WiFi, Shelly IP, and a fake `src` value.
3. Upload `src/boot.py`, `src/main.py`, and `src/config.py` to the Pico
   via Thonny.
4. Unplug from your computer, plug into the router's USB port. Done.
5. In the Marstek app: Bluetooth disconnect, switch the B2500 to
   Self‑Adaptation. After ~30 s the meter shows up.

## Status

Tested with:
- Marstek B2500 firmware **V110.9 (HMJ)**
- Shelly 3EM Gen3, model `S3EM-003CXCEU63`, firmware `1.7.5`
- Raspberry Pi Pico 2 W, MicroPython 1.x

If you confirm it works on a different combo, please open an issue or
PR — happy to grow the compatibility table.

## Optional: monitoring dashboard

The bridge can also report a heartbeat to Supabase every 5 minutes so a
companion dashboard knows it's alive — see
[bjolo-de/b2500-dashboard](https://github.com/bjolo-de/b2500-dashboard).
Two extra fields in `config.py` (both default empty = disabled), no
change to the bridge's primary function.

## Related projects

- [tomquist/AstraMeter](https://github.com/tomquist/AstraMeter) — the
  full‑featured Python emulator that supports many smart meter sources
  and runs on Linux/Docker/Home Assistant. This bridge is the
  minimal‑hardware counterpart, focused on a single use case.
- [tomquist/hm2mqtt](https://github.com/tomquist/hm2mqtt) and
  [tomquist/hame-relay](https://github.com/tomquist/hame-relay) — the
  upstream MQTT integrations the dashboard builds on top of.

## License

MIT — see [LICENSE](LICENSE).
