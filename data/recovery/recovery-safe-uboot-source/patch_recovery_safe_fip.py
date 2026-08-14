#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import lzma
import struct
import subprocess
import tempfile
import shutil
from pathlib import Path

FIP_MAGIC = 0xAA640001
SAFE_MARKER = b"medveflasher_recovery_safe=rc18"
SAFE_ENTRIES = (
    b"bootdelay=-1",
    b"bootcmd=echo RECOVERY_SAFE_RC18",
    b"preboot=echo RECOVERY_SAFE_RC18",
    SAFE_MARKER,
)
ENV_BACKEND_REPLACEMENTS = {
    b"ubootenv": b"RCSAFE00",
    b"ubootenv2": b"RCSAFE002",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_fip(data: bytes):
    if len(data) < 96:
        raise ValueError("FIP too small")
    magic, serial, flags = struct.unpack_from("<IIQ", data, 0)
    if magic != FIP_MAGIC:
        raise ValueError(f"unexpected FIP magic 0x{magic:08x}")
    entries = []
    pos = 16
    while pos + 40 <= len(data):
        uuid = data[pos:pos + 16]
        offset, size, eflags = struct.unpack_from("<QQQ", data, pos + 16)
        if uuid == b"\x00" * 16:
            return serial, flags, entries, pos, offset
        if offset + size > len(data):
            raise ValueError("FIP entry exceeds file")
        entries.append((uuid, offset, size, eflags))
        pos += 40
    raise ValueError("missing FIP terminator")


def lzma_decode(payload: bytes) -> bytes:
    if len(payload) < 13 or payload[0] != 0x5D:
        raise ValueError("expected LZMA-alone payload")
    return lzma.decompress(payload, format=lzma.FORMAT_ALONE)


def lzma_encode(raw: bytes, original: bytes) -> bytes:
    """Encode the Airoha LZMA-Alone form: known size, NO EOPM.

    Python FORMAT_ALONE always emits an end marker. Rewriting its size field
    produced the first RC18 FIPs, but strict liblzma builds correctly reject
    that mixed representation as corrupt. Build through LZMA1EXT instead.
    """
    if original[0] != 0x5D:
        raise ValueError("unsupported LZMA properties")
    dict_size = struct.unpack_from("<I", original, 1)[0]
    source_dir = Path(__file__).resolve().parent
    c_source = source_dir / "lzma1ext_noeopm.c"
    if not c_source.is_file():
        raise ValueError("missing lzma1ext_noeopm.c")
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        raise ValueError("C compiler is required to rebuild RECOVERY_SAFE FIP")
    with tempfile.TemporaryDirectory(prefix="mf-lzma1ext-") as tmp:
        tmp = Path(tmp)
        helper = tmp / "lzma1ext_noeopm"
        raw_path = tmp / "bl33.raw"
        out_path = tmp / "bl33.lzma"
        raw_path.write_bytes(raw)
        subprocess.run(
            [cc, "-O2", "-Wall", "-Wextra", str(c_source), "-llzma", "-o", str(helper)],
            check=True,
        )
        subprocess.run(
            [str(helper), str(raw_path), str(out_path), hex(dict_size)],
            check=True,
        )
        out = out_path.read_bytes()
    if out[:1] != b"\x5d" or struct.unpack_from("<I", out, 1)[0] != dict_size:
        raise ValueError("LZMA1EXT output header mismatch")
    if struct.unpack_from("<Q", out, 5)[0] != len(raw):
        raise ValueError("LZMA1EXT output size header mismatch")
    # A generic LZMA-Alone decoder must accept this exact known-size/no-EOPM form.
    if lzma_decode(out) != raw:
        raise ValueError("LZMA1EXT no-EOPM round-trip verification failed")
    return out


def find_default_env(raw: bytes) -> tuple[int, int]:
    candidates = []
    for needle in (b"ipaddr=192.168.1.1\x00", b"loadaddr=0x81800000\x00"):
        start = raw.find(needle)
        if start >= 0:
            end = raw.find(b"\x00\x00", start)
            if end >= 0:
                candidates.append((start, end + 2))
    if not candidates:
        raise ValueError("compiled default environment not found")
    # The recovery U-Boot has one relevant compiled environment block.
    start, end = max(candidates, key=lambda x: x[1] - x[0])
    return start, end


def patch_raw_uboot(raw: bytes) -> tuple[bytes, dict]:
    buf = bytearray(raw)
    env_start, env_end = find_default_env(raw)
    old_env = raw[env_start:env_end]
    new_env = b"\x00".join(SAFE_ENTRIES) + b"\x00\x00"
    if len(new_env) > len(old_env):
        raise ValueError(f"safe environment {len(new_env)} exceeds slot {len(old_env)}")
    buf[env_start:env_end] = new_env + b"\x00" * (len(old_env) - len(new_env))

    patched_backend = {}
    for old, new in ENV_BACKEND_REPLACEMENTS.items():
        # Patch only env-driver strings that occur before the compiled default
        # environment.  Do not touch any historical helper text inside the env
        # slot (the slot is replaced wholesale above).
        positions = []
        search = 0
        while True:
            pos = raw.find(old + b"\x00", search, env_start)
            if pos < 0:
                break
            positions.append(pos)
            search = pos + 1
        if len(positions) != 1:
            raise ValueError(f"expected one backend {old!r} before env, found {positions}")
        pos = positions[0]
        if len(old) != len(new):
            raise ValueError("backend replacement must be size preserving")
        buf[pos:pos + len(old)] = new
        patched_backend[old.decode()] = {"offset": pos, "replacement": new.decode()}

    out = bytes(buf)
    checks = {
        "env_start": env_start,
        "env_slot_size": env_end - env_start,
        "marker_count": out.count(SAFE_MARKER),
        "bootdelay_safe_count": out.count(b"bootdelay=-1"),
        "dangerous_bootcmd_count": out.count(b"bootcmd=run check_buttons ; run boot_ubi"),
        "dangerous_ubi_format_count": out.count(b"ubi_format=ubi detach ; mtd erase ubi"),
        "backend": patched_backend,
    }
    if checks["marker_count"] != 1 or checks["bootdelay_safe_count"] != 1:
        raise ValueError(f"safe marker verification failed: {checks}")
    if checks["dangerous_bootcmd_count"] != 0 or checks["dangerous_ubi_format_count"] != 0:
        raise ValueError(f"dangerous default env survived: {checks}")
    if b"RCSAFE00\x00" not in out or b"RCSAFE002\x00" not in out:
        raise ValueError("persistent environment backend names were not neutralized")
    return out, checks


def rebuild_fip(source: bytes) -> tuple[bytes, dict]:
    serial, flags, entries, term_pos, old_end = parse_fip(source)
    if len(entries) != 2:
        raise ValueError(f"expected BL31 + BL33 FIP, got {len(entries)} entries")
    payloads = [source[o:o+s] for _uuid, o, s, _f in entries]
    bl31_raw = lzma_decode(payloads[0])
    uboot_raw = lzma_decode(payloads[1])
    safe_raw, checks = patch_raw_uboot(uboot_raw)
    safe_uboot = lzma_encode(safe_raw, payloads[1])

    header_size = 16 + 40 * (len(entries) + 1)
    if entries[0][1] != header_size:
        raise ValueError("unexpected FIP payload layout")
    new_offsets = []
    cursor = header_size
    new_payloads = [payloads[0], safe_uboot]
    for payload in new_payloads:
        new_offsets.append(cursor)
        cursor += len(payload)

    out = bytearray(cursor)
    struct.pack_into("<IIQ", out, 0, FIP_MAGIC, serial, flags)
    pos = 16
    for idx, (uuid, _old_o, _old_s, eflags) in enumerate(entries):
        out[pos:pos+16] = uuid
        struct.pack_into("<QQQ", out, pos+16, new_offsets[idx], len(new_payloads[idx]), eflags)
        pos += 40
    # Null UUID terminator; offset records end-of-FIP as in the source image.
    out[pos:pos+16] = b"\x00" * 16
    struct.pack_into("<QQQ", out, pos+16, cursor, 0, 0)
    for off, payload in zip(new_offsets, new_payloads):
        out[off:off+len(payload)] = payload

    final = bytes(out)
    _serial2, _flags2, entries2, _term2, end2 = parse_fip(final)
    if end2 != len(final):
        raise ValueError("rebuilt FIP terminator does not match file length")
    if lzma_decode(final[entries2[0][1]:entries2[0][1]+entries2[0][2]]) != bl31_raw:
        raise ValueError("BL31 changed during rebuild")
    final_uboot = lzma_decode(final[entries2[1][1]:entries2[1][1]+entries2[1][2]])
    if final_uboot != safe_raw:
        raise ValueError("BL33 round-trip mismatch")
    report = {
        "source_sha256": sha256(source),
        "output_sha256": sha256(final),
        "source_size": len(source),
        "output_size": len(final),
        "bl31_compressed_sha256": sha256(payloads[0]),
        "bl31_raw_sha256": sha256(bl31_raw),
        "source_bl33_raw_sha256": sha256(uboot_raw),
        "safe_bl33_raw_sha256": sha256(safe_raw),
        "safe_bl33_compressed_sha256": sha256(safe_uboot),
        "safe_bl33_lzma_known_size": True,
        "safe_bl33_lzma_eopm": False,
        **checks,
    }
    return final, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    source = args.source.read_bytes()
    output, report = rebuild_fip(source)
    args.output.write_bytes(output)
    if args.report:
        import json
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    for key, value in report.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
