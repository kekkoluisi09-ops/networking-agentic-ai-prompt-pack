#!/usr/bin/env python3
"""
Device Availability Monitoring Daemon + Auto-Refreshing HTML Dashboard
Usage: python3 monitor.py
"""
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RUNNING = True
STATE_STORE = {}


def ping_once(ip: str) -> tuple[bool, float | None]:
    cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            for part in res.stdout.split():
                if part.startswith("time="):
                    return True, float(part.split("=")[1])
            return True, 1.0
        return False, None
    except Exception:
        return False, None


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        rows = ""
        for hname, st in STATE_STORE.items():
            rows += f"<tr><td>{hname}</td><td>{st['ip']}</td><td><b>{st['state']}</b></td><td>{st['last_rtt']} ms</td><td>{st['since']}</td></tr>"
        html = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="30"><title>Network Monitor</title>
<style>body{{font-family:monospace;margin:2rem;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #000;padding:8px;text-align:left;}}</style>
</head><body><h2>Corp.Example Lab — Availability Monitor</h2>
<table><tr><th>Device</th><th>IP</th><th>State</th><th>Last RTT</th><th>State Since</th></tr>{rows}</table>
<p>Last refresh: {datetime.now().isoformat()}</p></body></html>"""
        self.wfile.write(html.encode("utf-8"))


def monitor_device(dev: dict, interval: int, down_th: int, up_th: int) -> None:
    hname = dev["hostname"]
    ip = dev["ip"]
    STATE_STORE[hname] = {
        "ip": ip,
        "state": "UNKNOWN",
        "since": datetime.now().isoformat(),
        "consec_fail": 0,
        "consec_ok": 0,
        "last_rtt": None,
        "events": deque(maxlen=43200),
    }
    while RUNNING:
        ok, rtt = ping_once(ip)
        st = STATE_STORE[hname]
        old_state = st["state"]
        if ok:
            st["last_rtt"] = rtt
            st["consec_ok"] += 1
            st["consec_fail"] = 0
            if old_state in ("UNKNOWN", "FLAPPING") or (old_state == "DOWN" and st["consec_ok"] >= 1):
                st["state"] = "RECOVERING" if old_state == "DOWN" and st["consec_ok"] < up_th else "UP"
            elif old_state == "RECOVERING" and st["consec_ok"] >= up_th:
                st["state"] = "UP"
        else:
            st["consec_fail"] += 1
            st["consec_ok"] = 0
            if st["consec_fail"] >= down_th:
                st["state"] = "DOWN"
            else:
                st["state"] = "FLAPPING"

        if st["state"] != old_state:
            st["since"] = datetime.now().isoformat()
            print(f"[{st['since']}] {hname} ({ip}): {old_state} -> {st['state']}")
        time.sleep(interval)
