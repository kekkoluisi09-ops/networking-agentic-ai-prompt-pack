#!/usr/bin/env python3
"""
Automated Configuration Backup Script (Multi-Vendor SSH via Netmiko)
Usage:
  python3 backup.py --dry-run --config ./devices.yaml
  python3 backup.py --test-one --config ./devices.yaml
  python3 backup.py --config ./devices.yaml
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import yaml
    from netmiko import ConnectHandler
except ImportError:
    ConnectHandler = None

VENDOR_COMMANDS = {
    "fortinet": "show full-configuration",
    "d-link": "show running-config",
    "cisco_ios": "show running-config",
    "hp_procurve": "show running-config",
}


def load_credentials() -> dict:
    cred_file = os.environ.get("BACKUP_CREDENTIALS_FILE")
    if cred_file and Path(cred_file).exists():
        with open(cred_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    user = os.environ.get("BACKUP_USER")
    pw = os.environ.get("BACKUP_PASS")
    if user and pw:
        return {"default": {"username": user, "password": pw}, "overrides": {}}
    sys.exit("ERROR: Credentials not found. Set BACKUP_CREDENTIALS_FILE or BACKUP_USER/BACKUP_PASS.")


def rotate_backups(base_dir: Path, hostname: str, retention: int) -> None:
    files = sorted(base_dir.glob(f"**/{hostname}_*.cfg"))
    if len(files) > retention:
        for old_file in files[: len(files) - retention]:
            old_file.unlink()
            print(f"[ROTATION] Deleted old backup: {old_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Vendor Configuration Backup")
    parser.add_argument("--config", default="./devices.yaml", help="Path to devices YAML")
    parser.add_argument("--backup-dir", default="./backups", help="Base backup directory")
    parser.add_argument("--retention", type=int, default=30, help="Max backups per device")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without connecting")
    parser.add_argument("--test-one", action="store_true", help="Backup first device only")
    parser.add_argument("--device", default="", help="Backup specific hostname only")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        devices = yaml.safe_load(f).get("devices", [])

    if args.device:
        devices = [d for d in devices if d["hostname"] == args.device]
    if args.test_one and devices:
        devices = [devices[0]]

    date_str = datetime.now().strftime("%Y-%m-%d")
    hm_str = datetime.now().strftime("%H%M")
    target_dir = Path(args.backup_dir) / date_str

    if args.dry_run:
        print(f"[DRY RUN] Would back up {len(devices)} devices to {target_dir}/")
        for d in devices:
            print(f"  {d['hostname']} ({d['ip']}) [{d['vendor']}] -> {d['hostname']}_{date_str}_{hm_str}.cfg")
        return

    if ConnectHandler is None:
        sys.exit("Install netmiko: pip install netmiko pyyaml")

    creds = load_credentials()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.backup_dir) / f"backup_log_{date_str}.jsonl"

    for d in devices:
        hname = d["hostname"]
        ip = d["ip"]
        vendor = d["vendor"]
        port = d.get("port", 22)
        c = creds.get("overrides", {}).get(hname, creds.get("default", {}))
        cmd = VENDOR_COMMANDS.get(vendor, "show running-config")

        start_t = time.time()
        status = "FAILED"
        err_msg = None
        out_path = target_dir / f"{hname}_{date_str}_{hm_str}.cfg"

        for attempt in range(1, 4):
            try:
                conn = ConnectHandler(
                    device_type=vendor if vendor != "d-link" else "generic",
                    host=ip,
                    username=c["username"],
                    password=c["password"],
                    port=port,
                    timeout=30,
                )
                cfg_text = conn.send_command(cmd, read_timeout=60)
                conn.disconnect()
                out_path.write_text(cfg_text, encoding="utf-8")
                os.chmod(out_path, 0o600)
                status = "SUCCESS"
                print(f"[OK] {hname} ({ip}) -> {out_path.name}")
                rotate_backups(Path(args.backup_dir), hname, args.retention)
                break
            except Exception as exc:
                err_msg = str(exc)
                time.sleep(2 ** attempt)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "device": hname,
            "ip": ip,
            "status": status,
            "file_saved": str(out_path) if status == "SUCCESS" else None,
            "duration_s": round(time.time() - start_t, 2),
            "error": err_msg,
        }
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(log_entry) + "\n")


if __name__ == "__main__":
    main()
