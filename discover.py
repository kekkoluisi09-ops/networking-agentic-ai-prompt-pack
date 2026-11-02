#!/usr/bin/env python3
"""
Network Discovery Script — authorized networks only.
Usage: python3 discover.py --ranges 10.10.60.0/24 --ports 22,443 --output ./out.csv
Authorization: Run ONLY on networks you own or have explicit written permission to scan.
US CFAA (18 U.S.C. § 1030) and UK CMA 1990 apply.
"""
import argparse
import concurrent.futures
import csv
import ipaddress
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime

try:
    from tabulate import tabulate
except ImportError:
    sys.exit("Install requirements: pip install -r requirements.txt")


def require_authorization() -> None:
    """Prompt the operator to confirm they have authorization to scan the network."""
    print(
        "\n[!] AUTHORIZED USE ONLY\n"
        "    Network scanning without explicit written authorization is illegal\n"
        "    under the US Computer Fraud and Abuse Act (18 U.S.C. § 1030) and\n"
        "    UK Computer Misuse Act 1990. This tool must only be run on networks\n"
        "    you own or for which you hold written authorization.\n"
    )
    response = input('    Type "I CONFIRM" to continue: ').strip()
    if response != "I CONFIRM":
        sys.exit("Scan cancelled — authorization not confirmed.")


def ping_host(ip: str, timeout: float) -> dict:
    """Ping a single host and return status and RTT."""
    is_win = platform.system().lower() == "windows"
    param = "-n" if is_win else "-c"
    wait_flag = "-w" if is_win else "-W"
    wait_val = str(int(timeout * 1000)) if is_win else str(int(max(1, timeout)))
    cmd = ["ping", param, "1", wait_flag, wait_val, ip]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1.0)
        alive = result.returncode == 0
        rtt = None
        if alive:
            for part in result.stdout.split():
                if "time=" in part.lower() or "durata=" in part.lower():
                    val = part.split("=")[1].replace("ms", "").strip()
                    try:
                        rtt = float(val)
                    except ValueError:
                        pass
                    break
        return {"ip": ip, "alive": alive, "rtt_ms": rtt}
    except Exception as exc:
        return {"ip": ip, "alive": False, "rtt_ms": None, "error": str(exc)}


def get_mac(ip: str) -> str:
    """Look up MAC address from OS ARP cache."""
    is_win = platform.system().lower() == "windows"
    cmd = ["arp", "-a", ip] if is_win else ["arp", "-n", ip]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        for line in result.stdout.splitlines():
            if ip in line:
                for part in line.split():
                    clean = part.replace("-", ":")
                    if clean.count(":") == 5 and len(clean) == 17:
                        return clean.lower()
        return "unknown"
    except Exception:
        return "requires-root"


def get_hostname(ip: str) -> str:
    """Reverse DNS lookup."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "no-rdns"


def scan_ports(ip: str, ports: list[int], timeout: float) -> str:
    """Socket-based TCP port scan."""
    open_ports = []
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                open_ports.append(str(port))
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
    return ", ".join(open_ports) if open_ports else "(none)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-threaded Network Discovery Tool")
    parser.add_argument("--ranges", required=True, help="Comma-separated CIDR ranges")
    parser.add_argument("--ports", default="22,80,443,8080", help="Comma-separated TCP ports")
    parser.add_argument("--output", default="", help="Output CSV path")
    parser.add_argument("--threads", type=int, default=50, help="Max worker threads")
    parser.add_argument("--ping-timeout", type=float, default=1.0, help="Ping timeout (s)")
    parser.add_argument("--port-timeout", type=float, default=0.5, help="Port timeout (s)")
    parser.add_argument("--skip-ports", action="store_true", help="Skip TCP port scan")
    args = parser.parse_args()

    require_authorization()

    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip().isdigit()]
    hosts = []
    for r in args.ranges.split(","):
        net = ipaddress.ip_network(r.strip(), strict=False)
        hosts.extend([str(ip) for ip in net.hosts()])

    start_time = time.time()
    print(f"[+] Scanning {len(hosts)} hosts | Threads: {args.threads}")

    alive_hosts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.threads, 200)) as executor:
        futures = {executor.submit(ping_host, ip, args.ping_timeout): ip for ip in hosts}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res.get("alive"):
                alive_hosts.append(res)

    alive_hosts.sort(key=lambda x: ipaddress.ip_address(x["ip"]))
    table_rows = []
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = args.output if args.output else f"discovery_{ts_str}.csv"

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "ip", "alive", "rtt_ms", "mac", "hostname", "open_ports"])
        for h in alive_hosts:
            ip = h["ip"]
            mac = get_mac(ip)
            hname = get_hostname(ip)
            oports = "(skipped)" if args.skip_ports else scan_ports(ip, ports, args.port_timeout)
            now_iso = datetime.now().isoformat()
            writer.writerow([now_iso, ip, True, h["rtt_ms"], mac, hname, oports])
            table_rows.append([ip, "YES", h["rtt_ms"], mac, hname, oports])

    print(tabulate(table_rows, headers=["IP", "Alive", "RTT(ms)", "MAC", "Hostname", "Open Ports"], tablefmt="grid"))
    print(f"[+] Scan finished in {time.time() - start_time:.1f}s. Saved to {out_file}")


if __name__ == "__main__":
    main()
