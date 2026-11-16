"""手機展示：偵測筆電的區網 IPv4、組啟動提示。只在手機模式（JOB_RAG_HOST 非本機）使用；不做任何通道或轉發。"""
import ipaddress
import json
import os
import subprocess

LOOPBACK = ("127.0.0.1", "localhost", "::1")
# 虛擬網卡與非區網介面的名稱字樣（小寫比對）。shortcut: 只認名稱字樣，未知的虛擬網卡會被列為候選，請看清單選。
VIRTUAL = ("vmware", "virtualbox", "vethernet", "hyper-v", "wsl", "docker", "loopback", "bluetooth", "藍牙",
           "tap-", "vpn", "tailscale", "zerotier", "虛擬")


def listen_host() -> str:
    return os.environ.get("JOB_RAG_HOST", "").strip() or "127.0.0.1"


def phone_mode() -> bool:
    return listen_host() not in LOOPBACK


def adapters() -> list[tuple[str, str]]:
    """(網卡名稱, IPv4)。用 PowerShell 取，名稱才不受 ipconfig 語系與編碼影響。失敗時回空，由呼叫端顯示找不到。"""
    cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
           "Get-NetIPAddress -AddressFamily IPv4|Select-Object InterfaceAlias,IPAddress|ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=15).stdout
        rows = json.loads(out.decode("utf-8"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return [(r["InterfaceAlias"], r["IPAddress"]) for r in ([rows] if isinstance(rows, dict) else rows)]


def lan_candidates(found: list[tuple[str, str]]) -> list[dict]:
    """排除 127.*、169.254.*、虛擬網卡；其餘依「最可能」排序。第一個標 best。
    排序：私有網段在前；名稱像 Wi-Fi 在前（手機熱點）；結尾 .1 的位址在後（多半是虛擬網路的主機端）。"""
    rows = []
    for name, ip in found:
        a = ipaddress.ip_address(ip)
        if a.is_loopback or a.is_link_local or any(v in name.lower() for v in VIRTUAL):
            continue
        wifi = any(w in name.lower() for w in ("wi-fi", "wifi", "wlan", "無線"))
        rows.append(({"name": name, "ip": ip, "best": False}, (not a.is_private, not wifi, ip.endswith(".1"))))
    out = [r for r, _ in sorted(rows, key=lambda x: x[1])]
    if out:
        out[0]["best"] = True
    return out


def detect() -> list[dict]:
    return lan_candidates(adapters())


def banner(cands: list[dict], port) -> str:
    if not cands:
        return "找不到區網 IPv4：請確認筆電已連上手機熱點，再重新啟動。"
    lines = [f"手機請開：http://{c['ip']}:{port}" + (f"  （{c['name']}，最可能）" if c["best"] else f"  （{c['name']}）")
             for c in cands]
    if len(cands) > 1:
        lines.insert(0, f"偵測到 {len(cands)} 個區網位址，請用連到手機熱點的那一個：")
    return chr(10).join(lines)
