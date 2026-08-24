#!/usr/bin/env python3
"""Create a device-specific Nokia XG-040G-MD/MF stock U-Boot env erase-block image.

Input may be the raw/gzipped 0x80000-byte mtd0 backup or an already extracted
0x20000-byte final erase block. The tool validates the stock U-Boot environment,
preserves every byte outside the 0x4000-byte environment payload, preserves all
variables, changes only bootcmd, recalculates CRC32, and emits a 0x20000 image.
"""

from __future__ import annotations

import argparse
import os
import gzip
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

BOOTLOADER_SIZE = 0x80000
ERASE_BLOCK_OFFSET = 0x60000
ERASE_BLOCK_SIZE = 0x20000
ENV_OFFSET = 0x1C000
ENV_SIZE = 0x4000
DEFAULT_BOOTCMD = "flash read 0xc0000 0x900000 0x92000000; bootm 0x92000000"

_LANG = os.environ.get("NOKIA_LANG", "").strip().lower()

def select_language() -> str:
    global _LANG
    if _LANG in ("ru", "rus", "1"):
        _LANG = "ru"
    elif _LANG in ("en", "eng", "2"):
        _LANG = "en"
    else:
        print("Select language / Выберите язык:")
        print("  1. RUS\n  2. ENG")
        value = input("RUS or ENG [1/2]: ").strip().lower()
        _LANG = "en" if value in ("2", "en", "eng") else "ru"
    os.environ["NOKIA_LANG"] = _LANG
    return _LANG

def tr(ru: str, en: str) -> str:
    return en if select_language() == "en" else ru

def localize_error(text: str) -> str:
    if select_language() == "en":
        return text
    replacements = (("cannot decompress", "не удалось распаковать"), ("input must be", "входной файл должен быть"), ("bytes", "байт"), ("environment", "environment"), ("invalid", "некорректный"), ("contains no", "не содержит"), ("duplicate", "дублирующийся"), ("output already exists", "выходной файл уже существует"), ("use --force", "используйте --force"), ("changed", "изменено"))
    for a,b in replacements:
        text=text.replace(a,b)
    return text


