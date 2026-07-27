#!/usr/bin/env python3
"""Verify a Nokia XG-040G-MD stock MTD backup directory."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import sys
from pathlib import Path

EXPECTED = [
    (0, 0x00080000, "bootloader"),
    (1, 0x00040000, "romfile"),
    (2, 0x003AF6DA, "kernel"),
    (3, 0x01CC0000, "rootfs"),
    (4, 0x00480000, "kernel_slave"),
    (5, 0x02400000, "rootfs_slave"),
    (6, 0x00040000, "bosa"),
    (7, 0x00040000, "ri"),
    (8, 0x00040000, "flag"),
    (9, 0x00040000, "flagback"),
    (10, 0x00A00000, "config"),
    (11, 0x080E0000, "data"),
    (12, 0x00400000, "oopsfs"),
    (13, 0x00A00000, "log"),
    (14, 0x02880000, "nsb_master"),
    (15, 0x02880000, "nsb_slave"),
    (16, 0x0EBA0000, "all_flash"),
]
LINE_RE = re.compile(
    r'^mtd(?P<index>\d+):\s+(?P<size>[0-9a-fA-F]+)\s+'
    r'(?P<erase>[0-9a-fA-F]+)\s+"(?P<name>[^"]+)"$'
)
MANIFEST_RE = re.compile(r"^(?P<sha>[0-9a-fA-F]{64})\s+[ *](?P<name>.+)$")


class BackupError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def parse_proc_mtd(path: Path) -> list[tuple[int, int, str]]:
    parsed = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        match = LINE_RE.match(line.strip())
        if not match:
            raise BackupError(f"invalid /proc/mtd line: {line!r}")
        parsed.append(
            (
                int(match.group("index")),
                int(match.group("size"), 16),
                match.group("name"),
            )
        )
    return parsed


def parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        match = MANIFEST_RE.match(line)
        if not match:
            raise BackupError(f"invalid SHA256SUMS.txt line {line_number}: {raw_line!r}")
        name = match.group("name")
        if Path(name).name != name or name in entries:
            raise BackupError(f"unsafe or duplicate manifest entry: {name!r}")
        entries[name] = match.group("sha").lower()
    if not entries:
        raise BackupError("SHA256SUMS.txt is empty")
    return entries


def verify_manifest(root: Path) -> None:
    manifest_path = root / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise BackupError("missing SHA256SUMS.txt")
    entries = parse_manifest(manifest_path)
    for name, expected_sha in entries.items():
        path = root / name
        if not path.is_file():
            raise BackupError(f"manifest references missing file: {name}")
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            raise BackupError(
                f"compressed/file SHA-256 mismatch for {name}: "
                f"expected {expected_sha}, got {actual_sha}"
            )


def gzip_length_and_hash(path: Path) -> tuple[int, str]:
    total = 0
    digest = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                digest.update(chunk)
    except (OSError, EOFError) as exc:
        raise BackupError(f"invalid gzip archive {path.name}: {exc}") from exc
    return total, digest.hexdigest()


def verify_backup_directory(root: Path, *, verbose: bool = True) -> None:
    if not root.is_dir():
        raise BackupError(f"backup directory not found: {root}")

    proc_mtd = root / "proc_mtd.txt"
    if not proc_mtd.is_file():
        raise BackupError(f"missing {proc_mtd}")
    actual = parse_proc_mtd(proc_mtd)
    if actual != EXPECTED:
        raise BackupError("stock MTD layout does not match the supported reference layout")

    verify_manifest(root)

    for index, size, name in EXPECTED:
        archive = root / f"mtd{index}_{name}.bin.gz"
        if not archive.is_file():
            raise BackupError(f"missing {archive.name}")
        actual_size, digest = gzip_length_and_hash(archive)
        if actual_size != size:
            raise BackupError(
                f"{archive.name}: decompressed size 0x{actual_size:x}, "
                f"expected 0x{size:x}"
            )
        if verbose:
            print(f"OK mtd{index:02d} {name:13s} 0x{size:08x} raw-sha256={digest}")

    for raw_name in ("bosa.bin", "ri.bin"):
        raw = root / raw_name
        if not raw.is_file() or raw.stat().st_size != 0x40000:
            raise BackupError(f"{raw_name} must exist and be exactly 0x40000 bytes")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        verify_backup_directory(args.backup_dir)
    except (OSError, BackupError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Backup verification completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
