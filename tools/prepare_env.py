#!/usr/bin/env python3
"""Build a personalized Nokia XG-040G-MD OpenWrt U-Boot env partition.

The tool reads either the device's raw/gzipped 0x80000-byte stock bootloader
backup or a 0x20000-byte environment-partition image. It preserves all valid
variables and changes only bootcmd, matching OpenWrt's stock-layout upgrade
hook. No router access is performed by this tool.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Iterable

BOOTLOADER_SIZE = 0x80000
ENV_PARTITION_OFFSET = 0x60000
ENV_PARTITION_SIZE = 0x20000
ENV_BLOCK_OFFSET = 0x1C000
ENV_BLOCK_SIZE = 0x4000
DEFAULT_BOOTCMD = "flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000"


class EnvError(ValueError):
    pass


def read_maybe_gzip(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError as exc:
            raise EnvError(f"cannot decompress {path}: {exc}") from exc
    return raw


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def extract_partition(source: bytes) -> bytearray:
    if len(source) == BOOTLOADER_SIZE:
        return bytearray(
            source[ENV_PARTITION_OFFSET : ENV_PARTITION_OFFSET + ENV_PARTITION_SIZE]
        )
    if len(source) == ENV_PARTITION_SIZE:
        return bytearray(source)
    raise EnvError(
        "input must be a 0x80000-byte bootloader backup or a "
        f"0x20000-byte env partition; got 0x{len(source):x} bytes"
    )


def parse_env_block(block: bytes) -> list[tuple[str, str]]:
    if len(block) != ENV_BLOCK_SIZE:
        raise EnvError(f"environment block must be 0x{ENV_BLOCK_SIZE:x} bytes")

    stored = struct.unpack_from("<I", block, 0)[0]
    calculated = crc32(block[4:])
    if stored != calculated:
        raise EnvError(
            f"invalid U-Boot env CRC: stored=0x{stored:08x}, "
            f"calculated=0x{calculated:08x}"
        )

    payload = block[4:]
    end = payload.find(b"\x00\x00")
    if end < 0:
        raise EnvError("environment has no double-NUL terminator")

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in payload[:end].split(b"\x00"):
        if not item:
            continue
        try:
            text = item.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvError("environment contains non-UTF-8 data") from exc
        if "=" not in text:
            raise EnvError(f"invalid environment entry: {text!r}")
        key, value = text.split("=", 1)
        if not key or key in seen:
            raise EnvError(f"invalid or duplicate environment key: {key!r}")
        seen.add(key)
        entries.append((key, value))

    if not entries:
        raise EnvError("environment contains no variables")
    return entries


def replace_variable(
    entries: Iterable[tuple[str, str]], key: str, value: str
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    replaced = False
    for current_key, current_value in entries:
        if current_key == key:
            result.append((key, value))
            replaced = True
        else:
            result.append((current_key, current_value))
    if not replaced:
        result.append((key, value))
    return result


def build_env_block(entries: Iterable[tuple[str, str]]) -> bytes:
    encoded_items = []
    for key, value in entries:
        if (
            not key
            or "=" in key
            or "\x00" in key
            or "\x00" in value
            or "\r" in value
            or "\n" in value
        ):
            raise EnvError(f"invalid environment variable {key!r}")
        encoded_items.append(f"{key}={value}".encode("utf-8"))

    payload = b"\x00".join(encoded_items) + b"\x00\x00"
    capacity = ENV_BLOCK_SIZE - 4
    if len(payload) > capacity:
        raise EnvError(
            f"environment payload is too large: {len(payload)} > {capacity} bytes"
        )
    payload += b"\x00" * (capacity - len(payload))
    return struct.pack("<I", crc32(payload)) + payload


def build_partition(source: bytes, bootcmd: str) -> tuple[bytes, dict[str, object]]:
    if not bootcmd or "\x00" in bootcmd or "\r" in bootcmd or "\n" in bootcmd:
        raise EnvError("bootcmd contains invalid characters")

    partition = extract_partition(source)
    original_partition = bytes(partition)
    start = ENV_BLOCK_OFFSET
    end = start + ENV_BLOCK_SIZE
    original_block = bytes(partition[start:end])
    entries = parse_env_block(original_block)
    old_bootcmd = next((value for key, value in entries if key == "bootcmd"), None)
    updated = replace_variable(entries, "bootcmd", bootcmd)
    new_block = build_env_block(updated)
    parse_env_block(new_block)
    partition[start:end] = new_block

    if partition[:start] != original_partition[:start] or partition[end:] != original_partition[end:]:
        raise EnvError("internal error: bytes outside the environment block changed")

    report = {
        "partition_size": len(partition),
        "env_block_offset": ENV_BLOCK_OFFSET,
        "env_block_size": ENV_BLOCK_SIZE,
        "variable_count": len(updated),
        "old_bootcmd": old_bootcmd,
        "new_bootcmd": bootcmd,
        "env_crc32": f"{struct.unpack_from('<I', new_block, 0)[0]:08x}",
        "source_partition_sha256": hashlib.sha256(original_partition).hexdigest(),
        "sha256": hashlib.sha256(partition).hexdigest(),
    }
    return bytes(partition), report


def generate_env_image(
    input_path: Path,
    output_path: Path,
    *,
    bootcmd: str = DEFAULT_BOOTCMD,
    report_json: Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    if output_path.exists() and not force:
        raise EnvError(f"output already exists: {output_path}; use --force")
    source = read_maybe_gzip(input_path)
    output, report = build_partition(source, bootcmd)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)
    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="raw/gzipped mtd0 bootloader backup or 0x20000 env image",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootcmd", default=DEFAULT_BOOTCMD)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument(
        "--force", action="store_true", help="allow replacing an existing output file"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = generate_env_image(
            args.input,
            args.output,
            bootcmd=args.bootcmd,
            report_json=args.report_json,
            force=args.force,
        )
    except (OSError, EnvError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Created: {args.output}")
    print(f"Size:    {report['partition_size']} bytes (0x{report['partition_size']:x})")
    print(f"SHA256:  {report['sha256']}")
    print(f"CRC32:   {report['env_crc32']}")
    print(f"bootcmd: {report['new_bootcmd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
