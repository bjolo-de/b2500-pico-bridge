"""
B2500 <-> Shelly bridge for Raspberry Pi Pico W / Pico 2 W.

The Marstek B2500 storage system reads its smart-meter data only
from a whitelist of supported Shelly devices (Pro 3EM, EM Gen3,
Pro EM 50, ...). Newer Shellys like the 3EM Gen3 speak the same
JSON-RPC over UDP but advertise a device-id prefix the B2500 does
not (yet) accept.

This bridge listens for the B2500's EM.GetStatus requests on
UDP 1010 and 2220, fetches live power data from a Shelly 3EM Gen3
via HTTP RPC, and replies under a device-id the B2500 accepts.

Designed for unattended, always-on operation off any USB power
source — typically a router USB port.
"""

import gc
import json
import select
import socket
import time

import network
import ntptime
import urequests
from machine import WDT, reset

import config

HTTP_TIMEOUT_S = 2
CACHE_TTL_MS = 1000
WIFI_TIMEOUT_S = 30
WDT_TIMEOUT_MS = 8000
GC_INTERVAL_MS = 30_000
HEARTBEAT_INTERVAL_MS = 60_000
SUPABASE_HB_INTERVAL_MS = 5 * 60 * 1000  # 5 min
STARTUP_GRACE_S = 3
REBOOT_DELAY_S = 5

_cache = {"powers": None, "ts": 0}
_time_synced = False


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Disable WiFi power saving. Default mode lets the CYW43439 sleep
    # between beacons, which drops inbound UDP packets that arrive
    # mid-sleep — fatal for a UDP server.
    wlan.config(pm=0xa11140)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        deadline = time.time() + WIFI_TIMEOUT_S
        while not wlan.isconnected():
            if time.time() > deadline:
                return None
            time.sleep(0.5)
    ip = wlan.ifconfig()[0]
    print("WiFi: {} @ {} (RSSI {} dBm)".format(
        config.WIFI_SSID, ip, wlan.status("rssi")
    ))
    return wlan


def sync_time():
    # NTP sync. Required before sending heartbeats with valid timestamps.
    # If sync fails, heartbeat is silently skipped — bridge keeps running.
    global _time_synced
    try:
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        _time_synced = True
        print("NTP synced")
    except Exception as e:
        print("NTP sync failed:", e)


def _iso_now():
    t = time.gmtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )


