"""
CLI Output Parser — D-Link DGS-1210-52TP
Command: show vlan
"""
import re

SHOW_VLAN_PATTERN = re.compile(
    r"VID\s*:\s*(?P<vlan_id>\d+)\n"
    r"VLAN Name\s*:\s*(?P<vlan_name>\S+)\n"
    r"Member Ports\s*:\s*(?P<member_ports>[^\n]*)\n"
    r"Static Ports\s*:\s*(?P<static_ports>[^\n]*)\n"
    r"Dynamic Ports\s*:\s*(?P<dynamic_ports>[^\n]*)\n"
    r"VLAN Type\s*:\s*(?P<vlan_type>\S+)",
    re.MULTILINE,
)


def parse_show_vlan(raw: str) -> list[dict]:
    if not raw or not raw.strip():
        return []
    results = []
    for match in SHOW_VLAN_PATTERN.finditer(raw):
        results.append({
            "vlan_id": int(match.group("vlan_id")),
            "vlan_name": match.group("vlan_name"),
            "member_ports": match.group("member_ports").strip() or None,
            "static_ports": match.group("static_ports").strip() or None,
            "dynamic_ports": match.group("dynamic_ports").strip() or None,
            "vlan_type": match.group("vlan_type"),
        })
    return results
