#!/usr/bin/env python3
"""Parse MD/MF stock-audit logs into a data-derived profile.

No model geometry is accepted merely because a constant says so.  The stock
restore span comes from the stock /proc/mtd all_flash view (normally mtd16).
Physical NAND capacity is derived only from NAND-driver evidence such as dmesg;
stock mtd0 is a 512-KiB bootloader partition and is NOT the physical NAND size.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

HISTORICAL_RESTORE_SPAN = 0x0EBA0000
KNOWN_PHYSICAL_NAND_REFERENCE = 0x10000000

MD_SLOT_LAYOUTS = (
    ("MD-A", {2: 0x003AF6DA, 3: 0x01CC0000, 4: 0x00480000, 5: 0x02400000}),
    ("MD-A-MIRROR", {2: 0x00480000, 3: 0x02400000, 4: 0x003AF6DA, 5: 0x01CC0000}),
)
MF_SLOT_LAYOUTS = (
    ("MF-A", {2: 0x003B6CC0, 3: 0x01D00000, 4: 0x00480000, 5: 0x02400000}),
    ("MF-A-MIRROR", {2: 0x00480000, 3: 0x02400000, 4: 0x003B6CC0, 5: 0x01D00000}),
    ("MF-B", {2: 0x003B6D40, 3: 0x01D10000, 4: 0x00480000, 5: 0x02400000}),
    ("MF-B-MIRROR", {2: 0x00480000, 3: 0x02400000, 4: 0x003B6D40, 5: 0x01D10000}),
)

STOCK_SLOT_CANONICAL_PAIR = (0x00480000, 0x02400000)
STOCK_SLOT_REVISION_REFERENCE = {
    "md": ((0x003AF6DA, 0x01CC0000),),
    "mf": ((0x003B6CC0, 0x01D00000), (0x003B6D40, 0x01D10000)),
}
STOCK_SLOT_IMAGE_TOLERANCE = 0x2000
STOCK_SLOT_PARTITION_TOLERANCE = 0x10000
STOCK_SLOT_PARTITION_GRANULARITY = 0x10000


def split_sections(text: str) -> dict[str, str]:
    text = text.replace("\x00", "")
    out: dict[str, str] = {}
    cur = "PREAMBLE"
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^===([A-Z0-9-]+)===$", line.strip())
        if m:
            out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    out[cur] = "\n".join(buf)
    return out


def parse_kv(sec: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in sec.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def parse_identity(sec: str) -> dict[str, str]:
    d: dict[str, str] = {}
    m = re.search(r"\b(?:AN|EN)(75\d\d)\b", sec, re.I)
    if m:
        d["soc"] = "AN" + m.group(1)
    m = re.search(r"Nokia\s+XG-040G-M[DF]", sec, re.I)
    if m:
        d["model"] = m.group(0)
    m = re.search(r"nokia,(xg-040g-m[df][\w-]*)", sec, re.I)
    if m:
        d["board"] = m.group(1)
    m = re.search(r"Linux\s+\S+\s+(\S+)", sec)
    if m:
        d["kernel"] = m.group(1)
    m = re.search(r"\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", sec, re.I)
    if m:
        d["mac"] = m.group(1).lower()
    return d


def parse_mtd(sec: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in sec.splitlines():
        m = re.match(r'^\s*(mtd\d+):\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+"([^"]*)"', line)
        if m:
            rows.append({
                "dev": m.group(1),
                "size": int(m.group(2), 16),
                "erase": int(m.group(3), 16),
                "name": m.group(4),
            })
    return rows


def parse_sysfs_mtd(sec: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for line in sec.splitlines():
        m = re.match(r"^SYSFS_MTD\s+dev=(mtd\d+)\s+name=(.*?)\s+size=(\d+)\s+erasesize=(\d+)\s*$", line.strip())
        if not m:
            continue
        out[m.group(1)] = {
            "dev": m.group(1), "name": m.group(2),
            "size": int(m.group(3)), "erase": int(m.group(4)),
        }
    return out


def parse_physical_nand(sec: str) -> tuple[int | None, str]:
    candidates: list[int] = []
    for line in sec.splitlines():
        low = line.lower()
        if "nand" not in low:
            continue
        for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(mib|mb|gib|gb)\b", line, re.I):
            value = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ("mib", "mb"):
                size = int(round(value * 1024 * 1024))
            else:
                size = int(round(value * 1024 * 1024 * 1024))
            if size >= 16 * 1024 * 1024:
                candidates.append(size)
    if not candidates:
        return None, "not observed in NAND driver log"
    return max(candidates), "NAND driver/dmesg"


def detect_layout(rows: list[dict[str, object]]) -> tuple[str, str]:
    sizes = {int(str(r["dev"])[3:]): int(r["size"]) for r in rows}
    for label, layout in MD_SLOT_LAYOUTS:
        if all(sizes.get(n) == size for n, size in layout.items()):
            return "md", label
    for label, layout in MF_SLOT_LAYOUTS:
        if all(sizes.get(n) == size for n, size in layout.items()):
            return "mf", label

    master = (sizes.get(2), sizes.get(3))
    slave = (sizes.get(4), sizes.get(5))
    if None in master or None in slave:
        return "unknown", "UNKNOWN"
    if slave == STOCK_SLOT_CANONICAL_PAIR:
        orientation, pair = "A", master
    elif master == STOCK_SLOT_CANONICAL_PAIR:
        orientation, pair = "A-MIRROR", slave
    else:
        return "unknown", "UNKNOWN"
    image, partition = pair
    if image <= 0 or partition <= image or partition % STOCK_SLOT_PARTITION_GRANULARITY:
        return "unknown", "UNKNOWN"
    matched = {
        family
        for family, refs in STOCK_SLOT_REVISION_REFERENCE.items()
        for ref_image, ref_partition in refs
        if abs(image - ref_image) <= STOCK_SLOT_IMAGE_TOLERANCE
        and abs(partition - ref_partition) <= STOCK_SLOT_PARTITION_TOLERANCE
    }
    if len(matched) != 1:
        return "unknown", "UNKNOWN"
    family = next(iter(matched))
    return family, f"{family.upper()}-{orientation}-REV"

def parse_tools(sec: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for line in sec.splitlines():
        m = re.match(r"^AUDIT_TOOL\s+name=([^\s]+)\s+present=([01])(?:\s|$)", line.strip())
        if m:
            out[m.group(1)] = m.group(2) == "1"
    return out


def parse_upgrade(sec: str) -> dict[str, object]:
    files: list[str] = []
    binaries: list[str] = []
    hits: list[str] = []
    meta: list[str] = []
    strings: list[str] = []
    text_lines: list[str] = []
    for raw in sec.splitlines():
        line = raw.strip()
        if line.startswith("AUDIT_FILE path="):
            files.append(line[len("AUDIT_FILE path="):])
        elif line.startswith("AUDIT_BINARY path="):
            binaries.append(line[len("AUDIT_BINARY path="):])
        elif line.startswith("AUDIT_HIT path="):
            hits.append(line[len("AUDIT_HIT "):])
        elif line.startswith("AUDIT_META path="):
            meta.append(line[len("AUDIT_META "):])
        elif line.startswith("AUDIT_STRING path="):
            strings.append(line[len("AUDIT_STRING "):])
        elif line.startswith("AUDIT_TEXT path="):
            text_lines.append(line[len("AUDIT_TEXT "):])
    return {"files": files, "binaries": binaries, "hits": hits, "meta": meta, "strings": strings, "text": text_lines}


def build_profile(text: str) -> dict[str, object]:
    text = text.replace("\x00", "")
    secs = split_sections(text)
    evidence = parse_kv(secs.get("CAPABILITY-EVIDENCE", ""))
    root_kv = parse_kv(secs.get("ROOT-STATUS", ""))
    ident = parse_identity(secs.get("IDENTITY", ""))
    if not ident.get("model") and evidence.get("web_model") not in (None, "", "unknown"):
        ident["model"] = evidence["web_model"]
    if not ident.get("soc") and evidence.get("web_chipset") not in (None, "", "unknown"):
        ident["soc"] = evidence["web_chipset"]
    mtd = parse_mtd(secs.get("MTD", ""))
    sysfs = parse_sysfs_mtd(secs.get("MTD", ""))
    tools = parse_tools(secs.get("READ-PRIMITIVES", ""))
    upgrade = parse_upgrade(secs.get("STOCK-UPGRADE-MECHANISM", ""))
    physical_nand, physical_source = parse_physical_nand(secs.get("NAND-UBI", ""))

    by_dev = {str(r["dev"]): r for r in mtd}
    span_row = by_dev.get("mtd16")
    if span_row is None:
        candidates = [r for r in mtd if str(r["name"]).lower() == "all_flash"]
        if candidates:
            span_row = max(candidates, key=lambda r: int(str(r["dev"])[3:]))
    restore_span = int(span_row["size"]) if span_row else None
    restore_span_source = f"{span_row['dev']}:/proc/mtd" if span_row else "not observed"
    erase = int(span_row["erase"]) if span_row else None

    family, variant = detect_layout(mtd)

    required_cross = ["mtd2", "mtd3", "mtd4", "mtd5"]
    if span_row:
        required_cross.append(str(span_row["dev"]))
    mismatch: list[str] = []
    missing: list[str] = []
    for dev in required_cross:
        p = by_dev.get(dev)
        s = sysfs.get(dev)
        if p is None or s is None:
            missing.append(dev)
            continue
        if int(p["size"]) != int(s["size"]) or int(p["erase"]) != int(s["erase"]):
            mismatch.append(dev)
    if mismatch:
        mtd_consistency = "FAIL"
    elif missing:
        mtd_consistency = "UNKNOWN"
    else:
        mtd_consistency = "PASS"

    root_uid_raw = evidence.get("root_uid", root_kv.get("AUDIT_ROOT_UID", ""))
    root_rc_raw = evidence.get("root_probe_rc", root_kv.get("AUDIT_ROOT_RC", ""))
    root_uid = int(root_uid_raw) if root_uid_raw.isdigit() else None
    root_rc = int(root_rc_raw) if root_rc_raw.isdigit() else None
    stock_root = root_uid == 0 and root_rc == 0

    web_creds = evidence.get("web_creds") == "verified"
    telnet_ok = evidence.get("transport") == "telnet" and evidence.get("telnet") == "verified"
    read_ready = all(tools.get(x, False) for x in ("cat", "gzip", "sha256sum"))
    mtd_sec = secs.get("MTD", "")
    mf_ro_ready = all(re.search(rf"/dev/mtd{n}ro\b", mtd_sec) for n in range(17)) if family == "mf" else True
    mf_transport_ready = tools.get("tftp", False) if family == "mf" else True
    backup_ready = stock_root and mtd_consistency == "PASS" and family in ("md", "mf") and restore_span is not None and read_ready and mf_ro_ready and mf_transport_ready

    if family == "md":
        full_backup_cap = "YES - restore-grade MD backend available" if backup_ready else "BLOCKED/UNKNOWN"
        ram_cap = "YES - HW CONFIRMED MD transition path" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        ubi_format_cap = "READY - RAM stage exact physical target gate" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        ubi_write_cap = "READY - canonical UBI volumes + readback" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        bootloader_replace_cap = "EXPERIMENTAL - tcboot research; not enabled"
        permanent_cap = "READY - HW-confirmed MD path; full backup + exact target gates mandatory" if backup_ready else "BLOCKED/UNKNOWN"
        uart_cap = "YES - HW CONFIRMED"
    elif family == "mf":
        full_backup_cap = "YES - restore-grade MF backend available" if backup_ready else "BLOCKED/UNKNOWN"
        ram_cap = "YES - HW CONFIRMED AN7583 transition path" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        ubi_format_cap = "READY - RAM stage exact physical target gate" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        ubi_write_cap = "READY - canonical UBI volumes + readback" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        bootloader_replace_cap = "READY - pinned MF BL2 written last" if stock_root and mtd_consistency == "PASS" else "BLOCKED/UNKNOWN"
        permanent_cap = "READY - HW-confirmed MF path; full backup + exact target gates mandatory" if backup_ready else "BLOCKED/UNKNOWN"
        uart_cap = "YES - HW CONFIRMED full stock restore"
    else:
        full_backup_cap = "BLOCKED/UNKNOWN"
        ram_cap = "UNKNOWN"
        ubi_format_cap = "BLOCKED/UNKNOWN"
        ubi_write_cap = "BLOCKED/UNKNOWN"
        bootloader_replace_cap = "BLOCKED/UNKNOWN"
        permanent_cap = "BLOCKED/UNKNOWN"
        uart_cap = "UNKNOWN"

    caps = {
        "CAP_WEB_CREDS": "YES" if web_creds else "UNKNOWN",
        "CAP_TELNET": "YES" if telnet_ok else "UNKNOWN",
        "CAP_STOCK_ROOT": "YES" if stock_root else ("NO" if root_uid is not None else "UNKNOWN"),
        "CAP_FULL_BACKUP": full_backup_cap,
        "CAP_RAM_OPENWRT": ram_cap,
        "CAP_UBI_FORMAT": ubi_format_cap,
        "CAP_UBI_VOLUME_WRITE": ubi_write_cap,
        "CAP_BOOTLOADER_REPLACE": bootloader_replace_cap,
        "CAP_PERMANENT_INSTALL": permanent_cap,
        "CAP_UART_RECOVERY": uart_cap,
    }

    return {
        "ident": ident,
        "evidence": evidence,
        "root_uid": root_uid,
        "root_rc": root_rc,
        "root_via": evidence.get("root_via", "unknown"),
        "mtd": mtd,
        "sysfs": sysfs,
        "mtd_consistency": mtd_consistency,
        "mtd_mismatch": mismatch,
        "mtd_missing": missing,
        "physical_nand": physical_nand,
        "physical_source": physical_source,
        "restore_span": restore_span,
        "restore_span_source": restore_span_source,
        "erase": erase,
        "family": family,
        "variant": variant,
        "tools": tools,
        "upgrade": upgrade,
        "caps": caps,
    }


def hx(value: int | None) -> str:
    return f"0x{value:08X}" if isinstance(value, int) else "????????"


def render(prof: dict[str, object]) -> str:
    ident = prof["ident"]
    assert isinstance(ident, dict)
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("  MD/MF STOCK AUDIT - DATA-DERIVED PROFILE")
    lines.append("=" * 64)
    lines.append(f"  Model                  {ident.get('model', '?')}")
    lines.append(f"  SoC                    {ident.get('soc', '?')}")
    lines.append(f"  Board                  {ident.get('board', '?')}")
    lines.append(f"  Kernel                 {ident.get('kernel', '?')}")
    lines.append(f"  MAC                    {ident.get('mac', '?')}")
    lines.append(f"  Detected family        {prof['family']}")
    lines.append(f"  Stock slot variant     {prof['variant']}")
    lines.append("")
    uid = prof["root_uid"]
    rc = prof["root_rc"]
    if uid == 0 and rc == 0:
        lines.append(f"  Stock root             YES via {prof['root_via']}")
    elif uid is None:
        lines.append("  Stock root             UNKNOWN")
    else:
        lines.append(f"  Stock root             NO (uid={uid}, rc={rc})")
    lines.append("")
    phys = prof["physical_nand"]
    span = prof["restore_span"]
    lines.append(f"  Physical NAND          {hx(phys)}" + (f" = {phys/1048576:.3f} MiB" if isinstance(phys, int) else ""))
    lines.append(f"  Physical NAND source   {prof['physical_source']}")
    lines.append(f"  Stock restore span     {hx(span)}" + (f" = {span/1048576:.3f} MiB" if isinstance(span, int) else ""))
    lines.append(f"  Restore span source    {prof['restore_span_source']}")
    if isinstance(span, int):
        if span == HISTORICAL_RESTORE_SPAN:
            lines.append("  Historical comparison  == 0x0EBA0000")
        else:
            lines.append(f"  Historical comparison  != 0x{HISTORICAL_RESTORE_SPAN:08X} - family-specific review required")
    lines.append(f"  Erase size             {hx(prof['erase'])}")
    lines.append(f"  /proc vs sysfs MTD     {prof['mtd_consistency']}")
    if prof["mtd_mismatch"]:
        lines.append("  MTD mismatches         " + ", ".join(prof["mtd_mismatch"]))
    if prof["mtd_missing"]:
        lines.append("  MTD cross-check gaps   " + ", ".join(prof["mtd_missing"]))
    if isinstance(phys, int) and isinstance(span, int) and phys >= span:
        tail = phys - span
        lines.append(f"  Outside restore span   {hx(tail)} = {tail/1048576:.3f} MiB (investigate BMT/spare/reserved policy)")
    lines.append("")
    lines.append("  CAPABILITIES")
    caps = prof["caps"]
    assert isinstance(caps, dict)
    for key, value in caps.items():
        lines.append(f"    {key:<24} {value}")
    lines.append("")
    upg = prof["upgrade"]
    assert isinstance(upg, dict)
    lines.append("  STOCK UPGRADE MECHANISM")
    lines.append(f"    candidate files:      {len(upg['files'])}")
    lines.append(f"    binary candidates:    {len(upg['binaries'])}")
    lines.append(f"    explicit write hits:  {len(upg['hits'])}")
    lines.append(f"    metadata records:     {len(upg['meta'])}")
    lines.append(f"    binary strings:       {len(upg['strings'])}")
    lines.append(f"    text lines captured:  {len(upg['text'])}")
    for hit in upg["hits"][:30]:
        lines.append(f"      {hit}")
    lines.append("")
    lines.append("  MTD MAP")
    for row in prof["mtd"]:
        lines.append(f"    {row['dev']:<6} {hx(row['size'])} erase {hx(row['erase'])}  {row['name']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        text = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    else:
        text = sys.stdin.read()
    print(render(build_profile(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