def supabase_heartbeat(pkt_count, err_count):
    # Optional: report liveness to a Supabase REST endpoint so a remote
    # dashboard can show this Pico as online. No-op if config fields are
    # not set, keeping the bridge standalone-usable.
    url = getattr(config, "SUPABASE_HEARTBEAT_URL", "")
    key = getattr(config, "SUPABASE_KEY", "")
    if not url or not key:
        return
    # If NTP failed at boot (server unreachable at that moment), retry now
    # lazily before each heartbeat. Without this, a Pico that boots before
    # the WiFi/NTP path is ready stays silently silent until next reboot.
    if not _time_synced:
        sync_time()
        if not _time_synced:
            return
    try:
        body = json.dumps([{
            "component": "pico_bridge",
            "last_seen": _iso_now(),
            "details": {"pkts": pkt_count, "errs": err_count},
        }])
        headers = {
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        r = urequests.post(
            url + "?on_conflict=component",
            data=body,
            headers=headers,
            timeout=4,
        )
        r.close()
    except Exception as e:
        print("supabase hb failed:", e)


def fetch_shelly_powers():
    nm = time.ticks_ms()
    if _cache["powers"] is not None and time.ticks_diff(nm, _cache["ts"]) < CACHE_TTL_MS:
        return _cache["powers"]
    r = urequests.get(
        "http://{}/rpc/EM.GetStatus?id=0".format(config.SHELLY_IP),
        timeout=HTTP_TIMEOUT_S,
    )
    try:
        j = r.json()
    finally:
        r.close()
    powers = (j["a_act_power"], j["b_act_power"], j["c_act_power"])
    _cache["powers"] = powers
    _cache["ts"] = nm
    return powers


def build_response(req_id, powers):
    # The Marstek B2500 firmware does not parse this response with a
    # general JSON parser — it appears to validate by field order and
    # absence of whitespace. Off-spec responses are silently rejected:
    # the B2500 keeps polling, but App pairing never completes and
    # regulation never engages. The format below mirrors what a real
    # Shelly Pro 3EM emits as compact JSON, byte-for-byte.
    #
    # MicroPython's json.dumps cannot produce this output: it has no
    # `separators` parameter (always inserts spaces) and does not
    # preserve dict insertion order. So we construct the response
    # string by hand. Phase values are passed through raw — synthetic
    # padding (e.g. 0.001 in place of true 0) appears to trip the
    # firmware's plausibility check and prevents regulation from
    # engaging.
    a, b, c = powers
    total = round(a + b + c, 3)
    return ('{"id":%s,"src":"%s","dst":"unknown",'
            '"result":{"a_act_power":%s,"b_act_power":%s,'
            '"c_act_power":%s,"total_act_power":%s}}') % (
        req_id, config.FAKE_SRC, a, b, c, total
    )


def handle_packet(sock, data, addr):
    try:
        req = json.loads(data.decode())
    except (UnicodeError, ValueError):
        return False
    if req.get("method") != "EM.GetStatus":
        return False
    powers = fetch_shelly_powers()
    sock.sendto(build_response(req.get("id", 0), powers).encode(), addr)
    return True


def serve():
    poll = select.poll()
    sockets = []
    for port in config.LISTEN_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # MicroPython on Pico W: bind(("", port)) does NOT actually bind
        # to all interfaces — inbound UDP never reaches userspace. The
        # explicit "0.0.0.0" string is required.
        s.bind(("0.0.0.0", port))
        s.setblocking(False)
        poll.register(s, select.POLLIN)
        sockets.append(s)
        print("Listening on UDP", port)

    print("Pretending to be", config.FAKE_SRC)

    wdt = WDT(timeout=WDT_TIMEOUT_MS)
    last_gc = time.ticks_ms()
    last_heartbeat = time.ticks_ms()
    last_supabase_hb = time.ticks_ms()
    pkt_count = 0
    err_count = 0

    while True:
        for s, _evt in poll.ipoll(1000):
            while True:
                try:
                    data, addr = s.recvfrom(2048)
                except OSError:
                    break
                pkt_count += 1
                try:
                    handle_packet(s, data, addr)
                except Exception as e:
                    err_count += 1
                    print("handler error:", e)

        wdt.feed()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_heartbeat) > HEARTBEAT_INTERVAL_MS:
            print("[hb] pkts={} errs={}".format(pkt_count, err_count))
            last_heartbeat = now

        if time.ticks_diff(now, last_supabase_hb) > SUPABASE_HB_INTERVAL_MS:
            wdt.feed()
            supabase_heartbeat(pkt_count, err_count)
            wdt.feed()
            last_supabase_hb = now

        if time.ticks_diff(now, last_gc) > GC_INTERVAL_MS:
            gc.collect()
            last_gc = now


def main():
    # Startup grace period. Lets the user Ctrl+C into the REPL before
    # WiFi association saturates USB-CDC and before the watchdog starts
    # (once started, WDT cannot be stopped — it would brick interactive
    # debugging via mpremote/Thonny within 8 s).
    print("Bridge starting in {}s. Ctrl+C for REPL.".format(STARTUP_GRACE_S))
    time.sleep(STARTUP_GRACE_S)

    if connect_wifi() is None:
        print("WiFi failed — rebooting in {}s".format(REBOOT_DELAY_S))
        time.sleep(REBOOT_DELAY_S)
        reset()

    sync_time()

    try:
        p = fetch_shelly_powers()
        print("Shelly OK ({:.0f} W)".format(sum(p)))
    except Exception as e:
        print("Shelly check failed:", e, "— continuing")

    serve()


try:
    main()
except KeyboardInterrupt:
    # Manual stop in REPL — leave the device usable for debugging.
    print("Stopped by user")
except Exception as e:
    # Fatal error — reboot. Once serve() has started, WDT would already
    # reboot us within 8 s; this branch covers failures before that.
    print("Fatal:", e, "— rebooting in {}s".format(REBOOT_DELAY_S))
    time.sleep(REBOOT_DELAY_S)
    reset()