class EnvError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_input(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            raise EnvError(f"cannot decompress {path}: {exc}") from exc
    return raw


def extract_erase_block(source: bytes) -> bytearray:
    if len(source) == BOOTLOADER_SIZE:
        return bytearray(source[ERASE_BLOCK_OFFSET : ERASE_BLOCK_OFFSET + ERASE_BLOCK_SIZE])
    if len(source) == ERASE_BLOCK_SIZE:
        return bytearray(source)
    raise EnvError(
        "input must be a 0x80000-byte mtd0 backup or a 0x20000-byte erase-block image; "
        f"got 0x{len(source):x} bytes"
    )


def parse_env(block: bytes) -> list[tuple[str, str]]:
    if len(block) != ENV_SIZE:
        raise EnvError(f"environment block must be 0x{ENV_SIZE:x} bytes")
    stored = struct.unpack_from("<I", block, 0)[0]
    calculated = zlib.crc32(block[4:]) & 0xFFFFFFFF
    if stored != calculated:
        raise EnvError(
            f"invalid environment CRC32: stored=0x{stored:08x}, calculated=0x{calculated:08x}"
        )
    payload = block[4:]
    end = payload.find(b"\x00\x00")
    if end < 0:
        raise EnvError("environment has no double-NUL terminator")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_item in payload[:end].split(b"\x00"):
        if not raw_item:
            continue
        try:
            item = raw_item.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvError("environment contains non-UTF-8 data") from exc
        if "=" not in item:
            raise EnvError(f"invalid environment item: {item!r}")
        key, value = item.split("=", 1)
        if not key or key in seen:
            raise EnvError(f"invalid or duplicate environment key: {key!r}")
        seen.add(key)
        result.append((key, value))
    if not result:
        raise EnvError("environment contains no variables")
    return result


def build_env(entries: list[tuple[str, str]]) -> bytes:
    encoded: list[bytes] = []
    for key, value in entries:
        if not key or "=" in key or any(ch in key for ch in "\x00\r\n"):
            raise EnvError(f"invalid key: {key!r}")
        if any(ch in value for ch in "\x00\r\n"):
            raise EnvError(f"invalid value for key: {key!r}")
        encoded.append(f"{key}={value}".encode("utf-8"))
    payload = b"\x00".join(encoded) + b"\x00\x00"
    capacity = ENV_SIZE - 4
    if len(payload) > capacity:
        raise EnvError(f"environment payload is too large: {len(payload)} > {capacity}")
    payload += b"\x00" * (capacity - len(payload))
    return struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + payload


def create_image(source: bytes, bootcmd: str) -> tuple[bytes, dict[str, object]]:
    if not bootcmd or any(ch in bootcmd for ch in "\x00\r\n"):
        raise EnvError("bootcmd contains invalid characters")
    erase_block = extract_erase_block(source)
    original = bytes(erase_block)
    env_start = ENV_OFFSET
    env_end = env_start + ENV_SIZE
    entries = parse_env(original[env_start:env_end])
    old_bootcmd = None
    updated: list[tuple[str, str]] = []
    for key, value in entries:
        if key == "bootcmd":
            old_bootcmd = value
            updated.append((key, bootcmd))
        else:
            updated.append((key, value))
    if old_bootcmd is None:
        updated.append(("bootcmd", bootcmd))
    new_env = build_env(updated)
    parse_env(new_env)
    erase_block[env_start:env_end] = new_env
    output = bytes(erase_block)
    if output[:env_start] != original[:env_start] or output[env_end:] != original[env_end:]:
        raise EnvError("bytes outside the environment payload changed")
    old_map = dict(entries)
    new_map = dict(updated)
    changed_keys = sorted(k for k in set(old_map) | set(new_map) if old_map.get(k) != new_map.get(k))
    if changed_keys != ["bootcmd"]:
        raise EnvError(f"unexpected changed variables: {changed_keys}")
    report = {
        "source_erase_block_sha256": sha256(original),
        "output_sha256": sha256(output),
        "output_size": len(output),
        "environment_offset": ENV_OFFSET,
        "environment_size": ENV_SIZE,
        "environment_crc32": f"{struct.unpack_from('<I', new_env, 0)[0]:08x}",
        "variable_count": len(updated),
        "changed_variables": changed_keys,
        "old_bootcmd": old_bootcmd,
        "new_bootcmd": bootcmd,
        "bytes_changed": sum(a != b for a, b in zip(original, output)),
        "bytes_changed_outside_environment": sum(
            a != b
            for index, (a, b) in enumerate(zip(original, output))
            if not (env_start <= index < env_end)
        ),
    }
    return output, report


def parse_args(argv: list[str]) -> argparse.Namespace:
    select_language()
    parser = argparse.ArgumentParser(description=tr("Создание персонального erase-block образа U-Boot environment Nokia XG-040G-MD/MF", __doc__ or "Create a device-specific Nokia XG-040G-MD/MF U-Boot environment image"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--bootcmd", default=DEFAULT_BOOTCMD)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.output.exists() and not args.force:
            raise EnvError(f"output already exists: {args.output}; use --force")
        output, report = create_image(read_input(args.input), args.bootcmd)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    except (OSError, EnvError) as exc:
        print(f"ERROR: {localize_error(str(exc))}", file=sys.stderr)
        return 1
    print(tr(f"Создано: {args.output}", f"Created: {args.output}"))
    print(tr(f"Размер:  {report['output_size']} байт", f"Size:    {report['output_size']} bytes"))
    print(f"SHA256:  {report['output_sha256']}")
    print(f"CRC32:   {report['environment_crc32']}")
    print(tr(f"Изменено: {', '.join(report['changed_variables'])}", f"Changed: {', '.join(report['changed_variables'])}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
