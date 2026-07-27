#!/usr/bin/env python3
"""Validate OpenWrt factory images and create a USB installation bundle."""

from __future__ import annotations

import argparse
import hashlib
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


class BundleError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_env(path: Path) -> None:
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
    if b"bootcmd=flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000\x00" not in block:
        raise BundleError("env image does not contain the expected OpenWrt bootcmd")


def verify_kernel(path: Path) -> None:
    size = path.stat().st_size
    if size <= 0 or size > KERNEL_LIMIT:
        raise BundleError(f"kernel size 0x{size:x} exceeds limit 0x{KERNEL_LIMIT:x}")
    magic = struct.unpack(">I", path.read_bytes()[:4])[0]
    if magic != FIT_MAGIC:
        raise BundleError(f"kernel does not start with FIT magic 0x{FIT_MAGIC:08x}")


def verify_rootfs(path: Path) -> None:
    size = path.stat().st_size
    if size <= 0 or size > ROOTFS_LIMIT:
        raise BundleError(f"rootfs size 0x{size:x} exceeds limit 0x{ROOTFS_LIMIT:x}")
    if path.read_bytes()[:4] != UBI_MAGIC:
        raise BundleError("factory rootfs does not start with UBI# magic")


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BundleError(f"missing file: {source}")
    shutil.copy2(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--router-dir", type=Path, default=Path(__file__).resolve().parents[1] / "router")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--confirm-skyhigh",
        action="store_true",
        help="confirm the device physically uses SkyHigh ML02G300WHI00 NAND",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        if not args.confirm_skyhigh:
            raise BundleError("--confirm-skyhigh is required")
        verify_kernel(args.kernel)
        verify_rootfs(args.rootfs)
        verify_env(args.env)

        if args.output.exists() and any(args.output.iterdir()):
            if not args.force:
                raise BundleError(f"output directory is not empty: {args.output}; use --force")
            shutil.rmtree(args.output)
        args.output.mkdir(parents=True, exist_ok=True)

        destinations = {
            args.kernel: args.output / "factory-kernel.bin",
            args.rootfs: args.output / "factory-rootfs.bin",
            args.env: args.output / "OpenWrt.mtd2.u-boot-env.bin",
        }
        for source, destination in destinations.items():
            copy_file(source, destination)

        for name in ("lib.sh", "preflight.sh", "flash-stock-layout.sh"):
            copy_file(args.router_dir / name, args.output / name)

        (args.output / "SKYHIGH_NAND_CONFIRMED.txt").write_text(
            "SkyHigh ML02G300WHI00\n", encoding="utf-8"
        )

        files = sorted(path for path in args.output.iterdir() if path.is_file())
        sums = "".join(f"{sha256(path)}  {path.name}\n" for path in files)
        (args.output / "SHA256SUMS").write_text(sums, encoding="ascii")

        info = ["Nokia XG-040G-MD stock-layout installation bundle", ""]
        for path in files:
            info.append(f"{path.name}: {path.stat().st_size} bytes, sha256={sha256(path)}")
        (args.output / "BUNDLE_INFO.txt").write_text("\n".join(info) + "\n", encoding="utf-8")
    except (OSError, BundleError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Bundle created at: {args.output}")
    print("Copy the bundle and the verified backup directory to a USB drive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
