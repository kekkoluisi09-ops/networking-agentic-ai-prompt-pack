"""
Multi-Vendor Python 3.11+ Network Device SSH Library
Supports: D-Link DGS-1210, Fortinet FortiOS, Cisco IOS-XE, HP/Aruba ProCurve
"""
import logging
import time
from typing import Any

try:
    from netmiko import ConnectHandler
except ImportError:
    ConnectHandler = None


class NetworkDeviceError(Exception):
    """Base exception for network device operations."""


class ConnectionError(NetworkDeviceError):
    """SSH connection failed."""


class AuthenticationError(NetworkDeviceError):
    """Credentials rejected."""


class CommandError(NetworkDeviceError):
    """Command execution failed or timed out."""


class NetworkDevice:
    def __init__(
        self,
        hostname: str,
        ip: str,
        vendor: str,
        username: str,
        password: str,
        port: int = 22,
        connection_timeout: int = 30,
        command_timeout: int = 60,
    ) -> None:
        self.hostname = hostname
        self.ip = ip
        self.vendor = vendor.lower()
        self.username = username
        self.password = password
        self.port = port
        self.connection_timeout = connection_timeout
        self.command_timeout = command_timeout
        self._conn: Any = None
        self.logger = logging.getLogger(f"NetworkDevice.{hostname}")

    def _get_netmiko_device_type(self) -> str:
        mapping = {
            "fortinet": "fortinet",
            "cisco_ios": "cisco_ios",
            "aruba": "hp_procurve",
            "d-link": "generic",
        }
        if self.vendor not in mapping:
            raise ValueError(f"Unsupported vendor: {self.vendor}")
        return mapping[self.vendor]

    def _get_backup_command(self) -> str:
        if self.vendor == "fortinet":
            return "show full-configuration"
        return "show running-config"

    def connect(self) -> None:
        if ConnectHandler is None:
            raise ConnectionError("Netmiko library is not installed.")
        dev_type = self._get_netmiko_device_type()
        for attempt in range(3):
            try:
                self._conn = ConnectHandler(
                    device_type=dev_type,
                    host=self.ip,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    timeout=self.connection_timeout,
                )
                return
            except Exception as exc:
                if attempt == 2:
                    raise ConnectionError(f"Failed to connect to {self.hostname} ({self.ip}): {exc}") from exc
                time.sleep(2 ** attempt)

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            finally:
                self._conn = None

    def __enter__(self) -> "NetworkDevice":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()

    def send_command(self, cmd: str, timeout: int | None = None) -> str:
        if self._conn is None:
            raise CommandError("Not connected.")
        try:
            return self._conn.send_command(cmd, read_timeout=timeout or self.command_timeout)
        except Exception as exc:
            raise CommandError(f"Command '{cmd}' failed on {self.hostname}: {exc}") from exc

    def send_config(self, config_lines: list[str], dry_run: bool = False) -> str:
        if dry_run:
            return "[DRY RUN] Would send:\n" + "\n".join(config_lines)
        if self._conn is None:
            raise CommandError("Not connected.")
        return self._conn.send_config_set(config_lines)

    def backup_config(self) -> str:
        return self.send_command(self._get_backup_command())
