#!/usr/bin/env python3
"""Rebuild MedveFlasher MD transition/recovery payloads from a pinned OpenWrt UBI recovery FIT.

Inputs are the exact OpenWrt snapshot artifacts pinned in OPENWRT_BASELINE.json.
The production sysupgrade and production BL31+U-Boot FIP remain byte-identical to
those inputs.  Transition/recovery initramfs images are derived locally:

* Linux/kernel/modules come from the pinned snapshot recovery FIT.
* Transition keeps a 9 MiB boot window because current snapshot FITs no longer fit
  the historical 8 MiB window after MedveFlasher installer payloads are embedded.
* Only LuCI web-root files are removed from transition initramfs; transition does
  not use LuCI. Kernel modules and the rest of the snapshot userspace are retained.
* LAN1/2.5G is disabled for transition/recovery control-plane use.
* Raw stock RI is exposed read-only for pre-format MAC NVMEM.
* BL2 is writable only in these transient transition/recovery DTs.
* The transition installer embeds the pinned production preloader and production
  Fudan-capable FIP and uses NAND identity for diagnostics only.
* Recovery embeds pinned nokia-tftp/nokia-scp and blank-root Dropbear -B support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
REPO = DATA.parent
NETSRC = DATA / "recovery" / "transition-network-source"
CLISRC = DATA / "recovery" / "recovery-clients-source"
sys.path.insert(0, str(NETSRC))
from patch_transition_network import Fdt, Node, cstr, hash_image  # type: ignore
sys.path.insert(0, str(CLISRC))
from patch_recovery_clients import (  # type: ignore
    Entry, DROPBEAR_NEW, DROPBEAR_OLD, RECLAIM, build_entry, find_archive, new_entry,
)

WINDOW = 0x900000
EXPECTED = {
    "source_initramfs": "ee88a11e1ff7f232afb8eda38870e65f6625e0d95b97c70ccbe59098bd1ba05a",
    "preloader": "ed42a1d2f2cfca1af08c0ba935a8311260954c7424301d1ff99166f9e10c2f30",
    "production_fip": "8625d786cdded8ce2e5de27abc1ead7b1546e058ee055089e5c9780518f540f1",
    "sysupgrade": "b0556660c1939a9dc1ebbce5b4a3b3c8318c76eacae04de53ce047b43af8d867",
    "tftp": "2b6bbc51975e22f420565c42363821eb362936136b03f70a2a0cedee99c1641a",
    "scp": "232a4ba7f8ae62922815bb12503fd7d09c3b4f40929d130475e467f0a597ac89",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_sha(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    got = sha256(data)
    if got != expected:
        raise SystemExit(f"ERROR: {path}: SHA256 {got} != {expected}")
    return data


def u32(n: int) -> bytes:
    return struct.pack(">I", n)


def patch_transient_dtb(blob: bytes, kind: str) -> bytes:
    dt = Fdt(blob)
    parts = dt.node("/soc/spi@1fa10000/nand@0/partitions")
    bl2 = dt.node("/soc/spi@1fa10000/nand@0/partitions/partition@0")
    ubi = dt.node("/soc/spi@1fa10000/nand@0/partitions/partition@20000")
    eth1 = dt.node("/soc/ethernet@1fb50000/ethernet@1")
    eth4 = dt.node("/soc/ethernet@1fb50000/ethernet@4")

    # Transient-only physical layout. all_flash stays read-only; BL2 is the only
    # raw boot partition that the installer/recovery path may write.
    bl2.delete("read-only")
    ubi.set("label", b"ibu\0")
    ubi.delete("compatible")  # do not auto-attach a stock/nonexistent UBI layout

    # Recreate the raw stock RI NVMEM slice deterministically.
    parts.children = [c for c in parts.children if c.name != "partition@5200000"]
    max_phandle = 0
    for _path, n in dt.walk():
        ph = n.get("phandle")
        if ph is not None and len(ph) == 4:
            max_phandle = max(max_phandle, struct.unpack(">I", ph)[0])
    mac_phandle = max_phandle + 1
    mac = Node("macaddr@3e", props=[
        ("compatible", b"mac-base\0"),
        ("reg", struct.pack(">II", 0x3E, 6)),
        ("#nvmem-cell-cells", u32(1)),
        ("phandle", u32(mac_phandle)),
    ])
    layout = Node("nvmem-layout", props=[
        ("compatible", b"fixed-layout\0"),
        ("#address-cells", u32(1)),
        ("#size-cells", u32(1)),
    ], children=[mac])
    ri = Node("partition@5200000", props=[
        ("label", b"ri-stock\0"),
        ("reg", struct.pack(">II", 0x05200000, 0x00040000)),
        ("read-only", b""),
    ], children=[layout])
    parts.children.append(ri)
    eth1.set("nvmem-cell-names", b"mac-address\0")
    eth1.set("nvmem-cells", u32(mac_phandle) + u32(0))

    # Recovery/control plane never uses the unstable 2.5G/LAN1 path.
    eth4.set("status", b"disabled\0")
    eth4.delete("openwrt,netdev-name")
    eth4.delete("nvmem-cell-names")
    eth4.delete("nvmem-cells")

    root = dt.node("/")
    if kind == "transition":
        root.set("model", b"Nokia XG-040G-MD (MedveFlasher rc32 transition raw RI)\0")
    else:
        root.set("model", b"Nokia XG-040G-MD (MedveFlasher rc32 stock recovery)\0")

    out = dt.build()
    check = Fdt(out)
    if check.node("/soc/spi@1fa10000/nand@0/partitions/partition@0").get("read-only") is not None:
        raise ValueError("BL2 remained read-only")
    if cstr(check.node("/soc/spi@1fa10000/nand@0/partitions/partition@20000").get("label")) != "ibu":
        raise ValueError("transient UBI span label mismatch")
    if cstr(check.node("/soc/ethernet@1fb50000/ethernet@4").get("status")) != "disabled":
        raise ValueError("LAN1/2.5G disable failed")
    return out


def load_runtime_entries(kind: str) -> tuple[dict[str, bytes], dict[str, int]]:
    root = HERE / f"md-transition-runtime-{kind}"
    meta = json.loads((root / "entries.json").read_text(encoding="utf-8"))
    data: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    for name, info in meta.items():
        data[name] = (root / name).read_bytes()
        modes[name] = int(info["mode"])
    ctl = DATA / "recovery" / "transition-control-source"
    if kind == "auto":
        data["usr/sbin/nokia-ubi-installer"] = (ctl / "shipped-md-nokia-ubi-installer.sh").read_bytes()
        modes["usr/sbin/nokia-ubi-installer"] = 0o100755
        data["usr/sbin/nokia-ubi-autoflash"] = (ctl / "shipped-md-nokia-ubi-autoflash.sh").read_bytes()
        modes["usr/sbin/nokia-ubi-autoflash"] = 0o100755
        data["installer/boot-autoflash.sh"] = (ctl / "shipped-md-boot-autoflash.sh").read_bytes()
        modes["installer/boot-autoflash.sh"] = 0o100755
    else:
        data["usr/sbin/nokia-ubi-installer"] = (ctl / "shipped-md-manual-nokia-ubi-installer.sh").read_bytes()
        modes["usr/sbin/nokia-ubi-installer"] = 0o100755
        data["usr/sbin/nokia-ubi-finish"] = (ctl / "shipped-md-manual-nokia-ubi-finish.sh").read_bytes()
        modes["usr/sbin/nokia-ubi-finish"] = 0o100755
        data["etc/init.d/nokia-manual-ready"] = (ctl / "shipped-md-manual-ready.sh").read_bytes()
        modes["etc/init.d/nokia-manual-ready"] = 0o100755
    return data, modes


def rebuild_cpio(raw_image: bytes, replacements: dict[str, tuple[bytes, int]], *, transition: bool) -> tuple[bytes, dict]:
    start, end, entries = find_archive(raw_image)
    next_nonzero = end
    while next_nonzero < len(raw_image) and raw_image[next_nonzero] == 0:
        next_nonzero += 1
    capacity = next_nonzero - start
    names = {e.name for e in entries}
    if "etc/board.d/02_network" not in names or "etc/init.d/dropbear" not in names:
        raise ValueError("fresh initramfs lacks required network/auth files")
    shadow = next(e.data for e in entries if e.name == "etc/shadow")
    if not shadow.startswith(b"root:::"):
        raise ValueError("transient root account is not intentionally blank")

    maxino = max(e.vals[0] for e in entries)
    remove_names = set(replacements)
    rebuilt: list[Entry] = []
    removed: list[tuple[str, int]] = []
    for e in entries:
        if e.name == "TRAILER!!!" or e.name in remove_names:
            continue
        if transition and e.name.startswith("www/"):
            # Transition exposes only generated status/log files under /www.
            # LuCI static content is not used and provides the space needed for
            # the embedded production preloader/FIP without dropping kmods.
            removed.append((e.name, len(e.data)))
            continue
        if not transition and e.name in RECLAIM:
            # Existing recovery policy: reclaim APK metadata only.
            removed.append((e.name, len(e.data)))
            continue
        if e.name == "etc/init.d/dropbear" and DROPBEAR_NEW not in e.data:
            if e.data.count(DROPBEAR_OLD) != 1:
                raise ValueError("unexpected Dropbear command layout")
            e = Entry(e.magic, e.vals[:], e.name, e.data.replace(DROPBEAR_OLD, DROPBEAR_NEW, 1))
        rebuilt.append(e)

    # Parent directory for embedded transition payloads does not exist upstream.
    if transition and "installer" not in {e.name for e in rebuilt}:
        maxino += 1
        rebuilt.append(new_entry("installer", b"", 0o040755, maxino))

    for name, (data, mode) in replacements.items():
        maxino += 1
        rebuilt.append(new_entry(name, data, mode, maxino))
    maxino += 1
    rebuilt.append(new_entry("TRAILER!!!", b"", 0, maxino))

    archive = b"".join(build_entry(e) for e in rebuilt)
    if len(archive) > capacity:
        raise ValueError(f"rebuilt cpio {len(archive)} exceeds fixed Image window {capacity}")
    out = bytearray(raw_image)
    out[start:next_nonzero] = archive + b"\0" * (capacity - len(archive))
    if out[:start] != raw_image[:start] or out[next_nonzero:] != raw_image[next_nonzero:]:
        raise AssertionError("linked Image bytes outside initramfs moved")
    return bytes(out), {
        "cpio_start": start,
        "cpio_end": next_nonzero,
        "cpio_capacity": capacity,
        "cpio_archive_size": len(archive),
        "removed_count": len(removed),
        "removed_data_bytes": sum(n for _p, n in removed),
    }


def compress_image(raw: bytes) -> bytes:
    filters = [{"id": lzma.FILTER_LZMA1, "dict_size": 4 * 1024 * 1024, "lc": 3, "lp": 0, "pb": 2,
                "mode": lzma.MODE_NORMAL, "nice_len": 64, "mf": lzma.MF_BT4, "depth": 0}]
    return lzma.compress(raw, format=lzma.FORMAT_ALONE, filters=filters)


def build_fit(source_fit_file: bytes, replacements: dict[str, tuple[bytes, int]], *, kind: str, version: str) -> tuple[bytes, dict]:
    fit_size = struct.unpack(">I", source_fit_file[4:8])[0]
    fit = Fdt(source_fit_file[:fit_size])
    kernel = fit.node("/images/kernel-1")
    fdt = fit.node("/images/fdt-1")
    if cstr(kernel.get("compression")) != "lzma":
        raise ValueError("expected LZMA kernel")
    old_kernel = kernel.get("data")
    old_dtb = fdt.get("data")
    assert old_kernel is not None and old_dtb is not None
    raw = lzma.decompress(old_kernel, format=lzma.FORMAT_ALONE)
    raw2, cpio_report = rebuild_cpio(raw, replacements, transition=(kind in ("auto", "manual")))
    kernel.set("data", compress_image(raw2))
    fdt.set("data", patch_transient_dtb(old_dtb, "transition" if kind in ("auto", "manual") else "recovery"))
    if kind in ("auto", "manual"):
        fit.node("/").set("description", f"Nokia Router MedveFlasher {version} MD {kind} transition".encode() + b"\0")
        kernel.set("description", f"ARM64 OpenWrt Linux-6.18.44 MedveFlasher MD {kind} transition".encode() + b"\0")
        fdt.set("description", b"Nokia XG-040G-MD transition DT raw RI; LAN1/2.5G disabled\0")
    else:
        fit.node("/").set("description", f"Nokia XG-040G-MD MedveFlasher {version} stock recovery".encode() + b"\0")
        kernel.set("description", b"ARM64 OpenWrt Linux-6.18.44 MedveFlasher stock recovery\0")
        fdt.set("description", b"Nokia XG-040G-MD recovery DT all_flash RO; BL2 writable; raw RI; LAN1/2.5G disabled\0")
    hash_image(kernel)
    hash_image(fdt)
    out = fit.build()
    # Reparse output and hash-check image nodes.
    vf = Fdt(out)
    for path in ("/images/kernel-1", "/images/fdt-1"):
        n = vf.node(path)
        data = n.get("data")
        assert data is not None
        for h in n.children:
            algo = cstr(h.get("algo"))
            val = h.get("value")
            if algo == "sha1" and val != hashlib.sha1(data).digest():
                raise AssertionError(f"{path} sha1 mismatch")
            if algo == "crc32":
                import zlib
                if val != struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF):
                    raise AssertionError(f"{path} crc32 mismatch")
    report = {
        **cpio_report,
        "source_fit_size": fit_size,
        "output_fit_size": len(out),
        "source_kernel_lzma_size": len(old_kernel),
        "output_kernel_lzma_size": len(vf.node("/images/kernel-1").get("data") or b""),
        "output_fit_sha256": sha256(out),
    }
    return out, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-initramfs", type=Path, required=True)
    ap.add_argument("--preloader", type=Path, required=True)
    ap.add_argument("--production-fip", type=Path, required=True)
    ap.add_argument("--sysupgrade", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, default=Path("/tmp/medve-md-payloads"))
    ap.add_argument("--version", default="1.0.0-rc32")
    ns = ap.parse_args()

    source = require_sha(ns.source_initramfs, EXPECTED["source_initramfs"])
    preloader = require_sha(ns.preloader, EXPECTED["preloader"])
    production_fip = require_sha(ns.production_fip, EXPECTED["production_fip"])
    sysupgrade = require_sha(ns.sysupgrade, EXPECTED["sysupgrade"])
    clients = DATA / "recovery" / "recovery-clients-bin"
    tftp = require_sha(clients / "nokia-tftp", EXPECTED["tftp"])
    scp = require_sha(clients / "nokia-scp", EXPECTED["scp"])
    network_template = (NETSRC / "shipped-md-02_network.sh").read_bytes()

    common = {
        "etc/board.d/02_network": (network_template, 0o100755),
        "usr/bin/nokia-tftp": (tftp, 0o100755),
        "usr/bin/tftp": (b"nokia-tftp", 0o120777),
        "usr/bin/nokia-scp": (scp, 0o100755),
        "usr/bin/scp": (b"nokia-scp", 0o120777),
    }

    reports = {}
    outputs = {}
    for kind in ("auto", "manual"):
        data, modes = load_runtime_entries(kind)
        # Refresh the embedded transition manifest at build time.
        if kind == "auto":
            data["installer/MANIFEST.txt"] = (
                f"version={ns.version}\nfamily=MD\nboard=nokia,xg-040g-md-ubi\n"
                "autoflash=enabled\nautoflash_service=/etc/init.d/nokia-autoflash\n"
                "autoflash_worker=/usr/sbin/nokia-ubi-autoflash\n"
                "transition_window=0x900000\nembedded_openwrt_sysupgrade=enabled\n"
                "embedded_openwrt_sysupgrade_offset=0x9c0000\n"
                f"embedded_openwrt_sysupgrade_size={len(sysupgrade)}\n"
                f"embedded_openwrt_sysupgrade_sha256={sha256(sysupgrade)}\n"
                f"production_fip_sha256={sha256(production_fip)}\n"
                "nand_identity=informational\nsupported_nand=SkyHigh+Fudan\n"
                "destructive_gate=board+geometry+MTD/UBI capability+payload hashes+readback\n"
            ).encode("ascii")
        else:
            data["installer/MANIFEST.txt"] = (
                f"version={ns.version}-manual\nfamily=MD\nboard=nokia,xg-040g-md-ubi\n"
                "autoflash=disabled\ntransition_window=0x900000\n"
                "manual_ready_marker=/tmp/NOKIA_MANUAL_TRANSITION_READY\n"
                "custom_sysupgrade_path=/tmp/nokia-custom-sysupgrade.itb\n"
                "custom_sysupgrade_sha=/tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256\n"
                f"default_sysupgrade_sha256={sha256(sysupgrade)}\n"
                f"production_fip_sha256={sha256(production_fip)}\n"
                "nand_identity=informational\nsupported_nand=SkyHigh+Fudan\n"
            ).encode("ascii")
        reps = dict(common)
        reps.update({name: (blob, modes[name]) for name, blob in data.items()})
        reps["installer/openwrt-airoha-an7581-nokia_xg-040g-md-ubi-preloader.bin"] = (preloader, 0o100600)
        reps["installer/openwrt-airoha-an7581-nokia_xg-040g-md-ubi-bl31-uboot.fip"] = (production_fip, 0o100600)
        fit, rep = build_fit(source, reps, kind=kind, version=ns.version)
        if len(fit) > WINDOW:
            raise SystemExit(f"ERROR: {kind} transition FIT {len(fit)} exceeds 9 MiB window")
        padded = fit + b"\0" * (WINDOW - len(fit))
        if kind == "auto":
            padded += sysupgrade
        outputs[kind] = padded
        rep.update({"bundle_size": len(padded), "bundle_sha256": sha256(padded), "window_size": WINDOW,
                    "window_sha256": sha256(padded[:WINDOW]),
                    "production_offset_in_bundle": WINDOW,
                    "production_physical_offset_in_nand": 0x0C0000 + WINDOW,
                    "production_size": len(sysupgrade) if kind == "auto" else 0,
                    "production_sha256": sha256(sysupgrade) if kind == "auto" else None})
        reports[kind] = rep

    # Standalone stock recovery: no installer/FIP, but transport clients and safe DT/network policy.
    recovery_fit, recovery_report = build_fit(source, common, kind="recovery", version=ns.version)
    reports["recovery"] = recovery_report
    outputs["recovery"] = recovery_fit

    ns.output_dir.mkdir(parents=True, exist_ok=True)
    (ns.output_dir / "nokia-xg-040g-md-an7581-transition-auto.bin").write_bytes(outputs["auto"])
    (ns.output_dir / "nokia-xg-040g-md-an7581-transition-manual.bin").write_bytes(outputs["manual"])
    (ns.output_dir / "nokia-xg-040g-md-an7581-stock-recovery-initramfs.itb").write_bytes(outputs["recovery"])
    (ns.output_dir / "build-report.json").write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n", encoding="ascii")
    for name, blob in outputs.items():
        print(f"{name}: size={len(blob)} sha256={sha256(blob)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
