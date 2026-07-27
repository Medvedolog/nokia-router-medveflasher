#!/usr/bin/env python3
"""Validate official OpenWrt factory images and create a USB installation bundle."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import struct
import sys
import zlib
from pathlib import Path

KERNEL_LIMIT = 0x800000
ROOTFS_LIMIT = 0x80E0000
ENV_PARTITION_SIZE = 0x20000
ENV_BLOCK_OFFSET = 0x1C000
ENV_BLOCK_SIZE = 0x4000
FIT_MAGIC = 0xD00DFEED
UBI_MAGIC = b"UBI#"
EXPECTED_BOOTCMD = "flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000"
KERNEL_SUFFIX = "nokia_xg-040g-md-squashfs-factory-kernel.bin"
ROOTFS_SUFFIX = "nokia_xg-040g-md-squashfs-factory-rootfs.bin"
SUM_RE = re.compile(r"^(?P<sha>[0-9a-fA-F]{64})\s+[ *](?P<name>.+)$")


class BundleError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def first_bytes(path: Path, count: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(count)


def parse_sha256sums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        match = SUM_RE.match(line)
        if not match:
            raise BundleError(f"invalid sha256sums line {line_number}: {raw_line!r}")
        name = match.group("name")
        if Path(name).name != name or name in entries:
            raise BundleError(f"unsafe or duplicate sha256sums entry: {name!r}")
        entries[name] = match.group("sha").lower()
    if not entries:
        raise BundleError("sha256sums file is empty")
    return entries


def verify_official_hash(path: Path, entries: dict[str, str]) -> str:
    expected = entries.get(path.name)
    if expected is None:
        raise BundleError(f"{path.name} is not listed in the supplied OpenWrt sha256sums")
    actual = sha256(path)
    if actual != expected:
        raise BundleError(
            f"OpenWrt SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        )
    return actual


def verify_env(path: Path) -> dict[str, str | int]:
    data = path.read_bytes()
    if len(data) != ENV_PARTITION_SIZE:
        raise BundleError(f"env image must be exactly 0x{ENV_PARTITION_SIZE:x} bytes")
    block = data[ENV_BLOCK_OFFSET : ENV_BLOCK_OFFSET + ENV_BLOCK_SIZE]
    stored = struct.unpack_from("<I", block, 0)[0]
    calculated = zlib.crc32(block[4:]) & 0xFFFFFFFF
    if stored != calculated:
        raise BundleError(
            f"env CRC mismatch: stored=0x{stored:08x}, calculated=0x{calculated:08x}"
        )
    expected_entry = f"bootcmd={EXPECTED_BOOTCMD}".encode("ascii") + b"\x00"
    if expected_entry not in block:
        raise BundleError("env image does not contain the exact expected OpenWrt bootcmd")
    return {"crc32": f"{stored:08x}", "sha256": sha256(path), "size": len(data)}


def verify_kernel(path: Path) -> dict[str, str | int]:
    if not path.is_file():
        raise BundleError(f"missing file: {path}")
    if not path.name.endswith(KERNEL_SUFFIX) or "-ubi-" in path.name or "tcboot" in path.name:
        raise BundleError(f"unexpected factory kernel filename: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > KERNEL_LIMIT:
        raise BundleError(f"kernel size 0x{size:x} exceeds limit 0x{KERNEL_LIMIT:x}")
    header = first_bytes(path, 4)
    if len(header) != 4 or struct.unpack(">I", header)[0] != FIT_MAGIC:
        raise BundleError(f"kernel does not start with FIT magic 0x{FIT_MAGIC:08x}")
    return {"sha256": sha256(path), "size": size}


def verify_rootfs(path: Path) -> dict[str, str | int]:
    if not path.is_file():
        raise BundleError(f"missing file: {path}")
    if not path.name.endswith(ROOTFS_SUFFIX) or "-ubi-" in path.name or "tcboot" in path.name:
        raise BundleError(f"unexpected factory rootfs filename: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > ROOTFS_LIMIT:
        raise BundleError(f"rootfs size 0x{size:x} exceeds limit 0x{ROOTFS_LIMIT:x}")
    if first_bytes(path, 4) != UBI_MAGIC:
        raise BundleError("factory rootfs does not start with UBI# magic")
    return {"sha256": sha256(path), "size": size}


def default_router_dir() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "router"
    return Path(__file__).resolve().parents[1] / "router"


def copy_binary(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BundleError(f"missing file: {source}")
    shutil.copy2(source, destination)


def copy_script_lf(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BundleError(f"missing router script: {source}")
    data = source.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if b"\x00" in data:
        raise BundleError(f"router script contains NUL bytes: {source}")
    destination.write_bytes(data)


def create_bundle(
    *,
    kernel: Path,
    rootfs: Path,
    env: Path,
    openwrt_sha256sums: Path,
    output: Path,
    router_dir: Path | None = None,
    confirm_skyhigh: bool = False,
    force: bool = False,
) -> Path:
    if not confirm_skyhigh:
        raise BundleError("--confirm-skyhigh is required")

    kernel_info = verify_kernel(kernel)
    rootfs_info = verify_rootfs(rootfs)
    env_info = verify_env(env)
    entries = parse_sha256sums(openwrt_sha256sums)
    kernel_official_sha = verify_official_hash(kernel, entries)
    rootfs_official_sha = verify_official_hash(rootfs, entries)

    if output.exists():
        if not output.is_dir():
            raise BundleError(f"output exists and is not a directory: {output}")
        if any(output.iterdir()):
            if not force:
                raise BundleError(f"output directory is not empty: {output}; use --force")
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    copy_binary(kernel, output / "factory-kernel.bin")
    copy_binary(rootfs, output / "factory-rootfs.bin")
    copy_binary(env, output / "OpenWrt.mtd2.u-boot-env.bin")
    copy_binary(openwrt_sha256sums, output / "OPENWRT_SHA256SUMS.txt")

    scripts = router_dir or default_router_dir()
    for name in ("lib.sh", "preflight.sh", "flash-stock-layout.sh"):
        copy_script_lf(scripts / name, output / name)

    (output / "SKYHIGH_NAND_CONFIRMED.txt").write_text(
        "SkyHigh ML02G300WHI00\n", encoding="ascii", newline="\n"
    )

    info_lines = [
        "Nokia XG-040G-MD stock-layout installation bundle",
        "",
        f"source-kernel={kernel.name}",
        f"source-rootfs={rootfs.name}",
        f"kernel-size={kernel_info['size']}",
        f"kernel-sha256={kernel_official_sha}",
        f"rootfs-size={rootfs_info['size']}",
        f"rootfs-sha256={rootfs_official_sha}",
        f"env-size={env_info['size']}",
        f"env-sha256={env_info['sha256']}",
        f"env-crc32={env_info['crc32']}",
        f"bootcmd={EXPECTED_BOOTCMD}",
    ]
    (output / "BUNDLE_INFO.txt").write_text(
        "\n".join(info_lines) + "\n", encoding="utf-8", newline="\n"
    )

    manifest_files = sorted(
        path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    sums = "".join(f"{sha256(path)}  {path.name}\n" for path in manifest_files)
    (output / "SHA256SUMS").write_text(sums, encoding="ascii", newline="\n")
    return output


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--sha256sums", required=True, type=Path)
    parser.add_argument("--router-dir", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--confirm-skyhigh",
        action="store_true",
        help="confirm the device physically uses SkyHigh ML02G300WHI00 NAND",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output = create_bundle(
            kernel=args.kernel,
            rootfs=args.rootfs,
            env=args.env,
            openwrt_sha256sums=args.sha256sums,
            output=args.output,
            router_dir=args.router_dir,
            confirm_skyhigh=args.confirm_skyhigh,
            force=args.force,
        )
    except (OSError, BundleError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Bundle created at: {output}")
    print("Copy the bundle and the verified backup directory to a USB drive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
