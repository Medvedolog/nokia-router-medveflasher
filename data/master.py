#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import codecs
import contextlib
import ftplib
import gzip
import getpass
import hashlib
import importlib.util
import json
import lzma
import os
import re
import shlex
import shutil
import socket
import ssl
import ctypes
import glob
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

APP_VERSION = "1.0.0-rc29"
BUILD_TAG = "medveflasher-1.0.0-rc29"
BOOTCMD = "flash read 0xc0000 0x800000 0x92000000; bootm 0x92000000"
KIT = Path(__file__).resolve().parent.parent
DATA = KIT / "data"
VENDOR = DATA / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
from rich.console import Console as RichConsole
from rich.text import Text as RichText
WORK = KIT / "work"
BUNDLE = DATA / "transition-bundle.bin"
MANUAL_BUNDLE = DATA / "transition-manual-bundle.bin"
MF_TRANSITION_BUNDLE = DATA / "mf-transition-bundle.bin"
MF_MANUAL_TRANSITION_BUNDLE = DATA / "mf-transition-manual-bundle.bin"
LAUNCHER_TEMPLATE = DATA / "stock-launcher.sh.in"
BACKUP_AGENT = DATA / "backup-agent.sh"
STOCK_WEB = DATA / "stock_web.py"
RECOVERY_DIR = DATA / "recovery"
RECOVERY_PRELOADER = RECOVERY_DIR / "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-preloader.bin"
RECOVERY_FIP = RECOVERY_DIR / "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-bl31-uboot-ethfix.fip"
RECOVERY_INITRAMFS = RECOVERY_DIR / "nokia-xg040gmd-stock-recovery-initramfs.itb"
UBOOT_DEFAULT_RECOVERY_FILENAME = "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-initramfs-recovery.itb"
RECOVERY_PRELOADER_SHA = "6c3b2339d036340396730a13adfe35c0d2a4dddedeffb6f9965a24e0c7908808"
RECOVERY_FIP_SHA = "2ebcbf3981e3e56b6389521fc2caa3320cf259c08f173b660b29366b9290bcc1"
RECOVERY_FIP_SIZE = 308154
RECOVERY_FIP_SOURCE_SHA = "9c29cdbcc3f9c00070cc72262c83dcd1eb212f89f6fb84806ad8657eadec2b8b"
RECOVERY_INITRAMFS_SHA = "c40c87354566eb44fc933c1ce6c0cd9c81227b525243c67c9932b80a656d01c6"
RECOVERY_INITRAMFS_SIZE = 11_285_480
RECOVERY_CLIENT_DIR = RECOVERY_DIR / "recovery-clients-bin"
RECOVERY_TFTP_CLIENT = RECOVERY_CLIENT_DIR / "nokia-tftp"
RECOVERY_SCP_CLIENT = RECOVERY_CLIENT_DIR / "nokia-scp"
RECOVERY_TFTP_CLIENT_SHA = "2b6bbc51975e22f420565c42363821eb362936136b03f70a2a0cedee99c1641a"
RECOVERY_SCP_CLIENT_SHA = "232a4ba7f8ae62922815bb12503fd7d09c3b4f40929d130475e467f0a597ac89"
MD_RECOVERY_SOURCE_INITRAMFS_SHA = "a8e24301925c4a7b120594b61aa679bac835b26ef70736fd28a69c9029ffda3b"
MD_RECOVERY_SOURCE_INITRAMFS_SIZE = 11_141_120
MF_RECOVERY_DIR = RECOVERY_DIR / "mf"
MF_RECOVERY_METADATA = MF_RECOVERY_DIR / "OPENWRT_SNAPSHOT.json"
MF_RECOVERY_BASE_URL = "https://downloads.openwrt.org/snapshots/targets/airoha/an7583/"
MF_RECOVERY_PRELOADER_NAME = "openwrt-airoha-an7583-airoha_an7583-evb-preloader.bin"
MF_RECOVERY_FIP_NAME = "openwrt-airoha-an7583-airoha_an7583-evb-bl31-uboot.fip"
MF_RECOVERY_PRELOADER = MF_RECOVERY_DIR / MF_RECOVERY_PRELOADER_NAME
MF_RECOVERY_FIP = MF_RECOVERY_DIR / MF_RECOVERY_FIP_NAME
MF_RECOVERY_PRELOADER_SHA = "c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f"
MF_RECOVERY_FIP_SHA = "8bfe8870e44923a463a3ed66c8b1906214f5c820fd8c15865c63430185de8bb2"
MF_RECOVERY_FIP_SOURCE_SHA = "b2f5f93f52afbaf539fe362267b13a91fb0a3a22c4ea770f2fc984dece176c12"
MF_RECOVERY_PRELOADER_SIZE = 118322
MF_RECOVERY_FIP_SIZE = 339010
MF_STOCK_RECOVERY_INITRAMFS = MF_RECOVERY_DIR / "nokia-xg040gmf-stock-recovery-initramfs.itb"
MF_STOCK_RECOVERY_INITRAMFS_SHA = "da1f3cb376ad599a2d8ffea3d03abeb02bdec1114aad06d6ad049885914b045f"
MF_STOCK_RECOVERY_INITRAMFS_SIZE = 7_479_380
MF_UBI_PRELOADER_SIZE = 118333
MF_UBI_PRELOADER_SHA = "778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e"
MF_UBI_FIP_SIZE = 319568
MF_UBI_FIP_SHA = "99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7"
MF_UBI_SYSUPGRADE_SIZE = 9191705
MF_UBI_SYSUPGRADE_SHA = "db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b"
MF_UBI_BOARD = "nokia,xg-040g-mf-ubi"
RECOVERY_SAFE_MARKER = "rc18"  # SAFE BL33 bytes are retained from RC18
RECOVERY_SAFE_BOOTCMD = "echo RECOVERY_SAFE_RC18"

@dataclass(frozen=True)
class InstallProfile:
    family: str
    model: str
    soc: str
    expected_board: str
    auto_bundle: Path
    manual_bundle: Path
    runtime_bundle_name: str
    runtime_env_name: str
    force_tftp: bool = False


MD_INSTALL_PROFILE = InstallProfile(
    family="md",
    model="Nokia XG-040G-MD",
    soc="AN7581",
    expected_board="nokia,xg-040g-md-ubi",
    auto_bundle=BUNDLE,
    manual_bundle=MANUAL_BUNDLE,
    runtime_bundle_name="transition-bundle.bin",
    runtime_env_name="OpenWrt.mtd2.u-boot-env.bin",
)
MF_INSTALL_PROFILE = InstallProfile(
    family="mf",
    model="Nokia XG-040G-MF",
    soc="AN7583",
    expected_board=MF_UBI_BOARD,
    auto_bundle=MF_TRANSITION_BUNDLE,
    manual_bundle=MF_MANUAL_TRANSITION_BUNDLE,
    runtime_bundle_name="mf-transition-bundle.bin",
    runtime_env_name="OpenWrt.mf.u-boot-env.bin",
    force_tftp=True,
)
INSTALL_PROFILES = {"md": MD_INSTALL_PROFILE, "mf": MF_INSTALL_PROFILE}
BOOTROM_BACKUP_TFTP_PORT = 1069
DIAGNOSTICS_DIR = DATA / "diagnostics"
STOCK_AUDIT_SCRIPT = DIAGNOSTICS_DIR / "mf-stock-audit.sh"
STOCK_AUDIT_PARSER = DIAGNOSTICS_DIR / "mf_audit_parse.py"
FIRMWARE_CAPABILITIES = DATA / "FIRMWARE_CAPABILITIES.json"
# Canonical stock image/restore span captured by stock mtd16.  This is not
# the capacity of the physical SPI-NAND chip.
STOCK_RESTORE_SPAN = 0x0EBA0000
# Known AN7581/AN7583 physical SPI-NAND capacity used only as a hardware
# reference. Stock audit derives physical capacity from NAND-driver evidence,
# never from mtd0 (stock mtd0 is the 512-KiB bootloader partition).
PHYSICAL_NAND_SIZE = 0x10000000
STOCK_BL2_SIZE = 0x00020000
STOCK_IBU_SIZE = STOCK_RESTORE_SPAN - STOCK_BL2_SIZE
UBOOT_ERASE_SIZE = 0x00020000
UBOOT_RESTORE_CHUNK_SIZE = 0x00800000
UBOOT_LOAD_ADDRESS = 0x90000000
# Stock config/data/oopsfs/log_truncated are UBI-backed and can tolerate
# physical bad eraseblocks. Raw bootloader/kernel/rootfs/flags cannot be
# safely reconstructed by the OpenWrt RAM U-Boot without proven stock BMT
# semantics, so UART restore fails closed if a bad block is found there.
STOCK_BADBLOCK_SAFE_PHYS_START = 0x052C0000
STOCK_BADBLOCK_SAFE_PHYS_END = 0x0EB60000
STOCK_BADBLOCK_SAFE_UBI_START = STOCK_BADBLOCK_SAFE_PHYS_START - STOCK_BL2_SIZE
STOCK_BADBLOCK_SAFE_UBI_END = STOCK_BADBLOCK_SAFE_PHYS_END - STOCK_BL2_SIZE
OPENWRT_PRELOADER_SIZE = 113447
OPENWRT_PRELOADER_SHA = "6c3b2339d036340396730a13adfe35c0d2a4dddedeffb6f9965a24e0c7908808"
STOCK_RAW_SLICES = {
    0: (0x0000000, 0x0080000),
    1: (0x0080000, 0x0040000),
    14: (0x00C0000, 0x2880000),
    15: (0x2940000, 0x2880000),
    6: (0x51C0000, 0x0040000),
    7: (0x5200000, 0x0040000),
    8: (0x5240000, 0x0040000),
    9: (0x5280000, 0x0040000),
    10: (0x52C0000, 0x0A00000),
    11: (0x5CC0000, 0x80E0000),
    12: (0xDDA0000, 0x0400000),
    13: (0xE1A0000, 0x0A00000),
}
# These partitions are expected to remain byte-stable while a live stock backup
# is being captured.  They must match the later all_flash/mtd16 snapshot exactly.
STOCK_STABLE_RAW_SLICES = frozenset((0, 1, 6, 7, 14, 15))
# Stock updates these areas during normal operation.  The individual dump and
# mtd16 are taken at different times, so byte equality would be a false invariant.
# Their own transfer SHA256, gzip integrity and exact size are still mandatory;
# mtd16 is the canonical restore image.
STOCK_LIVE_RAW_SLICES = frozenset(STOCK_RAW_SLICES) - STOCK_STABLE_RAW_SLICES
EXPECTED_BUNDLE_SHA = "bb421ef151a5ea118f10780042461f594b84925cdc92381dcc4de19f8ac35fb1"
EXPECTED_BUNDLE_SIZE = 21_626_880
EXPECTED_MANUAL_BUNDLE_SHA = "394461e5cb65eddef7615967603c08b14811c07168293bdc93a630f823aaf85f"
EXPECTED_MANUAL_BUNDLE_SIZE = 8_388_608
EXPECTED_MF_TRANSITION_BUNDLE_SHA = "9ec21e8f7454011e91f251a0784c0c57b815c39e4defe74cc031eb270e6a9aa3"
EXPECTED_MF_TRANSITION_BUNDLE_SIZE = 17_694_720
EXPECTED_MF_TRANSITION_FIT_SIZE = 7_702_044
EXPECTED_MF_TRANSITION_FIT_SHA = "d32997998f0e74bf6063982b4a20da656048ea9c3443df61fd297cb512cdf341"
EXPECTED_MF_TRANSITION_WINDOW_SHA = "5ef8e2c1d433c5e3d695517de40f0dd093a100487e9f0cee1a07f23ff4b17215"
EXPECTED_MF_MANUAL_TRANSITION_BUNDLE_SHA = "120488c7b2c26cc3a036a12de1572e207d506e54ea98a4fd94de96f08301a733"
EXPECTED_MF_MANUAL_TRANSITION_BUNDLE_SIZE = 8_388_608
EXPECTED_MF_MANUAL_TRANSITION_FIT_SIZE = 7_702_276
EXPECTED_MF_MANUAL_TRANSITION_FIT_SHA = "f8a8d9a1ce867029ab8b74e497910678530fc1cf54ac0211b174089e8459240c"
EXPECTED_PROD_SIZE = 13_226_255
EXPECTED_PROD_SHA = "c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03"
FIXED_EXPECTED = {
    0: 524288, 1: 262144, 6: 262144, 7: 262144, 8: 262144,
    9: 262144, 10: 10485760, 11: 135135232, 12: 4194304,
    13: 10485760, 14: 42467328, 15: 42467328, 16: STOCK_RESTORE_SPAN,
}
# Stock-side objects that stage 1 writes or uses as the canonical handoff span.
# These remain byte-exact for both MD and MF even though mtd2..mtd5 are
# revision-tolerant vendor slot views.
INSTALL_STOCK_HANDOFF = {
    0: (0x00080000, "bootloader"),
    14: (0x02880000, "nsb_master"),
    15: (0x02880000, "nsb_slave"),
    16: (STOCK_RESTORE_SPAN, "all_flash"),
}
SLOT_LAYOUTS = (
    {2: 0x003AF6DA, 3: 0x01CC0000, 4: 0x00480000, 5: 0x02400000},
    {2: 0x00480000, 3: 0x02400000, 4: 0x003AF6DA, 5: 0x01CC0000},
)
MF_SLOT_LAYOUTS = (
    # MF-A: hardware-confirmed stock layout.
    {2: 0x003B6CC0, 3: 0x01D00000, 4: 0x00480000, 5: 0x02400000},
    {2: 0x00480000, 3: 0x02400000, 4: 0x003B6CC0, 5: 0x01D00000},
    # MF-B: second real stock layout observed in the field.
    {2: 0x003B6D40, 3: 0x01D10000, 4: 0x00480000, 5: 0x02400000},
    {2: 0x00480000, 3: 0x02400000, 4: 0x003B6D40, 5: 0x01D10000},
)
MF_SLOT_VARIANTS = (
    ("MF-A", MF_SLOT_LAYOUTS[0]),
    ("MF-A-MIRROR", MF_SLOT_LAYOUTS[1]),
    ("MF-B", MF_SLOT_LAYOUTS[2]),
    ("MF-B-MIRROR", MF_SLOT_LAYOUTS[3]),
)
MD_SLOT_VARIANTS = (
    ("MD-A", SLOT_LAYOUTS[0]),
    ("MD-A-MIRROR", SLOT_LAYOUTS[1]),
)
# Revision-tolerant stock slot matching.
#
# mtd2/mtd3 (kernel/rootfs) and mtd4/mtd5 (kernel_slave/rootfs_slave) are the
# only stock partitions whose sizes move between vendor firmware revisions;
# every other slot is pinned byte-exact by FIXED_EXPECTED.  On every unit seen
# so far exactly one of the two slots publishes the canonical pair below, and
# the opposite slot publishes a revision-dependent pair: a raw kernel image
# size plus a rootfs slot size that steps in 0x10000 units.  Adding one table
# entry per vendor revision does not scale, so the canonical pair is still
# required byte-exact and only the revision-dependent pair gets a window.
STOCK_SLOT_CANONICAL_PAIR = (0x00480000, 0x02400000)
# Each reference carries the vendor profile letter it belongs to, so a tolerated
# match can name the profile it actually resembles instead of inheriting the slot
# orientation. Under the symmetric write policy the label is the only thing the
# slot revision still produces, and operators and evidence files read it.
STOCK_SLOT_REVISION_REFERENCE = {
    "md": (("A", 0x003AF6DA, 0x01CC0000),),
    "mf": (("A", 0x003B6CC0, 0x01D00000), ("B", 0x003B6D40, 0x01D10000)),
}
# The slot pair is the only MD/MF discriminator — every fixed partition is
# identical across the two models — so the windows must stay well inside half
# the distance between the family reference points, which is 0x75E6 for the
# kernel entry and 0x40000 for the rootfs entry.  Observed revision drift is
# 0x68 (MD kernel), 0x80 (MF kernel) and 0x10000 (both rootfs entries).
STOCK_SLOT_IMAGE_TOLERANCE = 0x2000
STOCK_SLOT_PARTITION_TOLERANCE = 0x10000
STOCK_SLOT_PARTITION_GRANULARITY = 0x10000
# mtd2..mtd5 are vendor kernel/rootfs slot views, not the physical OpenWrt UBI
# format target.  They classify MD versus MF and remain relevant to stock
# restore metadata, but they are deliberately NOT a permanent-write allowlist.
# Destructive authorization is instead bound to exact fixed stock handoff
# partitions, /proc<->sysfs agreement, NAND erase geometry, a fully validated
# device backup, and the exact board-specific transition target checks embedded
# in the RAM installer (all_flash=0x10000000, BL2=0x20000, UBI=0x0FFE0000).
EXPECTED_NUMBERS = tuple(range(17))
IAC, DO, DONT, WILL, WONT = 255, 253, 254, 251, 252

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SESSION_LOG_PATH: Path | None = None
LATEST_LOG_PATH: Path | None = None
_SESSION_FILES: list[object] = []
_COLOR_ENABLED = False
_LOG_SECRET_VALUES: set[str] = set()
_LOG_SECRET_LOCK = threading.Lock()
_LOG_SECRET_REPLACEMENT = "[REDACTED]"
_STARTUP_DEVICE_PROFILE: dict[str, object] = {
    "family": "unknown", "model": "", "chipset": "", "host": "192.168.1.1",
    "verified": False, "source": "not-probed",
}
_STARTUP_WEB_AUTH: dict[str, str] = {}


def _register_log_secret(value: object | None) -> None:
    """Register a known in-memory secret for exact substring redaction in logs."""
    if value is None:
        return
    secret = str(value)
    # Very short values would destroy ordinary diagnostics if replaced globally.
    # Nokia label/web passwords are materially longer; keep the filter useful and
    # deterministic rather than redacting every occurrence of a one-character value.
    if len(secret) < 4:
        return
    with _LOG_SECRET_LOCK:
        _LOG_SECRET_VALUES.add(secret)


def _redact_log_text(text: str) -> str:
    with _LOG_SECRET_LOCK:
        secrets = sorted(_LOG_SECRET_VALUES, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, _LOG_SECRET_REPLACEMENT)
    return text


# Column position of the log stream. A timestamp is a line prefix, so it may only
# be emitted where a line actually begins: live mirrors write partial chunks and
# stamping each one would cut the device's own output apart. stdout and stderr are
# two tees feeding the same files, so the column is shared rather than per-tee.
_LOG_AT_LINE_START = True


def _stamp_log_text(payload: str) -> str:
    """Prefix every line that begins inside payload, then remember the column.

    A chunk written mid-line passes through untouched: it continues a line the
    device already started. Blank separator lines stay blank. A carriage return is
    deliberately not a new line, so a progress counter refreshing with \\r does not
    collect one stamp per redraw.
    """
    global _LOG_AT_LINE_START
    if not payload:
        return payload
    stamp = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
    parts = payload.split("\n")
    rendered = [
        stamp + part if part and (_LOG_AT_LINE_START if index == 0 else True) else part
        for index, part in enumerate(parts)
    ]
    _LOG_AT_LINE_START = payload.endswith("\n")
    return "\n".join(rendered)


class _ConsoleTee:
    """Console sees exactly what the code printed; the log carries the clock.

    RC23 introduced the absolute timestamp so PC output could be correlated with
    UART events. That is a job for the file you read afterwards, not for the screen
    the operator is working on, where the prefix competes with the content on every
    single line. From RC26 the console is clean and work/logs/*.log carries the
    stamps.
    """

    def __init__(self, console, files):
        self.console = console
        self.files = files

    def write(self, text):
        written = self.console.write(text)
        clean = _redact_log_text(ANSI_RE.sub("", text))
        stamped = _stamp_log_text(clean)
        for fh in self.files:
            fh.write(stamped)
        return written

    def flush(self):
        self.console.flush()
        for fh in self.files:
            fh.flush()

    def isatty(self):
        return bool(getattr(self.console, "isatty", lambda: False)())

    def fileno(self):
        return self.console.fileno()

    @property
    def encoding(self):
        return getattr(self.console, "encoding", "utf-8")


def _write_session_only(text: str) -> None:
    """Append technical diagnostics only to the timestamped session log.

    LATEST.log intentionally mirrors the operator-facing console and stays clean.
    """
    if not text or not _SESSION_FILES:
        return
    clean = _redact_log_text(ANSI_RE.sub("", text))
    if not clean.endswith("\n"):
        clean += "\n"
    clean = _stamp_log_text(clean)
    fh = _SESSION_FILES[0]
    fh.write(clean)
    fh.flush()


def _clean_telnet_protocol(text: str) -> str:
    """Remove command wrappers, rc markers and bare shell prompts."""
    cleaned = re.sub(r"__NOKIA_RC_\d+_\d+__", "", text.replace("\r", ""))
    lines: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.rstrip()
        if re.fullmatch(r"\s*[#$]\s*", line):
            continue
        if line.startswith("[LOG] stock-preflight output mirror active:"):
            _write_session_only("[TECH] " + line)
            continue
        lines.append(line)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def start_session_logging() -> Path:
    global SESSION_LOG_PATH, LATEST_LOG_PATH, _COLOR_ENABLED
    if SESSION_LOG_PATH is not None:
        return SESSION_LOG_PATH
    logs_dir = WORK / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    SESSION_LOG_PATH = logs_dir / f"session-{stamp}-{os.getpid()}.log"
    LATEST_LOG_PATH = logs_dir / "LATEST.log"
    session_fh = SESSION_LOG_PATH.open("w", encoding="utf-8", newline="\n", buffering=1)
    latest_fh = LATEST_LOG_PATH.open("w", encoding="utf-8", newline="\n", buffering=1)
    _SESSION_FILES[:] = [session_fh, latest_fh]
    sys.stdout = _ConsoleTee(sys.stdout, _SESSION_FILES)
    sys.stderr = _ConsoleTee(sys.stderr, _SESSION_FILES)
    _enable_windows_ansi()
    _COLOR_ENABLED = bool(getattr(sys.stdout, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    return SESSION_LOG_PATH


def _color(text: str, code: str) -> str:
    if not _COLOR_ENABLED or not text:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def colorize_text(text: str) -> str:
    if not _COLOR_ENABLED or "\x1b[" in text:
        return text
    lines = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        stripped = body.lstrip()
        upper = stripped.upper()
        if re.match(r"^-{6,}\s*STAGE(?:_|-)", upper) or re.match(r"^-{6,}\s*COMPLETE", upper):
            body = _color(body, "1;36")
        elif re.match(r"^(?:ERROR(?: / OSHIBKA)?|ОШИБКА|CRITICAL FAILURE):", upper) or upper.startswith(("[ERROR]", "[FAIL]")):
            body = _color(body, "1;31")
        elif upper.startswith(("[ПРЕДУПРЕЖДЕНИЕ]", "[WARNING]")):
            body = _color(body, "1;33")
        elif upper.startswith("[OK]") or re.match(r"^OK:", upper) or upper.startswith(("PREFLIGHT PASSED", "ГОТОВО:")):
            body = _color(body, "1;32")
        elif upper.startswith(("[ОПАСНО]", "[DANGER]")):
            body = _color(body, "1;31")
        elif upper.startswith(("[ВАЖНО]", "[IMPORTANT]")):
            body = _color(body, "1;33")
        elif upper.startswith(("[READY]", "[SUCCESS]")):
            body = _color(body, "1;32")
        elif upper.startswith(("[WAIT]", "[TRANSFER]", "[FLASH]", "[VERIFY]", "[TFTP]", "[SCP]", "[TCP/NC]", "[NET]", "[STEP ", "[INFO]")):
            body = _color(body, "1;34" if upper.startswith("[WAIT]") else "1;36")
        elif upper.startswith("[INPUT]"):
            body = _color(body, "1;35")
        elif upper.startswith("[PATH]"):
            body = _color(body, "1;36")
        elif upper.startswith("[TECH]"):
            body = _color(body, "2;37")
        elif upper.startswith("[LOG]"):
            body = _color(body, "36")
        lines.append(body + ending)
    return "".join(lines)


def print_app_banner() -> None:
    """Rich-coloured startup banner; ANSI is stripped from LATEST/session logs by _ConsoleTee."""
    console = RichConsole(file=sys.stdout, force_terminal=_COLOR_ENABLED, color_system="truecolor" if _COLOR_ENABLED else None, highlight=False)
    bear = RichText()
    bear.append("       ʕ•ᴥ•ʔ\n", style="bold rgb(150,75,0)")
    bear.append("      /|   |\\\n", style="rgb(150,75,0)")
    bear.append("     /_|___|_\\", style="rgb(150,75,0)")
    console.print(bear)
    title = RichText("Nokia Router MedveFlasher", style="bold cyan")
    title.append("  •  ", style="dim")
    title.append(APP_VERSION, style="bold green")
    console.print(title)
    console.print(RichText(BUILD_TAG, style="green"))


def stage_header(number: str, ru: str, en: str) -> None:
    title = en if ensure_language() == "en" else ru
    print()
    print(f"---------- STAGE_{number}: {title} ----------")
    print()


# Language is selected by START/RECOVER_STOCK launchers and propagated to every
# user-facing component through NOKIA_LANG. Direct master.py launches ask here.
_LANG = os.environ.get("NOKIA_LANG", "").strip().lower()
if _LANG in ("rus", "ru", "1"):
    _LANG = "ru"
elif _LANG in ("eng", "en", "2"):
    _LANG = "en"
else:
    _LANG = ""

_RAW_PRINT = print
_RAW_INPUT = input
_RAW_GETPASS = getpass.getpass

# Phrase-level catalog intentionally leaves protocol tokens, paths, hashes,
# command names and machine-readable markers unchanged.
_RU_EN = [
    ("повреждён комплект: отсутствует", "damaged kit: missing"),
    ("размер transition bundle не совпадает с релизом", "transition bundle size does not match this release"),
    ("SHA256 transition bundle не совпадает с релизом", "transition bundle SHA256 does not match this release"),
    ("SHA256 recovery-артефакта не совпадает", "recovery artifact SHA256 mismatch"),
    ("Нет SHA256SUMS; файлы будут проверены по gzip и точным размерам.", "SHA256SUMS is missing; files will be checked by gzip integrity and exact sizes."),
    ("в manifest отсутствует файл", "manifest references a missing file"),
    ("SHA256 не совпал", "SHA256 mismatch"),
    ("SHA256SUMS не содержит пригодных записей", "SHA256SUMS contains no usable entries"),
    ("backup-каталог не найден", "backup directory not found"),
    ("Нет proc_mtd.txt; ориентация слотов определяется по размерам dump-файлов.", "proc_mtd.txt is missing; slot orientation will be detected from dump sizes."),
    ("неполный backup: отсутствует", "incomplete backup: missing"),
    ("повреждён", "corrupted"),
    ("неподдерживаемые размеры stock-слотов", "unsupported stock slot sizes"),
    ("размер", "size"),
    ("ожидается", "expected"),
    ("proc_mtd не совпадает с dump для", "proc_mtd does not match the dump for"),
    ("не удалось загрузить env_patcher.py", "failed to load env_patcher.py"),
    ("уже существует", "already exists"),
    ("не удалось персонализировать stock launcher", "failed to personalize the stock launcher"),
    ("Пакет привязан к одному устройству. Не публиковать env-файл.", "This package is bound to one device. Do not publish the environment file."),
    ("Персональный пакет Nokia XG-040G-MD. Запускается мастером START; вручную", "Device-specific Nokia XG-040G-MD package. Use the START wizard; manual command"),
    ("тайм-аут Telnet: не найден маркер", "Telnet timeout: marker not found"),
    ("внутренний маркер встретился в скрипте", "internal marker occurred inside the script"),
    ("не удалось загрузить", "failed to upload"),
    ("через Telnet", "through Telnet"),
    ("не найден доступный UID 0 аккаунт", "no usable UID 0 account found"),
    ("Найден UID 0 аккаунт", "UID 0 account found"),
    ("не дал UID 0", "did not grant UID 0"),
    ("в stock firmware отсутствует nc; используйте USB-накопитель на Nokia через Samba/FTP", "stock firmware has no usable nc; use the Nokia-attached USB drive through Samba/FTP"),
    ("в stock firmware отсутствует BusyBox tftp; используйте USB-накопитель на Nokia через Samba/FTP", "stock firmware has no BusyBox tftp; use the Nokia-attached USB drive through Samba/FTP"),
    ("stock tftp не поддерживает PUT/GET; используйте USB-накопитель на Nokia через Samba/FTP", "stock tftp does not support PUT/GET; use the Nokia-attached USB drive through Samba/FTP"),
    ("короткий TFTP request", "truncated TFTP request"),
    ("повреждённый TFTP request", "malformed TFTP request"),
    ("распакованный размер", "decompressed size"),
    ("не удалось получить точную stock-разметку /proc/mtd", "failed to obtain the exact stock /proc/mtd layout"),
    ("не удалось открыть TCP-порт", "failed to open TCP port"),
    ("Приём", "Receiving"),
    ("попытка", "attempt"),
    ("Тайм-аут потока; повтор раздела.", "Stream timeout; retrying this partition."),
    ("Сетевая ошибка", "Network error"),
    ("байт", "bytes"),
    ("не удалось надёжно снять", "failed to capture reliably"),
    ("через TFTP после трёх попыток", "through TFTP after three attempts"),
    ("Для mtd16 это может занять долго", "mtd16 may take a long time"),
    ("повторяется только текущий раздел", "only the current partition will be retried"),
    ("backup на USB завершился ошибкой", "USB backup failed"),
    ("backup завершён, но не удалось определить каталог на USB", "backup completed, but the USB directory could not be determined"),
    ("некорректный UNC-путь Samba", "invalid Samba UNC path"),
    ("не удалось подключить Samba share", "failed to connect the Samba share"),
    ("Samba/смонтированная папка недоступна", "Samba/mounted directory is unavailable"),
    ("ошибка копирования", "copy error"),
    ("не удалось передать", "failed to transfer"),
    ("на router", "to the router"),
    ("SHA256 после сетевой передачи не совпал", "SHA256 mismatch after network transfer"),
    ("не удалось открыть TFTP GET server", "failed to start the TFTP GET server"),
    ("через TFTP", "through TFTP"),
    ("SHA256 после TFTP передачи не совпал", "SHA256 mismatch after TFTP transfer"),
    ("Передача", "Transferring"),
    ("на Nokia через TFTP", "to Nokia over TFTP"),
    ("неподдерживаемый способ deploy", "unsupported deployment method"),
    ("проверка персонального пакета на Nokia не пройдена", "device-specific package verification failed on Nokia"),
    ("тайм-аут ожидания", "timeout waiting for"),
    ("не найден OpenSSH client (ssh). В Windows включите Optional Feature: OpenSSH Client", "OpenSSH Client (ssh) was not found. Enable the Windows Optional Feature: OpenSSH Client"),
    ("тайм-аут SSH-команды", "SSH command timeout"),
    ("SSH-команда завершилась с кодом", "SSH command exited with code"),
    ("stage 1 preflight не пройден", "stage 1 preflight failed"),
    ("Одно подтверждение разрешает запись transition и последующий автономный stage 2.", "One confirmation authorizes the transition write and the subsequent autonomous stage 2."),
    ("ВНИМАНИЕ: после reboot initramfs автоматически отформатирует stock NAND и установит embedded OpenWrt.", "WARNING: after reboot, initramfs will automatically format the stock NAND and install the embedded OpenWrt image."),
    ("Продолжайте только когда полный проверенный backup сохранён на компьютере, питание стабильно,", "Continue only after a complete verified backup is saved on the PC and power is stable,"),
    ("а NAND совместима. Явно обнаруженная FudanMicro FM25G02B блокируется;", "and the NAND is compatible. Explicitly detected FudanMicro FM25G02B is blocked;"),
    ("неопределённая модель допускается только после точной проверки платы и геометрии и остаётся ответственностью пользователя.", "an unidentified model is accepted only after exact board and geometry checks and remains the operator's responsibility."),
    ("Введите точно CONFIRM FORMAT AND FLASH", "Type exactly CONFIRM FORMAT AND FLASH"),
    ("операция отменена", "operation cancelled"),
    ("RAM worker stage 1 не стартовал", "stage 1 RAM worker did not start"),
    ("Ожидание автономного stage 2. После загрузки transition никаких SSH-команд не требуется.", "Waiting for autonomous stage 2. No SSH commands are required after transition boots."),
    ("production OpenWrt отвечает, но проверка UBI board/fit не пройдена", "production OpenWrt responds, but UBI board/fit verification failed"),
    ("ГОТОВО: Nokia загрузилась в production OpenWrt all-in-UBI.", "DONE: Nokia booted into production OpenWrt all-in-UBI."),
    ("автоматическая прошивка не завершилась; transition initramfs оставлена доступной по SSH.", "automatic flashing did not complete; transition initramfs remains available over SSH."),
    ("Войдите", "Log in to"),
    ("и прочитайте", "and read"),
    ("служба autoflash не стартовала за 60 секунд; transition initramfs доступна по SSH.", "the autoflash service did not start within 60 seconds; transition initramfs is available over SSH."),
    ("Проверьте", "Check"),
    ("Transition загружен; ожидаю запуска службы autoflash...", "Transition booted; waiting for the autoflash service..."),
    ("Ожидаю reboot в production OpenWrt...", "Waiting for reboot into production OpenWrt..."),
    ("после обнаружения transition", "after transition was detected"),
    ("тайм-аут автономного stage 2", "autonomous stage 2 timeout"),
    ("подключитесь по SSH и проверьте", "connect over SSH and check"),
    ("для stock restore", "for stock restore"),
    ("mtd16 не согласован с", "mtd16 is inconsistent with"),
    ("изменился во время подготовки recovery payload", "changed while preparing the recovery payload"),
    ("не удалось открыть UART", "failed to open UART"),
    ("Проверяю программные зависимости recovery...", "Checking recovery software dependencies..."),
    ("встроенный Win32-бэкенд, pyserial и pip не нужны.", "built-in Win32 backend; pyserial and pip are not required."),
    ("OpenSSH Client не установлен. Это компонент Windows, не Python-пакет.", "OpenSSH Client is not installed. It is a Windows component, not a Python package."),
    ("Установка из PowerShell от администратора", "Install from an elevated PowerShell"),
    ("Открыть страницу 'Дополнительные компоненты Windows' сейчас?", "Open the Windows Optional Features page now?"),
    ("установите компонент и снова запустите recovery", "install the component and run recovery again"),
    ("Ожидание BootROM XMODEM для", "Waiting for BootROM XMODEM for"),
    ("Символ C означает готовность приёмника.", "The C character means the receiver is ready."),
    ("Найдено приглашение Press x; отправляю x.", "Press x prompt detected; sending x."),
    ("BootROM выдаёт C: готов к XMODEM", "BootROM is sending C: ready for XMODEM"),
    ("тайм-аут: BootROM не перешёл в XMODEM для", "timeout: BootROM did not enter XMODEM for"),
    ("BootROM отменил XMODEM", "BootROM cancelled XMODEM"),
    ("Повтор блока", "Retrying block"),
    ("передан и подтверждён.", "transferred and acknowledged."),
    ("не подтверждён", "was not acknowledged"),
    ("EOT не подтверждён", "EOT was not acknowledged"),
    ("Ожидаю U-Boot, запущенный из RAM, и останавливаю автоматическую загрузку...", "Waiting for and intercepting U-Boot running from RAM..."),
    ("Ctrl-C/ESC используются для остановки autoboot; Enter не отправляется.", "Ctrl-C/ESC are used to stop autoboot; Enter is never sent."),
    ("Обнаружен RAM U-Boot; прерываю autoboot.", "RAM U-Boot detected; interrupting autoboot."),
    ("Меню U-Boot обнаружено; отправляю ESC, не Enter.", "U-Boot menu detected; sending ESC, not Enter."),
    ("Получено приглашение U-Boot; загрузка с NAND не запускалась.", "U-Boot control acquired; the NAND bootcmd was not started."),
    ("Началось чтение production FIT; посылаю Ctrl-C до передачи управления ядру.", "Production FIT read started; sending Ctrl-C before control reaches the kernel."),
    ("Обычная OpenWrt уже начала загрузку; продолжу через SSH и аварийный RAM-образ без повторного XMODEM.", "Production Linux has already started; switching to SSH one-shot recovery without terminating the workflow."),
    ("после передачи FIP устройство вернулось в BootROM вместо RAM U-Boot", "after FIP transfer the device returned to BootROM instead of RAM U-Boot"),
    ("autoboot не считается успешно перехваченным", "autoboot is not considered successfully intercepted"),
    ("тайм-аут U-Boot-команды или prompt не вернулся", "U-Boot command timed out or the prompt did not return"),
    ("Подтверждена разметка системы восстановления: mtd2=ibu.", "The recovery-system layout mtd2=ibu is confirmed."),
    ("после bootm загрузилась production OpenWrt", "production OpenWrt booted after bootm"),
    ("ядро recovery стартовало, но UART не подтвердил безопасную MTD-разметку mtd2=ibu", "the recovery kernel started, but UART did not confirm the safe mtd2=ibu layout"),
    ("TFTP recovery FIT не завершился после возврата U-Boot prompt", "recovery FIT TFTP did not finish after the U-Boot prompt returned"),
    ("TFTP передан сервером, но U-Boot не подтвердил успешную загрузку FIT", "the TFTP server transferred the image, but U-Boot did not confirm a successful FIT load"),
    ("iminfo не подтвердил корректный recovery FIT; bootm запрещён", "iminfo did not validate the recovery FIT; bootm is blocked"),
    ("iminfo подтвердил recovery FIT; запускаю только RAM-образ.", "iminfo validated the recovery FIT; booting the RAM image only."),
    ("Ожидаю production OpenWrt по SSH для автоматического one-shot перехода в recovery...", "Waiting for production OpenWrt over SSH for an automatic one-shot transition to recovery..."),
    ("Production fallback подтверждён; one-shot recovery запускается автоматически без повторного XMODEM.", "Production fallback confirmed; one-shot recovery starts automatically without another XMODEM session."),
    ("Production fallback: автоматически повторяю one-shot TFTP без повторного XMODEM.", "Production fallback: automatically retrying one-shot TFTP without repeating XMODEM."),
    ("Ожидание U-Boot, запущенного из RAM...", "Waiting for U-Boot running from RAM..."),
    ("U-Boot prompt найден.", "U-Boot prompt detected."),
    ("U-Boot prompt не появился после передачи FIP", "U-Boot prompt did not appear after FIP transfer"),
    ("TFTP recovery server не запустился", "TFTP recovery server did not start"),
    ("U-Boot не запросил recovery FIT по TFTP", "U-Boot did not request the recovery FIT over TFTP"),
    ("TFTP recovery FIT передан не полностью", "TFTP recovery FIT transfer was incomplete"),
    ("recovery FIT передан", "recovery FIT transferred"),
    ("загружена не recovery-initramfs: автоматическая UBI-служба не подтверждена как отключённая", "the loaded image is not the recovery initramfs: the automatic UBI service was not confirmed disabled"),
    ("recovery-initramfs сообщает другую плату", "recovery initramfs reports a different board"),
    ("неожиданная recovery MTD-разметка; нет", "unexpected recovery MTD layout; missing"),
    ("Текущий raw RI совпадает с mtd7 из выбранного backup: привязка устройства подтверждена.", "Current raw RI matches mtd7 from the selected backup: device binding confirmed."),
    ("raw RI не совпал с backup. После all-in-UBI миграции это ожидаемо, потому что старый raw RI мог быть стёрт.", "raw RI does not match the backup. This is expected after all-in-UBI migration because the old raw RI may have been erased."),
    ("Продолжайте только если backup точно снят с этой Nokia.", "Continue only if the backup was definitely captured from this Nokia."),
    ("не запустился", "did not start"),
    ("не завершился", "did not complete"),
    ("передано", "transferred"),
    ("ожидалось", "expected"),
    ("readback SHA256", "readback SHA256"),
    ("не совпал; BL2 не перезагружать и не выключать питание", "mismatch; do not reboot BL2 or remove power"),
    ("Нужен USB-UART 3.3 V: подключать только GND, TX и RX; VCC к Nokia не подключать.", "A 3.3 V USB-UART adapter is required: connect only GND, TX and RX; do not connect VCC to Nokia."),
    ("Ethernet должен соединять ПК с Nokia. На ПК задайте статический адрес 192.168.1.254/24.", "Ethernet must connect the PC to Nokia. Set the PC to the static address 192.168.1.254/24."),
    ("Загрузчик и система восстановления запускаются из оперативной памяти; автоматическая установка OpenWrt в этом образе отключена.", "The recovery bootloader and system run from memory; automatic OpenWrt installation is disabled in this image."),
    ("Windows COM работает встроенными средствами Win32; pyserial и pip не требуются.", "Windows COM uses the built-in Win32 backend; pyserial and pip are not required."),
    ("Реально обнаруженные UART-порты", "Detected UART ports"),
    ("UART-порты автоматически не обнаружены. Проверьте драйвер USB-UART и Диспетчер устройств.", "No UART ports were detected automatically. Check the USB-UART driver and Device Manager."),
    ("UART-порт или номер из списка", "UART port or list number"),
    ("UART-порт не указан", "UART port was not specified"),
    ("Проверяю доступ к UART", "Checking access to UART"),
    ("до подготовки большого recovery payload", "before preparing the large recovery payload"),
    ("открыт как 115200 8N1 без flow control.", "opened as 115200 8N1 with no flow control."),
    ("Статический IP ПК", "Static PC IP"),
    ("Порт передачи больших restore-файлов, TFTP/TCP", "Large restore-file transfer port, TFTP/TCP"),
    ("Путь к ранее снятому полному stock-backup", "Path to the previously captured full stock backup"),
    ("Проверяю комплект backup: mtd0..mtd16, размеры и соответствие разделов полному дампу mtd16...", "Strictly checking mtd0..mtd16 and consistency between mtd16 and the physical stock partitions..."),
    ("Backup пригоден для stock restore. Payload", "Backup is valid for stock restore. Payload"),
    ("Выключите Nokia. Удерживайте Reset, включите питание и держите кнопку до приглашения BootROM.", "Power off Nokia. Hold Reset, power it on, and keep holding the button until the BootROM prompt appears."),
    ("Нажмите Enter на ПК, когда готовы начать прослушивание UART", "Press Enter on the PC when ready to start listening on UART"),
    ("Запускаю TFTP на UDP/69 и загружаю безопасную recovery-initramfs без autoflash.", "Starting TFTP on UDP/69 and loading the safe recovery initramfs with autoflash disabled."),
    ("нет прав на UDP/69; в Linux запустите recovery через sudo ./START.sh", "permission denied for UDP/69; on Linux run recovery with sudo ./START.sh"),
    ("Ожидаю SSH recovery OpenWrt...", "Waiting for recovery OpenWrt SSH..."),
    ("будет восстановлен полный stock NAND из mtd16 выбранного backup.", "the complete stock NAND will be restored from mtd16 of the selected backup."),
    ("Сначала пишется и проверяется IBU 0x20000..0xEBA0000; BL2 0..0x20000 пишется последним.", "IBU 0x20000..0xEBA0000 is written and verified first; BL2 0..0x20000 is written last."),
    ("После записи каждого этапа выполняется readback SHA256; при несовпадении reboot запрещён.", "A readback SHA256 check follows each stage; reboot is forbidden on mismatch."),
    ("Введите точно RESTORE STOCK BACKUP", "Type exactly RESTORE STOCK BACKUP"),
    ("stock restore отменён", "stock restore cancelled"),
    ("Основная stock-область восстановлена. Теперь записывается BL2 последним.", "The main stock area has been restored. BL2 will now be written last."),
    ("финальный SHA256 all_flash не совпал; не перезагружайте Nokia, сохраните UART/SSH логи", "final all_flash SHA256 mismatch; do not reboot Nokia, preserve the UART/SSH logs"),
    ("Полный stock all_flash совпал", "Complete stock all_flash matches"),
    ("Stock backup восстановлен побайтно. Перезагружаю Nokia в штатную прошивку.", "Stock backup was restored byte-for-byte. Rebooting Nokia into stock firmware."),
    ("Recovery завершён. UART-лог", "Recovery completed. UART log"),
    ("Проверьте stock Web UI/Telnet по адресу 192.168.1.1. Если загрузка не завершилась, питание не дёргать до анализа UART-лога.", "Check the stock Web UI/Telnet at 192.168.1.1. If boot does not complete, do not remove power before reviewing the UART log."),
    ("Пароль Telnet/с наклейки", "Telnet/password from the label"),
    ("Пароль UID 0 [тот же]", "UID 0 password [same]"),
    ("Транспорт backup и установочного пакета", "Backup and installation package transport"),
    ("USB-накопитель подключён к Nokia: Samba/сетевая папка (флешку не вынимать)", "USB drive connected to the Nokia: Samba/network share (do not remove the drive)"),
    ("USB-накопитель подключён к Nokia: FTP штатной прошивки", "USB drive connected to the Nokia: stock-firmware FTP"),
    ("прямой TFTP между Nokia и ПК, USB не требуется", "direct TFTP between Nokia and the PC; USB is not required"),
    ("Выберите", "Select"),
    ("Путь к корню USB", "Path to the USB root"),
    ("уже подключено/пусто", "already connected/blank"),
    ("Путь USB внутри Nokia", "USB path inside Nokia"),
    ("IP этого ПК для Nokia", "This PC's IP address for Nokia"),
    ("UDP-порт TFTP", "TFTP UDP port"),
    ("неверный выбор транспорта", "invalid transport selection"),
    ("backup не виден через share", "backup is not visible through the share"),
    ("Полный backup сохранён на ПК", "Complete backup saved on the PC"),
    ("Персональный пакет создан", "Device-specific package created"),
    ("backup ТОЛЬКО на вставленную USB-флешку", "backup ONLY to the inserted USB drive"),
    ("backup напрямую на ПК через TFTP, без флешки", "backup directly to the PC over TFTP, without a USB drive"),
    ("Backup готов ТОЛЬКО на USB-флешке", "Backup completed ONLY on the USB drive"),
    ("Скопируйте весь каталог backup на компьютер до любых операций с NAND.", "Copy the entire backup directory to the PC before any NAND operation."),
    ("Backup готов на ПК", "Backup completed on the PC"),
    ("неверный выбор", "invalid selection"),
    ("после трёх попыток", "after three attempts"),
    ("не удалось открыть UDP-порт", "failed to open UDP port"),
    ("на UDP", "on UDP"),
    ("и logread", "and logread"),
    ("отдельный dump SHA256", "separate dump SHA256"),
    (": блок ", ": block "),
    (" блоков)", " blocks)"),
    ("TFTP server для", "TFTP server for"),
    ("например", "for example"),
    (" или ", " or "),
    ("ВНИМАНИЕ:", "WARNING:"),
    ("[пусто]", "[blank]"),
    ("Путь к каталогу полного backup", "Path to the complete backup directory"),
    ("Готово", "Done"),
    ("только снять полный backup", "capture a complete backup only"),
    ("создать персональный пакет из готового backup", "create a device-specific package from an existing backup"),
    ("продолжить со второго этапа в transition OpenWrt", "resume from stage 2 in transition OpenWrt"),
    ("восстановить кирпич через UART: C → XMODEM → полный stock-backup", "recover a bricked device over UART: C → XMODEM → complete stock backup"),
    ("выход", "exit"),
    ('откатиться на stock из работающего OpenWrt/recovery без UART', 'restore stock from a running OpenWrt/recovery without UART'),
    ('Откат на stock из работающего OpenWrt/recovery без XMODEM', 'Stock rollback from a running OpenWrt/recovery without XMODEM'),
    ('Поддерживаются: уже запущенная система восстановления и установленная OpenWrt.', 'Supported states: a running recovery system or installed OpenWrt.'),
    ('Для production OpenWrt мастер использует самоотменяющийся one-shot U-Boot bootcmd → TFTP recovery FIT; Reset не требуется.', 'For production OpenWrt the wizard uses a self-reverting one-shot U-Boot bootcmd → TFTP recovery FIT; Reset is not required.'),
    ('IP OpenWrt/recovery', 'OpenWrt/recovery IP'),
    ('Подключаюсь к работающему OpenWrt по SSH...', 'Connecting to the running OpenWrt over SSH...'),
    ('Обнаружена установленная OpenWrt. Сначала будет временно запущена система восстановления.', 'Installed OpenWrt detected. The recovery system will be started temporarily first.'),
    ('Безопасная recovery-initramfs уже работает; UART/XMODEM повторять не требуется.', 'The safe recovery initramfs is already running; UART/XMODEM does not need to be repeated.'),
    ('Откат завершён. Проверьте stock Web UI/Telnet по адресу 192.168.1.1.', 'Rollback completed. Check the stock Web UI/Telnet at 192.168.1.1.'),
    ('Способ перехода в режим восстановления stock', 'Method for entering stock recovery mode'),
    ('OpenWrt/recovery уже загружается: продолжить по SSH без UART', 'OpenWrt/recovery already boots: continue over SSH without UART'),
    ('кирпич, в UART повторяется C: BootROM → XMODEM → recovery → stock', 'bricked device with repeated C on UART: BootROM → XMODEM → recovery → stock'),
    ('Recovery MTD-разметка уже готова; поздняя служба RECOVERY_READY ещё не отметилась. Ожидаю 5 секунд...', 'The recovery MTD layout is ready; the late RECOVERY_READY service has not reported yet. Waiting 5 seconds...'),
    ('RECOVERY_READY не появился, но точная безопасная recovery MTD-разметка подтверждена; продолжаю.', 'RECOVERY_READY did not appear, but the exact safe recovery MTD layout is confirmed; continuing.'),
    ('запущен production OpenWrt, а не безопасная recovery-initramfs', 'production OpenWrt is running instead of the safe recovery initramfs'),
    ('OpenWrt обнаружен, но его плата/MTD-разметка не соответствует Nokia XG-040G-MD recovery или all-in-UBI production', 'OpenWrt was detected, but its board/MTD layout does not match Nokia XG-040G-MD recovery or all-in-UBI production'),
    ('в recovery-initramfs отсутствует обязательный инструмент mtd/tftp/gzip/sha256sum', 'the recovery initramfs is missing a required mtd/tftp/gzip/sha256sum tool'),
    ('recovery OpenWrt не перешёл в готовое состояние за отведённое время', 'recovery OpenWrt did not become ready within the allotted time'),
    ('raw RI не совпал или недоступен. После all-in-UBI миграции это ожидаемо.', 'raw RI does not match or is unavailable. This is expected after all-in-UBI migration.'),
    ('U-Boot ожидает файл', 'U-Boot expects file'),
    ('Нажмите и удерживайте Reset на Nokia. Не отпускайте кнопку до сообщения о начале TFTP.', 'Press and hold Reset on Nokia. Do not release it until the TFTP-start message appears.'),
    ('Когда Reset уже удерживается, нажмите Enter — мастер перезагрузит OpenWrt', 'When Reset is being held, press Enter — the wizard will reboot OpenWrt'),
    ('U-Boot запросил recovery FIT. Кнопку Reset можно отпустить.', 'U-Boot requested the recovery FIT. You may release Reset.'),
    ('Ожидаю загрузки recovery OpenWrt по SSH...', 'Waiting for recovery OpenWrt to boot over SSH...'),
    ('U-Boot не запросил recovery FIT. Nokia должна была вернуться в production OpenWrt; повторите и удерживайте Reset дольше', 'U-Boot did not request the recovery FIT. Nokia should have returned to production OpenWrt; retry and hold Reset longer'),
    ('U-Boot serverip=', 'U-Boot serverip='),
    ('а IP ПК=', 'while the PC IP is='),
    ('Задайте компьютеру адрес', 'Assign the PC address'),
    ('или исправьте serverip перед повтором', 'or correct serverip before retrying'),
    ('U-Boot ipaddr=', 'U-Boot ipaddr='),
    ('а ожидаемый IP Nokia=', 'while the expected Nokia IP is='),
    ('One-shot recovery вооружён. Штатный bootcmd будет восстановлен до начала TFTP.', 'One-shot recovery is armed. The normal bootcmd will be restored before TFTP starts.'),
    ('TFTP/69 запущен и ожидает запрос от U-Boot.', 'TFTP/69 is running and waiting for a request from U-Boot.'),
    ('не загрузила recovery FIT', 'did not load the recovery FIT'),
    ('recovery FIT не был загружен после TFTP-попытки; Nokia вернулась в production OpenWrt', 'the recovery FIT was not loaded after the TFTP attempt; Nokia returned to production OpenWrt'),
    ('после неудачной TFTP-попытки не вернулись ни recovery, ни production SSH.', 'after the failed TFTP attempt neither recovery nor production SSH returned.'),
    ('Проверьте UART: Press x означает BootROM; используйте пункт UART/XMODEM без выключения питания', 'Check UART: Press x means BootROM; use the UART/XMODEM option without removing power'),
    ('исчерпаны три попытки загрузки recovery FIT', 'all three recovery FIT loading attempts were exhausted'),
    ('передано', 'transferred'),
    ('Reset НЕ нажимайте: раннее удержание Reset переводит BootROM в приглашение Press x.', 'Do NOT press Reset: holding Reset too early enters the BootROM Press x prompt.'),
    ('Мастер установит самоотменяющийся one-shot bootcmd, перезагрузит Nokia и автоматически подаст recovery FIT.', 'The wizard will install a self-reverting one-shot bootcmd, reboot Nokia, and serve the recovery FIT automatically.'),
    ('Reset не нажимайте. Нажмите Enter, чтобы вооружить one-shot boot и перезагрузить OpenWrt', 'Do not press Reset. Press Enter to arm the one-shot boot and reboot OpenWrt'),
    ('TFTP/69 запущен и ожидает запрос от U-Boot.', 'TFTP/69 is running and waiting for the U-Boot request.'),
    ('U-Boot запросил recovery FIT; передача началась.', 'U-Boot requested the recovery FIT; transfer started.'),
    ('Ожидаю возврата production OpenWrt по SSH. One-shot bootcmd должен был восстановить обычную загрузку до попытки TFTP...', 'Waiting for production OpenWrt to return over SSH. The one-shot bootcmd should have restored normal boot before TFTP was attempted...'),
    ('Production OpenWrt снова доступен; backup повторно проверять не нужно.', 'Production OpenWrt is reachable again; the backup does not need to be revalidated.'),
    ('Повторить TFTP/reboot попытку?', 'Retry the TFTP/reboot attempt?'),
    ('не удалось подтвердить временный one-shot bootcmd; reboot отменён', 'failed to verify the temporary one-shot bootcmd; reboot cancelled'),
    ('неожиданный U-Boot bootcmd; one-shot recovery не будет установлен автоматически', 'unexpected U-Boot bootcmd; one-shot recovery will not be installed automatically'),
    ('Получено', 'Received'),
    ('Ожидалось', 'Expected'),
    ('Используйте адрес', 'Use address'),
    ('в мастере', 'in the wizard'),
]


# Restore, Samba, and input-validation messages.  New recovery messages are translated explicitly so an
# English run never falls back to Russian error text.
_RU_EN.extend([
    ("не удалось прочитать диапазон", "failed to read range"),
    ("неполный диапазон", "incomplete range"),
    ("для восстановления stock", "for stock restoration"),
    ("SHA256 диапазона", "range SHA256"),
    ("SHA256 отдельного дампа", "separate dump SHA256"),
    ("выбранный backup содержит OpenWrt preloader в начале BL2 без смещения. Это копия повреждённого OpenWrt BL2, а не исходный stock backup", "the selected backup contains the OpenWrt preloader at the beginning of BL2 without an offset. This is a copy of the damaged OpenWrt BL2, not an original stock backup"),
    ("выбранный backup содержит OpenWrt all-in-UBI BL2 (FF 0x800 + preloader), а не исходный stock BL2", "the selected backup contains the OpenWrt all-in-UBI BL2 (FF 0x800 + preloader), not the original stock BL2"),
    ("mtd16 изменился во время подготовки файлов восстановления", "mtd16 changed while restore files were being prepared"),
    ("stock-ibu.bin.gz закончился раньше ожидаемого размера", "stock-ibu.bin.gz ended before the expected size"),
    ("stock-ibu.bin.gz содержит лишние данные", "stock-ibu.bin.gz contains trailing data"),
    ("не удалось подготовить полный набор IBU-блоков", "failed to prepare the complete set of IBU chunks"),
    ("не удалось подготовить точный stock BL2 для U-Boot", "failed to prepare the exact stock BL2 for U-Boot"),
    ("U-Boot-команда завершилась с кодом", "U-Boot command exited with code"),
    ("U-Boot SHA256 не совпал для", "U-Boot SHA256 mismatch for"),
    ("не удалось запустить TFTP/69", "failed to start TFTP/69"),
    ("не удалось передать", "failed to transfer"),
    ("в RAM U-Boot", "into RAM U-Boot"),
    ("RAM U-Boot не показал ожидаемые разделы bl2 и ubi; запись запрещена", "RAM U-Boot did not expose the expected bl2 and ubi partitions; writing is prohibited"),
    ("U-Boot сообщил ошибку чтения IBU-блока", "U-Boot reported a read error for IBU chunk"),
    ("восстановление stock отменено", "stock restoration cancelled"),
    ("обычная OpenWrt не готова к следующей попытке", "the installed OpenWrt is not ready for the next attempt"),
    ("тайм-аут U-Boot-команды или prompt не вернулся", "U-Boot command timeout or prompt did not return"),
    ("после записи stock BL2 устройство снова вернулось в BootROM Press x; сохраните UART-лог", "after writing stock BL2 the device returned to BootROM Press x; keep the UART log"),
])

_RU_EN.extend([
    ("Папка установки Samba", "Samba installation folder"),
    ("Путь USB внутри Nokia", "USB path inside Nokia"),
    ("автоопределение", "auto-detect"),
    ("Samba-пакет скопирован на ПК-путь", "Samba package copied to PC path"),
    ("Samba-пакет найден на Nokia", "Samba package found on Nokia"),
    ("не удалось найти скопированный Samba-пакет на Nokia", "failed to locate the copied Samba package on Nokia"),
    ("Проверены пути", "Paths checked"),
    ("каталог установки", "installation directory"),
    ("корень USB", "USB root"),
])

_EN_RU = [
    ("TFTP receiver", "Приёмник TFTP"),
    ("block size", "размер блока"),
    ("Windows Firewall may ask for access.", "Брандмауэр Windows может запросить разрешение доступа."),
    ("Each dump is first stored as .part and appears under its final name only after gzip and size validation.", "Каждый дамп сначала сохраняется как .part и получает окончательное имя только после проверки gzip и размера."),
    ("OpenSSH client", "Клиент OpenSSH"),
    ("UART/BootROM recovery: C -> XMODEM -> stock backup", "Восстановление UART/BootROM: C -> XMODEM -> stock backup"),
    ("FTP user", "Пользователь FTP"),
    ("FTP password", "Пароль FTP"),
    ("Telnet user", "Пользователь Telnet"),
    ("UID 0 account", "Учётная запись UID 0"),
    ("IP recovery OpenWrt", "IP recovery OpenWrt"),
    ("IP transition OpenWrt", "IP transition OpenWrt"),
    ("UART write timeout", "Тайм-аут записи UART"),
    ("TFTP upload timeout", "Тайм-аут загрузки TFTP"),
    ("TFTP PUT timeout", "Тайм-аут TFTP PUT"),
    ("TFTP GET timeout", "Тайм-аут TFTP GET"),
    ("TFTP client returned ERROR", "Клиент TFTP вернул ERROR"),
    ("WARNING", "ПРЕДУПРЕЖДЕНИЕ"),
]


def ensure_language() -> str:
    global _LANG
    if _LANG:
        os.environ["NOKIA_LANG"] = _LANG
        return _LANG
    _RAW_PRINT("Select language / Выберите язык:")
    _RAW_PRINT("  1. RUS")
    _RAW_PRINT("  2. ENG")
    while True:
        value = _RAW_INPUT("RUS or ENG [1/2]: ").strip().lower()
        if value in ("1", "ru", "rus", "russian", "рус", "русский"):
            _LANG = "ru"
            break
        if value in ("2", "en", "eng", "english"):
            _LANG = "en"
            break
        _RAW_PRINT("Invalid choice / Неверный выбор.")
    os.environ["NOKIA_LANG"] = _LANG
    return _LANG


def tr(ru: str, en: str) -> str:
    return en if ensure_language() == "en" else ru


def transition_lan_policy_notice() -> None:
    """Operator-visible safety policy for every transition/recovery network path."""
    print(tr(
        "[NETWORK POLICY] LAN1 / 2.5G исключён из transition/recovery из-за нестабильности. Подключайте ПК только к LAN2, LAN3 или LAN4.",
        "[NETWORK POLICY] LAN1 / 2.5G is excluded from transition/recovery because it is unstable. Connect the PC only to LAN2, LAN3, or LAN4.",
    ))


def _replace_catalog(text: str, catalog: list[tuple[str, str]]) -> str:
    for source, target in sorted(catalog, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(source, target)
    return text


def localize_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    lang = ensure_language()
    return _replace_catalog(value, _RU_EN if lang == "en" else _EN_RU)


def _localized_print(*args, **kwargs):
    values = []
    for arg in args:
        value = localize_text(arg)
        values.append(colorize_text(value) if isinstance(value, str) else value)

    # Timestamp only operator console/stderr output. Prints intentionally directed
    # to another file retain their exact original format.
    target = kwargs.get("file")
    if target is None or target is sys.stdout or target is sys.stderr:
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        rendered = sep.join(str(value) for value in values)
        return _RAW_PRINT(rendered, end=end, **kwargs)
    return _RAW_PRINT(*values, **kwargs)


def _log_prompt_newline() -> None:
    """Terminate an input prompt in PC logs without adding a blank console line."""
    global _LOG_AT_LINE_START
    _LOG_AT_LINE_START = True
    for fh in _SESSION_FILES:
        try:
            fh.write("\n")
            fh.flush()
        except Exception:
            pass


def _localized_input(prompt: str = "") -> str:
    # The prompt goes through sys.stdout, so the tee stamps the log copy of it.
    value = _RAW_INPUT(colorize_text(str(localize_text(prompt))))
    _log_prompt_newline()
    return value


def _localized_getpass(prompt: str = "Password: ", stream=None) -> str:
    localized = colorize_text(str(localize_text(prompt)))
    if os.environ.get("NOKIA_HIDE_PASSWORDS", "").strip().lower() in ("1", "yes", "true"):
        value = _RAW_GETPASS(localized, stream=stream)
    else:
        # Passwords are visible while typed by request. Terminal echo is not
        # generated by Python and therefore is not copied into PC session logs.
        value = _RAW_INPUT(localized)
    _log_prompt_newline()
    return value


print = _localized_print
input = _localized_input
getpass.getpass = _localized_getpass


def _console_can_prompt() -> bool:
    """True when a real operator console is attached to this process.

    ssh reads a password from the terminal, so "ask for the password" only makes
    sense while someone can type into it. Under a pipe, a service or CI the same
    call turns into an invisible wait that ends at the timeout, which is exactly
    the failure this guard exists to prevent. Selftests drive the wizard through
    a pipe and therefore always stay on the non-interactive path.
    """
    if os.environ.get("NOKIA_NONINTERACTIVE", "").strip().lower() in ("1", "yes", "true"):
        return False
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return False
        return bool(getattr(sys.stdout, "isatty", lambda: False)())
    except Exception:
        return False


class Error(RuntimeError):
    def __str__(self) -> str:
        return str(localize_text(super().__str__()))


class TransportError(Error):
    """A restore transport failed before any NAND write command was issued."""


class WriteStateUnknownError(Error):
    """The NAND write command was issued but completion/readback is unproven."""


# RC24 interactive navigation state. A WRITE_STATE_UNKNOWN failure must never
# turn a friendly menu return into permission to repeat a destructive action.
# The latch keeps the process alive for diagnostics/backup/UART recovery while
# blocking normal install/no-UART write paths until a full UART recovery succeeds.
_INTERACTIVE_DESTRUCTIVE_LATCH: dict[str, object] = {"blocked": False, "reason": ""}
_WIZARD_RECOVERABLE_ERRORS = (Error, OSError, EOFError, ftplib.Error, subprocess.SubprocessError)


def _set_interactive_destructive_latch(exc: BaseException) -> None:
    _INTERACTIVE_DESTRUCTIVE_LATCH["blocked"] = True
    _INTERACTIVE_DESTRUCTIVE_LATCH["reason"] = str(exc).replace("\n", " ")[-1200:]
    print(tr(
        "[SAFETY-LATCH] Состояние NAND после write не доказано. Обычная установка, no-UART restore и продолжение destructive stage заблокированы в этом запуске. Доступны read-only диагностика/backup и полный BootROM/UART recovery.",
        "[SAFETY-LATCH] NAND state after a write is unproven. Normal installation, no-UART restore, and destructive-stage continuation are blocked for this process. Read-only diagnostics/backup and full BootROM/UART recovery remain available.",
    ))


def _clear_interactive_destructive_latch() -> None:
    if _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
        print(tr(
            "[SAFETY-LATCH] Полный BootROM/UART recovery завершён; блокировка destructive menu снята.",
            "[SAFETY-LATCH] Full BootROM/UART recovery completed; the destructive-menu latch is cleared.",
        ))
    _INTERACTIVE_DESTRUCTIVE_LATCH["blocked"] = False
    _INTERACTIVE_DESTRUCTIVE_LATCH["reason"] = ""


def _interactive_navigation_prompt(section_ru: str, section_en: str, *, failed: bool) -> str:
    """Return section/main/exit after an interactive action without ending Python."""
    print()
    if failed:
        print(tr(
            "[NAV] Задание завершилось ошибкой. Скрипт остаётся запущенным.",
            "[NAV] The task ended with an error. The script remains running.",
        ))
    else:
        print(tr(
            "[NAV] Задание завершено. Скрипт остаётся запущенным.",
            "[NAV] The task is complete. The script remains running.",
        ))
    # The [NAV] status lines above stay timestamped: they report when the action
    # actually ended. Only the selector itself is rendered as menu text.
    print(tr(f"1 — вернуться: {section_ru}", f"1 — back: {section_en}"))
    print(tr("2 — в главное меню", "2 — main menu"))
    print(tr("3 — выход", "3 — exit"))
    while True:
        choice = input(tr("Выберите 1/2/3 [1]: ", "Select 1/2/3 [1]: ")).strip().lower() or "1"
        if choice in {"1", "b", "back", "назад"}:
            return "section"
        if choice in {"2", "m", "main", "menu", "главное"}:
            return "main"
        if choice in {"3", "q", "quit", "exit", "выход"}:
            return "exit"
        print(tr("Неверный выбор. Скрипт не закрывается; выберите 1, 2 или 3.", "Invalid selection. The script remains open; select 1, 2, or 3."))


def _run_interactive_action(action, *, label_ru: str, label_en: str, section_ru: str, section_en: str) -> tuple[str, bool]:
    """Run one wizard action and convert ordinary failures into menu navigation.

    KeyboardInterrupt intentionally remains process-level: interrupting a NAND
    operation cannot safely be reinterpreted as a normal menu cancellation.
    Direct CLI subcommands also do not use this helper and keep their exit codes.
    """
    failed = False
    try:
        action()
        print(tr(f"[DONE] {label_ru}", f"[DONE] {label_en}"))
    except WriteStateUnknownError as exc:
        failed = True
        print(f"\nERROR: {exc}", file=sys.stderr)
        _set_interactive_destructive_latch(exc)
    except _WIZARD_RECOVERABLE_ERRORS as exc:
        failed = True
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(tr(
            "[SAFE] Ошибка сама по себе не разрешает повторять destructive action или отключать питание. Все существующие state/content gates остаются обязательными.",
            "[SAFE] An error by itself does not authorize repeating a destructive action or removing power. All existing state/content gates remain mandatory.",
        ))
    return _interactive_navigation_prompt(section_ru, section_en, failed=failed), not failed


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_exact_artifact(path: Path, expected_size: int, expected_sha: str, label: str) -> None:
    if not path.is_file():
        raise Error(tr(f"отсутствует {label}: {path}", f"missing {label}: {path}"))
    size = path.stat().st_size
    if size != expected_size:
        raise Error(tr(
            f"{label}: размер {size}, ожидается {expected_size}",
            f"{label}: size {size}, expected {expected_size}",
        ))
    actual = sha_file(path)
    if actual != expected_sha:
        raise Error(tr(
            f"{label}: SHA256 {actual}, ожидается {expected_sha}",
            f"{label}: SHA256 {actual}, expected {expected_sha}",
        ))


def _mf_artifact_spec() -> tuple[tuple[str, int, str, str], ...]:
    return (
        (MF_RECOVERY_PRELOADER_NAME, MF_RECOVERY_PRELOADER_SIZE, MF_RECOVERY_PRELOADER_SHA, "AN7583 preloader"),
        (MF_RECOVERY_FIP_NAME, MF_RECOVERY_FIP_SIZE, MF_RECOVERY_FIP_SHA, "AN7583 RC18 RECOVERY_SAFE BL31+U-Boot FIP"),
    )


def _load_mf_snapshot_metadata() -> dict:
    try:
        meta = json.loads(MF_RECOVERY_METADATA.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise Error(tr(
            f"не удалось прочитать {MF_RECOVERY_METADATA.relative_to(KIT)}: {exc}",
            f"failed to read {MF_RECOVERY_METADATA.relative_to(KIT)}: {exc}",
        )) from exc
    if meta.get("target") != "airoha/an7583" or meta.get("source") != MF_RECOVERY_BASE_URL:
        raise Error(tr(
            "metadata MF recovery указывает неожиданный target/source",
            "MF recovery metadata points to an unexpected target/source",
        ))
    artifacts = meta.get("artifacts", {})
    expected = {
        "preloader": (MF_RECOVERY_PRELOADER_NAME, MF_RECOVERY_PRELOADER_SIZE, MF_RECOVERY_PRELOADER_SHA),
        "fip": (MF_RECOVERY_FIP_NAME, MF_RECOVERY_FIP_SIZE, MF_RECOVERY_FIP_SHA),
    }
    for key, (name, size, digest) in expected.items():
        entry = artifacts.get(key, {})
        if entry.get("file") != name or int(entry.get("size", -1)) != size or entry.get("sha256") != digest:
            raise Error(tr(
                f"metadata MF recovery не совпадает с кодом для {key}",
                f"MF recovery metadata does not match the code for {key}",
            ))
    return meta


def _bundled_pinned_mf_recovery_artifact(name: str, expected_size: int, expected_sha: str, label: str) -> Path:
    """Resolve one release-pinned MF RAM stage from the full rollup only.

    The BootROM/XMODEM recovery path is hardware-confirmed, but critical stage
    bytes are versioned independently.  The full rollup therefore carries the
    exact release-pinned stages and verifies local size/SHA256 before COM/XMODEM;
    missing or changed bytes fail closed and are never fetched at runtime.
    """
    bundled = MF_RECOVERY_DIR / name
    print(tr(
        f"[CHECK] {label}: проверяю bundled stage и SHA256...",
        f"[CHECK] {label}: verifying bundled stage and SHA256...",
    ))
    try:
        _verify_exact_artifact(bundled, expected_size, expected_sha, label)
    except Error as exc:
        raise Error(tr(
            f"{label}: полный MedveFlasher rollup неполон или повреждён; "
            "аварийный recovery не скачивает boot stages из сети. "
            f"Нужен bundled файл {name} с закреплённым SHA256. Причина: {exc}",
            f"{label}: the full MedveFlasher rollup is incomplete or corrupt; "
            "emergency recovery never downloads boot stages from the network. "
            f"The bundled file {name} with the pinned SHA256 is required. Cause: {exc}",
        )) from exc
    print(tr(f"[OK] {label}: bundled SHA256 подтверждён.", f"[OK] {label}: bundled SHA256 verified."))
    return bundled


def recovery_profile_for_family(family: str) -> dict[str, object]:
    if family == "md":
        return {
            "family": "md",
            "model": "Nokia XG-040G-MD",
            "soc": "AN7581",
            "preloader": RECOVERY_PRELOADER,
            "fip": RECOVERY_FIP,
            "initramfs": RECOVERY_INITRAMFS,
            "preloader_sha": RECOVERY_PRELOADER_SHA,
            "fip_sha": RECOVERY_FIP_SHA,
            "initramfs_sha": RECOVERY_INITRAMFS_SHA,
            "backup_initramfs": RECOVERY_INITRAMFS,
            "backup_initramfs_sha": RECOVERY_INITRAMFS_SHA,
            "allow_linux_fallback": False,
        }
    if family != "mf":
        raise Error(tr(
            "backup не распознан как известный stock-профиль MD или MF; XMODEM recovery запрещён",
            "backup was not recognized as a known MD or MF stock profile; XMODEM recovery is blocked",
        ))
    _load_mf_snapshot_metadata()
    resolved = {}
    # Hardware-confirmed AN7583 BootROM stages are release payloads, not runtime
    # downloads.  Snapshot metadata is provenance only; emergency recovery is
    # network-independent until RAM U-Boot is ready for the stock TFTP restore.
    for name, size, digest, label in _mf_artifact_spec():
        resolved[name] = _bundled_pinned_mf_recovery_artifact(name, size, digest, label)
    return {
        "family": "mf",
        "model": "Nokia XG-040G-MF",
        "soc": "AN7583",
        "preloader": resolved[MF_RECOVERY_PRELOADER_NAME],
        "fip": resolved[MF_RECOVERY_FIP_NAME],
        "initramfs": MF_STOCK_RECOVERY_INITRAMFS,
        "preloader_sha": MF_RECOVERY_PRELOADER_SHA,
        "fip_sha": MF_RECOVERY_FIP_SHA,
        "initramfs_sha": MF_STOCK_RECOVERY_INITRAMFS_SHA,
        "backup_initramfs": MF_STOCK_RECOVERY_INITRAMFS,
        "backup_initramfs_sha": MF_STOCK_RECOVERY_INITRAMFS_SHA,
        # The first MF brick-recovery release writes stock directly in RAM
        # U-Boot.  It deliberately does not enter the MD-specific Linux
        # recovery fallback when U-Boot capture is missed.
        "allow_linux_fallback": False,
    }


def bundle_release_metadata(bundle_path: Path = BUNDLE) -> dict[str, int | str]:
    raw = bundle_path.read_bytes()
    if len(raw) < 8:
        raise Error(tr("transition bundle слишком мал", "transition bundle is too small"))
    magic, fit_size = struct.unpack(">II", raw[:8])
    if magic != 0xD00DFEED or fit_size < 8 or fit_size > len(raw):
        raise Error(tr("transition bundle не начинается с корректного FIT", "transition bundle does not begin with a valid FIT"))
    manifest_path = DATA / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_info = manifest["manual_bundle" if bundle_path == MANUAL_BUNDLE else "bundle"]
        production_size = int(bundle_info["production_size"])
        production_sha = str(bundle_info["production_sha256"])
        production_offset = int(bundle_info.get("production_offset_in_bundle", 0x800000))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Error(tr(
            f"не удалось прочитать metadata bundle из MANIFEST.json: {exc}",
            f"failed to read bundle metadata from MANIFEST.json: {exc}",
        )) from exc
    window_size = 0x800000
    if production_offset != window_size:
        raise Error(tr(
            "неожиданный offset embedded sysupgrade в MANIFEST.json",
            "unexpected embedded sysupgrade offset in MANIFEST.json",
        ))
    if production_offset + production_size > len(raw):
        raise Error(tr(
            "embedded sysupgrade выходит за границы transition bundle",
            "embedded sysupgrade extends beyond the transition bundle",
        ))
    production = raw[production_offset:production_offset + production_size]
    actual_production_sha = hashlib.sha256(production).hexdigest()
    if actual_production_sha != production_sha:
        raise Error(tr(
            "SHA256 embedded sysupgrade не совпадает с MANIFEST.json",
            "embedded sysupgrade SHA256 does not match MANIFEST.json",
        ))
    return {
        "bundle_size": len(raw),
        "bundle_sha": hashlib.sha256(raw).hexdigest(),
        "transition_fit_size": fit_size,
        "transition_fit_sha": hashlib.sha256(raw[:fit_size]).hexdigest(),
        "transition_window_sha": hashlib.sha256(raw[:window_size]).hexdigest(),
        "production_size": production_size,
        "production_sha": production_sha,
    }


def mf_transition_release_metadata(bundle_path: Path = MF_TRANSITION_BUNDLE) -> dict[str, int | str]:
    raw = bundle_path.read_bytes()
    manual = bundle_path == MF_MANUAL_TRANSITION_BUNDLE
    exp_size = EXPECTED_MF_MANUAL_TRANSITION_BUNDLE_SIZE if manual else EXPECTED_MF_TRANSITION_BUNDLE_SIZE
    exp_sha = EXPECTED_MF_MANUAL_TRANSITION_BUNDLE_SHA if manual else EXPECTED_MF_TRANSITION_BUNDLE_SHA
    exp_fit_size = EXPECTED_MF_MANUAL_TRANSITION_FIT_SIZE if manual else EXPECTED_MF_TRANSITION_FIT_SIZE
    exp_fit_sha = EXPECTED_MF_MANUAL_TRANSITION_FIT_SHA if manual else EXPECTED_MF_TRANSITION_FIT_SHA
    if len(raw) != exp_size:
        raise Error(tr("размер MF transition bundle не совпадает с релизом", "MF transition bundle size does not match this release"))
    if len(raw) < 8 or struct.unpack(">I", raw[:4])[0] != 0xD00DFEED:
        raise Error(tr("MF transition bundle не начинается с FIT", "MF transition bundle does not begin with a FIT"))
    fit_size = struct.unpack(">I", raw[4:8])[0]
    if fit_size != exp_fit_size:
        raise Error(tr("FIT totalsize MF transition не совпадает с релизом", "MF transition FIT totalsize does not match this release"))
    bundle_sha = hashlib.sha256(raw).hexdigest()
    fit_sha = hashlib.sha256(raw[:fit_size]).hexdigest()
    window_sha = hashlib.sha256(raw[:0x800000]).hexdigest()
    if bundle_sha != exp_sha or fit_sha != exp_fit_sha:
        raise Error(tr("SHA256 MF transition bundle не совпадает с релизом", "MF transition bundle SHA256 does not match this release"))
    if manual:
        production_size = 0
        production_sha = ""
        if window_sha != exp_sha:
            raise Error(tr("SHA256 MF manual transition window не совпадает", "MF manual transition window SHA256 mismatch"))
    else:
        if window_sha != EXPECTED_MF_TRANSITION_WINDOW_SHA:
            raise Error(tr("SHA256 первых 8 MiB MF transition не совпадает", "MF transition 8 MiB window SHA256 mismatch"))
        production_size = MF_UBI_SYSUPGRADE_SIZE
        production_sha = hashlib.sha256(raw[0x800000:0x800000 + production_size]).hexdigest()
        if production_sha != MF_UBI_SYSUPGRADE_SHA:
            raise Error(tr("embedded MF sysupgrade SHA256 не совпадает", "embedded MF sysupgrade SHA256 mismatch"))
    return {
        "bundle_size": len(raw), "bundle_sha": bundle_sha,
        "transition_fit_size": fit_size, "transition_fit_sha": fit_sha,
        "transition_window_sha": window_sha,
        "production_size": production_size, "production_sha": production_sha,
    }


def transition_release_metadata(profile: InstallProfile, bundle_path: Path) -> dict[str, int | str]:
    """Return pinned metadata for either board using the same installer contract."""
    if profile.family == "mf":
        return mf_transition_release_metadata(bundle_path)
    if profile.family == "md":
        return bundle_release_metadata(bundle_path)
    raise Error(tr("неизвестный install profile", "unknown install profile"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def _verify_recovery_safe_fip(
    path: Path,
    expected_bl31_compressed_sha: str,
    expected_bl33_compressed_sha: str,
    label: str,
) -> None:
    """Verify the exact shipped RECOVERY_SAFE FIP without host-side decode.

    Runtime preflight already pins the whole FIP by size+SHA256.  Decoding BL33
    again on the operator PC is redundant and made the first RC18 package
    dependent on liblzma implementation details.  Build/release QA performs the
    full decode and marker audit; runtime only proves FIP structure and exact
    compressed payload identities.
    """
    data = path.read_bytes()
    if len(data) < 96 or struct.unpack_from("<I", data, 0)[0] != 0xAA640001:
        raise Error(f"{label}: invalid FIP header")
    entries: list[tuple[int, int]] = []
    pos = 16
    while pos + 40 <= len(data):
        uuid = data[pos:pos+16]
        offset, size, _flags = struct.unpack_from("<QQQ", data, pos+16)
        if uuid == b"\x00" * 16:
            break
        if offset + size > len(data):
            raise Error(f"{label}: FIP entry outside file")
        entries.append((offset, size))
        pos += 40
    if len(entries) != 2:
        raise Error(f"{label}: expected exactly BL31+BL33 FIP entries")
    bl31 = data[entries[0][0]:entries[0][0]+entries[0][1]]
    bl33 = data[entries[1][0]:entries[1][0]+entries[1][1]]
    if hashlib.sha256(bl31).hexdigest() != expected_bl31_compressed_sha:
        raise Error(f"{label}: BL31 payload changed")
    if hashlib.sha256(bl33).hexdigest() != expected_bl33_compressed_sha:
        raise Error(f"{label}: RECOVERY_SAFE BL33 payload changed")
    if len(bl33) < 13 or bl33[0] != 0x5D:
        raise Error(f"{label}: BL33 is not LZMA-Alone")
    raw_size = struct.unpack_from("<Q", bl33, 5)[0]
    if raw_size in (0, 0xFFFFFFFFFFFFFFFF):
        raise Error(f"{label}: BL33 must carry a known uncompressed size")


def verify_kit() -> None:
    root_version = KIT / "VERSION"
    data_version = DATA / "VERSION"
    manifest_path = DATA / "MANIFEST.json"
    required = (root_version, data_version, manifest_path, BUNDLE, MANUAL_BUNDLE, MF_TRANSITION_BUNDLE, MF_MANUAL_TRANSITION_BUNDLE, LAUNCHER_TEMPLATE, BACKUP_AGENT, STOCK_WEB, DATA / "env_patcher.py", RECOVERY_PRELOADER, RECOVERY_FIP, RECOVERY_INITRAMFS, MF_RECOVERY_METADATA, MF_RECOVERY_PRELOADER, MF_RECOVERY_FIP, MF_STOCK_RECOVERY_INITRAMFS, STOCK_AUDIT_SCRIPT, STOCK_AUDIT_PARSER, FIRMWARE_CAPABILITIES, RECOVERY_DIR / "transition-network-source" / "patch_transition_network.py", RECOVERY_DIR / "recovery-clients-source" / "patch_recovery_clients.py", RECOVERY_TFTP_CLIENT, RECOVERY_SCP_CLIENT, RECOVERY_DIR / "transition-network-source" / "shipped-md-02_network.sh", RECOVERY_DIR / "transition-network-source" / "shipped-mf-02_network.sh", RECOVERY_DIR / "recovery-safe-uboot-source" / "patch_recovery_safe_fip.py", RECOVERY_DIR / "recovery-safe-uboot-source" / "lzma1ext_noeopm.c", RECOVERY_DIR / "recovery-safe-uboot-source" / "md-rc18-safe-fip-report.json", RECOVERY_DIR / "recovery-safe-uboot-source" / "mf-rc18-safe-fip-report.json", VENDOR / "rich" / "__init__.py", VENDOR / "RICH_LICENSE.txt")
    for path in required:
        if not path.is_file():
            raise Error(f"повреждён комплект: отсутствует {path.relative_to(KIT)}")
    for template_name in ("shipped-md-02_network.sh", "shipped-mf-02_network.sh"):
        template_path = RECOVERY_DIR / "transition-network-source" / template_name
        template_text = template_path.read_text(encoding="ascii")
        if "lan1" in template_text.lower() or "lan2 lan3 lan4" not in template_text:
            raise Error(tr(
                f"transition network policy нарушена в {template_name}: LAN1/2.5G должен быть исключён, LAN2-LAN4 обязательны",
                f"transition network policy is violated in {template_name}: LAN1/2.5G must be excluded and LAN2-LAN4 are required",
            ))
    root_version_text = root_version.read_text(encoding="utf-8").strip()
    data_version_text = data_version.read_text(encoding="utf-8").strip()
    if root_version_text != APP_VERSION or data_version_text != APP_VERSION:
        raise Error(tr(
            f"VERSION/data/VERSION не совпадают с кодом {APP_VERSION}",
            f"VERSION/data/VERSION do not match code version {APP_VERSION}",
        ))
    try:
        release_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise Error(tr(f"не удалось прочитать MANIFEST.json: {exc}", f"failed to read MANIFEST.json: {exc}")) from exc
    if release_manifest.get("version") != APP_VERSION or release_manifest.get("build_tag") != BUILD_TAG:
        raise Error(tr(
            "MANIFEST.json version/build_tag не совпадают с кодом",
            "MANIFEST.json version/build_tag do not match the code",
        ))
    # The nested release block is what the release workflow stamps onto the
    # archive.  Leaving it unchecked is exactly how two materially different
    # builds end up shipping under one version string.
    release_block = release_manifest.get("release") or {}
    if (release_block.get("version") != APP_VERSION
            or release_block.get("build_tag") != BUILD_TAG
            or release_block.get("archive_root") != f"Nokia-Router-MedveFlasher-{APP_VERSION}"):
        raise Error(tr(
            "MANIFEST.json release.version/build_tag/archive_root не совпадают с кодом",
            "MANIFEST.json release.version/build_tag/archive_root do not match the code",
        ))
    _verify_exact_artifact(RECOVERY_TFTP_CLIENT, 7792, RECOVERY_TFTP_CLIENT_SHA, "pinned AArch64 nokia-tftp")
    _verify_exact_artifact(RECOVERY_SCP_CLIENT, 6072, RECOVERY_SCP_CLIENT_SHA, "pinned AArch64 nokia-scp")
    _verify_exact_artifact(RECOVERY_PRELOADER, 113447, RECOVERY_PRELOADER_SHA, "AN7581 preloader")
    _verify_exact_artifact(RECOVERY_FIP, RECOVERY_FIP_SIZE, RECOVERY_FIP_SHA, "AN7581 RC18 RECOVERY_SAFE BL31+U-Boot FIP")
    _verify_recovery_safe_fip(RECOVERY_FIP, "a81dbbe98acb1dabc2afcbf72e73ad87e24efa8dd88e559612a024c28ece920e", "df4803b9f70bb35050555947268fc35d61f1724814a1ea59b480689f056fa123", "AN7581 RC18 RECOVERY_SAFE FIP")
    _load_mf_snapshot_metadata()
    _verify_exact_artifact(MF_RECOVERY_PRELOADER, MF_RECOVERY_PRELOADER_SIZE, MF_RECOVERY_PRELOADER_SHA, "AN7583 preloader")
    _verify_exact_artifact(MF_RECOVERY_FIP, MF_RECOVERY_FIP_SIZE, MF_RECOVERY_FIP_SHA, "AN7583 RC18 RECOVERY_SAFE BL31+U-Boot FIP")
    _verify_recovery_safe_fip(MF_RECOVERY_FIP, "6d97815b5cdf905eff874062f9364ebe41a2a11f4b25944a82aea4fcbdd71e35", "3bb4cf1aa950dd212e1b5781abf55c239ff61326d5ca0c19e9f2c010285f5bb1", "AN7583 RC18 RECOVERY_SAFE FIP")
    try:
        capability_manifest = json.loads(FIRMWARE_CAPABILITIES.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise Error(tr(f"не удалось прочитать FIRMWARE_CAPABILITIES.json: {exc}", f"failed to read FIRMWARE_CAPABILITIES.json: {exc}")) from exc
    if capability_manifest.get("version") != APP_VERSION:
        raise Error(tr("FIRMWARE_CAPABILITIES.json version не совпадает с кодом", "FIRMWARE_CAPABILITIES.json version does not match the code"))
    if BUNDLE.stat().st_size != EXPECTED_BUNDLE_SIZE:
        raise Error("размер transition bundle не совпадает с релизом")
    if sha_file(BUNDLE) != EXPECTED_BUNDLE_SHA:
        raise Error("SHA256 transition bundle не совпадает с релизом")
    if MANUAL_BUNDLE.stat().st_size != EXPECTED_MANUAL_BUNDLE_SIZE:
        raise Error("размер manual transition bundle не совпадает с релизом")
    if sha_file(MANUAL_BUNDLE) != EXPECTED_MANUAL_BUNDLE_SHA:
        raise Error("SHA256 manual transition bundle не совпадает с релизом")
    # Both boards use one stock launcher template. Bundle/env/profile values are
    # personalized from InstallProfile; the template must expose every placeholder.
    launcher_template = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    for key in (
        "PROFILE_FAMILY", "PROFILE_LABEL", "RELEASE_VERSION", "BUNDLE_NAME", "ENV_NAME",
        "BUNDLE_SIZE", "BUNDLE_SHA", "TRANSITION_TOTALSIZE", "TRANSITION_FIT_SHA",
        "TRANSITION_WINDOW_SHA", "SYSUPGRADE_SIZE", "SYSUPGRADE_SHA",
        "MANUAL_TRANSITION", "ENV_SHA", "ENV_SOURCE_SHA",
    ):
        if not re.search(rf"^{key}=", launcher_template, flags=re.M):
            raise Error(tr(
                f"общий launcher не содержит поле {key}",
                f"shared launcher does not contain field {key}",
            ))
    # Validate both ready-made board bundles independently. No runtime repacking.
    bundle_metadata = {
        "bundle": bundle_release_metadata(BUNDLE),
        "manual_bundle": bundle_release_metadata(MANUAL_BUNDLE),
        "mf_transition_bundle": mf_transition_release_metadata(MF_TRANSITION_BUNDLE),
        "mf_manual_transition_bundle": mf_transition_release_metadata(MF_MANUAL_TRANSITION_BUNDLE),
    }
    # RC16 regression gate: release metadata must describe the exact shipped FIT/bundle,
    # not merely a historically correct SHA.  This catches the stale rc15fix MF
    # transition_fit_totalsize fields before a rollup can pass verify_kit().
    for section, actual in bundle_metadata.items():
        info = release_manifest.get(section, {})
        checks = (
            ("size", int(actual["bundle_size"])),
            ("sha256", str(actual["bundle_sha"])),
            ("transition_fit_totalsize", int(actual["transition_fit_size"])),
            ("production_size", int(actual["production_size"])),
            ("production_sha256", str(actual["production_sha"])),
        )
        for field, expected_actual in checks:
            declared = info.get(field)
            if field in ("size", "transition_fit_totalsize", "production_size"):
                try:
                    declared = int(declared)
                except (TypeError, ValueError):
                    declared = None
            if declared != expected_actual:
                raise Error(tr(
                    f"MANIFEST.json {section}.{field} не совпадает с shipped bundle: {declared!r} != {expected_actual!r}",
                    f"MANIFEST.json {section}.{field} does not match the shipped bundle: {declared!r} != {expected_actual!r}",
                ))
        declared_fit_sha = info.get("transition_fit_sha256")
        if declared_fit_sha != actual["transition_fit_sha"]:
            raise Error(tr(
                f"MANIFEST.json {section}.transition_fit_sha256 не совпадает с shipped FIT",
                f"MANIFEST.json {section}.transition_fit_sha256 does not match the shipped FIT",
            ))
    _verify_exact_artifact(RECOVERY_INITRAMFS, RECOVERY_INITRAMFS_SIZE, RECOVERY_INITRAMFS_SHA, "AN7581/MD Dark-derived stock-recovery initramfs")
    recovery_expected = {
        RECOVERY_PRELOADER: RECOVERY_PRELOADER_SHA,
        RECOVERY_FIP: RECOVERY_FIP_SHA,
        RECOVERY_INITRAMFS: RECOVERY_INITRAMFS_SHA,
        MF_STOCK_RECOVERY_INITRAMFS: MF_STOCK_RECOVERY_INITRAMFS_SHA,
    }
    _load_mf_snapshot_metadata()
    for path, expected in recovery_expected.items():
        if sha_file(path) != expected:
            raise Error(f"SHA256 recovery-артефакта не совпадает: {path.name}")


def find_dump(directory: Path, number: int) -> Path | None:
    hits: list[Path] = []
    patterns = (
        f"mtd{number}.bin.gz", f"mtd{number}_*.bin.gz", f"mtd{number}.gz",
        f"mtd{number}.bin", f"mtd{number}_*.bin",
    )
    for pattern in patterns:
        hits.extend(directory.glob(pattern))
    return sorted(set(hits))[0] if hits else None


def read_dump(path: Path) -> bytes:
    raw = path.read_bytes()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def parse_proc_mtd_text(text: str) -> dict[int, tuple[int, int, str]]:
    out: dict[int, tuple[int, int, str]] = {}
    pattern = re.compile(r'^mtd(\d+):\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+"([^"]+)"$')
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            out[int(match.group(1))] = (
                int(match.group(2), 16), int(match.group(3), 16), match.group(4)
            )
    return out


def verify_manifest(directory: Path) -> list[str]:
    manifest = next((p for p in (directory / "SHA256SUMS", directory / "SHA256SUMS.txt") if p.exists()), None)
    if not manifest:
        return ["Нет SHA256SUMS; файлы будут проверены по gzip и точным размерам."]
    checked = 0
    for line in manifest.read_text(errors="replace").splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", line.strip())
        if not match:
            continue
        digest, name = match.groups()
        path = directory / name
        if not path.exists():
            raise Error(f"в manifest отсутствует файл: {name}")
        if sha_file(path).lower() != digest.lower():
            raise Error(f"SHA256 не совпал: {name}")
        checked += 1
    if not checked:
        raise Error("SHA256SUMS не содержит пригодных записей")
    return []


def _layout_matches(sizes: dict[int, int], layout: dict[int, int]) -> bool:
    return all(sizes.get(number) == expected for number, expected in layout.items())


def _stock_slot_orientation(sizes: dict[int, int]) -> tuple[str, tuple[int, int]] | None:
    """Split mtd2..mtd5 into the canonical pair and the revision-dependent pair.

    Returns ``(orientation, revision_pair)``, or None when neither slot carries
    the canonical pair — that is not a stock slot arrangement at all and must
    stay unrecognised regardless of how close the numbers look.
    """
    master = (sizes.get(2), sizes.get(3))
    slave = (sizes.get(4), sizes.get(5))
    if None in master or None in slave:
        return None
    if slave == STOCK_SLOT_CANONICAL_PAIR:
        return "A", master
    if master == STOCK_SLOT_CANONICAL_PAIR:
        return "A-MIRROR", slave
    return None


def _revision_pair_match(pair: tuple[int, int]) -> tuple[str, str]:
    """Classify a revision-dependent kernel/rootfs pair, fail-closed on doubt.

    Returns ``(family, profile)`` — the profile being the vendor letter of the
    single reference the pair falls closest to. An ambiguous pair returns
    ``("unknown", "")``: these sizes are the only MD/MF discriminator, and the
    wrong family selects the wrong firmware.
    """
    image, partition = pair
    if image <= 0 or partition <= image:
        return "unknown", ""
    if partition % STOCK_SLOT_PARTITION_GRANULARITY:
        return "unknown", ""
    matched = [
        (family, profile, abs(image - reference_image))
        for family, references in STOCK_SLOT_REVISION_REFERENCE.items()
        for profile, reference_image, reference_partition in references
        if abs(image - reference_image) <= STOCK_SLOT_IMAGE_TOLERANCE
        and abs(partition - reference_partition) <= STOCK_SLOT_PARTITION_TOLERANCE
    ]
    if not matched:
        return "unknown", ""
    if len({family for family, _profile, _distance in matched} - {""}) != 1:
        return "unknown", ""
    # Within one family several profiles can overlap; name the nearest.
    family, profile, _distance = min(matched, key=lambda item: item[2])
    return family, profile


def _revision_pair_family(pair: tuple[int, int]) -> str:
    """Family alone, for diagnostics that do not care which profile matched."""
    return _revision_pair_match(pair)[0]


def _stock_slot_match(sizes: dict[int, int]) -> tuple[str, str]:
    """Return ``(family, variant)`` for live or dumped stock slot sizes."""
    for label, layout in MD_SLOT_VARIANTS + MF_SLOT_VARIANTS:
        if _layout_matches(sizes, layout):
            return ("md" if label.startswith("MD") else "mf"), label
    orientation = _stock_slot_orientation(sizes)
    if orientation is None:
        return "unknown", "UNKNOWN"
    variant_prefix, revision_pair = orientation
    family, profile = _revision_pair_match(revision_pair)
    if family == "unknown":
        return "unknown", "UNKNOWN"
    # A tolerated match never reuses an exact label.  Exact labels remain useful
    # evidence for stock backup/restore diagnostics, but install authorization
    # is intentionally independent of the vendor slot revision.  The label names
    # the profile the revision resembles and the slot orientation separately:
    # deriving it from orientation alone reported every tolerated MF unit as
    # MF-A-REV, including ones sitting next to the MF-B reference.
    mirrored = "-MIRROR" if variant_prefix.endswith("MIRROR") else ""
    return family, f"{family.upper()}-{profile}{mirrored}-REV"


def detect_stock_backup_family(sizes: dict[int, int]) -> str:
    """Classify known stock slot layouts without weakening install validation."""
    return _stock_slot_match(sizes)[0]


def detect_stock_backup_variant(sizes: dict[int, int]) -> str:
    return _stock_slot_match(sizes)[1]


def _slot_layout_diagnostic(sizes: dict[int, int]) -> str:
    got = {n: sizes.get(n) for n in (2, 3, 4, 5)}
    candidates = MD_SLOT_VARIANTS + MF_SLOT_VARIANTS
    best_label = "none"
    best_diff = None
    for label, layout in candidates:
        diff = sum(abs((got.get(n) or 0) - layout[n]) for n in (2, 3, 4, 5))
        if best_diff is None or diff < best_diff:
            best_label, best_diff = label, diff
    formatted = ", ".join(f"mtd{n}=0x{(got.get(n) or 0):08X}" for n in (2,3,4,5))
    orientation = _stock_slot_orientation(sizes)
    if orientation is None:
        reason = (
            f"canonical pair 0x{STOCK_SLOT_CANONICAL_PAIR[0]:08X}/"
            f"0x{STOCK_SLOT_CANONICAL_PAIR[1]:08X} is on neither slot"
        )
    else:
        image, partition = orientation[1]
        matched_family = _revision_pair_family((image, partition))
        if matched_family in ("md", "mf"):
            reason = (
                f"{orientation[0]} orientation, revision pair "
                f"0x{image:08X}/0x{partition:08X} is inside the "
                f"{matched_family.upper()} recognition window"
            )
        else:
            reason = (
                f"{orientation[0]} orientation, revision pair "
                f"0x{image:08X}/0x{partition:08X} outside every family window"
            )
    return f"{formatted}; nearest={best_label}; {reason}"


def verify_backup(directory: Path, *, require_md_slot_layout: bool = True) -> dict:
    directory = directory.resolve()
    if not directory.is_dir():
        raise Error(f"backup-каталог не найден: {directory}")
    warnings = verify_manifest(directory)
    proc_path = next((p for p in (directory / "proc_mtd.txt", directory / "proc-mtd.txt") if p.exists()), None)
    proc = parse_proc_mtd_text(proc_path.read_text(errors="replace")) if proc_path else {}
    if not proc:
        warnings.append("Нет proc_mtd.txt; ориентация слотов определяется по размерам dump-файлов.")

    files: dict[int, Path] = {}
    sizes: dict[int, int] = {}
    for number in EXPECTED_NUMBERS:
        path = find_dump(directory, number)
        if not path:
            raise Error(f"неполный backup: отсутствует mtd{number}")
        try:
            with path.open("rb") as probe:
                magic = probe.read(2)
            with gzip.open(path, "rb") if magic == b"\x1f\x8b" else path.open("rb") as fh:
                total = 0
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
        except (OSError, EOFError) as exc:
            raise Error(f"повреждён mtd{number}: {exc}") from exc
        files[number] = path
        sizes[number] = total

    family = detect_stock_backup_family(sizes)
    variant = detect_stock_backup_variant(sizes)
    selected: dict[int, int] | None = None
    for layout in SLOT_LAYOUTS:
        if _layout_matches(sizes, layout):
            selected = layout
            break
    if selected is None and family in ("md", "mf"):
        # Revision-tolerant match for either family: pin the observed slot sizes
        # instead of a table entry, so the dump <-> /proc/mtd cross-check below
        # stays exact. The table above only walks the MD layouts, so without this
        # every MF backup — including the hardware-confirmed exact MF-A — used to
        # fall through to the rejection below.
        selected = {number: sizes[number] for number in (2, 3, 4, 5)}
    if require_md_slot_layout and selected is None:
        raise Error(tr(
            "stock-слоты mtd2..mtd5 не относятся ни к MD, ни к MF: " + _slot_layout_diagnostic(sizes),
            "the mtd2..mtd5 stock slots belong to neither MD nor MF: " + _slot_layout_diagnostic(sizes),
        ))

    expected = dict(FIXED_EXPECTED)
    if selected is not None:
        expected.update(selected)
    for number, size in sizes.items():
        # mtd2..mtd5 describe the vendor kernel/rootfs slot geometry.  The
        # brick-restore path uses canonical mtd16 and therefore validates those
        # slots only for family detection, not as a physical NAND invariant.
        if not require_md_slot_layout and number in (2, 3, 4, 5):
            continue
        if size != expected[number]:
            raise Error(f"mtd{number}: размер {size}, ожидается {expected[number]}")
    if proc:
        for number, expected_size in expected.items():
            if not require_md_slot_layout and number in (2, 3, 4, 5):
                continue
            if number not in proc or proc[number][0] != expected_size:
                raise Error(f"proc_mtd не совпадает с dump для mtd{number}")
    return {
        "directory": str(directory),
        "files": {str(k): str(v) for k, v in files.items()},
        "sizes": {str(k): v for k, v in sizes.items()},
        "stock_family": family,
        "stock_variant": variant,
        "warnings": warnings,
    }


def env_module():
    path = DATA / "env_patcher.py"
    spec = importlib.util.spec_from_file_location("nokia_env_patcher", path)
    if not spec or not spec.loader:
        raise Error("не удалось загрузить env_patcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_install_backup(profile: InstallProfile, backup_dir: Path) -> dict:
    """Validate the same complete stock backup invariant for MD and MF installs.

    Vendor slot sizes identify the stock family, but they do not authorize the
    later UBI format.  Both families therefore use the restore-grade validator:
    complete mtd0..mtd16 content, manifest/gzip integrity, canonical mtd16 span,
    stable raw-slice cross-checks, and stock-BL2 provenance.
    """
    validation = verify_stock_restore_backup(backup_dir)
    family = str(validation.get("stock_family") or "")
    if family != profile.family:
        raise Error(tr(
            f"backup не соответствует {profile.model}: family={family or 'unknown'}",
            f"backup does not match {profile.model}: family={family or 'unknown'}",
        ))
    return validation

def _print_install_backup_validation(profile: InstallProfile, backup_dir: Path, validation: dict) -> None:
    files = validation.get("files") or {}
    sizes = validation.get("sizes") or {}
    family = str(validation.get("stock_family") or "unknown").upper()
    variant = str(validation.get("stock_variant") or "UNKNOWN")
    present = sum(1 for n in EXPECTED_NUMBERS if str(n) in files)
    mtd16_size = int(sizes.get("16") or 0)
    checksum_file = next((backup_dir / name for name in ("SHA256SUMS", "SHA256SUMS.txt") if (backup_dir / name).is_file()), None)
    print(tr(
        f"[OK] Backup: mtd0..mtd16 {present}/{len(EXPECTED_NUMBERS)} на месте; gzip/raw читаются полностью.",
        f"[OK] Backup: mtd0..mtd16 {present}/{len(EXPECTED_NUMBERS)} present; gzip/raw streams read completely.",
    ))
    print(tr(
        f"[OK] Backup family/profile: {family} / {variant}; ожидаемый аппарат: {profile.model}.",
        f"[OK] Backup family/profile: {family} / {variant}; expected hardware: {profile.model}.",
    ))
    if mtd16_size:
        print(tr(
            f"[OK] Backup canonical mtd16 span: 0x{mtd16_size:08X} байт.",
            f"[OK] Backup canonical mtd16 span: 0x{mtd16_size:08X} bytes.",
        ))
    mac_info = _read_backup_device_mac(backup_dir / "DEVICE_MAC.txt")
    if mac_info is not None:
        interface, mac = mac_info
        print(tr(
            f"[OK] Backup source MAC: {mac} ({interface}); DEVICE_MAC.txt.",
            f"[OK] Backup source MAC: {mac} ({interface}); DEVICE_MAC.txt.",
        ))
    else:
        print(tr(
            "[INFO] Backup source MAC metadata отсутствует (старый формат backup); это не блокирует совместимость.",
            "[INFO] Backup source MAC metadata is absent (legacy backup format); compatibility is not blocked.",
        ))
    if checksum_file is not None:
        print(tr(
            f"[OK] Backup SHA256 manifest проверен: {checksum_file.name}.",
            f"[OK] Backup SHA256 manifest verified: {checksum_file.name}.",
        ))
    else:
        print(tr(
            "[WARNING] В backup нет SHA256SUMS; целостность подтверждена gzip и точными размерами, но manifest отсутствует.",
            "[WARNING] The backup has no SHA256SUMS; gzip integrity and exact sizes passed, but the manifest is absent.",
        ))
    for warning in validation.get("warnings") or []:
        print(tr(f"[WARNING] Backup: {warning}", f"[WARNING] Backup: {warning}"))


def personalize_transition(
    profile: InstallProfile,
    backup_dir: Path,
    force: bool = True,
    manual_transition: bool = False,
) -> tuple[Path, dict]:
    """Create one board-profiled installer package using the shared launcher engine."""
    validation = _validate_install_backup(profile, backup_dir)
    mtd0 = Path(validation["files"]["0"])
    module = env_module()
    env_data, report = module.create_image(module.read_input(mtd0), BOOTCMD)
    device_id = report["source_erase_block_sha256"][:16]
    device_root = WORK / device_id
    output = device_root / "install"
    if output.exists():
        if not force:
            raise Error(f"уже существует: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    selected_bundle = profile.manual_bundle if manual_transition else profile.auto_bundle
    metadata = transition_release_metadata(profile, selected_bundle)
    shutil.copy2(selected_bundle, output / profile.runtime_bundle_name)
    (output / profile.runtime_env_name).write_bytes(env_data)

    template = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    substitutions = {
        "PROFILE_FAMILY": f"'{profile.family}'",
        "PROFILE_LABEL": f"'{profile.model}'",
        "RELEASE_VERSION": f"'{APP_VERSION}'",
        "BUNDLE_NAME": f"'{profile.runtime_bundle_name}'",
        "ENV_NAME": f"'{profile.runtime_env_name}'",
        "BUNDLE_SIZE": str(metadata["bundle_size"]),
        "BUNDLE_SHA": f"'{metadata['bundle_sha']}'",
        "TRANSITION_TOTALSIZE": str(metadata["transition_fit_size"]),
        "TRANSITION_FIT_SHA": f"'{metadata['transition_fit_sha']}'",
        "TRANSITION_WINDOW_SHA": f"'{metadata['transition_window_sha']}'",
        "SYSUPGRADE_SIZE": str(metadata["production_size"]),
        "SYSUPGRADE_SHA": f"'{metadata['production_sha']}'",
        "MANUAL_TRANSITION": "1" if manual_transition else "0",
        "ENV_SHA": f"'{report['output_sha256']}'",
        "ENV_SOURCE_SHA": f"'{report['source_erase_block_sha256']}'",
    }
    for key, value in substitutions.items():
        template, count = re.subn(rf"^{key}=.*$", f"{key}={value}", template, count=1, flags=re.M)
        if count != 1:
            raise Error(tr(
                f"не удалось записать {key} в общий stock launcher",
                f"failed to write {key} into the shared stock launcher",
            ))
    if "@ENV_" in template:
        raise Error(tr("не удалось персонализировать общий launcher", "failed to personalize the shared launcher"))
    launcher = output / "INSTALL.sh"
    write_text(launcher, template)
    os.chmod(launcher, 0o755)

    info = {
        "kit_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_id": device_id,
        "family": profile.family,
        "model": profile.model,
        "variant": str(validation.get("stock_variant") or ""),
        "backup": validation,
        "environment": report,
        "bundle_sha256": metadata["bundle_sha"],
        "manual_transition": manual_transition,
        "production_sha256": metadata["production_sha"],
        "expected_board": profile.expected_board,
        "language": ensure_language(),
        "behavior": "shared profile-driven stock -> transition -> UBI install; BL2 last",
        "warning": tr(
            "Пакет привязан к одному устройству. Не публиковать env-файл.",
            "This package is bound to one device. Do not publish the environment file.",
        ),
    }
    write_text(output / "device.json", json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    sums = []
    for path in sorted(p for p in output.iterdir() if p.is_file() and p.name != "SHA256SUMS"):
        sums.append(f"{sha_file(path)}  {path.name}")
    write_text(output / "SHA256SUMS", "\n".join(sums) + "\n")
    write_text(output / "README.txt", tr(
        f"Персональный пакет {profile.model}. Используется общим MD/MF installer engine; BL2 записывается последней.\n",
        f"Device-specific {profile.model} package. Uses the shared MD/MF installer engine; BL2 is written last.\n",
    ))
    save_state(device_root / "state.json", {
        "version": APP_VERSION, "device_id": device_id, "family": profile.family,
        "phase": "personalized", "install_dir": str(output),
    })
    return output, info


def personalize(backup_dir: Path, force: bool = True, manual_transition: bool = False) -> tuple[Path, dict]:
    """Compatibility wrapper: MD now delegates to the shared engine."""
    return personalize_transition(MD_INSTALL_PROFILE, backup_dir, force=force, manual_transition=manual_transition)


def save_state(path: Path, data: dict) -> None:
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text())
        except Exception:
            current = {}
    current.update(data)
    current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_text(path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")


class Telnet:
    def __init__(self, host: str, port: int = 23, timeout: int = 10):
        self.host = host
        self.sock = socket.create_connection((host, port), timeout)
        self.sock.settimeout(0.4)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.closed = False

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_line(self, text: str) -> None:
        self.sock.sendall(text.encode("utf-8") + b"\n")

    def send_login_line(self, text: str) -> None:
        """Send a line during the telnet login dialogue using CRLF.

        BusyBox shells accept LF for commands after login, but some stock
        telnetd/getty combinations are stricter during the Login/Password
        dialogue and expect the Telnet-standard CRLF line ending.
        """
        self.sock.sendall(text.encode("utf-8") + b"\r\n")

    def send_bytes(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read(self, duration: float = 0.8, echo: bool = True) -> str:
        end = time.time() + duration
        output = bytearray()
        while time.time() < end:
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not data:
                self.closed = True
                break
            i = 0
            while i < len(data):
                if data[i] == IAC and i + 2 < len(data):
                    cmd, opt = data[i + 1], data[i + 2]
                    self.sock.sendall(bytes((IAC, WONT if cmd == DO else DONT, opt)))
                    i += 3
                else:
                    output.append(data[i])
                    i += 1
        text = self._decoder.decode(bytes(output), final=False)
        if echo and text:
            print(text, end="", flush=True)
        return text

    def wait_regex(self, pattern: str, timeout: int, echo: bool = True) -> str:
        accumulated = ""
        end = time.time() + timeout
        regex = re.compile(pattern, re.M)
        while time.time() < end:
            accumulated += self.read(0.7, echo=echo)
            if regex.search(accumulated):
                return accumulated
        raise Error(f"тайм-аут Telnet: не найден маркер {pattern}")

    def command(self, command: str, timeout: int = 60, echo: bool = True) -> tuple[int, str]:
        token = f"NOKIA_RC_{int(time.time()*1000)}"
        self.send_line(f"{command}; __rc=$?; printf '\\n__{token}_%s__\\n' \"$__rc\"")
        text = self.wait_regex(rf"__{token}_(\d+)__", timeout, echo=echo)
        match = re.search(rf"__{token}_(\d+)__", text)
        return int(match.group(1)), text

    def command_clean(self, command: str, timeout: int = 60) -> tuple[int, str]:
        """Run a command without terminal input echo and return operator-clean output."""
        echo_disabled = False
        try:
            stty_rc, _ = self.command("stty -echo 2>/dev/null", timeout=10, echo=False)
            echo_disabled = stty_rc == 0
            rc, text = self.command(command, timeout=timeout, echo=False)
        finally:
            if echo_disabled:
                try:
                    self.command("stty echo 2>/dev/null || true", timeout=10, echo=False)
                except Exception:
                    pass
        return rc, _clean_telnet_protocol(text)

    def upload_text(self, remote: str, text: str) -> None:
        marker = "__NOKIA_MEDVEFLASHER_EOF_7F4C__"
        if marker in text:
            raise Error("внутренний маркер встретился в скрипте")
        # Stock Telnet echoes every here-document line. Suppress that technical
        # transcript from the user console; only runtime messages are shown.
        self.command("stty -echo 2>/dev/null || true", timeout=10, echo=False)
        rc = 1
        try:
            self.send_line(f"cat > {shlex.quote(remote)} <<'{marker}'")
            self.send_bytes(text.encode("utf-8"))
            if not text.endswith("\n"):
                self.send_bytes(b"\n")
            self.send_line(marker)
            rc, _ = self.command(f"chmod 700 {shlex.quote(remote)}", timeout=30, echo=False)
        finally:
            try:
                self.command("stty echo 2>/dev/null || true", timeout=10, echo=False)
            except Exception:
                pass
        if rc:
            raise Error(f"не удалось загрузить {remote} через Telnet")



def _parse_uid0_accounts(text: str) -> list[str]:
    """Extract UID-0 account names from output, never from command echo.

    Stock BusyBox telnetd may echo and wrap the submitted awk command. Older
    marker parsing could then treat a wrapped shell fragment such as ``"$1"``
    as an account name. Only complete conservative Unix username lines are
    accepted; command/protocol fragments are rejected.
    """
    result: list[str] = []
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("__"):
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", line):
            continue
        if line not in result:
            result.append(line)
    return result


def _read_uid0_accounts(telnet: Telnet) -> list[str]:
    """Read actual UID-0 account names from the connected stock firmware."""
    echo_disabled = False
    roots_text = ""
    try:
        stty_rc, _ = telnet.command("stty -echo 2>/dev/null", timeout=10, echo=False)
        echo_disabled = stty_rc == 0
        _, roots_text = telnet.command(
            "awk -F: '$3==0 {print $1}' /etc/passwd",
            timeout=10,
            echo=False,
        )
    finally:
        if echo_disabled:
            try:
                telnet.command("stty echo 2>/dev/null || true", timeout=10, echo=False)
            except Exception:
                pass
    return _parse_uid0_accounts(roots_text)


def _ordered_uid0_candidates(accounts: list[str], preferred: tuple[str, ...]) -> list[str]:
    """Order only accounts that the device actually reports with UID 0.

    Names from guides are hints, not authority.  Unknown service accounts are
    allowed as candidates, but they are never trusted merely by name: every
    candidate must successfully pass ``id -u`` after ``su``.
    """
    result: list[str] = []
    for name in preferred:
        if name in accounts and name not in result:
            result.append(name)
    for name in accounts:
        if name != "root" and name not in result:
            result.append(name)
    if "root" in accounts and "root" not in result:
        result.append("root")
    return result


def _secret_candidates(*values: str | None, include_empty: bool = False) -> list[str]:
    """Return unique in-memory password candidates without logging them."""
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text not in result:
            result.append(text)
    if include_empty and "" not in result:
        result.append("")
    return result

def _telnet_login_dialogue(telnet: Telnet, user: str, password: str) -> None:
    """Wait for each login state and wake a slow stock telnetd if needed.

    Some stock builds can accept TCP/23 before getty is ready to print ``Login:``. Never
    send the username merely because the socket opened: an early line can be
    discarded and the following password is then consumed as the username.
    Each connection is nudged with an empty CRLF up to three times while the
    wizard waits for a real login or shell prompt.
    """
    login_prompt = r"(?i:(?:login|username)\s*:\s*$)"
    password_prompt = r"(?i:password\s*:\s*$)"
    shell_prompt = r"(?:^|[\r\n])[^\r\n]{0,160}[$#>]\s*$"
    failure = r"(?i:(?:login incorrect|authentication failed|access denied|incorrect password|invalid password|error!))"

    banner = ""
    for wake in range(4):
        banner += telnet.read(2.5 if wake == 0 else 3.0, echo=False)
        if re.search(shell_prompt, banner, re.M):
            return
        if re.search(login_prompt, banner, re.M):
            break
        if wake < 3:
            telnet.send_bytes(b"\r\n")
    else:
        raise Error(tr(
            "Telnet-сервис принял TCP-соединение, но не выдал приглашение Login:",
            "The Telnet service accepted TCP but did not present a Login: prompt",
        ))

    # A slow getty can redraw Login: after receiving an empty wake-up line.
    # Send the username only after the prompt is actually visible.
    telnet.send_login_line(user)
    second = telnet.wait_regex(
        rf"(?:{password_prompt})|(?:{shell_prompt})|(?:{failure})|(?:{login_prompt})",
        15,
        echo=False,
    )
    if re.search(shell_prompt, second, re.M):
        return
    if re.search(failure, second, re.M):
        raise Error(tr(
            "Telnet отклонил имя пользователя",
            "Telnet rejected the username",
        ))
    if re.search(login_prompt, second, re.M) and not re.search(password_prompt, second, re.M):
        raise Error(tr(
            "Telnet снова запросил Login: после отправки имени пользователя",
            "Telnet requested Login: again after the username was sent",
        ))

    telnet.send_login_line(password)
    third = telnet.wait_regex(
        rf"(?:{shell_prompt})|(?:{failure})|(?:{login_prompt})|(?:{password_prompt})",
        20,
        echo=False,
    )
    if re.search(shell_prompt, third, re.M):
        return
    raise Error(tr(
        "Telnet отклонил реквизиты или вернулся к приглашению входа",
        "Telnet rejected the credentials or returned to the login prompt",
    ))


def _telnet_open_logged_in(host: str, port: int, user: str, password: str,
                           attempts: int) -> Telnet:
    """Open a fresh TCP session for every login attempt."""
    last_error: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        print(tr(
            f"[WAIT] Попытка Telnet {attempt}/{attempts}: {host}:{port}",
            f"[WAIT] Telnet attempt {attempt}/{attempts}: {host}:{port}",
        ))
        telnet: Telnet | None = None
        try:
            telnet = Telnet(host, port=port, timeout=10)
            _telnet_login_dialogue(telnet, user, password)
            print(tr(
                f"[OK] Telnet-аутентификация успешна; обычный shell открыт на {host}:{port}.",
                f"[OK] Telnet authentication succeeded; an ordinary shell is open on {host}:{port}.",
            ))
            return telnet
        except (OSError, Error) as exc:
            last_error = exc
            if telnet is not None:
                telnet.close()
            if attempt < attempts:
                print(tr(
                    "[WARNING] Telnet ещё не готов или вход не завершён; закрываю соединение и повторяю.",
                    "[WARNING] Telnet is not ready or login did not complete; closing the socket and retrying.",
                ))
                time.sleep(min(2.0 + attempt, 5.0))
    detail = str(last_error) if last_error else tr("неизвестная ошибка", "unknown error")
    raise Error(tr(
        f"не удалось войти по Telnet после {attempts} попыток: {detail}",
        f"failed to log in over Telnet after {attempts} attempts: {detail}",
    ))


def _telnet_probe_uid(telnet: Telnet, timeout: int = 8) -> int | None:
    """Return the current UID using a unique marker, or None if no shell replied."""
    token = f"NOKIA_SU_UID_{int(time.time() * 1000)}"
    # Do not use Telnet.command() here: during a failed su dialogue there may
    # be no shell yet, and its rc wrapper would only add more text that could
    # be consumed as a password.  A single harmless printf is sufficient.
    telnet.send_line(f"printf '\\n__{token}_%s__\\n' \"$(id -u 2>/dev/null)\"")
    try:
        text = telnet.wait_regex(rf"__{token}_(\d+)__", timeout, echo=False)
    except Error:
        return None
    match = re.search(rf"__{token}_(\d+)__", text)
    return int(match.group(1)) if match else None


def _telnet_su_root(telnet: Telnet, su_user: str, su_password: str,
                    attempts: int = 3) -> None:
    """Enter the UID-0 account and verify it by ``id -u``.

    Do not treat a ``$`` prompt as the result of ``su``.  Stock telnetd can
    leave the previous shell prompt or the echoed command in the socket
    buffer; the old code matched that stale ``$`` and retried before sending
    the password.  Each attempt now drains pending output, waits only for a
    password request / explicit failure / an immediate root prompt, and then
    verifies the effective UID with a unique marker.  The UID check is the
    authority; the visual prompt may remain ``$`` even for a UID-0 shell.
    """
    password_prompt = r"(?i:password\s*:\s*$)"
    root_prompt = r"(?:^|[\r\n])[^\r\n]{0,160}#\s*$"
    failure = r"(?i:(?:authentication failed|incorrect password|invalid password|permission denied|su:.*(?:failed|incorrect|unknown user|not found)|unknown user|sorry))"

    total = max(1, attempts)
    for attempt in range(1, total + 1):
        # Remove the previous prompt / command echo before looking at the su
        # dialogue.  This is essential when stock telnet output is delayed.
        telnet.read(0.8, echo=False)
        telnet.send_line("su " + shlex.quote(su_user))

        response = ""
        deadline = time.time() + 12
        while time.time() < deadline:
            response += telnet.read(0.6, echo=False)
            if re.search(password_prompt, response, re.M):
                break
            if re.search(root_prompt, response, re.M):
                break
            if re.search(failure, response, re.M):
                break

        if re.search(root_prompt, response, re.M):
            uid = _telnet_probe_uid(telnet)
            if uid == 0:
                return
        elif re.search(password_prompt, response, re.M):
            telnet.send_login_line(su_password)
            # Give su time to replace the shell.  Do not require '#': the
            # firmware may retain '$' despite effective UID 0.
            telnet.read(1.8, echo=False)
            uid = _telnet_probe_uid(telnet)
            if uid == 0:
                return
        elif not re.search(failure, response, re.M):
            # Some builds do not render a recognisable Password: prompt.
            # One blind password line is safe here because the only command
            # active is su; never print or log the password.
            telnet.send_login_line(su_password)
            telnet.read(1.8, echo=False)
            uid = _telnet_probe_uid(telnet)
            if uid == 0:
                return

        # A failed / half-open su may still be waiting for input.  Abort that
        # dialogue, return to the ordinary shell, and start a clean attempt.
        telnet.send_bytes(b"\x03\r\n")
        telnet.read(1.0, echo=False)
        if attempt < total:
            print(tr(
                f"[WARNING] su {su_user}: попытка {attempt}/{total} не дала UID 0; повторяю.",
                f"[WARNING] su {su_user}: attempt {attempt}/{total} did not produce UID 0; retrying.",
            ))

    raise Error(tr(
        f"su {su_user} не дал UID 0 после {total} попыток",
        f"su {su_user} did not grant UID 0 after {total} attempts",
    ))


def login_root(host: str, user: str, password: str, su_user: str = "auto",
               su_password: str | None = None, port: int = 23,
               connect_attempts: int = 2) -> Telnet:
    print(tr(
        f"[WAIT] Подключение к {host}:{port} по Telnet...",
        f"[WAIT] Connecting to {host}:{port} over Telnet...",
    ))
    telnet = _telnet_open_logged_in(host, port, user, password, connect_attempts)
    try:
        rc, text = telnet.command(
            'printf \'__UID__%s__\' "$(id -u 2>/dev/null)"',
            timeout=10,
            echo=False,
        )
        match = re.search(r"__UID__(\d+)__", text)
        uid = int(match.group(1)) if match else -1
        if uid == 0:
            print(tr(
                "[OK] Telnet-вход выполнен сразу с UID 0.",
                "[OK] Telnet login already has UID 0.",
            ))
            return telnet

        if su_user == "auto":
            roots = _read_uid0_accounts(telnet)
            candidates = _ordered_uid0_candidates(
                roots,
                ("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "root"),
            )
            if not candidates:
                detected = ", ".join(roots) if roots else tr("нет", "none")
                raise Error(tr(
                    f"в /etc/passwd не найден пригодный UID 0 аккаунт; обнаружены: {detected}",
                    f"no usable UID-0 account was found in /etc/passwd; detected: {detected}",
                ))
            su_user = candidates[0]
            print(tr(
                f"[OK] Первый кандидат UID 0: {su_user}; доступ будет подтверждён через id -u.",
                f"[OK] First UID-0 candidate: {su_user}; access will be verified with id -u.",
            ))

        _telnet_su_root(
            telnet,
            su_user,
            su_password if su_password is not None else password,
            attempts=3,
        )
        _, root_text = telnet.command(
            'printf \'__ROOT__%s__\' "$(id -u)"',
            timeout=10,
            echo=False,
        )
        if "__ROOT__0__" not in root_text:
            raise Error(tr(
                f"su {su_user} не дал UID 0",
                f"su {su_user} did not grant UID 0",
            ))
        print(tr("[OK] UID 0 подтверждён.", "[OK] UID 0 confirmed."))
        return telnet
    except Exception:
        telnet.close()
        raise

# Stock services whose UID-0 account the wizard can enter, in escalation order.
# FTP alone was sufficient on every unit observed so far, so Samba is attempted
# only when FTP did not produce a usable account: each service enabled here is
# extra attack surface that stays on after the run.
UID0_SERVICE_ESCALATION = (
    ("FTP", "enable_ftp"),
    ("Samba", "enable_samba"),
)


def _provision_uid0_service_account(access, label: str, method: str) -> bool:
    """Publish one UID-0 service account through the stock Web UI.

    Stock MD firmware ships /etc/passwd with ``root`` as its only UID-0 entry,
    and the Web-UI/Telnet password does not authenticate ``root`` through
    ``su``.  The UID-0 service accounts the wizard can actually enter —
    ``user_ftp`` and ``samba_anony`` — exist only while the matching stock
    service is enabled, so on a unit with those services off there is no
    reachable root account at all and backup can never start.

    This saves a stock Web-UI settings form.  It sends no raw MTD, flash or
    firmware write, but where the stock firmware persists its own settings is
    not observable from here, so this is deliberately NOT described as leaving
    NAND untouched.  It is a state change: callers opt in through
    ``allow_service_provisioning`` and read-only flows never do.
    """
    setup = getattr(access, "web_setup", None)
    if setup is None:
        return False
    handler = getattr(setup, method, None)
    if handler is None:
        return False
    print(tr(
        f"[WAIT] Ни один UID 0 аккаунт не подтверждён; включаю {label} через штатный веб-интерфейс, "
        f"чтобы появился пригодный UID 0 сервис-аккаунт. Сохраняется настройка stock Web UI; "
        f"raw MTD/flash/firmware write не выполняется.",
        f"[WAIT] No UID-0 account was confirmed; enabling {label} through the stock web UI so that a "
        f"usable UID-0 service account appears. This saves a stock Web-UI setting; no raw MTD, flash "
        f"or firmware write is performed.",
    ))
    try:
        handler()
    except Exception as exc:
        print(tr(
            f"[WARNING] {label} не удалось включить через веб-интерфейс: {_web_failure_detail(exc)}",
            f"[WARNING] {label} could not be enabled through the web UI: {_web_failure_detail(exc)}",
        ))
        return False
    # A freshly enabled FTP server publishes its own account password; without
    # re-reading it the next su attempt would still use the stale empty value.
    try:
        credentials = setup.read_credentials()
    except Exception as exc:
        print(tr(
            f"[WARNING] Не удалось перечитать реквизиты после включения {label}: {_web_failure_detail(exc)}",
            f"[WARNING] Credentials could not be re-read after enabling {label}: {_web_failure_detail(exc)}",
        ))
    else:
        access.ftp_user = str(credentials.get("ftp_user") or access.ftp_user)
        access.ftp_password = str(credentials.get("ftp_password") or "")
        access.ftp_port = int(credentials.get("ftp_port") or access.ftp_port)
        access.ftp_enabled = bool(credentials.get("ftp_enabled"))
        _register_log_secret(access.ftp_password)
    print(tr(
        f"[ВНИМАНИЕ] {label} включён и останется включённым после работы мастера; "
        f"выключите его в штатной веб-морде, когда он больше не нужен.",
        f"[NOTICE] {label} was enabled and stays enabled after the wizard finishes; "
        f"switch it off in the stock web UI once it is no longer needed.",
    ))
    return True


def login_root_profile_dynamic(
    access,
    *,
    model: str,
    sessions: int,
    connect_attempts: int,
    preferred_accounts: tuple[str, ...],
    allow_service_provisioning: bool = False,
) -> Telnet:
    """Discover and verify a working UID-0 account on fresh Telnet sessions.

    Stock builds do not expose a stable account name across devices.  The
    guide may say ``user_ftp`` while the actual firmware contains only service
    accounts such as ``samba_anony`` or ``osgi_admin``.  Account names are
    therefore discovered from /etc/passwd, then every candidate/password pair
    is tested on a new TCP session and accepted only after ``id -u`` returns 0.

    ``allow_service_provisioning`` decides whether a failed cycle may enable a
    stock service through the Web UI to make a UID-0 account exist at all.  It
    defaults to False because this helper also serves flows that are declared
    read-only (stock audit, firmware capability probe); only backup and install
    opt in.
    """
    total = max(1, sessions)
    last_error: Exception | None = None
    provisioned = False
    pending_services = list(UID0_SERVICE_ESCALATION) if allow_service_provisioning else []

    def provision_next() -> bool:
        """Attempt exactly one stock service per failed root-discovery cycle."""
        if not pending_services:
            return False
        label, method = pending_services.pop(0)
        # Deliberately do not fall through to the next service when the Web
        # handler reports a failure.  A handler may have saved the setting and
        # then timed out waiting for the daemon/port; enabling Samba in the same
        # cycle would silently widen the device state change.
        return _provision_uid0_service_account(access, label, method)

    for session in range(1, total + 1):
        print(tr(
            f"[WAIT] {model} root-сеанс Telnet {session}/{total}",
            f"[WAIT] {model} Telnet root session {session}/{total}",
        ))
        discovery: Telnet | None = None
        try:
            discovery = _telnet_open_logged_in(
                access.host, access.telnet_port, access.user, access.password,
                connect_attempts,
            )
            current_uid = _telnet_probe_uid(discovery)
            if current_uid is None:
                raise Error(tr(
                    "обычный Telnet shell открыт, но команда id -u не вернула результат",
                    "the ordinary Telnet shell opened, but id -u returned no result",
                ))
            print(tr(
                f"[OK] Обычный Telnet shell отвечает; текущий UID: {current_uid}.",
                f"[OK] The ordinary Telnet shell is responsive; current UID: {current_uid}.",
            ))
            if current_uid == 0:
                print(tr(
                    "[OK] Telnet-вход выполнен сразу с UID 0.",
                    "[OK] Telnet login already has UID 0.",
                ))
                return discovery
            roots = _read_uid0_accounts(discovery)
        except (OSError, Error) as exc:
            last_error = exc
            if discovery is not None:
                discovery.close()
            if session < total:
                print(tr(
                    f"[WARNING] {model}: не удалось прочитать UID 0 аккаунты; открываю новый Telnet-сеанс.",
                    f"[WARNING] {model}: could not read UID-0 accounts; opening a fresh Telnet session.",
                ))
                time.sleep(2.0 if model == "MD" else 3.0)
                continue
            break

        discovery.close()
        candidates = _ordered_uid0_candidates(roots, preferred_accounts)
        detected = ", ".join(roots) if roots else tr("нет", "none")
        if not candidates:
            last_error = Error(tr(
                f"в /etc/passwd не найдены UID 0 аккаунты; обнаружены: {detected}",
                f"no UID-0 accounts were found in /etc/passwd; detected: {detected}",
            ))
            if session < total and provision_next():
                provisioned = True
                time.sleep(2.0 if model == "MD" else 3.0)
                continue
            break
        print(tr(
            f"[OK] UID 0 аккаунты из /etc/passwd: {detected}. Проверяю фактический su-доступ.",
            f"[OK] UID-0 accounts from /etc/passwd: {detected}. Verifying actual su access.",
        ))

        passwords = _secret_candidates(
            access.su_password,
            access.ftp_password,
            access.password,
            include_empty=True,
        )
        for account in candidates:
            for secret_index, secret in enumerate(passwords, 1):
                telnet: Telnet | None = None
                try:
                    print(tr(
                        f"[WAIT] Проверка su {account}, реквизит {secret_index}/{len(passwords)}; пароль не выводится.",
                        f"[WAIT] Testing su {account}, credential {secret_index}/{len(passwords)}; the password is not printed.",
                    ))
                    telnet = _telnet_open_logged_in(
                        access.host, access.telnet_port, access.user, access.password,
                        connect_attempts,
                    )
                    login_uid = _telnet_probe_uid(telnet)
                    if login_uid is None:
                        raise Error(tr(
                            "Telnet shell открыт, но id -u не ответил",
                            "the Telnet shell opened, but id -u did not respond",
                        ))
                    print(tr(
                        f"[OK] Telnet-вход для проверки su успешен; текущий UID: {login_uid}.",
                        f"[OK] Telnet login for the su test succeeded; current UID: {login_uid}.",
                    ))
                    if login_uid == 0:
                        print(tr("[OK] UID 0 подтверждён.", "[OK] UID 0 confirmed."))
                        return telnet
                    _telnet_su_root(telnet, account, secret, attempts=1)
                    if _telnet_probe_uid(telnet) == 0:
                        print(tr(
                            f"[OK] UID 0 подтверждён через su {account}.",
                            f"[OK] UID 0 confirmed through su {account}.",
                        ))
                        access.su_user = account
                        access.su_password = secret
                        return telnet
                    raise Error(tr(
                        f"su {account} завершился без UID 0",
                        f"su {account} completed without UID 0",
                    ))
                except (OSError, Error) as exc:
                    last_error = exc
                    detail = str(exc).strip() or exc.__class__.__name__
                    for hidden in _secret_candidates(
                        access.password, access.su_password, access.ftp_password, secret
                    ):
                        if hidden:
                            detail = detail.replace(hidden, "<hidden>")
                    print(tr(
                        f"[WARNING] su {account}, реквизит {secret_index}/{len(passwords)} не подтверждён: {detail}",
                        f"[WARNING] su {account}, credential {secret_index}/{len(passwords)} was not confirmed: {detail}",
                    ))
                    if telnet is not None:
                        telnet.close()
                    continue

        if session < total:
            # One service per failed cycle: FTP first, Samba only if FTP was
            # not enough.
            if provision_next():
                provisioned = True
            print(tr(
                f"[WARNING] {model}: ни один UID 0 кандидат не подтверждён; повторяю весь цикл на новых соединениях.",
                f"[WARNING] {model}: no UID-0 candidate was confirmed; retrying the full cycle on fresh connections.",
            ))
            time.sleep(2.0 if model == "MD" else 3.0)

    detail = str(last_error) if last_error else tr("неизвестная ошибка", "unknown error")
    web_ok = getattr(access, "web_client", None) is not None
    if web_ok:
        summary_ru = "вход в stock Web UI и обычный Telnet подтверждены, но UID 0 не получен"
        summary_en = "stock Web UI and ordinary Telnet access were confirmed, but UID 0 was not obtained"
    else:
        summary_ru = "обычный Telnet подтверждён, но UID 0 не получен"
        summary_en = "ordinary Telnet access was confirmed, but UID 0 was not obtained"
    hint_ru = hint_en = ""
    if not provisioned:
        # Without FTP/Samba the stock build exposes only `root`, which the
        # Web-UI password does not open.  Say so instead of leaving the
        # operator with a bare su failure.
        hint_ru = (" Включите FTP (и Samba) в штатной веб-морде: пригодные UID 0 аккаунты "
                   "user_ftp/samba_anony существуют только вместе с этими сервисами.")
        hint_en = (" Enable FTP (and Samba) in the stock web UI: the usable UID-0 accounts "
                   "user_ftp/samba_anony exist only together with those services.")
    # Deliberately not "NAND untouched": with provisioning enabled a stock
    # Web-UI settings form may have been saved on this path, and where the
    # firmware persists its settings is not observable from here.
    raise Error(tr(
        f"{model}: {summary_ru}. Backup не начат, raw MTD/flash/firmware write не выполнялся."
        f"{hint_ru} Последний результат: {detail}",
        f"{model}: {summary_en}. Backup did not start and no raw MTD, flash or firmware write was "
        f"performed.{hint_en} Last result: {detail}",
    ))


def login_root_md(access, sessions: int = 3, *, allow_service_provisioning: bool = False) -> Telnet:
    if access.su_user == "auto":
        return login_root_profile_dynamic(
            access,
            model="MD",
            sessions=sessions,
            connect_attempts=3,
            preferred_accounts=("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "root"),
            allow_service_provisioning=allow_service_provisioning,
        )

    total = max(1, sessions)
    last_error: Exception | None = None
    for session in range(1, total + 1):
        print(tr(
            f"[WAIT] MD root-сеанс Telnet {session}/{total}",
            f"[WAIT] MD Telnet root session {session}/{total}",
        ))
        try:
            return login_root(
                access.host,
                access.user,
                access.password,
                access.su_user,
                access.su_password,
                port=access.telnet_port,
                connect_attempts=3,
            )
        except (OSError, Error) as exc:
            last_error = exc
            if session < total:
                print(tr(
                    "[WARNING] MD не дала UID 0 в этом Telnet-сеансе; полностью переподключаюсь.",
                    "[WARNING] The MD did not grant UID 0 in this Telnet session; reconnecting from scratch.",
                ))
                time.sleep(2.0)
    detail = str(last_error) if last_error else tr("неизвестная ошибка", "unknown error")
    raise Error(tr(
        f"MD не дала UID 0 после {total} независимых Telnet-сеансов: {detail}",
        f"The MD did not grant UID 0 after {total} independent Telnet sessions: {detail}",
    ))


def local_ip_for(host: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, 9))
        return sock.getsockname()[0]
    finally:
        sock.close()


# RC25 LAN1 uplink advisory.
#
# LAN1 is the only 2.5G port on both XG-040G-MD and XG-040G-MF, and it is excluded
# from transition/recovery because the link is unstable there. Nothing on the PC
# reports a vendor port label, but a negotiated link at 2500 Mbit/s or faster can
# only be LAN1: LAN2..LAN4 are gigabit ports and cannot negotiate above 1000.
#
# This is deliberately an advisory, not a gate. A gigabit PC NIC plugged into LAN1
# negotiates 1000 and is indistinguishable from LAN2..LAN4, so a hard block here
# would refuse correct setups while still missing the common mistake. Write
# authorization is unchanged and continues to come from the existing live family,
# MTD, handoff-target and backup gates.
LAN1_LINK_SPEED_MBIT = 2500
# A router-facing Ethernet link cannot run faster than the port at the other end,
# so anything well above 2.5G is not that link at all. VPN and overlay adapters
# advertise fantasy speeds — an observed throne-tun reported 100000 Mbit/s and was
# confidently announced as LAN1. Such an interface also means the route to the
# router is not the cable, which makes every network observation unreliable, so it
# is reported as its own condition rather than folded into "unknown".
LAN1_LINK_SPEED_MAX_MBIT = 5000


def _lan1_verdict_from_speed(speed_mbit: int | None) -> str:
    """Classify a negotiated PC link speed as the router's LAN1 port.

    Returns "lan1" for a 2.5G link, "other" for a link that a gigabit LAN2..LAN4
    port can produce, "virtual" for a speed no Ethernet port at the other end can
    negotiate, and "unknown" when the speed is unavailable.
    """
    if speed_mbit is None or speed_mbit <= 0:
        return "unknown"
    if speed_mbit > LAN1_LINK_SPEED_MAX_MBIT:
        return "virtual"
    return "lan1" if speed_mbit >= LAN1_LINK_SPEED_MBIT else "other"


def _interface_for_local_ip(local_ip: str) -> str | None:
    """Best-effort name of the interface that carries local_ip."""
    try:
        if sys.platform.startswith("linux"):
            for name in sorted(os.listdir("/sys/class/net")):
                out = subprocess.run(
                    ["ip", "-o", "-4", "addr", "show", "dev", name],
                    capture_output=True, text=True, timeout=5,
                )
                if f"inet {local_ip}/" in (out.stdout or ""):
                    return name
            return None
        if sys.platform == "darwin":
            out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
            current = None
            for line in (out.stdout or "").splitlines():
                if line and not line[0].isspace():
                    current = line.split(":", 1)[0]
                elif f"inet {local_ip} " in line:
                    return current
            return None
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetIPAddress -IPAddress '{local_ip}' -ErrorAction SilentlyContinue).InterfaceAlias"],
                capture_output=True, text=True, timeout=20,
            )
            alias = (out.stdout or "").strip().splitlines()
            return alias[0].strip() if alias and alias[0].strip() else None
    except Exception:
        return None
    return None


def _is_hardware_interface(interface: str) -> bool | None:
    """True for a real NIC, False for a tunnel/overlay, None when undecidable."""
    try:
        if sys.platform.startswith("linux"):
            return (Path("/sys/class/net") / interface / "device").exists()
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetAdapter -Name '{interface}' -ErrorAction SilentlyContinue).HardwareInterface"],
                capture_output=True, text=True, timeout=20,
            )
            answer = (out.stdout or "").strip().splitlines()
            if answer and answer[0].strip():
                return answer[0].strip().lower() == "true"
            return None
    except Exception:
        return None
    return None


def _link_speed_mbit(interface: str) -> int | None:
    """Negotiated link speed of interface in Mbit/s, or None when unavailable."""
    try:
        if sys.platform.startswith("linux"):
            raw = Path(f"/sys/class/net/{interface}/speed").read_text(encoding="utf-8").strip()
            value = int(raw)
            return value if value > 0 else None
        if sys.platform == "darwin":
            out = subprocess.run(["ifconfig", interface], capture_output=True, text=True, timeout=5)
            match = re.search(r"media:.*?(\d+)\s*(G|M)base", out.stdout or "", re.IGNORECASE)
            if match:
                value = int(match.group(1))
                return value * 1000 if match.group(2).upper() == "G" else value
            return None
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetAdapter -Name '{interface}' -ErrorAction SilentlyContinue).Speed"],
                capture_output=True, text=True, timeout=20,
            )
            raw = (out.stdout or "").strip().splitlines()
            if raw and raw[0].strip().isdigit():
                # Get-NetAdapter reports bits per second.
                return int(raw[0].strip()) // 1_000_000
            return None
    except Exception:
        return None
    return None


def detect_lan1_uplink(host: str) -> tuple[str, dict[str, object]]:
    """Classify the PC's link toward host without sending anything to the device."""
    evidence: dict[str, object] = {
        "host": host, "local_ip": None, "interface": None,
        "speed_mbit": None, "hardware": None,
    }
    try:
        local_ip = local_ip_for(host)
    except Exception:
        return "unknown", evidence
    evidence["local_ip"] = local_ip
    interface = _interface_for_local_ip(local_ip)
    evidence["interface"] = interface
    if not interface:
        return "unknown", evidence
    speed = _link_speed_mbit(interface)
    evidence["speed_mbit"] = speed
    hardware = _is_hardware_interface(interface)
    evidence["hardware"] = hardware
    if hardware is False:
        return "virtual", evidence
    return _lan1_verdict_from_speed(speed), evidence


def warn_if_lan1_uplink(host: str, operation_ru: str, operation_en: str) -> None:
    """Advise before flashing/backup/restore when the PC appears to sit on LAN1.

    Never raises and never blocks: a wrong guess must not stand between the
    operator and a recovery. The prompt defaults to continuing, and a
    non-interactive run continues silently.
    """
    try:
        verdict, evidence = detect_lan1_uplink(host)
    except Exception:
        return
    interface = evidence.get("interface") or "?"
    speed = evidence.get("speed_mbit")
    if verdict == "lan1":
        print(tr(
            f"[NETWORK POLICY] ВНИМАНИЕ: {interface} согласован на {speed} Мбит/с — так умеет только LAN1 / 2.5G, "
            f"а он исключён из transition/recovery из-за нестабильности линка.",
            f"[NETWORK POLICY] WARNING: {interface} negotiated {speed} Mbit/s, which only LAN1 / 2.5G can do, "
            f"and that port is excluded from transition/recovery because the link is unstable.",
        ))
        print(tr(
            f"[NETWORK POLICY] Перед операцией «{operation_ru}» переключите кабель в LAN2, LAN3 или LAN4.",
            f"[NETWORK POLICY] Move the cable to LAN2, LAN3, or LAN4 before the '{operation_en}' operation.",
        ))
        try:
            answer = input(tr(
                "Продолжить всё равно? [Y/n]: ",
                "Continue anyway? [Y/n]: ",
            )).strip().lower()
        except (EOFError, OSError):
            answer = ""
        if answer in {"n", "no", "н", "нет"}:
            raise Error(tr(
                "операция отменена оператором: ПК подключён к LAN1 / 2.5G",
                "operation cancelled by the operator: the PC is connected to LAN1 / 2.5G",
            ))
        print(tr(
            "[NETWORK POLICY] Продолжаем по решению оператора. Порт остаётся вероятной причиной обрыва передачи.",
            "[NETWORK POLICY] Continuing at the operator's decision. The port remains a likely cause of a transfer drop.",
        ))
        return
    if verdict == "virtual":
        print(tr(
            f"[NETWORK POLICY] Маршрут к {host} идёт через {interface} — это не кабельный порт, "
            f"а туннель или виртуальный адаптер (линк {speed} Мбит/с).",
            f"[NETWORK POLICY] The route to {host} goes through {interface}, which is not a cabled port "
            f"but a tunnel or virtual adapter (link {speed} Mbit/s).",
        ))
        print(tr(
            "[NETWORK POLICY] Определить порт Nokia по такому маршруту нельзя, и другие сетевые наблюдения тоже ненадёжны: туннель может отвечать за чужие адреса. Проверьте, что кабель в LAN2, LAN3 или LAN4, и по возможности отключите VPN.",
            "[NETWORK POLICY] The Nokia port cannot be identified through such a route, and other network observations are unreliable too: a tunnel can answer for addresses that are not there. Confirm the cable is in LAN2, LAN3, or LAN4, and disable the VPN if you can.",
        ))
        return
    if verdict == "other":
        print(tr(
            f"[NETWORK POLICY] Линк {interface}: {speed} Мбит/с — признаков LAN1 / 2.5G нет.",
            f"[NETWORK POLICY] Link {interface}: {speed} Mbit/s — no sign of LAN1 / 2.5G.",
        ))
        return
    print(tr(
        "[NETWORK POLICY] Скорость линка определить не удалось. Убедитесь сами, что кабель в LAN2, LAN3 или LAN4, а не в LAN1 / 2.5G.",
        "[NETWORK POLICY] The link speed could not be determined. Confirm yourself that the cable is in LAN2, LAN3, or LAN4 rather than LAN1 / 2.5G.",
    ))


def find_nc(telnet: Telnet) -> str:
    rc, text = telnet.command("command -v nc 2>/dev/null || command -v netcat 2>/dev/null || true", echo=False)
    candidates = re.findall(r"(?:^|\r?\n)(/[A-Za-z0-9_./-]+)(?:\r?\n|$)", text)
    if candidates:
        return candidates[-1]
    rc, text = telnet.command("busybox 2>&1 | tr ',' ' ' | awk '{for(i=1;i<=NF;i++) if($i==\"nc\") found=1} END{exit !found}'", echo=False)
    if rc == 0:
        return "busybox nc"
    raise Error("в stock firmware отсутствует nc; используйте USB-накопитель на Nokia через Samba/FTP")


@dataclass
class ReceiverResult:
    error: Exception | None = None
    bytes_received: int = 0


@dataclass
class TftpResult:
    error: Exception | None = None
    bytes_transferred: int = 0
    remote_name: str = ""
    block_size: int = 512


def login_root_family(access: StockAccess, family: str, sessions: int = 3, *,
                      allow_service_provisioning: bool = False) -> Telnet:
    """Open a proven UID-0 stock Telnet shell for the selected hardware family.

    MD keeps the established backend unchanged. MF uses the same interactive
    root proof machinery but with the MF label and device-derived UID-0 accounts.

    ``allow_service_provisioning`` stays False unless the caller is a flow that
    is allowed to change stock settings; see login_root_profile_dynamic.
    """
    family = (family or "").lower()
    if family == "md":
        return login_root_md(access, sessions=sessions,
                             allow_service_provisioning=allow_service_provisioning)
    if family == "mf":
        return login_root_profile_dynamic(
            access,
            model="MF",
            sessions=sessions,
            connect_attempts=3,
            preferred_accounts=("user_ftp", "root", "useradmin_ftp", "osgi_admin", "samba_anony", "telecomadmin"),
            allow_service_provisioning=allow_service_provisioning,
        )
    raise Error(tr("неизвестный stock-профиль; UID 0 не запрашивается", "unknown stock profile; UID 0 will not be requested"))


def find_tftp(telnet: Telnet) -> str:
    rc, text = telnet.command("command -v tftp 2>/dev/null || true", echo=False)
    candidates = re.findall(r"(?:^|\r?\n)(/[A-Za-z0-9_./-]+)(?:\r?\n|$)", text)
    if not candidates:
        raise Error("в stock firmware отсутствует BusyBox tftp; используйте USB-накопитель на Nokia через Samba/FTP")
    path = candidates[-1]
    _, help_text = telnet.command(f"{path} --help 2>&1 || true", timeout=10, echo=False)
    if "-p" not in help_text or "-g" not in help_text:
        raise Error("stock tftp не поддерживает PUT/GET; используйте USB-накопитель на Nokia через Samba/FTP")
    return path


def _tftp_parse_request(packet: bytes) -> tuple[int, str, str, dict[str, str]]:
    if len(packet) < 4:
        raise Error("короткий TFTP request")
    opcode = struct.unpack("!H", packet[:2])[0]
    fields = packet[2:].split(b"\0")
    if len(fields) < 3:
        raise Error("повреждённый TFTP request")
    filename = fields[0].decode("utf-8", "replace")
    mode = fields[1].decode("ascii", "replace").lower()
    options: dict[str, str] = {}
    tail = fields[2:]
    if tail and tail[-1] == b"":
        tail = tail[:-1]
    for index in range(0, len(tail) - 1, 2):
        options[tail[index].decode("ascii", "replace").lower()] = tail[index + 1].decode("ascii", "replace")
    return opcode, filename, mode, options


def _tftp_error(code: int, message: str) -> bytes:
    return struct.pack("!HH", 5, code) + message.encode("ascii", "replace") + b"\0"


def _configure_tftp_udp_socket(sock: socket.socket) -> None:
    """Make repeated local TFTP sessions reliable, especially on Windows.

    Windows can surface ICMP errors from an earlier UDP peer as WSAECONNRESET/
    WSAECONNABORTED on recvfrom(). Disabling SIO_UDP_CONNRESET keeps an
    unrelated stale datagram from aborting the next partition transfer.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:
        pass
    if os.name == "nt":
        control = getattr(socket, "SIO_UDP_CONNRESET", None)
        if control is not None:
            try:
                sock.ioctl(control, False)
            except OSError:
                pass


def receive_tftp_put(
    bind_ip: str,
    port: int,
    output: Path,
    expected_name: str,
    allowed_host: str,
    ready: threading.Event,
    result: TftpResult,
    cancel: threading.Event | None = None,
    timeout: int = 120,
    maximum_block_size: int = 4096,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _configure_tftp_udp_socket(sock)
        sock.bind((bind_ip, port))
        sock.settimeout(1)
        ready.set()
        peer = None
        request_options: dict[str, str] = {}
        request_deadline = time.time() + timeout
        while True:
            try:
                packet, address = sock.recvfrom(65535)
            except socket.timeout:
                if cancel is not None and cancel.is_set():
                    raise Error("TFTP PUT cancelled")
                if time.time() >= request_deadline:
                    raise Error("TFTP PUT timed out waiting for the initial request")
                continue
            if allowed_host and address[0] != allowed_host:
                continue
            try:
                opcode, filename, mode, request_options = _tftp_parse_request(packet)
            except Exception:
                continue
            if opcode != 2:
                continue
            if filename != expected_name:
                sock.sendto(_tftp_error(1, "unexpected filename"), address)
                continue
            if mode != "octet":
                sock.sendto(_tftp_error(4, "octet mode required"), address)
                continue
            peer = address
            result.remote_name = filename
            break

        requested = 512
        if "blksize" in request_options:
            try:
                requested = int(request_options["blksize"])
            except ValueError:
                requested = 512
        block_size = max(512, min(requested, maximum_block_size))
        result.block_size = block_size
        if "blksize" in request_options:
            response = struct.pack("!H", 6) + b"blksize\0" + str(block_size).encode() + b"\0"
        else:
            response = struct.pack("!HH", 4, 0)
        sock.sendto(response, peer)
        last_response = response
        expected_block = 1
        retries = 0
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as fh:
            while True:
                try:
                    packet, address = sock.recvfrom(block_size + 4)
                except socket.timeout:
                    if cancel is not None and cancel.is_set():
                        raise Error("TFTP PUT cancelled")
                    retries += 1
                    if retries >= timeout:
                        raise Error("TFTP PUT timeout")
                    sock.sendto(last_response, peer)
                    continue
                if address != peer or len(packet) < 4:
                    continue
                opcode, block = struct.unpack("!HH", packet[:4])
                if opcode == 5:
                    raise Error("TFTP client returned ERROR")
                if opcode != 3:
                    continue
                payload = packet[4:]
                if block == expected_block:
                    fh.write(payload)
                    result.bytes_transferred += len(payload)
                    ack = struct.pack("!HH", 4, block)
                    sock.sendto(ack, peer)
                    last_response = ack
                    retries = 0
                    expected_block = (expected_block + 1) & 0xFFFF
                    if len(payload) < block_size:
                        fh.flush()
                        try:
                            import os as _os
                            _os.fsync(fh.fileno())
                        except OSError:
                            pass
                        # Linger briefly so a lost final ACK does not make the client fail.
                        sock.settimeout(2)
                        try:
                            duplicate, address2 = sock.recvfrom(block_size + 4)
                            if address2 == peer and len(duplicate) >= 4:
                                op2, block2 = struct.unpack("!HH", duplicate[:4])
                                if op2 == 3 and block2 == block:
                                    sock.sendto(ack, peer)
                        except socket.timeout:
                            pass
                        return
                elif block == ((expected_block - 1) & 0xFFFF):
                    sock.sendto(struct.pack("!HH", 4, block), peer)
    except Exception as exc:
        result.error = exc
        ready.set()
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
    finally:
        sock.close()


def serve_tftp_get(
    bind_ip: str,
    port: int,
    source: Path,
    expected_name: str,
    allowed_host: str,
    ready: threading.Event,
    result: TftpResult,
    timeout: int = 120,
    maximum_block_size: int = 4096,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _configure_tftp_udp_socket(sock)
        sock.bind((bind_ip, port))
        sock.settimeout(5)
        ready.set()
        peer = None
        options: dict[str, str] = {}
        request_deadline = time.time() + timeout
        while True:
            try:
                packet, address = sock.recvfrom(65535)
            except socket.timeout:
                if time.time() >= request_deadline:
                    raise Error("TFTP GET timed out waiting for the initial request")
                continue
            if allowed_host and address[0] != allowed_host:
                continue
            try:
                opcode, filename, mode, options = _tftp_parse_request(packet)
            except Exception:
                continue
            if opcode != 1:
                continue
            if filename != expected_name:
                sock.sendto(_tftp_error(1, "unexpected filename"), address)
                continue
            if mode != "octet":
                sock.sendto(_tftp_error(4, "octet mode required"), address)
                continue
            peer = address
            result.remote_name = filename
            break

        requested = 512
        if "blksize" in options:
            try:
                requested = int(options["blksize"])
            except ValueError:
                requested = 512
        block_size = max(512, min(requested, maximum_block_size))
        result.block_size = block_size
        if "blksize" in options:
            oack = struct.pack("!H", 6) + b"blksize\0" + str(block_size).encode() + b"\0"
            retries = 0
            while True:
                sock.sendto(oack, peer)
                try:
                    packet, address = sock.recvfrom(65535)
                except socket.timeout:
                    retries += 1
                    if retries * 5 >= timeout:
                        raise Error("TFTP GET option negotiation timeout")
                    continue
                if address == peer and len(packet) >= 4 and struct.unpack("!HH", packet[:4]) == (4, 0):
                    break
        block = 1
        with source.open("rb") as fh:
            while True:
                payload = fh.read(block_size)
                data_packet = struct.pack("!HH", 3, block) + payload
                retries = 0
                while True:
                    sock.sendto(data_packet, peer)
                    try:
                        packet, address = sock.recvfrom(65535)
                    except socket.timeout:
                        retries += 1
                        if retries * 5 >= timeout:
                            raise Error(f"TFTP GET timeout at block {block}")
                        continue
                    if address != peer or len(packet) < 4:
                        continue
                    opcode, ack_block = struct.unpack("!HH", packet[:4])
                    if opcode == 5:
                        raise Error("TFTP client returned ERROR")
                    if opcode == 4 and ack_block == block:
                        break
                result.bytes_transferred += len(payload)
                if len(payload) < block_size:
                    return
                block = (block + 1) & 0xFFFF
    except Exception as exc:
        result.error = exc
        ready.set()
    finally:
        sock.close()


def receive_one(bind_ip: str, port: int, output: Path, ready: threading.Event, result: ReceiverResult, timeout: int = 1200) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((bind_ip, port))
        server.listen(1)
        server.settimeout(timeout)
        ready.set()
        conn, _ = server.accept()
        with conn, output.open("wb") as fh:
            conn.settimeout(timeout)
            while True:
                chunk = conn.recv(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                result.bytes_received += len(chunk)
    except Exception as exc:
        result.error = exc
        ready.set()
    finally:
        server.close()


def validate_gzip_size(path: Path, expected: int) -> None:
    total = 0
    try:
        with gzip.open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                total += len(chunk)
    except (OSError, EOFError) as exc:
        raise Error(f"повреждён gzip {path.name}: {exc}") from exc
    if total != expected:
        raise Error(f"{path.name}: распакованный размер {total}, ожидается {expected}")


def _stock_sysfs_mtd_snapshot(telnet: Telnet) -> dict[int, tuple[int, int, str]]:
    command = (
        'for d in /sys/class/mtd/mtd[0-9]*; do [ -d "$d" ] || continue; '
        'dev=$(basename "$d"); case "$dev" in *ro) continue;; esac; '
        'n=$(cat "$d/name" 2>/dev/null); s=$(cat "$d/size" 2>/dev/null); '
        'e=$(cat "$d/erasesize" 2>/dev/null); '
        'echo "SYSFS_MTD dev=$dev name=$n size=$s erasesize=$e"; done'
    )
    rc, text = telnet.command(command, timeout=45, echo=False)
    if rc:
        raise Error(tr("не удалось прочитать sysfs MTD", "failed to read sysfs MTD"))
    out: dict[int, tuple[int, int, str]] = {}
    for line in text.splitlines():
        m = re.match(r"^SYSFS_MTD\s+dev=mtd(\d+)\s+name=(.*?)\s+size=(\d+)\s+erasesize=(\d+)\s*$", line.strip())
        if m:
            out[int(m.group(1))] = (int(m.group(3)), int(m.group(4)), m.group(2))
    return out


def _stock_live_geometry_preflight(
    telnet: Telnet,
    expected_family: str,
    require_ro: bool = True,
    *,
    require_slot_family: bool = True,
) -> tuple[dict[int, tuple[int, int, str]], str, str]:
    """Prove live stock geometry before an operation touches the device.

    ``require_slot_family`` is what separates reading from writing. Installation
    needs mtd2..mtd5 to name a family, because that choice selects the firmware
    payload. Backup does not: it is read-only, the device is identified by the
    fixed partitions, the /proc/mtd <-> sysfs cross-check and the MAC recorded in
    DEVICE_MAC.txt, and refusing to copy a NAND because a vendor slot revision
    drifted would deny a rollback image to exactly the operator who needs one.
    Callers that only read pass ``require_slot_family=False`` and get whatever is
    actually there, with the unrecognised layout reported as evidence.
    """
    rc, proc_text = telnet.command("cat /proc/mtd", timeout=20, echo=False)
    proc = parse_proc_mtd_text(proc_text)
    if rc or tuple(sorted(proc)) != EXPECTED_NUMBERS:
        raise Error(tr("не удалось получить полную stock-разметку /proc/mtd", "failed to obtain the complete stock /proc/mtd map"))
    sizes = {number: row[0] for number, row in proc.items()}
    family = detect_stock_backup_family(sizes)
    variant = detect_stock_backup_variant(sizes)
    if family not in ("md", "mf"):
        if require_slot_family:
            raise Error(tr("stock slot layout не распознан: " + _slot_layout_diagnostic(sizes), "stock slot layout is not recognized: " + _slot_layout_diagnostic(sizes)))
        print(tr(
            "[WARNING] Ревизия stock-слотов mtd2..mtd5 не распознана: " + _slot_layout_diagnostic(sizes),
            "[WARNING] The mtd2..mtd5 stock slot revision is not recognized: " + _slot_layout_diagnostic(sizes),
        ))
        print(tr(
            "[INFO] Backup продолжается по факту: фиксированные разделы, /proc/mtd == sysfs и MAC устройства проверяются как обычно. Установка на этом аппарате останется заблокированной до распознавания семейства.",
            "[INFO] Backup continues as observed: the fixed partitions, /proc/mtd == sysfs and the device MAC are verified as usual. Installation on this unit stays blocked until the family is recognized.",
        ))
    if family in ("md", "mf") and expected_family in ("md", "mf") and family != expected_family:
        raise Error(tr(
            f"модель/разметка не совпали: Web={expected_family.upper()}, MTD={family.upper()} ({variant})",
            f"model/layout mismatch: Web={expected_family.upper()}, MTD={family.upper()} ({variant})",
        ))
    for number, expected in FIXED_EXPECTED.items():
        if proc[number][0] != expected:
            raise Error(tr(
                f"mtd{number}: размер 0x{proc[number][0]:08X}, ожидается 0x{expected:08X}; backup заблокирован",
                f"mtd{number}: size 0x{proc[number][0]:08X}, expected 0x{expected:08X}; backup is blocked",
            ))
        if proc[number][1] != 0x20000:
            raise Error(tr(f"mtd{number}: неожиданный erase size 0x{proc[number][1]:X}", f"mtd{number}: unexpected erase size 0x{proc[number][1]:X}"))
    sysfs = _stock_sysfs_mtd_snapshot(telnet)
    missing = []
    mismatch = []
    for number in EXPECTED_NUMBERS:
        p = proc.get(number)
        x = sysfs.get(number)
        if p is None or x is None:
            missing.append(number)
            continue
        if p[0] != x[0] or p[1] != x[1] or (x[2] and p[2] != x[2]):
            mismatch.append(number)
    if missing or mismatch:
        raise Error(tr(
            f"/proc/mtd и sysfs не согласованы (missing={missing}, mismatch={mismatch}); backup заблокирован",
            f"/proc/mtd and sysfs disagree (missing={missing}, mismatch={mismatch}); backup is blocked",
        ))
    # An unrecognised slot revision must not silently drop the MF read-only
    # device requirement, so fall back to the family the Web UI reported.
    effective_family = family if family in ("md", "mf") else expected_family
    if effective_family == "mf" and require_ro:
        rc, ro_text = telnet.command(
            'ok=1; n=0; while [ $n -le 16 ]; do [ -r /dev/mtd${n}ro ] || { echo MISSING_RO=$n; ok=0; }; n=$((n+1)); done; echo RO_OK=$ok',
            timeout=20, echo=False)
        if rc or "RO_OK=1" not in ro_text:
            raise Error(tr("MF backup требует доступные /dev/mtd0ro..mtd16ro", "MF backup requires readable /dev/mtd0ro..mtd16ro"))
    label = family.upper() if family in ("md", "mf") else f"{(expected_family or 'unknown').upper()} (по Web, слот не распознан)"
    print(tr(
        f"[OK] Stock geometry: {label} / {variant}; /proc/mtd == sysfs; restore span 0x{proc[16][0]:08X}.",
        f"[OK] Stock geometry: {label} / {variant}; /proc/mtd == sysfs; restore span 0x{proc[16][0]:08X}.",
    ))
    return proc, effective_family, variant


def _human_transfer_size(value: int) -> str:
    value = max(0, int(value))
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MiB"
    return f"{value / (1024 * 1024 * 1024):.2f} GiB"


def _read_transport_sha_sidecar(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"(?im)^router_stream_sha256=([0-9a-f]{64})$", text)
    return m.group(1).lower() if m else None


_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")


def _stock_interface_macs(telnet: Telnet) -> dict[str, str]:
    """Read interface MAC addresses from stock Linux without changing device state."""
    command = (
        "for p in /sys/class/net/*/address; do "
        "[ -r \"$p\" ] || continue; "
        "i=${p%/address}; i=${i##*/}; [ \"$i\" = lo ] && continue; "
        "a=$(cat \"$p\" 2>/dev/null | tr 'A-F' 'a-f'); "
        "printf '__NOKIA_IFMAC__'; printf '%s=%s' \"$i\" \"$a\"; printf '__\\n'; "
        "done"
    )
    rc, text = telnet.command(command, timeout=20, echo=False)
    if rc:
        return {}
    result: dict[str, str] = {}
    for value in _runtime_marker_values(text, "__NOKIA_IFMAC__"):
        if "=" not in value:
            continue
        interface, mac = value.split("=", 1)
        interface = interface.strip()
        mac = mac.strip().lower()
        if not interface or not _MAC_RE.fullmatch(mac):
            continue
        if mac in {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}:
            continue
        result[interface] = mac
    return dict(sorted(result.items()))


def _backup_primary_mac(macs: dict[str, str]) -> tuple[str, str]:
    for interface in ("eth0", "br0", "eth1", "eth2"):
        if interface in macs:
            return interface, macs[interface]
    if macs:
        interface = sorted(macs)[0]
        return interface, macs[interface]
    return "unknown", "UNKNOWN"


def _read_backup_device_mac(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return None
    mac = values.get("primary_mac", "").lower()
    interface = values.get("primary_interface", "unknown")
    if _MAC_RE.fullmatch(mac):
        return interface, mac
    return None


def _write_backup_device_mac(destination: Path, telnet: Telnet, model_name: str, family: str) -> tuple[str, str]:
    macs = _stock_interface_macs(telnet)
    interface, mac = _backup_primary_mac(macs)
    existing = _read_backup_device_mac(destination / "DEVICE_MAC.txt")
    if existing is not None and mac != "UNKNOWN" and existing[1] != mac:
        raise Error(tr(
            f"backup-каталог уже привязан к другому MAC: {existing[1]} != {mac}",
            f"backup directory is already bound to a different MAC: {existing[1]} != {mac}",
        ))
    lines = [
        f"model={model_name}",
        f"family={family}",
        f"captured_at_local={time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"captured_at_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "source=stock-linux-sysfs",
        f"primary_interface={interface}",
        f"primary_mac={mac}",
    ]
    for name, value in macs.items():
        lines.append(f"interface_{name}={value}")
    write_text(destination / "DEVICE_MAC.txt", "\n".join(lines) + "\n")
    if mac == "UNKNOWN":
        print(tr(
            "[WARNING] Не удалось определить MAC stock-устройства; DEVICE_MAC.txt создан с primary_mac=UNKNOWN.",
            "[WARNING] Could not determine the stock device MAC; DEVICE_MAC.txt was created with primary_mac=UNKNOWN.",
        ))
    else:
        print(tr(
            f"[OK] Backup source MAC: {mac} ({interface}); сохранён в DEVICE_MAC.txt.",
            f"[OK] Backup source MAC: {mac} ({interface}); saved to DEVICE_MAC.txt.",
        ))
    return interface, mac


def backup_tftp(
    access: StockAccess,
    router_host: str,
    destination: Path,
    local_ip: str | None = None,
    port: int = 1069,
    block_size: int = 4096,
    expected_family: str = "md",
) -> Path:
    """Create a direct TFTP backup while reusing a healthy root session.

    One UID-0 Telnet shell is kept across successful partitions. A transfer
    timeout, receiver/socket error, missing completion marker, or Telnet error
    marks that shell as unsynchronised: it is closed to send HUP to a possibly
    stuck BusyBox tftp pipeline, and only the current partition is retried in a
    newly authenticated root session. Validated final files remain untouched.
    """
    local_ip = local_ip or local_ip_for(router_host)
    destination.mkdir(parents=True, exist_ok=True)

    telnet: Telnet | None = None
    try:
        telnet = login_root_family(access, expected_family, allow_service_provisioning=True)
        tftp = find_tftp(telnet)
        if expected_family == "md":
            # Preserve the hardware-confirmed MD backup/install preflight.
            rc, proc_text = telnet.command("cat /proc/mtd", timeout=15, echo=False)
            proc = parse_proc_mtd_text(proc_text)
            if rc or tuple(sorted(proc)) != EXPECTED_NUMBERS:
                raise Error("не удалось получить точную stock-разметку /proc/mtd")
            sizes = {number: row[0] for number, row in proc.items()}
            detected_family = detect_stock_backup_family(sizes)
            detected_variant = detect_stock_backup_variant(sizes)
        else:
            proc, detected_family, detected_variant = _stock_live_geometry_preflight(
                telnet, expected_family, require_slot_family=False)
            rc, stream_tools = telnet.command(
                'ok=1; for x in tee sha256sum; do command -v "$x" >/dev/null 2>&1 || { echo MISSING_STREAM_TOOL=$x; ok=0; }; done; '
                '(command -v mkfifo >/dev/null 2>&1 || command -v mknod >/dev/null 2>&1) || { echo MISSING_STREAM_TOOL=mkfifo_or_mknod; ok=0; }; '
                'echo STREAM_TOOLS_OK=$ok',
                timeout=20, echo=False,
            )
            if rc or "STREAM_TOOLS_OK=1" not in stream_tools:
                raise Error(tr(
                    "MF TFTP backup требует tee/sha256sum и mkfifo или mknod для проверки ровно переданного gzip-потока",
                    "MF TFTP backup requires tee/sha256sum plus mkfifo or mknod to verify the exact transmitted gzip stream",
                ))
        if detected_family == "mf":
            # A failed/resumed run must never leave an old success marker behind.
            for stale_marker in ("BACKUP_COMPLETE", "BACKUP_HW_VALIDATED"):
                (destination / stale_marker).unlink(missing_ok=True)
        model_name = "Nokia XG-040G-MD" if detected_family == "md" else "Nokia XG-040G-MF"
        _write_backup_device_mac(destination, telnet, model_name, detected_family)
        write_text(destination / "proc_mtd.txt", "\n".join(
            f'mtd{n}: {size:08x} {erase:08x} "{name}"' for n, (size, erase, name) in sorted(proc.items())
        ) + "\n")
        for meta_name, command in (
            ("cmdline.txt", "cat /proc/cmdline"),
            ("uname.txt", "uname -a"),
            ("id.txt", "id"),
            ("dmesg_full.txt", "dmesg"),
        ):
            _, text = telnet.command(command, timeout=30, echo=False)
            cleaned = re.sub(r"__NOKIA_RC_\d+_\d+__", "", text)
            write_text(destination / meta_name, cleaned.strip() + "\n")

        print(tr(
            f"Приёмник TFTP: {local_ip}:{port}/UDP, размер блока {block_size}. Брандмауэр Windows может запросить разрешение доступа.",
            f"TFTP receiver: {local_ip}:{port}/UDP, block size {block_size}. Windows Firewall may ask for access.",
        ))
        print(tr(
            "Один root-сеанс Telnet переиспользуется для успешных разделов; новый сеанс открывается только после фактического сбоя передачи или потери синхронизации shell.",
            "One Telnet root session is reused for successful partitions; a new session is opened only after an actual transfer failure or loss of shell synchronisation.",
        ))
        for number in EXPECTED_NUMBERS:
            size, _, name = proc[number]
            target = destination / f"mtd{number}_{name}.bin.gz"
            partial = destination / (target.name + ".part")
            if target.is_file():
                try:
                    validate_gzip_size(target, size)
                    if detected_family == "mf" and number == 16:
                        transport_sidecar = destination / "mtd16_transport_sha256.txt"
                        saved_stream_sha = _read_transport_sha_sidecar(transport_sidecar)
                        local_stream_sha = sha_file(target)
                        if not saved_stream_sha or saved_stream_sha != local_stream_sha:
                            print(tr(
                                "[WARNING] Для сохранённого mtd16 нет валидного transport-stream SHA256; mtd16 будет снят заново без сравнения с изменяемым live NAND.",
                                "[WARNING] The retained mtd16 has no valid transport-stream SHA256; mtd16 will be recaptured without comparing it to mutable live NAND.",
                            ))
                            target.unlink(missing_ok=True)
                            transport_sidecar.unlink(missing_ok=True)
                        else:
                            print(tr(
                                f"[{number + 1}/{len(EXPECTED_NUMBERS)}] Сохранён ранее проверенный {target.name}; gzip/size/transport SHA256 PASS.",
                                f"[{number + 1}/{len(EXPECTED_NUMBERS)}] Existing validated {target.name} retained; gzip/size/transport SHA256 PASS.",
                            ))
                            continue
                    else:
                        print(tr(
                            f"[{number + 1}/{len(EXPECTED_NUMBERS)}] Сохранён ранее проверенный {target.name}.",
                            f"[{number + 1}/{len(EXPECTED_NUMBERS)}] Existing validated {target.name} retained.",
                        ))
                        continue
                except Error:
                    target.unlink(missing_ok=True)
                    if detected_family == "mf" and number == 16:
                        (destination / "mtd16_transport_sha256.txt").unlink(missing_ok=True)

            for attempt in range(1, 4):
                partial.unlink(missing_ok=True)
                if telnet is None:
                    print(tr(
                        f"[WAIT] Открываю новый UID 0 Telnet-сеанс для повтора mtd{number}.",
                        f"[WAIT] Opening a new UID-0 Telnet session to retry mtd{number}.",
                    ))
                    telnet = login_root_family(access, expected_family, allow_service_provisioning=True)

                ready = threading.Event()
                cancel = threading.Event()
                result = TftpResult()
                thread = threading.Thread(
                    target=receive_tftp_put,
                    args=("0.0.0.0", port, partial, target.name, router_host, ready, result, cancel, 180, block_size),
                    daemon=True,
                )
                thread.start()
                if not ready.wait(5):
                    cancel.set()
                    thread.join(3)
                    raise Error(f"не удалось запустить TFTP-приёмник на UDP {port}")

                attempt_error: Exception | str | None = None
                marker_ok = False
                session_broken = False
                source_stream_sha: str | None = None
                try:
                    suffix = tr(" Для mtd16 это может занять долго...", " mtd16 may take a while...") if number == 16 else ""
                    print(tr(
                        f"[{number + 1}/{len(EXPECTED_NUMBERS)}] TFTP mtd{number} ({name}), попытка {attempt}.{suffix}",
                        f"[{number + 1}/{len(EXPECTED_NUMBERS)}] TFTP mtd{number} ({name}), attempt {attempt}.{suffix}",
                    ))
                    print(tr(
                        f"[TRANSFER] mtd{number}: приём начат; raw {_human_transfer_size(size)}.",
                        f"[TRANSFER] mtd{number}: receive started; raw {_human_transfer_size(size)}.",
                    ))
                    read_device = f"/dev/mtd{number}ro" if detected_family == "mf" else f"/dev/mtd{number}"
                    if detected_family == "mf" and number == 16:
                        fifo = f"/tmp/nokia-stream-{number}.fifo"
                        hash_file = f"/tmp/nokia-stream-{number}.sha"
                        command = (
                            f"rm -f {shlex.quote(fifo)} {shlex.quote(hash_file)}; "
                            f"if (command -v mkfifo >/dev/null 2>&1 && mkfifo {shlex.quote(fifo)}) || "
                            f"(command -v mknod >/dev/null 2>&1 && mknod {shlex.quote(fifo)} p); then "
                            f"sha256sum < {shlex.quote(fifo)} > {shlex.quote(hash_file)} & __hpid=$!; "
                            f"dd if={shlex.quote(read_device)} bs=131072 2>/tmp/nokia-dd-{number}.log | gzip -1 | "
                            f"tee {shlex.quote(fifo)} | {shlex.quote(tftp)} -p -l - -r {shlex.quote(target.name)} -b {block_size} "
                            f"{shlex.quote(local_ip)} {port}; __trc=$?; wait $__hpid; __hrc=$?; "
                            f"set -- $(cat {shlex.quote(hash_file)} 2>/dev/null); __sh=$1; "
                            f"rm -f {shlex.quote(fifo)} {shlex.quote(hash_file)}; "
                            f"[ $__hrc -eq 0 ] || __sh=FAIL; echo __TFTP_PUT_{number}_${{__trc}}_SHA_${{__sh}}__; "
                            f"else echo __TFTP_PUT_{number}_91_SHA_FAIL__; fi"
                        )
                        marker_pattern = rf"__TFTP_PUT_{number}_(\d+)_SHA_([0-9a-fA-F]{{64}}|FAIL)__"
                    else:
                        command = (
                            f"dd if={shlex.quote(read_device)} bs=131072 2>/tmp/nokia-dd-{number}.log | gzip -1 | "
                            f"{shlex.quote(tftp)} -p -l - -r {shlex.quote(target.name)} -b {block_size} "
                            f"{shlex.quote(local_ip)} {port}"
                        )
                        command += f"; __rc=$?; echo __TFTP_PUT_{number}_${{__rc}}__"
                        marker_pattern = rf"__TFTP_PUT_{number}_(\d+)__"
                    telnet.send_line(command)
                    started = time.time()
                    deadline = started + 7200
                    last_report = 0
                    last_bytes = 0
                    while thread.is_alive() and time.time() < deadline:
                        elapsed = int(time.time() - started)
                        done = int(result.bytes_transferred)
                        if done > 0 and (elapsed >= last_report + 15 or done >= last_bytes + 4 * 1024 * 1024):
                            print(tr(
                                f"[TRANSFER] mtd{number}: принято {_human_transfer_size(done)} сжатых данных, прошло {elapsed}s...",
                                f"[TRANSFER] mtd{number}: received {_human_transfer_size(done)} compressed, elapsed {elapsed}s...",
                            ))
                            last_report = elapsed
                            last_bytes = done
                        thread.join(1)
                    if thread.is_alive():
                        cancel.set()
                        thread.join(3)
                        attempt_error = tr("тайм-аут передачи", "transfer timeout")
                        session_broken = True
                    elif result.error:
                        attempt_error = result.error
                        session_broken = True
                    else:
                        marker_text = telnet.wait_regex(marker_pattern, 90, echo=False)
                        marker_match = re.search(marker_pattern, marker_text)
                        if marker_match:
                            marker_ok = marker_match.group(1) == "0"
                            if detected_family == "mf" and number == 16:
                                source_stream_sha = marker_match.group(2).lower()
                                if source_stream_sha == "fail":
                                    marker_ok = False
                                    attempt_error = "router stream sha256 failed"
                            if not marker_ok and attempt_error is None:
                                attempt_error = "router tftp rc != 0"
                        else:
                            attempt_error = "completion marker not received"
                            session_broken = True
                except (OSError, Error) as exc:
                    attempt_error = exc
                    session_broken = True
                finally:
                    cancel.set()
                    thread.join(3)
                    if session_broken and telnet is not None:
                        telnet.close()
                        telnet = None

                if attempt_error is not None or not marker_ok:
                    detail = str(attempt_error or result.error or "router tftp rc != 0")
                    if session_broken:
                        action_ru = "Повреждённый сеанс закрыт; повторю только этот раздел в новом root-сеансе."
                        action_en = "The unsynchronised session was closed; only this partition will be retried in a new root session."
                    else:
                        action_ru = "Shell синхронизирован; повторю только этот раздел в текущем root-сеансе."
                        action_en = "The shell remains synchronised; only this partition will be retried in the current root session."
                    print(tr(
                        f"[WARNING] TFTP mtd{number}, попытка {attempt} не завершена: {detail}. {action_ru}",
                        f"[WARNING] TFTP mtd{number}, attempt {attempt} did not complete: {detail}. {action_en}",
                    ))
                    partial.unlink(missing_ok=True)
                    continue
                try:
                    validate_gzip_size(partial, size)
                except Error as exc:
                    print(tr(
                        f"[WARNING] {exc}; shell остаётся синхронизированным, повторяется только mtd{number}.",
                        f"[WARNING] {exc}; the shell remains synchronised and only mtd{number} is retried.",
                    ))
                    continue
                compressed_sha = sha_file(partial)
                if detected_family == "mf" and number == 16:
                    if not source_stream_sha or source_stream_sha != compressed_sha:
                        partial.unlink(missing_ok=True)
                        raise Error(tr(
                            f"MF mtd16: SHA256 переданного gzip-потока не совпал с файлом на ПК: router={source_stream_sha or 'missing'}, PC={compressed_sha}",
                            f"MF mtd16: transmitted gzip-stream SHA256 does not match the PC file: router={source_stream_sha or 'missing'}, PC={compressed_sha}",
                        ))
                partial.replace(target)
                print(tr(
                    f"  OK: {target.name}; raw {_human_transfer_size(size)}; compressed {_human_transfer_size(target.stat().st_size)}; SHA256 {compressed_sha}",
                    f"  OK: {target.name}; raw {_human_transfer_size(size)}; compressed {_human_transfer_size(target.stat().st_size)}; SHA256 {compressed_sha}",
                ))
                if detected_family == "mf" and number == 16:
                    write_text(
                        destination / "mtd16_transport_sha256.txt",
                        f"router_stream_sha256={source_stream_sha}\npc_file_sha256={compressed_sha}\nraw_size={size}\ncompressed_size={target.stat().st_size}\n",
                    )
                    (destination / "mtd16_second_read_sha256.txt").unlink(missing_ok=True)
                    print(tr(
                        f"[OK] MF mtd16 transport SHA256 PASS: router gzip stream == PC file ({compressed_sha}).",
                        f"[OK] MF mtd16 transport SHA256 PASS: router gzip stream == PC file ({compressed_sha}).",
                    ))
                    print(tr(
                        "[INFO] Повторный full-NAND SHA256 не является fatal gate: live stock может менять config/data/log во время backup.",
                        "[INFO] A second full-NAND SHA256 is not a fatal gate: live stock may change config/data/log during backup.",
                    ))
                break
            else:
                raise Error(f"не удалось надёжно снять mtd{number} через TFTP после трёх попыток")

        (destination / "bosa.bin").write_bytes(read_dump(find_dump(destination, 6)))
        (destination / "ri.bin").write_bytes(read_dump(find_dump(destination, 7)))
        sums = []
        for path in sorted(p for p in destination.iterdir() if p.is_file() and p.name not in ("SHA256SUMS.txt", "BACKUP_COMPLETE")):
            sums.append(f"{sha_file(path)}  {path.name}")
        write_text(destination / "SHA256SUMS.txt", "\n".join(sums) + "\n")
        validation = verify_stock_restore_backup(destination)
        validated_family = str(validation.get("stock_family"))
        # "unknown" is not a contradiction: the slot revision was already reported
        # as unrecognised above. Only a different *named* family means the dump
        # disagrees with the live device, and that still blocks.
        if validated_family in ("md", "mf") and validated_family != detected_family:
            raise Error(tr("итоговый validator определил другую family", "the final validator detected a different family"))
        write_text(destination / "BACKUP_COMPLETE", f"{model_name} direct TFTP backup complete ({detected_variant})\n")
        # Common MD/MF evidence marker.  It records that the backup passed the
        # restore-grade validator, but the installer never trusts the marker by
        # itself: selected backups are revalidated from their actual content.
        write_text(destination / "BACKUP_HW_VALIDATED", f"family={detected_family}\nvariant={detected_variant}\nvalidator=verify_stock_restore_backup\npolicy=content-revalidated-before-install\n")
        print(tr(
            f"[OK] {model_name} / {detected_variant}: полный stock backup прошёл restore-validator.",
            f"[OK] {model_name} / {detected_variant}: full stock backup passed the restore validator.",
        ))
        return destination
    finally:
        if telnet is not None:
            telnet.close()

def backup_to_usb(telnet: Telnet, usb_mount: str, family: str = "md") -> str:
    telnet.upload_text("/tmp/nokia-backup-agent.sh", BACKUP_AGENT.read_text())
    # Disable terminal input echo while the agent command is entered. Runtime
    # output remains visible, but the shell command itself is not printed.
    telnet.command("stty -echo 2>/dev/null || true", timeout=10, echo=False)
    try:
        rc, text = telnet.command(
            f"NOKIA_LANG={shlex.quote(ensure_language())} NOKIA_USB_QUIET=1 "
            f"NOKIA_MODEL_NAME={shlex.quote('Nokia XG-040G-MF' if family == 'mf' else 'Nokia XG-040G-MD')} "
            f"NOKIA_BACKUP_PREFIX={shlex.quote('nokia-xg040gmf-backup' if family == 'mf' else 'nokia-xg040gmd-backup')} "
            f"NOKIA_BACKUP_FAMILY={shlex.quote(family)} "
            f"NOKIA_PREFER_RO_MTD={'1' if family == 'mf' else '0'} "
            f"ash /tmp/nokia-backup-agent.sh {shlex.quote(usb_mount)}",
            timeout=7200,
            echo=True,
        )
    finally:
        try:
            telnet.command("stty echo 2>/dev/null || true", timeout=10, echo=False)
        except Exception:
            pass
    if rc:
        detail = _remote_error_line(text)
        raise Error("backup на USB завершился ошибкой" + (f": {detail}" if detail else ""))
    values = _runtime_marker_values(text, "__BACKUP_DIR__")
    if not values:
        raise Error("backup завершён, но не удалось определить каталог на USB")
    selected = values[-1]
    expected_prefix = usb_mount.rstrip("/") + "/"
    if not selected.startswith(expected_prefix):
        raise Error(tr(
            f"backup-agent вернул неожиданный путь: {selected}",
            f"backup agent returned an unexpected path: {selected}",
        ))
    return selected


def _samba_share_root(path_text: str) -> str:
    try:
        anchor = PureWindowsPath(path_text).anchor.rstrip("\\")
    except Exception as exc:
        raise Error("некорректный UNC-путь Samba") from exc
    if not anchor.startswith("\\\\") or len(anchor.strip("\\").split("\\")) != 2:
        raise Error("некорректный UNC-путь Samba")
    return anchor


def _windows_error_text(code: int) -> str:
    try:
        text = ctypes.FormatError(code).strip()
    except Exception:
        text = ""
    return text or f"Windows error {code}"


def _wnet_api():
    """Return configured MPR functions and NETRESOURCEW.

    Loaded lazily so non-Windows hosts can still run syntax checks and tests.
    """
    if not hasattr(ctypes, "WinDLL"):
        raise Error(tr(
            "Windows API подключения к Samba недоступен",
            "The Windows Samba connection API is unavailable",
        ))
    from ctypes import wintypes

    class NETRESOURCEW(ctypes.Structure):
        _fields_ = [
            ("dwScope", wintypes.DWORD),
            ("dwType", wintypes.DWORD),
            ("dwDisplayType", wintypes.DWORD),
            ("dwUsage", wintypes.DWORD),
            ("lpLocalName", wintypes.LPWSTR),
            ("lpRemoteName", wintypes.LPWSTR),
            ("lpComment", wintypes.LPWSTR),
            ("lpProvider", wintypes.LPWSTR),
        ]

    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    add = mpr.WNetAddConnection2W
    add.argtypes = [ctypes.POINTER(NETRESOURCEW), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    add.restype = wintypes.DWORD
    cancel = mpr.WNetCancelConnection2W
    cancel.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL]
    cancel.restype = wintypes.DWORD
    return add, cancel, NETRESOURCEW


def _wnet_add_connection(remote: str, user: str, password: str) -> int:
    add, _cancel, netresource_type = _wnet_api()
    resource = netresource_type()
    resource.dwType = 1  # RESOURCETYPE_DISK
    resource.lpRemoteName = remote
    # CONNECT_TEMPORARY keeps the credential out of the persistent Windows profile.
    return int(add(ctypes.byref(resource), password, user, 0x00000004))


def _wnet_cancel_connection(remote: str) -> int:
    _add, cancel, _netresource_type = _wnet_api()
    return int(cancel(remote, 0, True))


def _samba_server_root(share_root: str) -> str:
    parts = share_root.strip("\\").split("\\")
    if len(parts) != 2 or not all(parts):
        raise Error("некорректный UNC-путь Samba")
    return "\\\\" + parts[0]


def connect_samba_share(path_text: str, user: str, password: str) -> None:
    """Establish a protected Windows UNC session without an OS prompt.

    rc4 used ``net use ... *`` and tried to feed the hidden password through
    stdin. Some Windows builds read that prompt directly from the console, so
    the piped password can be ignored even though the same password succeeds
    when typed by hand. WNetAddConnection2W accepts the secret directly in
    process memory and never places it in argv, stdout or the session log.
    """
    if os.name != "nt" or not path_text.startswith("\\\\"):
        return
    if not user or not password:
        raise Error(tr(
            "для защищённого Samba-ресурса нужны пользователь и пароль",
            "a username and password are required for the protected Samba share",
        ))
    share_root = _samba_share_root(path_text)
    rc = _wnet_add_connection(share_root, user, password)
    if rc == 0:
        return

    # Explorer or an earlier wizard run may have opened an anonymous session.
    # Windows then reports a credential conflict before checking the supplied
    # password. Remove only connections to this Nokia share/server and retry.
    if rc in (85, 1202, 1219):
        server_root = _samba_server_root(share_root)
        _wnet_cancel_connection(share_root)
        _wnet_cancel_connection(server_root + "\\IPC$")
        time.sleep(0.4)
        rc = _wnet_add_connection(share_root, user, password)
        if rc == 0:
            return

    detail = _windows_error_text(rc)
    if rc in (5, 86, 1326):
        message_ru = f"Samba отклонила пользователя или пароль (Windows {rc}: {detail})"
        message_en = f"Samba rejected the username or password (Windows {rc}: {detail})"
    else:
        message_ru = f"не удалось подключить Samba (Windows {rc}: {detail})"
        message_en = f"failed to connect to Samba (Windows {rc}: {detail})"
    raise Error(tr(message_ru, message_en))


def ensure_share_access(path_text: str, user: str = "", password: str = "") -> Path:
    path = Path(path_text)
    if os.name == "nt" and path_text.startswith("\\\\"):
        connect_samba_share(path_text, user, password)
    if not path.is_dir():
        raise Error(f"Samba/смонтированная папка недоступна: {path}")
    return path

def _share_usb_and_install_paths(path_text: str, user: str = "", password: str = "") -> tuple[Path, Path]:
    """Return the accessible USB root and exact local installation directory.

    The prompt accepts either the USB root or the complete
    ``.../nokia-openwrt-install`` directory.  The destination itself may not
    exist yet, so access is tested against the existing parent directory.
    """
    requested = Path(path_text)
    if requested.name.lower() == "nokia-openwrt-install":
        usb_root = requested.parent
        install_dir = requested
    else:
        usb_root = requested
        install_dir = requested / "nokia-openwrt-install"
    usb_root = ensure_share_access(str(usb_root), user, password)
    return usb_root, install_dir


def _infer_router_usb_mount_from_unc(path_text: str) -> str | None:
    """Map Nokia's stock UNC ``\\host\\mnt\\USB_disc1`` to ``/mnt/USB_disc1``."""
    if not path_text.startswith("\\\\"):
        return None
    try:
        parts = list(PureWindowsPath(path_text).parts)
    except Exception:
        return None
    # PureWindowsPath parts: ('\\\\host\\share\\', 'subdir', ...)
    if not parts:
        return None
    anchor = PureWindowsPath(path_text).anchor.rstrip("\\")
    anchor_parts = anchor.strip("\\").split("\\")
    if len(anchor_parts) != 2:
        return None
    share_name = anchor_parts[1]
    relative = list(PureWindowsPath(path_text).relative_to(PureWindowsPath(path_text).anchor).parts)
    if relative and relative[-1].lower() == "nokia-openwrt-install":
        relative.pop()
    if share_name.lower() != "mnt":
        return None
    path_parts = ["mnt", *relative]
    return "/" + "/".join(part for part in path_parts if part)


def _unique_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = str(PurePosixPath(value))
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _runtime_marker_values(text: str, prefix: str) -> list[str]:
    """Extract runtime marker values while rejecting shell format placeholders.

    Telnet echoes commands. A command containing ``printf '...%s...'`` must not
    be mistaken for the command's later runtime output.
    """
    values = re.findall(r"(?:^|\r?\n)" + re.escape(prefix) + r"([^\r\n]*?)__", text)
    return [value.strip() for value in values if value.strip() and value.strip() not in {"%s", "$d"}]


def cleanup_incomplete_usb_backups(usb_root: Path) -> None:
    candidates: list[Path] = []
    for child in sorted(usb_root.glob('nokia-xg040gmd-backup-*')):
        if not child.is_dir():
            continue
        if child.name.endswith('.incomplete') or not (child / 'BACKUP_COMPLETE').is_file():
            candidates.append(child)
    if not candidates:
        return
    print(tr(
        "\n[ПРЕДУПРЕЖДЕНИЕ] На USB найдены незавершённые backup-каталоги:",
        "\n[WARNING] Incomplete backup directories were found on the USB drive:",
    ))
    for path in candidates:
        print(f"  - {path}")
    answer = input(tr(
        "Удалить только эти незавершённые каталоги? [y/N]: ",
        "Delete only these incomplete directories? [y/N]: ",
    )).strip().lower()
    if answer not in ('y', 'yes', 'д', 'да'):
        print(tr(
            "[OK] Незавершённые каталоги оставлены; новый backup будет создан отдельно.",
            "[OK] Incomplete directories were preserved; the new backup will use a separate directory.",
        ))
        return
    for path in candidates:
        shutil.rmtree(path)
        print(tr(f"[OK] Удалён незавершённый каталог: {path}", f"[OK] Removed incomplete directory: {path}"))


def cleanup_incomplete_router_backups(telnet: Telnet, usb_mount: str) -> None:
    """Offer cleanup of incomplete backups without blocking a new backup.

    Complete backup directories from this or any other Nokia are ignored. The
    backup agent always creates a new unique directory, so even an unavailable
    directory scan is advisory rather than a safety gate.
    """
    mount_q = shlex.quote(usb_mount.rstrip("/"))
    command = (
        f'for d in {mount_q}/nokia-xg040gmd-backup-*; do [ -d "$d" ] || continue; '
        'case "$d" in *.incomplete) bad=1 ;; *) [ -f "$d/BACKUP_COMPLETE" ] && bad=0 || bad=1 ;; esac; '
        '[ "$bad" = 1 ] && { printf \'__NOKIA_INCOMPLETE_BACKUP__\'; printf \'%s\' "$d"; printf \'__\\n\'; }; '
        'done; printf \'__NOKIA_INCOMPLETE_SCAN__\'; printf \'OK\'; printf \'__\\n\''
    )
    rc, text = telnet.command(command, timeout=60, echo=False)
    scan_ok = "OK" in _runtime_marker_values(text, "__NOKIA_INCOMPLETE_SCAN__")
    if rc or not scan_ok:
        print(tr(
            "[ПРЕДУПРЕЖДЕНИЕ] Не удалось просканировать старые незавершённые backup. "
            "Это не блокирует работу: существующие каталоги не будут изменены, новый backup получит отдельное имя.",
            "[WARNING] Existing incomplete backups could not be scanned. "
            "This does not block the operation: existing directories will not be modified and the new backup will use a unique name.",
        ))
        return
    candidates = _runtime_marker_values(text, "__NOKIA_INCOMPLETE_BACKUP__")
    safe: list[str] = []
    prefix = usb_mount.rstrip("/") + "/"
    for item in candidates:
        name = PurePosixPath(item).name
        if item.startswith(prefix) and name.startswith("nokia-xg040gmd-backup-"):
            safe.append(item)
    safe = list(dict.fromkeys(safe))
    if not safe:
        print(tr(
            "[OK] Незавершённые backup-каталоги не найдены; существующие завершённые backup оставлены без изменений.",
            "[OK] No incomplete backup directories were found; existing completed backups were left unchanged.",
        ))
        return
    print(tr(
        "\n[ПРЕДУПРЕЖДЕНИЕ] На USB найдены незавершённые backup-каталоги:",
        "\n[WARNING] Incomplete backup directories were found on the USB drive:",
    ))
    for item in safe:
        print(f"  - {item}")
    answer = input(tr(
        "Удалить только эти незавершённые каталоги? [y/N]: ",
        "Delete only these incomplete directories? [y/N]: ",
    )).strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        print(tr(
            "[OK] Незавершённые каталоги оставлены; новый backup получит отдельное имя.",
            "[OK] Incomplete directories were preserved; the new backup will use a separate name.",
        ))
        return
    quoted = " ".join(shlex.quote(item) for item in safe)
    rc, _ = telnet.command(f"rm -rf {quoted}", timeout=300, echo=False)
    if rc:
        print(tr(
            "[ПРЕДУПРЕЖДЕНИЕ] Не удалось удалить выбранные незавершённые каталоги. "
            "Они оставлены без изменений; новый backup будет создан отдельно.",
            "[WARNING] The selected incomplete directories could not be removed. "
            "They were left unchanged and the new backup will be created separately.",
        ))
        return
    for item in safe:
        print(tr(f"[OK] Удалён незавершённый каталог: {item}", f"[OK] Removed incomplete directory: {item}"))

def resolve_router_usb_mount(telnet: Telnet, requested: str | None = None, share_path: str | None = None) -> str:
    inferred = _infer_router_usb_mount_from_unc(share_path or "")
    candidates = _unique_strings([requested, inferred, "/mnt/USB_disc1", "/mnt/USB_Disc1"])
    checks = " ".join(shlex.quote(item) for item in candidates)
    # Split the marker across three printf calls. The echoed command therefore
    # cannot contain a complete marker that matches the runtime-output regex.
    command = (
        f"for d in {checks}; do "
        "if [ -d \"$d\" ] && [ -w \"$d\" ]; then "
        "printf '__NOKIA_USB_MOUNT__'; printf '%s' \"$d\"; printf '__\\n'; break; fi; "
        "done"
    )
    rc, text = telnet.command(command, timeout=30, echo=False)
    values = _runtime_marker_values(text, "__NOKIA_USB_MOUNT__")
    if rc or not values:
        raise Error(tr(
            "USB mount не найден или недоступен для записи. Проверены пути: " + ", ".join(candidates),
            "USB mount was not found or is not writable. Paths checked: " + ", ".join(candidates),
        ))
    selected = values[-1]
    if selected not in candidates:
        raise Error(tr(f"Nokia вернула неожиданный USB-путь: {selected}", f"Nokia returned an unexpected USB path: {selected}"))
    return selected


def detect_router_install_dir(
    telnet: Telnet,
    install_dir: Path,
    requested_remote_mount: str | None = None,
    share_path: str | None = None,
) -> str:
    expected = sha_file(install_dir / "SHA256SUMS")
    inferred_mount = _infer_router_usb_mount_from_unc(share_path or "")
    explicit_dir = None
    if requested_remote_mount:
        explicit_dir = requested_remote_mount.rstrip("/")
        if PurePosixPath(explicit_dir).name.lower() != "nokia-openwrt-install":
            explicit_dir += "/nokia-openwrt-install"
    inferred_dir = inferred_mount.rstrip("/") + "/nokia-openwrt-install" if inferred_mount else None
    candidates = _unique_strings([
        explicit_dir, inferred_dir,
        "/mnt/USB_disc1/nokia-openwrt-install",
        "/mnt/USB_Disc1/nokia-openwrt-install",
    ])
    quoted = " ".join(shlex.quote(item) for item in candidates)
    command = (
        f"expected={shlex.quote(expected)}; for d in {quoted}; do "
        "[ -f \"$d/SHA256SUMS\" ] || continue; "
        "got=$(sha256sum \"$d/SHA256SUMS\" 2>/dev/null | awk '{print $1}'); "
        "if [ \"$got\" = \"$expected\" ]; then "
        "printf '__NOKIA_INSTALL_DIR__'; printf '%s' \"$d\"; printf '__\\n'; break; fi; done"
    )
    rc, text = telnet.command(command, timeout=60, echo=False)
    values = _runtime_marker_values(text, "__NOKIA_INSTALL_DIR__")
    if rc or not values:
        raise Error(tr(
            "не удалось найти скопированный Samba-пакет на Nokia. Проверены пути: " + ", ".join(candidates),
            "failed to locate the copied Samba package on Nokia. Paths checked: " + ", ".join(candidates),
        ))
    selected = values[-1]
    if selected not in candidates:
        raise Error(tr(f"Nokia вернула неожиданный путь пакета: {selected}", f"Nokia returned an unexpected package path: {selected}"))
    return selected


def _human_mib(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MiB"


class TransferProgress:
    """Throttled line-oriented progress suitable for console and session logs.

    Dynamic carriage-return bars are attractive in a terminal but turn LATEST.log
    into an unreadable stream.  This reporter emits a stable line on file changes,
    every five percentage points, at least every two seconds, and at completion.
    """

    def __init__(self, label: str, total_bytes: int, total_files: int = 0):
        self.label = label
        self.total_bytes = max(0, int(total_bytes))
        self.total_files = max(0, int(total_files))
        self.done_bytes = 0
        self.done_files = 0
        self.started = time.monotonic()
        self.last_emit = 0.0
        self.last_percent = -5
        self.last_file = ""
        self._emit(force=True)

    def start_file(self, name: str) -> None:
        name = str(name)
        if name != self.last_file:
            self.last_file = name
            self._emit(force=True)

    def add(self, count: int, name: str | None = None) -> None:
        if count > 0:
            self.done_bytes += int(count)
        if name:
            self.last_file = str(name)
        self._emit()

    def finish_file(self, name: str | None = None) -> None:
        if name:
            self.last_file = str(name)
        self.done_files += 1
        self._emit(force=True)

    def finish(self) -> None:
        if self.total_bytes:
            self.done_bytes = max(self.done_bytes, self.total_bytes)
        if self.total_files:
            self.done_files = max(self.done_files, self.total_files)
        self._emit(force=True, completed=True)

    def _emit(self, force: bool = False, completed: bool = False) -> None:
        now = time.monotonic()
        elapsed = max(now - self.started, 0.001)
        percent = int(min(100, self.done_bytes * 100 / self.total_bytes)) if self.total_bytes else -1
        if not force:
            percent_step = percent >= self.last_percent + 5 if percent >= 0 else False
            if not percent_step and now - self.last_emit < 2.0:
                return
        if percent >= 0:
            filled = min(20, percent // 5)
            bar = "#" * filled + "-" * (20 - filled)
            amount = f"{_human_mib(self.done_bytes)}/{_human_mib(self.total_bytes)}"
            progress = f"{percent:3d}% [{bar}] {amount}"
            self.last_percent = max(self.last_percent, percent)
        else:
            progress = _human_mib(self.done_bytes)
        speed = self.done_bytes / elapsed
        speed_text = f", {_human_mib(int(speed))}/s" if self.done_bytes else ""
        files_text = ""
        if self.total_files:
            files_text = tr(
                f", {min(self.done_files, self.total_files)}/{self.total_files} файлов",
                f", {min(self.done_files, self.total_files)}/{self.total_files} files",
            )
        current = f" — {self.last_file}" if self.last_file and not completed else ""
        status = "[OK]" if completed else "[TRANSFER]"
        print(f"{status} {self.label}: {progress}{speed_text}{files_text}{current}", flush=True)
        self.last_emit = now


def _tree_files(source: Path) -> list[Path]:
    return [path for path in sorted(source.rglob("*")) if path.is_file()]


def copy_tree_verified(source: Path, destination: Path, label: str | None = None) -> None:
    files = _tree_files(source)
    total = sum(path.stat().st_size for path in files)
    progress = TransferProgress(label or tr("Копирование", "Copying"), total, len(files))
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for directory in sorted(path for path in source.rglob("*") if path.is_dir()):
        (destination / directory.relative_to(source)).mkdir(parents=True, exist_ok=True)
    for src in files:
        relative = src.relative_to(source)
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        progress.start_file(str(relative))
        with src.open("rb") as input_fh, dst.open("wb") as output_fh:
            while True:
                chunk = input_fh.read(1024 * 1024)
                if not chunk:
                    break
                output_fh.write(chunk)
                progress.add(len(chunk), str(relative))
        try:
            shutil.copystat(src, dst)
        except OSError:
            # Some stock Samba shares reject timestamp/mode updates. Content
            # integrity is authoritative and is checked immediately below.
            pass
        if sha_file(src) != sha_file(dst):
            raise Error(f"ошибка копирования: {src.name}")
        progress.finish_file(str(relative))
    progress.finish()


def ftp_connect(host: str, user: str, password: str, port: int = 21) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=120)
    ftp.login(user, password)
    ftp.set_pasv(True)
    return ftp


def _ftp_router_path_candidates(router_path: str) -> list[str]:
    """Map a router-side /mnt/USB_* path into common ProFTPD chroot views."""
    normalized = "/" + str(PurePosixPath(router_path)).lstrip("/")
    candidates = [normalized]
    parts = PurePosixPath(normalized).parts
    # Stock useradmin_ftp commonly has HOME=/mnt and is chrooted there, so
    # /mnt/USB_disc1/x on Linux is /USB_disc1/x over FTP.
    if len(parts) >= 3 and parts[1].lower() == "mnt":
        candidates.append("/" + "/".join(parts[2:]))
        # Some builds chroot directly to the selected USB volume.
        tail = parts[3:]
        candidates.append("/" + "/".join(tail) if tail else "/")
    result: list[str] = []
    for item in candidates:
        item = str(PurePosixPath(item))
        if item not in result:
            result.append(item)
    return result


def ftp_resolve_router_dir(ftp: ftplib.FTP, router_path: str) -> str:
    current = ftp.pwd()
    errors: list[str] = []
    try:
        for candidate in _ftp_router_path_candidates(router_path):
            try:
                ftp.cwd(candidate)
                return candidate
            except ftplib.error_perm as exc:
                errors.append(f"{candidate}: {exc}")
    finally:
        try:
            ftp.cwd(current)
        except ftplib.Error:
            pass
    raise Error(tr(
        "FTP не видит каталог Nokia " + router_path + ". Проверены представления: " + ", ".join(_ftp_router_path_candidates(router_path)),
        "FTP cannot see the Nokia directory " + router_path + ". Views checked: " + ", ".join(_ftp_router_path_candidates(router_path)),
    ))


def ftp_join_dir(parent: str, child: str) -> str:
    return "/" + "/".join(part for part in (parent.strip("/"), child.strip("/")) if part)


def ftp_tree_stats(ftp: ftplib.FTP, remote_dir: str) -> tuple[int, int, bool]:
    """Return total bytes, file count and whether every remote SIZE was known."""
    current = ftp.pwd()
    total = 0
    files = 0
    complete = True
    ftp.cwd(remote_dir)
    try:
        try:
            ftp.voidcmd("TYPE I")
        except ftplib.Error:
            pass
        for name in ftp.nlst():
            base = PurePosixPath(name).name
            if base in (".", ".."): 
                continue
            try:
                ftp.cwd(base)
                ftp.cwd("..")
                child_total, child_files, child_complete = ftp_tree_stats(ftp, base)
                total += child_total
                files += child_files
                complete = complete and child_complete
            except ftplib.error_perm:
                files += 1
                try:
                    size = ftp.size(base)
                except ftplib.Error:
                    size = None
                if size is None:
                    complete = False
                else:
                    total += int(size)
    finally:
        ftp.cwd(current)
    return total, files, complete


def ftp_walk_download(
    ftp: ftplib.FTP,
    remote_dir: str,
    local_dir: Path,
    progress: TransferProgress | None = None,
    relative_prefix: PurePosixPath = PurePosixPath(),
) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    current = ftp.pwd()
    ftp.cwd(remote_dir)
    try:
        names = ftp.nlst()
        for name in names:
            base = PurePosixPath(name).name
            if base in (".", ".."): 
                continue
            relative = relative_prefix / base
            try:
                ftp.cwd(base)
                ftp.cwd("..")
                ftp_walk_download(ftp, base, local_dir / base, progress, relative)
            except ftplib.error_perm:
                if progress:
                    progress.start_file(str(relative))
                with (local_dir / base).open("wb") as fh:
                    def write_block(data: bytes) -> None:
                        fh.write(data)
                        if progress:
                            progress.add(len(data), str(relative))
                    ftp.retrbinary(f"RETR {base}", write_block, blocksize=1024 * 1024)
                if progress:
                    progress.finish_file(str(relative))
    finally:
        ftp.cwd(current)


def ftp_mkdirs(ftp: ftplib.FTP, remote: str) -> None:
    current = ftp.pwd()
    try:
        ftp.cwd("/")
        for part in PurePosixPath(remote).parts:
            if part in ("/", ""):
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)
    finally:
        ftp.cwd(current)


def _ftp_upload_current_dir(
    ftp: ftplib.FTP,
    local_dir: Path,
    progress: TransferProgress | None = None,
    relative_prefix: PurePosixPath = PurePosixPath(),
) -> None:
    for path in sorted(local_dir.iterdir()):
        relative = relative_prefix / path.name
        if path.is_dir():
            try:
                ftp.mkd(path.name)
            except ftplib.error_perm:
                pass
            ftp.cwd(path.name)
            try:
                _ftp_upload_current_dir(ftp, path, progress, relative)
            finally:
                ftp.cwd("..")
        else:
            if progress:
                progress.start_file(str(relative))
            with path.open("rb") as fh:
                def sent_block(data: bytes) -> None:
                    if progress:
                        progress.add(len(data), str(relative))
                ftp.storbinary(f"STOR {path.name}", fh, blocksize=256 * 1024, callback=sent_block)
            if progress:
                progress.finish_file(str(relative))


def ftp_upload_tree(ftp: ftplib.FTP, local_dir: Path, remote_dir: str, label: str | None = None) -> None:
    files = _tree_files(local_dir)
    progress = TransferProgress(
        label or tr("FTP upload", "FTP upload"),
        sum(path.stat().st_size for path in files),
        len(files),
    )
    ftp_mkdirs(ftp, remote_dir)
    current = ftp.pwd()
    ftp.cwd(remote_dir)
    try:
        _ftp_upload_current_dir(ftp, local_dir, progress)
    finally:
        ftp.cwd(current)
    progress.finish()


def send_file_to_router(telnet: Telnet, router_host: str, local_file: Path, remote_file: str, local_ip: str | None = None, port: int = 19092) -> None:
    nc = find_nc(telnet)
    local_ip = local_ip or local_ip_for(router_host)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    server.settimeout(30)
    remote_tmp = remote_file + ".part"
    parent = str(PurePosixPath(remote_file).parent)
    telnet.send_line(f"mkdir -p {shlex.quote(parent)} && {nc} {shlex.quote(local_ip)} {port} > {shlex.quote(remote_tmp)} && mv {shlex.quote(remote_tmp)} {shlex.quote(remote_file)}; __rc=$?; echo __UPLOAD_${{__rc}}__")
    try:
        conn, _ = server.accept()
        with conn, local_file.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                conn.sendall(chunk)
            try:
                conn.shutdown(socket.SHUT_WR)
            except OSError:
                pass
    finally:
        server.close()
    text = telnet.wait_regex(r"__UPLOAD_(\d+)__", 300, echo=False)
    match = re.search(r"__UPLOAD_(\d+)__", text)
    if not match or match.group(1) != "0":
        raise Error(f"не удалось передать {local_file.name} на router")
    rc, verify = telnet.command(f"sha256sum {shlex.quote(remote_file)}", timeout=60, echo=False)
    if rc or sha_file(local_file) not in verify:
        raise Error(f"SHA256 после сетевой передачи не совпал: {local_file.name}")




def send_file_to_router_tftp(
    telnet: Telnet,
    router_host: str,
    local_file: Path,
    remote_file: str,
    local_ip: str | None = None,
    port: int = 1069,
    block_size: int = 4096,
) -> None:
    tftp = find_tftp(telnet)
    local_ip = local_ip or local_ip_for(router_host)
    remote_tmp = remote_file + ".part"
    parent = str(PurePosixPath(remote_file).parent)
    ready = threading.Event()
    result = TftpResult()
    thread = threading.Thread(
        target=serve_tftp_get,
        args=("0.0.0.0", port, local_file, local_file.name, router_host, ready, result, 180, block_size),
        daemon=True,
    )
    thread.start()
    ready.wait(5)
    if result.error:
        raise Error(f"не удалось открыть TFTP GET server на UDP {port}: {result.error}")
    command = (
        f"mkdir -p {shlex.quote(parent)} && rm -f {shlex.quote(remote_tmp)} && "
        f"{shlex.quote(tftp)} -g -r {shlex.quote(local_file.name)} -l {shlex.quote(remote_tmp)} "
        f"-b {block_size} {shlex.quote(local_ip)} {port} && "
        f"mv {shlex.quote(remote_tmp)} {shlex.quote(remote_file)}"
    )
    telnet.send_line(command + "; __rc=$?; echo __TFTP_GET_${__rc}__")
    thread.join(timeout=3600)
    if thread.is_alive():
        raise Error(f"TFTP upload timeout: {local_file.name}")
    text = telnet.wait_regex(r"__TFTP_GET_(\d+)__", 90, echo=False)
    match = re.search(r"__TFTP_GET_(\d+)__", text)
    if result.error or not match or match.group(1) != "0":
        raise Error(f"не удалось передать {local_file.name} через TFTP: {result.error or 'router rc != 0'}")
    rc, verify = telnet.command(f"sha256sum {shlex.quote(remote_file)}", timeout=90, echo=False)
    if rc or sha_file(local_file) not in verify:
        raise Error(f"SHA256 после TFTP передачи не совпал: {local_file.name}")

def deploy_install(telnet: Telnet, router_host: str, install_dir: Path, method: str, **kwargs) -> str:
    remote_dir = ""
    if method == "share":
        share_path = kwargs["share_path"]
        remote_mount = resolve_router_usb_mount(telnet, kwargs.get("remote_mount"), share_path)
        verify_router_usb_storage(telnet, remote_mount)
        kwargs["remote_mount"] = remote_mount
        usb_root, destination = _share_usb_and_install_paths(
            share_path,
            kwargs.get("share_user", ""),
            kwargs.get("share_password", ""),
        )
        print(tr(
            f"[TRANSFER] Samba-пакет копируется в {destination}",
            f"[TRANSFER] Copying the Samba package to {destination}",
        ))
        copy_tree_verified(install_dir, destination, tr("Samba: пакет на USB Nokia", "Samba: package to Nokia USB"))
        print(tr(
            f"[OK] Samba-пакет скопирован на ПК-путь: {destination}",
            f"[OK] Samba package copied to PC path: {destination}",
        ))
        remote_dir = detect_router_install_dir(
            telnet,
            install_dir,
            kwargs.get("remote_mount"),
            share_path,
        )
        print(tr(
            f"[OK] Samba-пакет найден на Nokia: {remote_dir}",
            f"[OK] Samba package found on Nokia: {remote_dir}",
        ))
    elif method == "ftp":
        remote_mount = resolve_router_usb_mount(telnet, kwargs.get("remote_mount"))
        verify_router_usb_storage(telnet, remote_mount)
        remote_dir = remote_mount.rstrip("/") + "/nokia-openwrt-install"
        with ftp_connect(router_host, kwargs["ftp_user"], kwargs["ftp_password"], kwargs.get("ftp_port", 21)) as ftp:
            ftp_mount = ftp_resolve_router_dir(ftp, remote_mount)
            ftp_destination = ftp_join_dir(ftp_mount, "nokia-openwrt-install")
            print(tr(
                f"[TRANSFER] FTP-пакет загружается в {ftp_destination} (на Nokia: {remote_dir})",
                f"[TRANSFER] Uploading the FTP package to {ftp_destination} (on Nokia: {remote_dir})",
            ))
            ftp_upload_tree(ftp, install_dir, ftp_destination, tr("FTP: пакет на USB Nokia", "FTP: package to Nokia USB"))
    elif method == "tftp":
        remote_dir = "/tmp/nokia-openwrt-install"
        telnet.command(f"rm -rf {remote_dir}; mkdir -p {remote_dir}", timeout=30, echo=False)
        for path in sorted(install_dir.iterdir()):
            if path.is_file():
                print(tr(f"Передача {path.name} на Nokia через TFTP...", f"Sending {path.name} to Nokia over TFTP..."))
                send_file_to_router_tftp(
                    telnet, router_host, path, f"{remote_dir}/{path.name}",
                    kwargs.get("local_ip"), kwargs.get("tftp_port", 1069), kwargs.get("block_size", 4096)
                )
    else:
        raise Error(f"неподдерживаемый способ deploy: {method}")
    rc, text = telnet.command_clean(
        f"cd {shlex.quote(remote_dir)} && sha256sum -c SHA256SUMS", timeout=300
    )
    if rc or "FAILED" in text:
        if text:
            print(text)
        raise Error("проверка персонального пакета на Nokia не пройдена")
    checked_files = sum(1 for path in install_dir.iterdir() if path.is_file())
    print(tr(
        f"[OK] Установочный пакет проверен на Nokia: {checked_files} файлов, SHA256 совпали.",
        f"[OK] Installation package verified on Nokia: {checked_files} files, SHA256 matched.",
    ))
    return remote_dir


def wait_port(host: str, port: int, timeout: int, require_initial_down: bool = False) -> None:
    end = time.time() + timeout
    seen_down = not require_initial_down
    while time.time() < end:
        try:
            with socket.create_connection((host, port), 2):
                if seen_down:
                    return
        except OSError:
            seen_down = True
        time.sleep(2)
    raise Error(f"тайм-аут ожидания {host}:{port}")


def ssh_executable() -> str:
    exe = shutil.which("ssh")
    if exe:
        return exe
    if os.name == "nt":
        candidate = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/OpenSSH/ssh.exe"
        if candidate.exists():
            return str(candidate)
    raise Error("не найден OpenSSH client (ssh). В Windows включите Optional Feature: OpenSSH Client")


# Returned by ssh_run() when a caller passed allow_timeout and the command did
# not come back. It is not an exit status: the remote side never reported one.
SSH_TIMEOUT_ACCEPTED = -1


def ssh_run(host: str, command: str, input_text: str | None = None, timeout: int = 900,
            allow_disconnect: bool = False, quiet: bool = False,
            batch_mode: bool = False, minimal_auth: bool = False,
            allow_timeout: bool = False, password_prompts: int = 1) -> tuple[int, str]:
    """Run one SSH command.

    ``allow_disconnect`` tolerates a non-zero exit status; it does not cover a
    command that never returns at all. ``allow_timeout`` does: a command whose
    whole purpose is to stop the remote host — ``reboot -f`` — leaves the channel
    hanging instead of closing it, so waiting for an exit status is waiting for
    something that cannot arrive. Without this, the timeout raises straight
    through the caller and takes down whatever that caller was hosting.
    """
    ssh = ssh_executable()
    null = "NUL" if os.name == "nt" else "/dev/null"
    argv = [
        ssh, "-T", "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}",
        "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
        "-o", f"NumberOfPasswordPrompts={max(1, int(password_prompts))}",
    ]
    if batch_mode:
        argv.extend(["-o", "BatchMode=yes"])
    if minimal_auth:
        # The manual transition starts Dropbear with -B because
        # its root shadow password is intentionally empty. OpenSSH always sends
        # the protocol-level "none" request first; Dropbear may then accept the
        # blank-password account without an interactive prompt. Avoid local keys,
        # agents and password prompts so the detector stays deterministic.
        argv.extend([
            "-o", "ConnectionAttempts=1",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=no",
        ])
    identity = _RESTORE_SESSION_KEY.get(host)
    if identity:
        # Once the operator has authenticated once, every later call is ordinary
        # and deterministic again -- no prompt, no inherited console.
        argv.extend(["-o", "IdentitiesOnly=yes", "-i", str(identity)])
    argv.extend([f"root@{host}", command])
    # Interactive calls inherit the console so production OpenWrt may ask for a
    # password. Batch/minimal probes must never inherit console input: a detector
    # must either succeed or fail, not wait invisibly for user interaction.
    if input_text is not None:
        stdin_target = subprocess.PIPE
    elif batch_mode or minimal_auth:
        stdin_target = subprocess.DEVNULL
    else:
        stdin_target = None
    proc = subprocess.Popen(
        argv, stdin=stdin_target,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
    )
    try:
        output, _ = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
        if not allow_timeout:
            raise Error("тайм-аут SSH-команды\n" + output[-4000:])
        _write_session_only(
            f"[SSH-TIMEOUT-OK] host={host} command={command!r} timeout={timeout}s\n{output[-4000:]}")
        return SSH_TIMEOUT_ACCEPTED, output
    if quiet and output:
        _write_session_only(f"[SSH-RAW] host={host}\n{output}")
    elif not quiet:
        print(output, end="")
    if proc.returncode and not allow_disconnect:
        tail = output[-6000:].strip()
        detail = f"\nПоследний вывод SSH:\n{tail}" if tail else ""
        raise Error(f"SSH-команда завершилась с кодом {proc.returncode}{detail}")
    return proc.returncode, output


def scp_executable() -> str:
    exe = shutil.which("scp")
    if exe:
        return exe
    if os.name == "nt":
        candidate = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32/OpenSSH/scp.exe"
        if candidate.exists():
            return str(candidate)
    raise Error(tr(
        "не найден OpenSSH client scp; включите Windows Optional Feature: OpenSSH Client",
        "OpenSSH scp client was not found; enable the Windows OpenSSH Client optional feature",
    ))


def ssh_run_with_progress(host: str, command: str, timeout: int, label: str,
                          counter=None, total: int | None = None, *,
                          restore_auth: bool = False) -> tuple[int, str]:
    holder: dict[str, object] = {}
    def worker() -> None:
        try:
            if restore_auth:
                holder["result"] = _restore_probe_ssh(host, command, timeout=timeout, quiet=True)
            else:
                holder["result"] = ssh_run(host, command, timeout=timeout, quiet=True)
        except BaseException as exc:
            holder["error"] = exc
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    started = time.time(); last_pct = -10; last_heartbeat = -20
    while thread.is_alive():
        elapsed = int(time.time() - started)
        if counter is not None and total:
            done = min(int(getattr(counter, "bytes_transferred", 0)), total)
            pct = int(done * 100 / total)
            if pct >= last_pct + 10 or elapsed >= last_heartbeat + 20:
                print(f"[TRANSFER] {label}: {pct:3d}% ({done / 1048576:.1f}/{total / 1048576:.1f} MiB), {elapsed}s")
                last_pct = pct; last_heartbeat = elapsed
        elif elapsed >= last_heartbeat + 15:
            print(f"[WAIT] {label}: выполняется, прошло {elapsed}s..." if ensure_language() == "ru" else f"[WAIT] {label}: still running, elapsed {elapsed}s...")
            last_heartbeat = elapsed
        thread.join(1)
    if "error" in holder:
        raise holder["error"]  # type: ignore[misc]
    return holder["result"]  # type: ignore[return-value]


def scp_copy_to_recovery(host: str, source: Path, remote_path: str, timeout: int = 1800) -> None:
    try:
        scp = scp_executable()
    except Error as exc:
        raise TransportError(str(exc)) from exc
    null = "NUL" if os.name == "nt" else "/dev/null"
    argv = [
        scp, "-O", "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}",
        "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=4",
    ]
    identity = _RESTORE_SESSION_KEY.get(host)
    if identity:
        argv.extend(["-o", "IdentitiesOnly=yes", "-i", str(identity)])
    if _RESTORE_SSH_MINIMAL_AUTH.get(host) is True:
        argv.extend([
            "-o", "BatchMode=yes", "-o", "ConnectionAttempts=1",
            "-o", "PubkeyAuthentication=no", "-o", "PasswordAuthentication=no",
        ])
    argv.extend([str(source), f"root@{host}:{remote_path}"])
    print(tr(
        f"[SCP] Копирую {source.name}: {source.stat().st_size / 1048576:.1f} MiB в оперативную память системы восстановления...",
        f"[SCP] Copying {source.name}: {source.stat().st_size / 1048576:.1f} MiB into recovery-system memory with legacy SCP...",
    ))
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    started=time.time(); last=-15
    while proc.poll() is None:
        elapsed=int(time.time()-started)
        if elapsed>=last+15:
            print(tr(f"[SCP] Передача продолжается, прошло {elapsed}s...", f"[SCP] Transfer still active, elapsed {elapsed}s...")); last=elapsed
        time.sleep(1)
        if elapsed>timeout:
            proc.kill(); raise TransportError("SCP transfer timeout")
    output=proc.communicate()[0]
    if output.strip(): print(output,end="" if output.endswith("\n") else "\n")
    if proc.returncode:
        raise TransportError(tr(
            f"SCP завершился с кодом {proc.returncode}",
            f"SCP exited with code {proc.returncode}",
        ))
    print(tr("[SCP] Передача завершена.", "[SCP] Transfer completed."))


def _stage1_rearm_after_confirmation(
    telnet: Telnet, access: "StockAccess", remote_dir: str, profile: InstallProfile
) -> tuple[Telnet, bool]:
    """Re-prove the stock root channel immediately before destructive handoff.

    The operator may spend minutes reading the final confirmation text. Stock
    telnetd can close an idle shell during that interval. RC19 then sent the
    flash command through a stale socket and surfaced WinError 10053. RC20
    never treats the pre-confirmation session as durable: it probes it,
    reconnects if necessary, and repeats the read-only INSTALL --preflight
    before dispatching --flash.
    """
    active = telnet
    replacement = False
    nonce = f"__NOKIA_STAGE1_REARM_{time.time_ns():x}__"
    try:
        rc, out = active.command(f"printf '%s\\n' {shlex.quote(nonce)}", timeout=12, echo=False)
        if rc != 0 or nonce not in out:
            raise Error("stock Telnet nonce proof failed")
        print(tr(
            "[OK] Stock Telnet-сеанс после подтверждения всё ещё жив.",
            "[OK] The stock Telnet session is still alive after confirmation.",
        ))
    except Exception as exc:
        _write_session_only(f"[STAGE1-REARM] stale Telnet: {exc.__class__.__name__}: {exc}")
        print(tr(
            "[WAIT] Stock Telnet-сеанс истёк, пока ожидалось подтверждение. Переподключаюсь ДО любых NAND-write.",
            "[WAIT] The stock Telnet session expired while waiting for confirmation. Reconnecting BEFORE any NAND write.",
        ))
        try:
            active.close()
        except Exception:
            pass
        active = login_root_family(access, profile.family, allow_service_provisioning=True)
        replacement = True

    # Confirmation authorizes the operation, but it does not waive freshness.
    # Repeat the complete read-only device/package preflight on the fresh shell.
    rc, output = active.command_clean(
        f"cd {shlex.quote(remote_dir)} && NOKIA_LANG={shlex.quote(ensure_language())} ash ./INSTALL.sh --preflight",
        timeout=900,
    )
    _write_session_only(f"[{profile.family.upper()}-PREFLIGHT-REARM-RAW]\n" + output)
    if rc or "PREFLIGHT PASSED" not in output:
        raise Error(tr(
            "Повторный pre-destructive preflight после подтверждения не пройден; NAND write не запускался.",
            "The repeated pre-destructive preflight after confirmation failed; NAND writing was not started.",
        ))
    print(tr(
        "[OK] Свежий pre-destructive preflight PASS; NAND всё ещё не изменялась.",
        "[OK] Fresh pre-destructive preflight PASS; NAND is still unchanged.",
    ))
    return active, replacement


def run_stage1(telnet: Telnet, remote_dir: str, nand_unknown: bool, manual_transition: bool = False, profile: InstallProfile = MD_INSTALL_PROFILE, access: "StockAccess" | None = None) -> str:
    rc, output = telnet.command_clean(
        f"cd {shlex.quote(remote_dir)} && NOKIA_LANG={shlex.quote(ensure_language())} ash ./INSTALL.sh --preflight",
        timeout=900,
    )
    _write_session_only(f"[{profile.family.upper()}-PREFLIGHT-RAW]\n" + output)
    if rc or "PREFLIGHT PASSED" not in output:
        errors = [line.strip() for line in output.splitlines() if re.search(r"(?:ОШИБКА|ERROR|CRITICAL|КРИТИЧ)", line, re.I)]
        if errors:
            print(errors[-1])
        raise Error(tr("MF preflight не пройден", "MF preflight failed"))

    print(tr(
        f"[OK] {profile.model}: backup, root, MTD-разметка, transition и environment проверены.",
        f"[OK] {profile.model}: backup, root, MTD layout, transition and environment verified.",
    ))
    print(tr(
        "[OK] Preflight завершён. NAND ещё не изменялся.",
        "[OK] Preflight complete. NAND has not been modified yet.",
    ))

    if manual_transition:
        print(tr(
            "[READY] Будет записан transition; sysupgrade выберете после загрузки OpenWrt в RAM.",
            "[READY] The transition will be written; you will select sysupgrade after RAM OpenWrt boots.",
        ))
    else:
        print(tr(
            "[READY] После подтверждения начнётся переход на OpenWrt UBI.",
            "[READY] After confirmation, the OpenWrt UBI migration will begin.",
        ))
    print(tr(
        "[ВАЖНО] Не отключайте питание. UART и полный stock backup должны быть доступны для отката.",
        "[IMPORTANT] Do not interrupt power. Keep UART and the full stock backup available for rollback.",
    ))
    if nand_unknown:
        print(tr(
            f"[ПРЕДУПРЕЖДЕНИЕ] Модель NAND не экспортируется stock kernel; остальные {profile.family.upper()} gates пройдены.",
            f"[WARNING] The stock kernel does not expose the NAND model; all other {profile.family.upper()} gates passed.",
        ))

    if manual_transition:
        confirm = input(tr(
            "Записать transition и перезагрузить роутер? [y/N]: ",
            "Write the transition and reboot the router? [y/N]: ",
        )).strip().lower()
        if confirm not in ("y", "yes", "д", "да"):
            raise Error(tr("операция отменена", "operation cancelled"))
    else:
        confirm = input(tr(
            "Введите точно CONFIRM FORMAT AND FLASH: ",
            "Type exactly CONFIRM FORMAT AND FLASH: ",
        )).strip()
        if confirm != "CONFIRM FORMAT AND FLASH":
            raise Error(tr("операция отменена", "operation cancelled"))

    stage_header("5", "Запись transition", "Writing transition")
    if access is None:
        raise Error("internal error: stage1 access context is required")
    print(tr(
        "[WAIT] После подтверждения заново проверяю stock root-сеанс и read-only preflight.",
        "[WAIT] Re-checking the stock root session and read-only preflight after confirmation.",
    ))
    stage_telnet = telnet
    replacement = False
    try:
        stage_telnet, replacement = _stage1_rearm_after_confirmation(telnet, access, remote_dir, profile)
        print(tr(
            "[WAIT] Подготавливаю автономный RAM-worker. Не выключайте питание.",
            "[WAIT] Preparing the autonomous RAM worker. Do not power off.",
        ))
        auth = shlex.quote("CONFIRM FORMAT AND FLASH")
        command = (
            f"cd {shlex.quote(remote_dir)} && "
            f"NOKIA_FORMAT_AND_FLASH_AUTH={auth} "
            f"NOKIA_LANG={shlex.quote(ensure_language())} ash ./INSTALL.sh --flash"
        )
        dispatch_attempted = True
        try:
            stage_telnet.send_line(command + "; __rc=$?; printf '\\n__STAGE1_%s__\\n' \"$__rc\"")
            stage_output = stage_telnet.wait_regex(
                r"__NOKIA_RAM_WORKER_STARTED__\d+__|__STAGE1_\d+__",
                900,
                echo=False,
            )
        except (OSError, Error) as exc:
            # Once send_line has been attempted, bytes may already be in the
            # stock shell even when Windows reports WSAECONNABORTED/10053.
            # Retrying --flash would therefore violate the destructive-state
            # invariant. Continue only with read-only transition/production
            # observation.
            _write_session_only(
                f"[STAGE1-HANDOFF-UNKNOWN] {exc.__class__.__name__}: {exc}"
            )
            print(tr(
                "[ПРЕДУПРЕЖДЕНИЕ] Telnet оборвался после отправки команды запуска RAM-worker. "
                "Состояние handoff НЕИЗВЕСТНО; автоматически повторять --flash запрещено.",
                "[WARNING] Telnet disconnected after the RAM-worker launch command was dispatched. "
                "The handoff state is UNKNOWN; automatically retrying --flash is forbidden.",
            ))
            print(tr(
                "[STATE] STAGE1_HANDOFF_UNKNOWN — питание не трогать; мастер переходит только к read-only наблюдению transition/production.",
                "[STATE] STAGE1_HANDOFF_UNKNOWN — do not touch power; the wizard will continue with read-only transition/production observation only.",
            ))
            return "handoff-unknown"

        _write_session_only(f"[{profile.family.upper()}-STAGE1-RAW]\n" + stage_output)
        worker = re.search(r"__NOKIA_RAM_WORKER_STARTED__(\d+)__", stage_output)
        stage_rc = re.search(r"__STAGE1_(\d+)__", stage_output)
        if worker:
            print(tr(
                "[OK] RAM-worker запущен. Дальнейшая запись идёт автономно; Telnet может отключиться.",
                "[OK] RAM worker started. Flashing now continues autonomously; Telnet may disconnect.",
            ))
            return "worker-confirmed"
        if stage_rc and int(stage_rc.group(1)) == 0:
            print(tr(
                "[ПРЕДУПРЕЖДЕНИЕ] Worker-маркер не получен, но stock shell вернул rc=0; повторный запуск запрещён, продолжаю read-only проверку загрузки.",
                "[WARNING] The worker marker was not received, but the stock shell returned rc=0; relaunch is forbidden and read-only boot verification will continue.",
            ))
            return "stage1-rc0-unmarked"

        cleaned = _clean_telnet_protocol(stage_output)
        errors = [line.strip() for line in cleaned.splitlines() if re.search(r"(?:ОШИБКА|ERROR|CRITICAL|КРИТИЧ)", line, re.I)]
        if errors:
            print(errors[-1])
        rc_text = stage_rc.group(1) if stage_rc else "unknown"
        raise Error(tr(
            f"RAM-worker не стартовал; rc={rc_text}. NAND write не продолжен.",
            f"RAM worker did not start; rc={rc_text}. NAND writing did not continue.",
        ))
    finally:
        if replacement:
            try:
                stage_telnet.close()
            except Exception:
                pass


def choose_custom_sysupgrade() -> Path:
    prompt = tr(
        "Путь к sysupgrade (.itb); можно перетащить файл сюда, Enter — открыть окно выбора: ",
        "Path to the sysupgrade (.itb); drag the file here, or press Enter for a file dialog: ",
    )
    raw = input(prompt).strip().strip('"')
    if not raw:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.update()
            raw = filedialog.askopenfilename(
                title=tr("Выберите sysupgrade OpenWrt", "Select an OpenWrt sysupgrade image"),
                filetypes=[("OpenWrt sysupgrade", "*.itb *.bin"), ("All files", "*.*")],
            )
            root.destroy()
        except Exception:
            raw = input(tr("Введите путь к sysupgrade: ", "Enter the sysupgrade path: ")).strip().strip('"')
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise Error(tr(f"файл sysupgrade не найден: {path}", f"sysupgrade file not found: {path}"))
    size = path.stat().st_size
    if size < 1024 * 1024 or size > 128 * 1024 * 1024:
        raise Error(tr(f"неожиданный размер sysupgrade: {size} байт", f"unexpected sysupgrade size: {size} bytes"))
    with path.open("rb") as fh:
        if fh.read(4) != b"\xd0\x0d\xfe\xed":
            raise Error(tr("выбранный файл не является FIT/sysupgrade", "the selected file is not a FIT/sysupgrade image"))
    return path


def send_custom_sysupgrade_tftp(host: str, source: Path, local_ip: str | None, port: int, block_size: int) -> tuple[str, int]:
    local_ip = local_ip or local_ip_for(host)
    remote = "/tmp/nokia-custom-sysupgrade.itb"
    partial = remote + ".part"
    expected = sha_file(source)
    ready = threading.Event(); result = TftpResult()
    thread = threading.Thread(
        target=serve_tftp_get,
        args=("0.0.0.0", port, source, "nokia-custom-sysupgrade.itb", host, ready, result, 180, block_size),
        daemon=True,
    )
    thread.start()
    if not ready.wait(5) or result.error:
        raise Error(tr(f"не удалось запустить TFTP на UDP {port}: {result.error or 'timeout'}", f"failed to start TFTP on UDP {port}: {result.error or 'timeout'}"))
    command = (
        f"rm -f {shlex.quote(partial)} {shlex.quote(remote)}; "
        f"tftp -g -r nokia-custom-sysupgrade.itb -l {shlex.quote(partial)} -b {block_size} "
        f"{shlex.quote(local_ip)} {port} && mv {shlex.quote(partial)} {shlex.quote(remote)} && "
        f"wc -c < {shlex.quote(remote)}; sha256sum {shlex.quote(remote)}"
    )
    holder: dict[str, object] = {}
    def run_ssh():
        try: holder["value"] = _manual_ssh_run(host, command, timeout=3600, quiet=True)
        except Exception as exc: holder["error"] = exc
    ssh_thread = threading.Thread(target=run_ssh, daemon=True); ssh_thread.start()
    started=time.time(); last=-15
    while thread.is_alive() or ssh_thread.is_alive():
        elapsed=int(time.time()-started)
        if elapsed >= last + 15:
            done=int(result.bytes_transferred)
            print(tr(f"[TRANSFER] sysupgrade: {done/1048576:.1f}/{source.stat().st_size/1048576:.1f} MiB, {elapsed}s", f"[TRANSFER] sysupgrade: {done/1048576:.1f}/{source.stat().st_size/1048576:.1f} MiB, {elapsed}s"))
            last=elapsed
        thread.join(1); ssh_thread.join(0)
        if not ssh_thread.is_alive() and int(result.bytes_transferred) == 0:
            if "error" in holder:
                raise holder["error"]  # type: ignore[misc]
            early_rc, early_output = holder.get("value", (0, ""))  # type: ignore[assignment]
            if early_rc:
                raise Error(tr(
                    f"удалённая TFTP-команда завершилась до начала передачи: {str(early_output)[-1200:]}",
                    f"remote TFTP command exited before transfer started: {str(early_output)[-1200:]}",
                ))
        if elapsed > 3600: raise Error("TFTP sysupgrade timeout")
    if result.error: raise Error(tr(f"ошибка TFTP: {result.error}", f"TFTP error: {result.error}"))
    if "error" in holder: raise holder["error"]  # type: ignore[misc]
    rc, output = holder.get("value", (1, ""))  # type: ignore[assignment]
    if rc or expected not in output or str(source.stat().st_size) not in output:
        raise Error(tr("размер или SHA256 sysupgrade после TFTP не совпал", "sysupgrade size or SHA256 did not match after TFTP"))
    return expected, source.stat().st_size


def _manual_auth_mode(host: str) -> bool:
    minimal = _MANUAL_SSH_MINIMAL_AUTH.get(host)
    if minimal is None:
        ready, _, _, detail = _manual_transition_probe(host, timeout=8)
        if not ready:
            raise Error(tr(
                f"ручной transition не подтверждён перед передачей файла: {detail or 'служебная метка/состояние не прочитаны'}",
                f"manual transition was not confirmed before file transfer: {detail or 'marker/state not readable'}",
            ))
        minimal = _MANUAL_SSH_MINIMAL_AUTH.get(host, True)
    return bool(minimal)


def _manual_remote_has(host: str, command: str) -> bool:
    quoted = shlex.quote(command)
    _, out = _manual_ssh_run(
        host,
        f"if command -v {quoted} >/dev/null 2>&1; then echo NOKIA_HAVE=1; else echo NOKIA_HAVE=0; fi",
        timeout=20,
        quiet=True,
    )
    return "NOKIA_HAVE=1" in out


def _manual_scp_argv(host: str, source: Path, remote_path: str) -> list[str]:
    scp = scp_executable()
    null = "NUL" if os.name == "nt" else "/dev/null"
    argv = [
        scp, "-O",
        "-o", "StrictHostKeyChecking=no",
        "-o", f"UserKnownHostsFile={null}",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=4",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "BatchMode=yes",
    ]
    if _manual_auth_mode(host):
        argv.extend([
            "-o", "ConnectionAttempts=1",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=no",
        ])
    argv.extend([str(source), f"root@{host}:{remote_path}"])
    return argv


def send_custom_sysupgrade_scp(host: str, source: Path) -> tuple[str, int]:
    remote = "/tmp/nokia-custom-sysupgrade.itb"
    partial = remote + ".part"
    expected = sha_file(source)
    _manual_ssh_run(host, f"rm -f {shlex.quote(partial)} {shlex.quote(remote)}", timeout=30, quiet=True)
    argv = _manual_scp_argv(host, source, partial)
    print(tr(
        f"[SCP] sysupgrade: {source.stat().st_size/1048576:.1f} MiB → RAM transition.",
        f"[SCP] sysupgrade: {source.stat().st_size/1048576:.1f} MiB → transition RAM.",
    ))
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    started = time.time(); last = -15
    while proc.poll() is None:
        elapsed = int(time.time() - started)
        if elapsed >= last + 15:
            print(tr(
                f"[SCP] Передача продолжается, прошло {elapsed}s...",
                f"[SCP] Transfer still active, elapsed {elapsed}s...",
            ))
            last = elapsed
        if elapsed > 1800:
            proc.kill()
            raise Error("SCP sysupgrade timeout")
        time.sleep(1)
    output = proc.communicate()[0]
    if output.strip():
        _write_session_only(f"[SCP-RAW] host={host}\\n{output}")
    if proc.returncode:
        raise Error(tr(
            f"SCP завершился с кодом {proc.returncode}: {output[-1200:].strip()}",
            f"SCP exited with code {proc.returncode}: {output[-1200:].strip()}",
        ))
    _, out = _manual_ssh_run(
        host,
        f"mv {shlex.quote(partial)} {shlex.quote(remote)} && "
        f"wc -c < {shlex.quote(remote)}; sha256sum {shlex.quote(remote)}",
        timeout=300,
        quiet=True,
    )
    if expected not in out or str(source.stat().st_size) not in out:
        raise Error(tr(
            "размер или SHA256 sysupgrade после SCP не совпал",
            "sysupgrade size or SHA256 did not match after SCP",
        ))
    print(tr("[OK] Sysupgrade передан по SCP и проверен SHA256.", "[OK] Sysupgrade transferred by SCP and SHA256 verified."))
    return expected, source.stat().st_size


def _manual_ssh_stream_argv(host: str, remote_command: str) -> list[str]:
    ssh = ssh_executable()
    null = "NUL" if os.name == "nt" else "/dev/null"
    argv = [
        ssh, "-T",
        "-o", "StrictHostKeyChecking=no",
        "-o", f"UserKnownHostsFile={null}",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=4",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "BatchMode=yes",
    ]
    if _manual_auth_mode(host):
        argv.extend([
            "-o", "ConnectionAttempts=1",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=no",
        ])
    argv.extend([f"root@{host}", remote_command])
    return argv


def send_custom_sysupgrade_ssh_stream(host: str, source: Path) -> tuple[str, int]:
    remote = "/tmp/nokia-custom-sysupgrade.itb"
    partial = remote + ".part"
    expected = sha_file(source)
    command = (
        f"rm -f {shlex.quote(partial)} {shlex.quote(remote)}; "
        f"cat > {shlex.quote(partial)} && "
        f"mv {shlex.quote(partial)} {shlex.quote(remote)} && "
        f"wc -c < {shlex.quote(remote)}; sha256sum {shlex.quote(remote)}"
    )
    argv = _manual_ssh_stream_argv(host, command)
    print(tr(
        f"[SSH] sysupgrade: {source.stat().st_size/1048576:.1f} MiB → RAM transition.",
        f"[SSH] sysupgrade: {source.stat().st_size/1048576:.1f} MiB → transition RAM.",
    ))
    with source.open("rb") as fh:
        proc = subprocess.Popen(
            argv, stdin=fh, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=False,
        )
        started = time.time(); last = -15
        while proc.poll() is None:
            elapsed = int(time.time() - started)
            if elapsed >= last + 15:
                print(tr(
                    f"[SSH] Передача продолжается, прошло {elapsed}s...",
                    f"[SSH] Transfer still active, elapsed {elapsed}s...",
                ))
                last = elapsed
            if elapsed > 1800:
                proc.kill()
                raise Error("SSH-stream sysupgrade timeout")
            time.sleep(1)
        raw = proc.communicate()[0] or b""
    output = raw.decode("utf-8", "replace")
    if output.strip():
        _write_session_only(f"[SSH-STREAM-RAW] host={host}\\n{output}")
    if proc.returncode:
        raise Error(tr(
            f"SSH-stream завершился с кодом {proc.returncode}: {output[-1200:].strip()}",
            f"SSH-stream exited with code {proc.returncode}: {output[-1200:].strip()}",
        ))
    if expected not in output or str(source.stat().st_size) not in output:
        raise Error(tr(
            "размер или SHA256 sysupgrade после SSH-stream не совпал",
            "sysupgrade size or SHA256 did not match after SSH stream",
        ))
    print(tr("[OK] Sysupgrade передан через SSH и проверен SHA256.", "[OK] Sysupgrade transferred over SSH and SHA256 verified."))
    return expected, source.stat().st_size


def send_custom_sysupgrade(host: str, source: Path, local_ip: str | None, port: int, block_size: int) -> tuple[str, int]:
    errors: list[str] = []

    try:
        have_tftp = _manual_remote_has(host, "tftp")
    except Error as exc:
        have_tftp = False
        errors.append(f"TFTP preflight: {exc}")
    if have_tftp:
        try:
            print(tr("[TFTP] На transition найден tftp; пробую прямую передачу.", "[TFTP] tftp is available on the transition; trying direct transfer."))
            return send_custom_sysupgrade_tftp(host, source, local_ip, port, block_size)
        except Error as exc:
            errors.append(f"TFTP: {exc}")
            print(tr(
                f"[WARNING] TFTP не сработал: {str(exc)[-500:]}. Перехожу к SCP.",
                f"[WARNING] TFTP failed: {str(exc)[-500:]}. Falling back to SCP.",
            ))
    else:
        print(tr(
            "[INFO] В manual transition нет команды tftp; TFTP пропущен, использую SCP.",
            "[INFO] The manual transition has no tftp command; skipping TFTP and using SCP.",
        ))

    try:
        have_scp = _manual_remote_has(host, "scp")
    except Error as exc:
        have_scp = False
        errors.append(f"SCP preflight: {exc}")
    if have_scp:
        try:
            return send_custom_sysupgrade_scp(host, source)
        except Error as exc:
            errors.append(f"SCP: {exc}")
            print(tr(
                f"[WARNING] SCP не сработал: {str(exc)[-500:]}. Перехожу к передаче через SSH.",
                f"[WARNING] SCP failed: {str(exc)[-500:]}. Falling back to SSH streaming.",
            ))
    else:
        print(tr(
            "[INFO] В manual transition нет команды scp; использую передачу через уже подтверждённый SSH.",
            "[INFO] The manual transition has no scp command; using the already-proven SSH connection.",
        ))

    try:
        return send_custom_sysupgrade_ssh_stream(host, source)
    except Error as exc:
        errors.append(f"SSH-stream: {exc}")
        raise Error(tr(
            "не удалось передать sysupgrade ни одним безопасным транспортом: " + " | ".join(errors)[-1800:],
            "failed to transfer sysupgrade with any safe transport: " + " | ".join(errors)[-1800:],
        )) from exc


_MANUAL_SSH_MINIMAL_AUTH: dict[str, bool] = {}


def _manual_transition_probe(host: str, timeout: int = 8) -> tuple[bool, str, str, str]:
    """Content-probe the manual initramfs and return READY/state/board/diagnostics.

    Raw TCP openness is telemetry only.  Identity comes from the manual state
    protocol emitted by the transition image.  The device-side readiness monitor
    is persistent, so a delayed Ethernet/PHY probe can still become READY later.
    """
    command = (
        "echo NOKIA_MANUAL_PROBE_BEGIN; "
        "cat /tmp/NOKIA_MANUAL_STATE 2>/dev/null || true; "
        "[ -f /tmp/NOKIA_MANUAL_TRANSITION_READY ] && echo MANUAL_READY; "
        "[ -x /usr/sbin/nokia-ubi-installer ] && echo INSTALLER=1 || echo INSTALLER=0; "
        "echo NOKIA_MANUAL_PROBE_END"
    )
    errors: list[str] = []
    for minimal in (True, False):
        try:
            _, out = ssh_run(
                host, command, timeout=timeout, quiet=True, batch_mode=True, minimal_auth=minimal,
            )
        except Error as exc:
            detail = str(exc).replace("\r", " ").replace("\n", " ").strip()
            errors.append(("minimal" if minimal else "batch") + ": " + detail[-700:])
            continue
        if "NOKIA_MANUAL_PROBE_BEGIN" not in out or "NOKIA_MANUAL_PROBE_END" not in out:
            errors.append(("minimal" if minimal else "batch") + ": incomplete probe output")
            continue
        def kv(name: str) -> str:
            match = re.search(rf"(?m)^{re.escape(name)}=([^\r\n]*)", out)
            return match.group(1).strip() if match else ""
        protocol = kv("MEDVEFLASHER_MANUAL_PROTOCOL")
        mode = kv("MODE")
        state = kv("STATE")
        board = kv("BOARD")
        reason = kv("REASON")
        deferred = kv("DEFERRED")
        br_lan = kv("BR_LAN_PRESENT")
        lan_ip = kv("LAN_192_168_1_1")
        ssh22 = kv("SSH22_LISTEN")
        installer = "INSTALLER=1" in out
        identity = protocol == "1" and mode == "TRANSITION" and installer
        ready = identity and "MANUAL_READY" in out and state == "WAITING_FOR_CUSTOM_IMAGE"
        detail_parts = []
        if identity and not ready:
            if state: detail_parts.append(f"state={state}")
            if reason: detail_parts.append(f"reason={reason}")
            if deferred: detail_parts.append(f"deferred={deferred}")
            if br_lan: detail_parts.append(f"br-lan={br_lan}")
            if lan_ip: detail_parts.append(f"lan-ip={lan_ip}")
            if ssh22: detail_parts.append(f"ssh22={ssh22}")
        elif not identity:
            detail_parts.append("manual protocol/installer identity incomplete")
        if ready:
            _MANUAL_SSH_MINIMAL_AUTH[host] = minimal
        return ready, state, board, "; ".join(detail_parts)
    return False, "", "", "; ".join(errors)[-1400:]


def _manual_ssh_run(host: str, command: str, timeout: int = 900,
                    allow_disconnect: bool = False, quiet: bool = True) -> tuple[int, str]:
    minimal = _MANUAL_SSH_MINIMAL_AUTH.get(host)
    if minimal is None:
        ready, _, _, detail = _manual_transition_probe(host, timeout=min(8, timeout))
        if not ready:
            raise Error(tr(
                f"ручной transition не подтверждён перед SSH-командой: {detail or 'служебная метка/состояние не прочитаны'}",
                f"manual transition was not confirmed before the SSH command: {detail or 'marker/state not readable'}",
            ))
        minimal = _MANUAL_SSH_MINIMAL_AUTH.get(host, True)
    return ssh_run(
        host, command, timeout=timeout, allow_disconnect=allow_disconnect, quiet=quiet,
        batch_mode=True, minimal_auth=minimal,
    )



def _manual_transition_http_probe(host: str) -> tuple[bool, str, str, str]:
    """Read the manual transition ASCII state over HTTP when available.

    HTTP is diagnostic/control-plane evidence only; READY still requires the SSH
    content probe before custom image transfer. Raw port openness is never identity.
    """
    errors: list[str] = []
    for port in (80, 443):
        try:
            body = _http_get_body(host, port, "/medveflasher-manual.status", timeout=1.6, max_bytes=8192).decode("ascii", "replace")
        except (OSError, ssl.SSLError, ValueError) as exc:
            errors.append(f"http:{port}: {str(exc)[-160:]}")
            continue
        def kv(name: str) -> str:
            match = re.search(rf"(?m)^{re.escape(name)}=([^\r\n]*)", body)
            return match.group(1).strip() if match else ""
        protocol = kv("MEDVEFLASHER_MANUAL_PROTOCOL")
        mode = kv("MODE")
        if protocol != "1" or mode != "TRANSITION":
            errors.append(f"http:{port}: marker mismatch")
            continue
        state = kv("STATE")
        board = kv("BOARD")
        detail_parts = [f"transport=http:{port}"]
        for field, label in (("REASON", "reason"), ("DEFERRED", "deferred"), ("BR_LAN_PRESENT", "br-lan"), ("LAN_192_168_1_1", "lan-ip"), ("SSH22_LISTEN", "ssh22")):
            value = kv(field)
            if value:
                detail_parts.append(f"{label}={value}")
        return True, state, board, "; ".join(detail_parts)
    return False, "", "", " | ".join(errors)[-800:]

def wait_manual_transition(host: str, timeout: int = 600, expected_board: str | None = None) -> None:
    stage_header("6", "Ожидание ручного transition", "Waiting for the manual transition")
    started=time.time(); next_report=started; next_error_report=started
    last_error = ""
    while time.time()-started < timeout:
        ports=(_tcp_open(host,22),_tcp_open(host,80),_tcp_open(host,443),_tcp_open(host,23))
        http_identified, http_state, http_board, http_detail = _manual_transition_http_probe(host)
        if http_identified:
            if expected_board and http_board and http_board != expected_board:
                raise Error(tr(f"manual transition HTTP board mismatch: {http_board} != {expected_board}", f"manual transition HTTP board mismatch: {http_board} != {expected_board}"))
            if http_detail and time.time() >= next_error_report:
                print(tr(
                    f"[WAIT] Manual transition виден по content-based HTTP status: state={http_state or 'UNKNOWN'}; {http_detail}",
                    f"[WAIT] Manual transition is visible through content-based HTTP status: state={http_state or 'UNKNOWN'}; {http_detail}",
                ))
                _write_session_only(f"[MANUAL-HTTP] state={http_state!r} board={http_board!r} {http_detail}")
                next_error_report = time.time() + 30
        if ports[0]:
            ready, state, board, detail = _manual_transition_probe(host, timeout=8)
            if ready:
                print(tr(
                    f"[OK] Ручной transition готов; состояние {state}. Автоматическая запись NAND не запущена.",
                    f"[OK] Manual transition is ready; state {state}. No automatic NAND write has started.",
                ))
                if expected_board and board and board != expected_board:
                    raise Error(tr(f"manual transition board mismatch: {board} != {expected_board}", f"manual transition board mismatch: {board} != {expected_board}"))
                if board and board not in ("nokia,xg-040g-md-ubi", "nokia,xg-040g-mf-ubi"):
                    _write_session_only(f"[MANUAL-SSH] ready marker accepted; board_name={board!r}")
                return
            if detail:
                last_error = detail
                if time.time() >= next_error_report:
                    short = detail[-700:]
                    if state:
                        print(tr(
                            f"[WAIT] Manual transition распознан, но ещё не READY: {short}",
                            f"[WAIT] Manual transition is identified but not READY yet: {short}",
                        ))
                        _write_session_only(f"[MANUAL-STATE] not ready: {detail}")
                    else:
                        print(tr(
                            f"[WAIT] SSH 22 открыт, но content-probe manual transition не прошёл: {short}",
                            f"[WAIT] SSH 22 is open, but the manual-transition content probe did not pass: {short}",
                        ))
                        _write_session_only(f"[MANUAL-SSH] probe failed: {detail}")
                    next_error_report = time.time() + 30
        if time.time() >= next_report:
            elapsed=int(time.time()-started)
            print(tr(f"[NET] {elapsed//60:02d}:{elapsed%60:02d} — {_port_summary(*ports)}.", f"[NET] {elapsed//60:02d}:{elapsed%60:02d} — {_port_summary(*ports)}."))
            next_report=time.time()+30
        time.sleep(3)
    suffix = f"; последняя ошибка SSH: {last_error[-700:]}" if last_error else ""
    raise Error(tr(
        "ручной transition не появился по SSH" + suffix,
        "manual transition did not become available over SSH" + (f"; last SSH error: {last_error[-700:]}" if last_error else ""),
    ))


def run_custom_stage2(host: str, local_ip: str | None, port: int, block_size: int, expected_board: str = "nokia,xg-040g-md-ubi") -> str:
    wait_manual_transition(host, expected_board=expected_board)
    stage_header("7", "Выбор и проверка sysupgrade", "Selecting and validating sysupgrade")
    image=choose_custom_sysupgrade(); digest=sha_file(image); size=image.stat().st_size
    print(tr(f"[IMAGE] {image.name}; {size/1048576:.1f} MiB; SHA256 {digest}", f"[IMAGE] {image.name}; {size/1048576:.1f} MiB; SHA256 {digest}"))
    digest, _ = send_custom_sysupgrade(host,image,local_ip,port,block_size)
    check_cmd=(
        f"printf '%s\\n' {shlex.quote(digest)} > /tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256; "
        f"NOKIA_EXPECTED_SYSUPGRADE_SHA={shlex.quote(digest)} "
        f"nokia-ubi-installer check /tmp/nokia-custom-sysupgrade.itb"
    )
    _, out=_manual_ssh_run(host,check_cmd,timeout=900,quiet=True)
    if "CHECK PASSED" not in out or "accepted" not in out:
        print(out)
        raise Error(tr("transition отклонил выбранный sysupgrade; NAND не форматировалась", "transition rejected the selected sysupgrade; NAND was not formatted"))
    print(tr("[OK] Sysupgrade принят проверками transition и командой sysupgrade -T. NAND пока не изменялась.", "[OK] The image passed transition checks and sysupgrade -T. NAND has not been modified yet."))
    answer=input(tr("Прошить выбранный образ? [y/N]: ", "Flash the selected image? [y/N]: ")).strip().lower()
    if answer not in ("y","yes","д","да"):
        raise Error(tr("установка пользовательского образа отменена", "custom image installation was cancelled"))
    stage_header("8", "Автономная запись выбранного образа", "Autonomous flashing of the selected image")
    launch=(
        "rm -f /tmp/NOKIA_MANUAL_FLASH_FAILED; echo STARTING > /tmp/NOKIA_MANUAL_STATE; "
        "( trap '' HUP; export NOKIA_PC_CONFIRMED_CUSTOM_FLASH=1; "
        f"export NOKIA_EXPECTED_SYSUPGRADE_SHA={shlex.quote(digest)}; "
        "nokia-ubi-installer fullflash /tmp/nokia-custom-sysupgrade.itb; "
        "rc=$?; echo FAILED > /tmp/NOKIA_MANUAL_STATE; echo $rc > /tmp/NOKIA_MANUAL_FLASH_FAILED ) "
        ">/tmp/nokia-manual-flash.log 2>&1 </dev/null & echo STARTED=$!"
    )
    _, out=_manual_ssh_run(host,launch,timeout=60,quiet=True)
    if "STARTED=" not in out: raise Error(tr("не удалось запустить автономную запись", "failed to start autonomous flashing"))
    print(tr("[OK] Запись запущена. Не выключайте питание.", "[OK] Flashing started. Do not power off."))
    # The existing monitor understands the same installer milestones. Manual
    # transition has no autoflash service, so expose its installer log through
    # the same markers while monitoring.
    return run_stage2(host, manual_mode=True, expected_board=expected_board)

def _tcp_open(host: str, port: int, timeout: float = 1.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_luci(host: str, port: int, timeout: float = 2.5) -> bool:
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        raw.settimeout(timeout)
        if port == 443:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(raw, server_hostname=host)
        else:
            sock = raw
        with sock:
            request = f"GET / HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode("ascii", "strict"))
            data = bytearray()
            while len(data) < 16384:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
        lowered = bytes(data).lower()
        return b"/cgi-bin/luci" in lowered or b"luci" in lowered and b"http/" in lowered
    except (OSError, ssl.SSLError, ValueError):
        return False


def _http_get_body(host: str, port: int, path: str, timeout: float = 2.0, max_bytes: int = 131072) -> bytes:
    raw = socket.create_connection((host, port), timeout=timeout)
    raw.settimeout(timeout)
    if port == 443:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = context.wrap_socket(raw, server_hostname=host)
    else:
        sock = raw
    with sock:
        request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        sock.sendall(request.encode("ascii", "strict"))
        data = bytearray()
        while len(data) < max_bytes + 8192:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
    head, sep, body = bytes(data).partition(b"\r\n\r\n")
    if not sep or not re.match(br"HTTP/\d(?:\.\d)? 200(?: |\r?$)", head.split(b"\r\n", 1)[0]):
        raise OSError("HTTP status is not 200")
    return body[:max_bytes]


def _auto_transition_http_probe(host: str) -> tuple[str, str]:
    """Content-addressed transition control plane; raw port openness is never identity."""
    errors: list[str] = []
    for port in (80, 443):
        try:
            status = _http_get_body(host, port, "/medveflasher-transition.status", timeout=1.6, max_bytes=4096).decode("ascii", "replace")
            if "MEDVEFLASHER_TRANSITION_PROTOCOL=1" not in status or "MODE=TRANSITION" not in status:
                errors.append(f"http:{port}: marker mismatch")
                continue
            try:
                log = _http_get_body(host, port, "/medveflasher-transition.log", timeout=1.6, max_bytes=120000).decode("ascii", "replace")
            except OSError:
                log = ""
            state = re.search(r"(?m)^STATE=([^\r\n]+)", status)
            safe = re.search(r"(?m)^SAFE_TO_POWER_CYCLE=([01])", status)
            output = "MODE=TRANSITION\nAUTO_STATE=" + (state.group(1).strip() if state else "UNKNOWN") + "\n"
            if safe:
                output += "SAFE_TO_POWER_CYCLE=" + safe.group(1) + "\n"
            output += "AUTOFLOG_BEGIN\n" + log.rstrip("\r\n") + "\nAUTOFLOG_END\n"
            return output, f"http:{port}"
        except (OSError, ssl.SSLError, ValueError) as exc:
            errors.append(f"http:{port}: {str(exc)[-180:]}")
    return "TRANSITION_HTTP_PROBE_ERROR=" + " | ".join(errors)[-600:], ""


def _recover_rc27_false_fudan(host: str, probe_output: str) -> bool:
    """Continue a verified RC27 migration stopped by its self-poisoned NAND scan."""
    signatures = (
        "AUTO_STATE=FAILED",
        "FudanMicro FM25G02B NAND is not supported by this U-Boot",
        "UBI MIGRATION COMPLETE.",
        "SkyHigh ML02G300WHI00 explicitly detected.",
    )
    if not all(marker in probe_output for marker in signatures):
        return False

    command = (
        "echo BOARD=$(cat /tmp/sysinfo/board_name 2>/dev/null); "
        "[ -f /tmp/NOKIA_UBI_INSTALL_COMPLETE ] && echo MIGRATION=complete || echo MIGRATION=missing; "
        "[ -f /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED ] && echo AUTH=present || echo AUTH=missing; "
        "img=/tmp/nokia-embedded-openwrt-sysupgrade.itb; "
        "[ -f \"$img\" ] && { echo IMAGE_SIZE=$(wc -c < \"$img\" | tr -d ' '); echo IMAGE_SHA=$(sha256sum \"$img\" | awk '{print $1}'); } || echo IMAGE=missing; "
        "ubinfo -a 2>/dev/null | awk '$1 == \"Name:\" {print \"VOL=\" $2}'; "
        "grep -Fq '[OK] SkyHigh ML02G300WHI00 explicitly detected.' /tmp/nokia-autoflash.log && echo SKYHIGH_PRECHECK=present; "
        "grep -Fq 'UBI MIGRATION COMPLETE.' /tmp/nokia-autoflash.log && echo MIGRATION_LOG=present; "
        "grep -Fq 'ERROR: FudanMicro FM25G02B NAND is not supported by this U-Boot' /tmp/nokia-autoflash.log && echo FALSE_FUDAN_SIGNATURE=present"
    )
    _, diagnostics = ssh_run(host, command, timeout=90, quiet=True, batch_mode=True)
    required = (
        "BOARD=nokia,xg-040g-md-ubi", "MIGRATION=complete", "AUTH=present",
        f"IMAGE_SIZE={EXPECTED_PROD_SIZE}", f"IMAGE_SHA={EXPECTED_PROD_SHA}",
        "SKYHIGH_PRECHECK=present", "MIGRATION_LOG=present",
        "FALSE_FUDAN_SIGNATURE=present",
        "VOL=ubootenv", "VOL=ubootenv2", "VOL=bosa",
        "VOL=ri", "VOL=fip", "VOL=fit",
    )
    missing = [marker for marker in required if marker not in diagnostics]
    if missing:
        print(diagnostics, end="" if diagnostics.endswith("\n") else "\n")
        raise Error(tr(
            "Обнаружен похожий RC27-сбой, но строгая проверка безопасного продолжения не пройдена: " + ", ".join(missing),
            "A similar RC27 failure was detected, but strict continuation validation failed: " + ", ".join(missing),
        ))

    print(tr(
        "[ПРЕДУПРЕЖДЕНИЕ] Подтверждена известная ошибка RC27: собственная строка Fudan из dmesg была принята за аппаратную идентификацию после уже завершённой UBI migration.",
        "[WARNING] The known RC27 defect is confirmed: its own Fudan policy line in dmesg was mistaken for hardware identity after UBI migration had completed.",
    ))
    print(tr(
        "[OK] SkyHigh была подтверждена до форматирования; UBI layout 0..5, authorization и production ITB SHA256 проверены. Повторного форматирования не будет.",
        "[OK] SkyHigh was confirmed before formatting; UBI layout 0..5, authorization, and the production ITB SHA256 are verified. NAND will not be reformatted.",
    ))
    token = input(tr(
        "Введите точно CONTINUE PRODUCTION SYSUPGRADE: ",
        "Type exactly CONTINUE PRODUCTION SYSUPGRADE: ",
    )).strip()
    if token != "CONTINUE PRODUCTION SYSUPGRADE":
        raise Error(tr("Продолжение отменено", "Continuation cancelled"))

    rc, output = ssh_run(
        host,
        "img=/tmp/nokia-embedded-openwrt-sysupgrade.itb; "
        f"[ \"$(sha256sum \"$img\" | awk '{{print $1}}')\" = {EXPECTED_PROD_SHA} ] || exit 41; "
        "sysupgrade -T \"$img\" || exit 42; "
        "echo __MEDVEFLASHER_PRODUCTION_SYSUPGRADE_START__; sync; exec sysupgrade -v -n \"$img\"",
        timeout=900, allow_disconnect=True, quiet=False, batch_mode=True,
    )
    if "__MEDVEFLASHER_PRODUCTION_SYSUPGRADE_START__" not in output:
        raise Error(tr("Не получен маркер запуска production sysupgrade", "Production sysupgrade start marker was not received"))
    print(tr(
        "[OK] Production sysupgrade запущен из уже проверенного RAM-образа; ожидаю reboot и LuCI.",
        "[OK] Production sysupgrade started from the already verified RAM image; waiting for reboot and LuCI.",
    ))
    return True

_AUTOFLASH_STEP_RU = {
    "1": "форматирование области UBI",
    "2": "подключение UBI к NAND",
    "3": "создание системных UBI-томов",
    "4": "запись bosa и ri",
    "5": "запись FIP и резервного загрузочного образа",
    "6": "проверка записанных данных чтением и SHA256",
    "7": "запись BL2 последней",
    "8": "фиксация успешного завершения миграции",
}
_AUTOFLASH_STEP_EN = {
    "1": "formatting the all-in-UBI region",
    "2": "attaching UBI to NAND",
    "3": "creating the system UBI volumes",
    "4": "writing bosa and ri",
    "5": "writing FIP and the fallback FIT",
    "6": "readback and SHA256 verification",
    "7": "writing BL2 last",
    "8": "recording successful migration completion",
}


def _transition_state_label(state: str) -> str:
    labels = {
        "NOT_STARTED": tr("transition загружен; ожидается запуск автоматики", "transition booted; waiting for automation"),
        "CHECKING": tr("проверка платы, NAND и встроенного образа", "checking the board, NAND and embedded image"),
        "FORMATTING_AND_FLASHING": tr("форматирование UBI и запись загрузочных данных", "formatting UBI and writing boot data"),
        "BOOTING": tr("ранний запуск transition initramfs", "early transition initramfs boot"),
        "WAITING_FOR_SYSTEM": tr("transition ожидает завершения normal init", "transition is waiting for normal init to complete"),
        "STARTING": tr("запуск проверки выбранного образа", "starting validation of the selected image"),
        "FAILED": tr("установка остановлена с ошибкой", "installation stopped with an error"),
        "FULLFLASH_RETURNED_0": tr("fullflash вернул 0 без reboot; требуется проверка production", "fullflash returned 0 without reboot; production verification is required"),
    }
    return labels.get(state, state.replace("_", " ").lower())


def _port_summary(port22: bool, port80: bool, port443: bool, port23: bool) -> str:
    if ensure_language() == "en":
        return (
            f"SSH 22={'open' if port22 else 'closed'}; "
            f"HTTP 80={'open' if port80 else 'closed'}; "
            f"HTTPS 443={'open' if port443 else 'closed'}; "
            f"Telnet 23={'open' if port23 else 'closed'}"
        )
    return (
        f"SSH 22={'открыт' if port22 else 'закрыт'}; "
        f"HTTP 80={'открыт' if port80 else 'закрыт'}; "
        f"HTTPS 443={'открыт' if port443 else 'закрыт'}; "
        f"Telnet 23={'открыт' if port23 else 'закрыт'}"
    )


def _extract_autoflash_log(probe_output: str) -> str:
    match = re.search(r"AUTOFLOG_BEGIN\r?\n(.*?)\r?\nAUTOFLOG_END", probe_output, re.S)
    return match.group(1) if match else ""


def _normalise_autoflash_line(raw: str) -> str:
    line = raw.replace("\r", "").strip()
    line = re.sub(r"^\[\s*\d+(?:\.\d+)?\]\s*", "", line)
    line = re.sub(r"^(?:NOKIA-AUTOFLASH|NOKIA-UBI-INSTALLER):\s*", "", line)
    return line.strip()


def _new_autoflash_events(probe_output: str, seen: set[str]) -> list[tuple[str, str, str]]:
    """Return new operator-level events as (message, phase, event_key)."""
    events: list[tuple[str, str, str]] = []
    log_text = _extract_autoflash_log(probe_output)
    for raw in log_text.splitlines():
        line = _normalise_autoflash_line(raw)
        if not line or line in seen:
            continue
        seen.add(line)
        step = re.match(r"\[([1-8])/8\]\s*(.*)", line)
        if step:
            labels = _AUTOFLASH_STEP_EN if ensure_language() == "en" else _AUTOFLASH_STEP_RU
            phase = labels[step.group(1)]
            events.append((tr(f"[STEP {step.group(1)}/8] {phase}.", f"[STEP {step.group(1)}/8] {phase}."), phase, f"step:{step.group(1)}"))
            continue
        if "CHECK PASSED." in line:
            phase = tr("проверки переходной системы завершены", "transition checks completed")
            events.append((tr("[OK] Проверки переходной системы завершены; запись в NAND начинается.", "[OK] Transition checks completed; NAND writing is starting."), phase, "checks-complete"))
        elif line == "UBI MIGRATION COMPLETE.":
            phase = tr("разметка UBI создана и проверена", "UBI created and verified")
            events.append((tr("[OK] Переход на UBI завершён и проверен.", "[OK] UBI migration completed and verified."), phase, "ubi-complete"))
        elif "Migration completed and verified. Starting production sysupgrade stage." in line:
            phase = tr("запуск установки основной OpenWrt", "starting production sysupgrade")
            events.append((tr("[WAIT] Запускается установка основной OpenWrt.", "[WAIT] Production sysupgrade is starting."), phase, "sysupgrade-starting"))
        elif "Performing system upgrade" in line:
            phase = tr("запись основной OpenWrt", "writing production OpenWrt")
            events.append((tr("[WAIT] Основная OpenWrt записывается в UBI.", "[WAIT] Production OpenWrt is being written to UBI."), phase, "sysupgrade-writing"))
        elif "sysupgrade successful" in line.lower():
            phase = tr("установка OpenWrt завершена; ожидается перезагрузка", "sysupgrade completed; waiting for reboot")
            events.append((tr("[OK] Установка OpenWrt завершена; роутер перезагружается.", "[OK] Sysupgrade completed; the router is rebooting."), phase, "sysupgrade-success"))
        elif line.startswith("ERROR:") or "AUTOMATIC FLASH DID NOT COMPLETE" in line:
            events.append(("[ERROR] " + line.removeprefix("ERROR:").strip(), tr("ошибка переходной системы", "transition error"), "error"))
    return events



_AUTO_TRANSITION_SSH_MINIMAL_AUTH: dict[str, bool] = {}

def _transition_telnet_run(host: str, command: str, timeout: int = 12) -> tuple[int, str]:
    """Best-effort OpenWrt-transition command channel for stage2 monitoring.

    It is never an authorization channel for destructive actions. It only reads
    state/log files if transition telnetd is available while SSH is not.
    """
    telnet = Telnet(host, 23, timeout=min(6, timeout))
    try:
        dialogue = telnet.read(0.8, echo=False)
        if not dialogue:
            telnet.send_bytes(b"\r\n")
            dialogue += telnet.read(0.8, echo=False)
        if re.search(r"(?i)(?:login|username)\s*:", dialogue):
            telnet.send_login_line("root")
            dialogue += telnet.read(0.8, echo=False)
        if re.search(r"(?i)password\s*:", dialogue[-1200:]):
            telnet.send_login_line("")
            dialogue += telnet.read(0.8, echo=False)
        if re.search(r"(?i)login incorrect|authentication failed|access denied", dialogue):
            raise Error("transition Telnet authentication failed")
        return telnet.command_clean(command, timeout=timeout)
    finally:
        telnet.close()


def _auto_transition_probe(host: str, probe_cmd: str, port22: bool, port23: bool) -> tuple[str, str]:
    """Read auto-transition status over deterministic SSH, then Telnet fallback."""
    errors: list[str] = []
    if port22:
        preferred = _AUTO_TRANSITION_SSH_MINIMAL_AUTH.get(host)
        modes = [preferred] if preferred is not None else [True, False]
        for minimal in modes:
            try:
                _, out = ssh_run(
                    host, probe_cmd, timeout=12, allow_disconnect=True, quiet=True,
                    batch_mode=True, minimal_auth=bool(minimal),
                )
                if "MODE=" in out:
                    if "MODE=TRANSITION" in out:
                        _AUTO_TRANSITION_SSH_MINIMAL_AUTH[host] = bool(minimal)
                    return out, "ssh"
                errors.append("ssh: incomplete probe")
            except Error as exc:
                errors.append("ssh: " + str(exc).replace("\n", " ")[-500:])
        # If a cached mode stopped working after reboot, allow the other mode once.
        if preferred is not None:
            other = not preferred
            try:
                _, out = ssh_run(
                    host, probe_cmd, timeout=12, allow_disconnect=True, quiet=True,
                    batch_mode=True, minimal_auth=other,
                )
                if "MODE=" in out:
                    if "MODE=TRANSITION" in out:
                        _AUTO_TRANSITION_SSH_MINIMAL_AUTH[host] = other
                    return out, "ssh"
            except Error as exc:
                errors.append("ssh-alt: " + str(exc).replace("\n", " ")[-500:])
    if port23:
        try:
            _, out = _transition_telnet_run(host, probe_cmd, timeout=12)
            if "MODE=" in out:
                return out, "telnet"
            errors.append("telnet: incomplete probe")
        except Error as exc:
            errors.append("telnet: " + str(exc).replace("\n", " ")[-500:])
        except OSError as exc:
            errors.append("telnet: " + str(exc)[-500:])
    return "TRANSITION_PROBE_ERROR=" + " | ".join(errors)[-1400:], ""

def run_stage2(host: str, manual_mode: bool = False, expected_board: str = "nokia,xg-040g-md-ubi", initial_handoff_unknown: bool = False) -> str:
    if not manual_mode:
        stage_header("6", "Ожидание OpenWrt", "Waiting for OpenWrt")
    if initial_handoff_unknown:
        print(tr(
            "[STATE] STAGE1_HANDOFF_UNKNOWN: команда --flash могла быть принята stock shell. Автоповтор запрещён; выполняется только наблюдение.",
            "[STATE] STAGE1_HANDOFF_UNKNOWN: the stock shell may have accepted --flash. Automatic retry is forbidden; observation only.",
        ))
    print(tr(
        "[WAIT] Выбранный образ устанавливается; роутер перезагрузится автоматически. Не выключайте питание." if manual_mode else
        "[WAIT] Роутер загружает переходную систему, затем установит OpenWrt. Не выключайте питание.",
        "[WAIT] The selected image is being installed; the router will reboot automatically. Do not power off." if manual_mode else
        "[WAIT] The router is booting the transition system and will then install OpenWrt. Do not power off.",
    ))

    started = time.time()
    next_report = started + 30
    next_checkpoint = started + 1800
    previous_state = ""
    current_phase = tr(
        "запуск установки выбранного образа" if manual_mode else "ожидание загрузки переходной системы",
        "starting installation of the selected image" if manual_mode else "waiting for the transition system to boot",
    )
    previous_ports: tuple[bool, bool, bool, bool] | None = None
    seen_autoflash_lines: set[str] = set()
    last_raw_log = ""
    transition_seen = False
    highest_step = 0
    handoff_announced = False
    handoff_explicit = False
    handoff_outage_seen = False
    services_returned_announced = False
    last_transition_progress = started
    safe_to_power_cycle = False
    safe_retry_prompted = False
    last_probe_error = ""
    post_sysupgrade_reboot_prompted = False
    handoff_started_at: float | None = None

    while True:
        now = time.time()
        port22 = _tcp_open(host, 22)
        port80 = _tcp_open(host, 80)
        port443 = _tcp_open(host, 443)
        port23 = _tcp_open(host, 23)
        ports = (port22, port80, port443, port23)
        if ports != previous_ports:
            previous_ports = ports
            print(tr("[NET] TCP-порты: ", "[NET] TCP ports: ") + _port_summary(*ports) + ".")

        if transition_seen and not handoff_announced and not any(ports) and (
            highest_step >= 6 or previous_state in ("FORMATTING_AND_FLASHING", "WAITING_FOR_SYSTEM")
        ):
            handoff_announced = True
            handoff_outage_seen = True
            handoff_started_at = now
            current_phase = tr(
                "перезагрузка после записи UBI",
                "reboot after writing UBI",
            )
            print(tr(
                "[WAIT] Переходная система завершает финальные операции и перезапускает роутер для установки основной OpenWrt.",
                "[WAIT] The transition system is finishing its final operations and rebooting the router to install production OpenWrt.",
            ))
        elif handoff_announced and not any(ports):
            handoff_outage_seen = True

        detected_mode = ""
        probe_transport = ""
        http_output = ""
        if not manual_mode:
            http_output, http_transport = _auto_transition_http_probe(host)
        if http_output and "MODE=TRANSITION" in http_output:
            output = http_output
            probe_transport = http_transport
        elif port22 or (not manual_mode and port23):
            state_cmd = (
                "cat /tmp/NOKIA_MANUAL_STATE 2>/dev/null || echo STARTING; "
                if manual_mode else
                "cat /tmp/NOKIA_AUTOFLASH_STATE 2>/dev/null || echo NOT_STARTED; "
            )
            failure_cmd = (
                "[ ! -f /tmp/NOKIA_MANUAL_FLASH_FAILED ] || { printf 'AUTO_FAILURE='; cat /tmp/NOKIA_MANUAL_FLASH_FAILED; }; "
                if manual_mode else
                "[ ! -f /tmp/NOKIA_AUTOFLASH_FAILED ] || { printf 'AUTO_FAILURE='; cat /tmp/NOKIA_AUTOFLASH_FAILED; }; "
            )
            log_cmd = (
                "cat /tmp/nokia-ubi-installer.log /tmp/nokia-manual-flash.log 2>/dev/null; "
                if manual_mode else
                "cat /tmp/nokia-autoflash.log 2>/dev/null; "
            )
            probe_cmd = (
                "if [ -x /usr/sbin/nokia-ubi-installer ]; then "
                "echo MODE=TRANSITION; printf 'AUTO_STATE='; " + state_cmd + failure_cmd +
                "echo AUTOFLOG_BEGIN; " + log_cmd + "echo AUTOFLOG_END; "
                "else echo MODE=PRODUCTION; echo BOARD=$(cat /tmp/sysinfo/board_name 2>/dev/null); "
                "ubinfo -a 2>/dev/null | awk '$1 == \"Name:\" {print \"VOL=\" $2}'; "
                "grep -E 'DISTRIB_RELEASE|DISTRIB_REVISION' /etc/openwrt_release 2>/dev/null; fi"
            )
            if manual_mode and port22:
                try:
                    _, output = _manual_ssh_run(
                        host, probe_cmd, timeout=20, allow_disconnect=True, quiet=True,
                    )
                    probe_transport = "ssh"
                except Error as exc:
                    output = f"SSH_PROBE_ERROR={exc}"
            elif not manual_mode:
                output, probe_transport = _auto_transition_probe(host, probe_cmd, port22, port23)
            else:
                output = "SSH_PROBE_ERROR=SSH port closed"
        elif not manual_mode:
            output = http_output or "CONTROL_PROBE_UNAVAILABLE"
        else:
            output = "SSH_PROBE_ERROR=SSH port closed"

        if "TRANSITION_PROBE_ERROR=" in output or "TRANSITION_HTTP_PROBE_ERROR=" in output or "SSH_PROBE_ERROR=" in output:
            compact = output.replace("\r", " ").replace("\n", " ")[-1000:]
            if compact != last_probe_error:
                last_probe_error = compact
                _write_session_only("[CONTROL] " + compact)

        if "MODE=PRODUCTION" in output:
            detected_mode = "production"
            current_phase = tr("проверка основной OpenWrt", "verifying production OpenWrt")
            required_volumes = ("VOL=ubootenv", "VOL=ubootenv2", "VOL=bosa", "VOL=ri", "VOL=fip", "VOL=fit", "VOL=rootfs_data")
            strong_identity = f"BOARD={expected_board}" in output and all(v in output for v in required_volumes) and "DISTRIB_RELEASE=" in output
            if strong_identity:
                if highest_step < 7:
                    print(tr(
                        "[STEP 7/8] запись BL2 последней — подтверждено post-boot инвариантом production board/UBI.",
                        "[STEP 7/8] BL2 written last — reconciled from the production board/UBI post-boot invariant.",
                    ))
                    highest_step = 7
                if highest_step < 8:
                    print(tr(
                        "[STEP 8/8] completion state — подтверждено успешной загрузкой production из новой UBI-разметки.",
                        "[STEP 8/8] completion state — reconciled by successful production boot from the new UBI layout.",
                    ))
                    highest_step = 8
                luci_ok = _probe_luci(host, 80, timeout=2.0) or _probe_luci(host, 443, timeout=2.0)
                if luci_ok:
                    print(tr(
                        "[OK] Production OpenWrt подтверждена по SSH: board/UBI/release PASS; LuCI подтверждена HTTP-content probe.",
                        "[OK] Production OpenWrt verified over SSH: board/UBI/release PASS; LuCI verified by an HTTP content probe.",
                    ))
                    return "production-ssh+luci"
                print(tr(
                    "[WAIT] Production board/UBI уже подтверждены; жду LuCI content probe.",
                    "[WAIT] Production board/UBI are already verified; waiting for the LuCI content probe.",
                ))
            print(tr(
                "[ПРЕДУПРЕЖДЕНИЕ] OpenWrt отвечает, но итоговая проверка ещё не пройдена; продолжаю ждать.",
                "[WARNING] OpenWrt responds, but final verification has not passed yet; continuing to wait.",
            ))

        if "MODE=TRANSITION" in output:
            detected_mode = "transition"
            if not transition_seen:
                transition_seen = True
                last_transition_progress = now
                channel = "HTTP control" if probe_transport.startswith("http:") else "SSH" if probe_transport == "ssh" else "Telnet" if probe_transport == "telnet" else "control channel"
                print(tr(
                    f"[OK] Переходная система загружена; live-progress доступен через {channel}.",
                    f"[OK] The transition system has booted; live progress is available over {channel}.",
                ))
            match = re.search(r"AUTO_STATE=([^\r\n]+)", output)
            state = match.group(1).strip() if match else "UNKNOWN"
            safe_match = re.search(r"SAFE_TO_POWER_CYCLE=([01])", output)
            safe_to_power_cycle = bool(safe_match and safe_match.group(1) == "1")
            if state != previous_state:
                last_transition_progress = now
                previous_state = state
                current_phase = _transition_state_label(state)
                if state == "NOT_STARTED":
                    print(tr(
                        "[WAIT] Переходная система ожидает запуск установки.",
                        "[WAIT] The transition system is waiting for installation to start.",
                    ))
                elif state == "WAITING_FOR_SYSTEM":
                    print(tr(
                        "[WAIT] Transition initramfs загружен; автоматика ждёт завершения normal init. Destructive stage ещё не подтверждён.",
                        "[WAIT] Transition initramfs is running; automation is waiting for normal init. The destructive stage has not been observed yet.",
                    ))
                elif state != "FAILED":
                    print(tr(
                        f"[WAIT] Переходная система: {current_phase}.",
                        f"[WAIT] Transition system: {current_phase}.",
                    ))

            raw_log = _extract_autoflash_log(output)
            if raw_log and raw_log != last_raw_log:
                last_transition_progress = now
                new_tail = raw_log[len(last_raw_log):] if raw_log.startswith(last_raw_log) else raw_log
                _write_session_only("[TRANSITION-RAW]\n" + new_tail)
                last_raw_log = raw_log
            for message, phase, event_key in _new_autoflash_events(output, seen_autoflash_lines):
                current_phase = phase
                step_match = re.fullmatch(r"step:([1-8])", event_key)
                if step_match:
                    highest_step = max(highest_step, int(step_match.group(1)))
                if event_key in ("sysupgrade-starting", "sysupgrade-writing", "sysupgrade-success"):
                    handoff_announced = True
                    handoff_explicit = True
                    if handoff_started_at is None:
                        handoff_started_at = now
                print(message)

            if handoff_outage_seen and not handoff_explicit:
                # A brief service outage can happen while transition is
                # still running. If SSH identifies transition again, do
                # not mistake that outage for the production reboot.
                handoff_announced = False
                handoff_outage_seen = False
                services_returned_announced = False

            if state == "FAILED":
                print(output, end="" if output.endswith("\n") else "\n")
                if not manual_mode and _recover_rc27_false_fudan(host, output):
                    previous_state = "RC27_FALSE_FUDAN_RECOVERY"
                    current_phase = tr("продолжение установки основной OpenWrt после проверки", "continuing production sysupgrade after validation")
                    time.sleep(5)
                    continue
                raise Error(tr(
                    "установка выбранного образа остановлена; ручная переходная система доступна по SSH." if manual_mode else
                    "автоматическая прошивка не завершилась; переходная система оставлена запущенной для диагностики. Полный /tmp/nokia-autoflash.log сохранён в журнале сеанса на ПК.",
                    "installation of the selected image stopped; the manual transition remains available over SSH." if manual_mode else
                    "automatic flashing did not complete; the transition system remains running for diagnostics. The complete /tmp/nokia-autoflash.log was saved in the PC session log.",
                ))

        if handoff_announced and handoff_outage_seen and any(ports) and detected_mode != "transition" and not services_returned_announced:
            services_returned_announced = True
            current_phase = tr("запуск основной OpenWrt и сетевых служб", "starting production OpenWrt and network services")
            print(tr(
                "[WAIT] Роутер снова доступен после перезагрузки; проверяю основную OpenWrt.",
                "[WAIT] The router is reachable again after reboot; verifying production OpenWrt.",
            ))

        # Verify LuCI only after the transition-to-production handoff. This
        # avoids treating a web service in the transition initramfs as the
        # final installed system. SSH production verification above remains
        # preferred because it also checks the board and UBI volumes.
        if detected_mode != "transition" and handoff_announced and handoff_outage_seen and (port80 or port443):
            time.sleep(3)
            luci80 = port80 and _probe_luci(host, 80)
            luci443 = port443 and _probe_luci(host, 443)
            if luci80 or luci443:
                print(tr(
                    "[OK] Перезагрузка завершена; основная OpenWrt подтверждена по LuCI.",
                    "[OK] Reboot completed; production OpenWrt was verified through LuCI.",
                ))
                return "production-web"

        if (not post_sysupgrade_reboot_prompted and handoff_announced and handoff_outage_seen
                and handoff_started_at is not None and now - handoff_started_at >= 240
                and detected_mode != "production"):
            post_sysupgrade_reboot_prompted = True
            print(tr(
                "[REBOOT-CHECK] Перезагрузка production не подтверждена более 4 минут. Сам по себе тайм-аут НЕ разрешает отключать питание.",
                "[REBOOT-CHECK] Production reboot has not been verified for more than 4 minutes. Timeout alone does NOT authorize a power cycle.",
            ))
            print(tr(
                "[SAFE-REBOOT OPTION] Если подключён UART и на нём уже есть точная строка 'sysupgrade successful', а после неё несколько минут нет reboot, разрешён один ручной power-cycle: питание OFF 5 секунд → ON, Reset не нажимать. Если этой строки нет — питание НЕ трогать.",
                "[SAFE-REBOOT OPTION] If UART is connected and already shows the exact line 'sysupgrade successful', followed by several minutes without reboot, one manual power cycle is allowed: power OFF for 5 seconds → ON, do not press Reset. If that exact line is absent, do NOT touch power.",
            ))
            print(tr(
                "[INFO] Мастер продолжает мониторинг; после ручного power-cycle ничего вводить не нужно.",
                "[INFO] Monitoring continues; no input is required after the manual power cycle.",
            ))

        if now >= next_report:
            elapsed = int(now - started)
            print(tr(
                f"[WAIT] {elapsed // 60:02d}:{elapsed % 60:02d} — {current_phase}.",
                f"[WAIT] {elapsed // 60:02d}:{elapsed % 60:02d} — {current_phase}.",
            ))
            next_report = now + 30

        if not manual_mode and transition_seen and not safe_retry_prompted and highest_step == 0 and safe_to_power_cycle and previous_state in ("BOOTING", "WAITING_FOR_SYSTEM", "CHECKING") and now - last_transition_progress >= 120:
            safe_retry_prompted = True
            print(tr(
                "[BOOT-TIMEOUT] 120 секунд нет прогресса, но transition control-plane последний раз явно сообщил SAFE_TO_POWER_CYCLE=1 и destructive step 1/8 ещё не наблюдался.",
                "[BOOT-TIMEOUT] No progress for 120 seconds, but the transition control plane last explicitly reported SAFE_TO_POWER_CYCLE=1 and destructive step 1/8 has not been observed.",
            ))
            answer = input(tr(
                "Разрешён один контролируемый power-cycle. Y — выполнить его вручную сейчас и продолжить мониторинг; Enter — не трогать питание: ",
                "One controlled power cycle is permitted. Y — perform it manually now and continue monitoring; Enter — keep power unchanged: ",
            )).strip().lower()
            if answer in ("y", "yes", "д", "да"):
                input(tr(
                    "Отключите питание на 5 секунд, включите Nokia снова и нажмите Enter. Мастер продолжит мониторинг: ",
                    "Remove power for 5 seconds, power the Nokia on again, then press Enter. The wizard will continue monitoring: ",
                ))
                current_phase = tr("повторный безопасный запуск transition", "safe transition boot retry")
                last_transition_progress = time.time()
                previous_state = ""
                transition_seen = False
                safe_to_power_cycle = False
            else:
                print(tr("[INFO] Питание не трогаем; продолжаю мониторинг.", "[INFO] Power remains unchanged; continuing monitoring."))

        if now >= next_checkpoint:
            answer = input(tr(
                "30 минут без подтверждённого результата. Enter — продолжать; S — завершить как UNVERIFIED: ",
                "30 minutes passed without a verified result. Enter — continue; S — finish as UNVERIFIED: ",
            )).strip().lower()
            if answer in ("s", "stop", "стоп"):
                print(tr(
                    "[ПРЕДУПРЕЖДЕНИЕ] Ожидание остановлено. Установка могла завершиться, но не подтверждена мастером.",
                    "[WARNING] Waiting stopped. Installation may have completed, but the wizard did not verify it.",
                ))
                return "post-install-unverified"
            next_checkpoint = time.time() + 1800

        # Steps 7/8 and 8/8 can complete in well under one second after step 6.
        # Poll aggressively only in this narrow transition window; otherwise keep
        # the low-overhead 5-second cadence.
        if detected_mode == "transition" and 6 <= highest_step < 8:
            time.sleep(0.35)
        else:
            time.sleep(5)

def _raw_stream(path: Path):
    probe = path.open("rb")
    magic = probe.read(2)
    probe.seek(0)
    if magic == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=probe, mode="rb")
    return probe


def raw_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with _raw_stream(path) as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _read_raw_range(path: Path, offset: int, length: int) -> bytes:
    with _raw_stream(path) as fh:
        remaining = offset
        while remaining:
            chunk = fh.read(min(1024 * 1024, remaining))
            if not chunk:
                raise Error(tr(
                    f"не удалось прочитать диапазон {offset:#x}+{length:#x} из {path.name}",
                    f"failed to read range {offset:#x}+{length:#x} from {path.name}",
                ))
            remaining -= len(chunk)
        data = fh.read(length)
    if len(data) != length:
        raise Error(tr(
            f"неполный диапазон {offset:#x}+{length:#x} в {path.name}",
            f"incomplete range {offset:#x}+{length:#x} in {path.name}",
        ))
    return data


def verify_stock_restore_backup(directory: Path) -> dict:
    """Validate a complete, internally consistent stock backup.

    Besides cross-checking mtd16 against the individual stock partitions, RC11
    rejects the two known OpenWrt BL2 layouts.  A backup containing the OpenWrt
    preloader at offset 0 (the historical brick) or at offset 0x800 (the proper
    all-in-UBI BL2 container) is not an original stock backup and must never be
    used to restore stock firmware.
    """
    validation = verify_backup(directory, require_md_slot_layout=False)
    family = str(validation.get("stock_family", "unknown"))
    if family not in ("md", "mf"):
        raise Error(tr(
            "mtd2..mtd5 не совпали с известными stock-профилями MD/MF; brick recovery запрещён. " + _slot_layout_diagnostic({int(k): int(v) for k, v in validation["sizes"].items()}),
            "mtd2..mtd5 do not match a known MD/MF stock profile; brick recovery is blocked. " + _slot_layout_diagnostic({int(k): int(v) for k, v in validation["sizes"].items()}),
        ))
    files = {int(k): Path(v) for k, v in validation["files"].items()}
    expected_hashes: dict[int, str] = {}
    for number in STOCK_RAW_SLICES:
        digest, size = raw_sha256(files[number])
        expected_size = STOCK_RAW_SLICES[number][1]
        if size != expected_size:
            raise Error(f"mtd{number}: размер {size}, ожидается {expected_size} для восстановления stock")
        expected_hashes[number] = digest

    all_hash = hashlib.sha256()
    slice_hashes = {number: hashlib.sha256() for number in STOCK_RAW_SLICES}
    total = 0
    with _raw_stream(files[16]) as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            start = total
            end = total + len(chunk)
            all_hash.update(chunk)
            for number, (offset, length) in STOCK_RAW_SLICES.items():
                slice_end = offset + length
                left = max(start, offset)
                right = min(end, slice_end)
                if left < right:
                    slice_hashes[number].update(chunk[left - start:right - start])
            total = end
    if total != STOCK_RESTORE_SPAN:
        raise Error(f"mtd16/all_flash: распакованный размер {total}, ожидается {STOCK_RESTORE_SPAN}")
    live_differences: list[int] = []
    for number, digest in slice_hashes.items():
        actual = digest.hexdigest()
        if actual == expected_hashes[number]:
            continue
        if number in STOCK_STABLE_RAW_SLICES:
            raise Error(
                f"mtd16 не согласован со статическим mtd{number}: "
                f"SHA256 диапазона={actual}, SHA256 отдельного дампа={expected_hashes[number]}"
            )
        live_differences.append(number)

    if live_differences:
        names = ", ".join(f"mtd{number}" for number in live_differences)
        if len(live_differences) == 1:
            ru_difference = f"{names} отличается от более позднего снимка mtd16"
            en_difference = f"{names} differs from the later mtd16 snapshot"
        else:
            ru_difference = f"{names} отличаются от более позднего снимка mtd16"
            en_difference = f"{names} differ from the later mtd16 snapshot"
        validation["warnings"].append(tr(
            ru_difference + "; это допустимо для изменяемых stock-разделов. "
            "Для восстановления используется канонический mtd16.",
            en_difference + "; this is valid for live stock partitions. "
            "The canonical mtd16 image is used for restore.",
        ))

    stock_bl2 = _read_raw_range(files[16], 0, STOCK_BL2_SIZE)
    known_openwrt_preloaders = (
        (OPENWRT_PRELOADER_SIZE, OPENWRT_PRELOADER_SHA, "AN7581/MD"),
        (MF_RECOVERY_PRELOADER_SIZE, MF_RECOVERY_PRELOADER_SHA, "AN7583/MF"),
    )
    for preloader_size, preloader_sha, preloader_label in known_openwrt_preloaders:
        no_shift = hashlib.sha256(stock_bl2[:preloader_size]).hexdigest()
        shifted = hashlib.sha256(stock_bl2[0x800:0x800 + preloader_size]).hexdigest()
        if no_shift == preloader_sha:
            raise Error(
                f"выбранный backup содержит OpenWrt preloader {preloader_label} в начале BL2 без смещения. "
                "Это копия повреждённого OpenWrt BL2, а не исходный stock backup"
            )
        if shifted == preloader_sha and stock_bl2[:0x800] == b"\xff" * 0x800:
            raise Error(
                f"выбранный backup содержит OpenWrt all-in-UBI BL2 {preloader_label} "
                "(FF 0x800 + preloader), а не исходный stock BL2"
            )

    result = dict(validation)
    result["stock_restore"] = {
        "all_flash_size": total,
        "all_flash_sha256": all_hash.hexdigest(),
        "verified_static_slices": sorted(STOCK_STABLE_RAW_SLICES),
        "live_slices_checked_by_manifest": sorted(STOCK_LIVE_RAW_SLICES),
        "live_slice_differences": live_differences,
        "bl2_size": STOCK_BL2_SIZE,
        "bl2_sha256": hashlib.sha256(stock_bl2).hexdigest(),
        "bl2_provenance": "does not match known AN7581/AN7583 OpenWrt preloader placements",
        "device_family": family,
        "ibu_size": STOCK_IBU_SIZE,
    }
    return result


def prepare_stock_restore_payloads(directory: Path) -> tuple[Path, dict]:
    validation = verify_stock_restore_backup(directory)
    source = Path(validation["files"]["16"])
    device_id = validation["stock_restore"]["all_flash_sha256"][:16]
    output = WORK / "stock-recovery" / device_id
    output.mkdir(parents=True, exist_ok=True)
    bl2_gz = output / "stock-bl2.bin.gz"
    ibu_gz = output / "stock-ibu.bin.gz"
    bl2_hash = hashlib.sha256()
    ibu_hash = hashlib.sha256()
    total = 0
    with _raw_stream(source) as src, gzip.open(bl2_gz, "wb", compresslevel=1) as bl2_out, gzip.open(ibu_gz, "wb", compresslevel=1) as ibu_out:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            start = total
            end = start + len(chunk)
            if start < STOCK_BL2_SIZE:
                cut = min(len(chunk), STOCK_BL2_SIZE - start)
                part = chunk[:cut]
                bl2_out.write(part)
                bl2_hash.update(part)
                rest = chunk[cut:]
                if rest:
                    ibu_out.write(rest)
                    ibu_hash.update(rest)
            else:
                ibu_out.write(chunk)
                ibu_hash.update(chunk)
            total = end
    if total != STOCK_RESTORE_SPAN:
        raise Error("mtd16 изменился во время подготовки файлов восстановления")
    manifest = {
        "kit_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backup_directory": str(Path(directory).resolve()),
        "all_flash_sha256": validation["stock_restore"]["all_flash_sha256"],
        "all_flash_size": STOCK_RESTORE_SPAN,
        "bl2": {"file": bl2_gz.name, "raw_size": STOCK_BL2_SIZE, "raw_sha256": bl2_hash.hexdigest(), "gzip_sha256": sha_file(bl2_gz)},
        "ibu": {"file": ibu_gz.name, "raw_size": STOCK_IBU_SIZE, "raw_sha256": ibu_hash.hexdigest(), "gzip_sha256": sha_file(ibu_gz)},
        "write_order": ["ibu", "bl2"],
        "source_validation": {
            "device_family": validation["stock_restore"]["device_family"],
            "verified_static_slices": validation["stock_restore"]["verified_static_slices"],
            "live_slices_checked_by_manifest": validation["stock_restore"]["live_slices_checked_by_manifest"],
            "live_slice_differences": validation["stock_restore"]["live_slice_differences"],
            "warnings": validation.get("warnings", []),
        },
        "warning": "IBU is restored and verified first; exact stock BL2 is restored last. Use only on the Nokia that produced this backup.",
    }
    write_text(output / "restore-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return output, manifest


def prepare_uboot_restore_chunks(payload_dir: Path, manifest: dict) -> list[dict]:
    """Create aligned raw IBU chunks for direct RAM-U-Boot restoration."""
    chunk_dir = payload_dir / "uboot-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict] = []
    expected_total = int(manifest["ibu"]["raw_size"])
    total = 0
    with gzip.open(payload_dir / manifest["ibu"]["file"], "rb") as src:
        index = 0
        while total < expected_total:
            wanted = min(UBOOT_RESTORE_CHUNK_SIZE, expected_total - total)
            name = f"stock-ibu-{total:08x}-{wanted:08x}.bin"
            path = chunk_dir / name
            digest = hashlib.sha256()
            written = 0
            with path.open("wb") as dst:
                while written < wanted:
                    data = src.read(min(1024 * 1024, wanted - written))
                    if not data:
                        raise Error("stock-ibu.bin.gz закончился раньше ожидаемого размера")
                    dst.write(data)
                    digest.update(data)
                    written += len(data)
            chunks.append({
                "index": index,
                "file": path,
                "remote_name": f"nokia-stock-{index:02d}.bin",
                "offset": total,
                "size": wanted,
                "sha256": digest.hexdigest(),
            })
            total += wanted
            index += 1
        if src.read(1):
            raise Error("stock-ibu.bin.gz содержит лишние данные")
    if total != expected_total:
        raise Error("не удалось подготовить полный набор IBU-блоков")

    bl2_raw = chunk_dir / "nokia-stock-bl2.bin"
    digest = hashlib.sha256()
    size = 0
    with gzip.open(payload_dir / manifest["bl2"]["file"], "rb") as src, bl2_raw.open("wb") as dst:
        for data in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(data)
            digest.update(data)
            size += len(data)
    if size != STOCK_BL2_SIZE or digest.hexdigest() != manifest["bl2"]["raw_sha256"]:
        raise Error("не удалось подготовить точный stock BL2 для U-Boot")
    manifest["uboot_restore"] = {
        "chunk_size": UBOOT_RESTORE_CHUNK_SIZE,
        "chunks": [{k: (str(v) if isinstance(v, Path) else v) for k, v in c.items()} for c in chunks],
        "bl2_file": str(bl2_raw),
        "bl2_sha256": digest.hexdigest(),
        "method": "RAM U-Boot, whole ubi erase, bad-block-aware physical-span write/readback, exact stock BL2 last",
    }
    write_text(payload_dir / "restore-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return chunks


class WindowsNativeSerial:
    """Minimal dependency-free Win32 COM backend for 115200 8N1 XMODEM."""

    def __init__(self, port: str, baudrate: int = 115200):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._closed = False

        class DCB(ctypes.Structure):
            _fields_ = [
                ("DCBlength", wintypes.DWORD),
                ("BaudRate", wintypes.DWORD),
                ("Flags", wintypes.DWORD),
                ("wReserved", wintypes.WORD),
                ("XonLim", wintypes.WORD),
                ("XoffLim", wintypes.WORD),
                ("ByteSize", wintypes.BYTE),
                ("Parity", wintypes.BYTE),
                ("StopBits", wintypes.BYTE),
                ("XonChar", ctypes.c_char),
                ("XoffChar", ctypes.c_char),
                ("ErrorChar", ctypes.c_char),
                ("EofChar", ctypes.c_char),
                ("EvtChar", ctypes.c_char),
                ("wReserved1", wintypes.WORD),
            ]

        class COMMTIMEOUTS(ctypes.Structure):
            _fields_ = [
                ("ReadIntervalTimeout", wintypes.DWORD),
                ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
                ("ReadTotalTimeoutConstant", wintypes.DWORD),
                ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
                ("WriteTotalTimeoutConstant", wintypes.DWORD),
            ]

        self._DCB = DCB
        self._COMMTIMEOUTS = COMMTIMEOUTS
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32 = self._kernel32
        k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.GetCommState.argtypes = [wintypes.HANDLE, ctypes.POINTER(DCB)]
        k32.GetCommState.restype = wintypes.BOOL
        k32.SetCommState.argtypes = [wintypes.HANDLE, ctypes.POINTER(DCB)]
        k32.SetCommState.restype = wintypes.BOOL
        k32.SetCommTimeouts.argtypes = [wintypes.HANDLE, ctypes.POINTER(COMMTIMEOUTS)]
        k32.SetCommTimeouts.restype = wintypes.BOOL
        k32.SetupComm.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
        k32.SetupComm.restype = wintypes.BOOL
        k32.PurgeComm.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.PurgeComm.restype = wintypes.BOOL
        k32.ReadFile.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
        ]
        k32.ReadFile.restype = wintypes.BOOL
        k32.WriteFile.argtypes = [
            wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
        ]
        k32.WriteFile.restype = wintypes.BOOL
        k32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        k32.FlushFileBuffers.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL

        clean_port = port.strip().upper()
        device_path = clean_port
        if re.fullmatch(r"COM\d+", clean_port):
            device_path = "\\\\.\\" + clean_port
        generic_read = 0x80000000
        generic_write = 0x40000000
        open_existing = 3
        handle = k32.CreateFileW(
            device_path, generic_read | generic_write, 0, None,
            open_existing, 0, None,
        )
        invalid_handle = ctypes.c_void_p(-1).value
        if handle == invalid_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle

        try:
            k32.SetupComm(handle, 65536, 65536)
            dcb = DCB()
            dcb.DCBlength = ctypes.sizeof(DCB)
            if not k32.GetCommState(handle, ctypes.byref(dcb)):
                raise ctypes.WinError(ctypes.get_last_error())
            dcb.BaudRate = baudrate
            dcb.Flags = 0x00000001  # fBinary=1; flow control, DTR and RTS disabled
            dcb.XonLim = 2048
            dcb.XoffLim = 512
            dcb.ByteSize = 8
            dcb.Parity = 0  # NOPARITY
            dcb.StopBits = 0  # ONESTOPBIT
            dcb.XonChar = b"\x11"
            dcb.XoffChar = b"\x13"
            dcb.ErrorChar = b"\x00"
            dcb.EofChar = b"\x00"
            dcb.EvtChar = b"\x00"
            if not k32.SetCommState(handle, ctypes.byref(dcb)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._set_timeouts(0.1)
            self.reset_input_buffer()
        except Exception:
            k32.CloseHandle(handle)
            self._closed = True
            raise

    def _set_timeouts(self, timeout: float) -> None:
        milliseconds = max(0, min(0xFFFFFFFE, int(timeout * 1000)))
        values = self._COMMTIMEOUTS(
            0xFFFFFFFF, 0xFFFFFFFF, milliseconds, 0, 10000,
        )
        if not self._kernel32.SetCommTimeouts(
            self._handle, self._ctypes.byref(values)
        ):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    @property
    def timeout(self) -> float:
        return getattr(self, "_timeout", 0.1)

    @timeout.setter
    def timeout(self, value: float) -> None:
        self._timeout = float(value)
        self._set_timeouts(self._timeout)

    def read(self, size: int) -> bytes:
        if self._closed:
            return b""
        buffer = self._ctypes.create_string_buffer(size)
        received = self._wintypes.DWORD()
        if not self._kernel32.ReadFile(
            self._handle, buffer, size,
            self._ctypes.byref(received), None,
        ):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return buffer.raw[:received.value]

    def write(self, data: bytes) -> int:
        total = 0
        view = memoryview(data)
        while total < len(view):
            chunk = bytes(view[total:total + 65536])
            sent = self._wintypes.DWORD()
            buffer = self._ctypes.create_string_buffer(chunk)
            if not self._kernel32.WriteFile(
                self._handle, buffer, len(chunk),
                self._ctypes.byref(sent), None,
            ):
                raise self._ctypes.WinError(self._ctypes.get_last_error())
            if sent.value == 0:
                raise OSError("Windows COM write returned zero bytes")
            total += sent.value
        return total

    def flush(self) -> None:
        if not self._kernel32.FlushFileBuffers(self._handle):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def reset_input_buffer(self) -> None:
        purge_rxabort = 0x0002
        purge_rxclear = 0x0008
        if not self._kernel32.PurgeComm(
            self._handle, purge_rxabort | purge_rxclear
        ):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self) -> None:
        if not self._closed:
            self._kernel32.CloseHandle(self._handle)
            self._closed = True


class RecoverySerial:
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._fd = None
        try:
            if os.name == "nt":
                self._serial = WindowsNativeSerial(port, baudrate)
                return
            import termios
            fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                import fcntl
                tioc_excl = getattr(termios, "TIOCEXCL", None)
                if tioc_excl is not None:
                    fcntl.ioctl(fd, tioc_excl)
            except OSError as exc:
                os.close(fd)
                raise Error(tr(
                    f"UART {port} занят другой программой: {exc}",
                    f"UART {port} is busy in another program: {exc}",
                )) from exc
            attrs = termios.tcgetattr(fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            self._fd = fd
        except Exception as exc:
            raise Error(f"не удалось открыть UART {port}: {exc}") from exc

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def read(self, size: int = 4096, timeout: float = 0.2) -> bytes:
        if self._serial is not None:
            old = self._serial.timeout
            self._serial.timeout = timeout
            try:
                return bytes(self._serial.read(size))
            finally:
                self._serial.timeout = old
        assert self._fd is not None
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return b""
        try:
            return os.read(self._fd, size)
        except BlockingIOError:
            return b""

    def write(self, data: bytes) -> None:
        if self._serial is not None:
            self._serial.write(data)
            self._serial.flush()
            return
        assert self._fd is not None
        view = memoryview(data)
        while view:
            _, writable, _ = select.select([], [self._fd], [], 10)
            if not writable:
                raise Error("UART write timeout")
            count = os.write(self._fd, view)
            view = view[count:]

    def reset_input(self) -> None:
        if self._serial is not None:
            self._serial.reset_input_buffer()
            return
        while self.read(4096, 0):
            pass


def _serial_port_sort_key(name: str) -> tuple[int, str]:
    match = re.fullmatch(r"COM(\d+)", name.upper())
    return (int(match.group(1)), name.upper()) if match else (10**9, name.upper())


def list_serial_ports() -> list[str]:
    if os.name == "nt":
        ports: set[str] = set()
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DEVICEMAP\SERIALCOMM",
            ) as key:
                index = 0
                while True:
                    try:
                        _, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    port = str(value).strip().upper()
                    if re.fullmatch(r"COM\d+", port):
                        ports.add(port)
                    index += 1
        except OSError:
            pass
        return sorted(ports, key=_serial_port_sort_key)
    patterns = ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS*")
    return sorted({item for pattern in patterns for item in glob.glob(pattern)})


def probe_serial_port(port: str) -> None:
    probe = RecoverySerial(port)
    try:
        probe.reset_input()
    finally:
        probe.close()


def recovery_dependency_preflight(*, require_ssh: bool = True) -> None:
    print("Проверяю программные зависимости recovery...")
    if os.name == "nt":
        print("[OK] COM/XMODEM: встроенный Win32-бэкенд, pyserial и pip не нужны.")
    if not require_ssh:
        print(tr(
            "[OK] BootROM backup: SSH не используется; UART управляет RAM shell, данные идут по TFTP.",
            "[OK] BootROM backup: SSH is not used; UART controls the RAM shell and data uses TFTP.",
        ))
        return
    try:
        ssh = ssh_executable()
    except Error as exc:
        if os.name == "nt":
            print("OpenSSH Client не установлен. Это компонент Windows, не Python-пакет.")
            print("Установка из PowerShell от администратора:")
            print("  Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0")
            answer = input("Открыть страницу 'Дополнительные компоненты Windows' сейчас? [Y/n]: ").strip().lower()
            if answer in ("", "y", "yes", "д", "да"):
                try:
                    os.startfile("ms-settings:optionalfeatures")  # type: ignore[attr-defined]
                except OSError:
                    pass
        raise Error(str(exc) + "; установите компонент и снова запустите recovery") from exc
    print(f"[OK] OpenSSH client: {ssh}")


def _uart_log_write(log, data: bytes, echo: bool = True) -> None:
    if data:
        log.write(data)
        log.flush()
        if echo:
            print(data.decode("utf-8", "replace"), end="", flush=True)


def wait_bootrom_xmodem(serial_port: RecoverySerial, log, phase: str, timeout: int = 180, *, discard_stale: bool = True) -> None:
    print(tr(
        f"\nОжидание BootROM XMODEM для {phase}. Символ C означает готовность приёмника.",
        f"\nWaiting for BootROM XMODEM for {phase}. Character C means the receiver is ready.",
    ))
    # Between XMODEM stages, discard stale ACK/C bytes left by the preceding
    # transfer.  For the *first* BootROM wait this must be disabled: the router
    # may already be printing ``Press x`` / ``C`` while the operator has both
    # hands on Reset and power, and flushing RX here can throw away the exact
    # readiness indication we are trying to auto-detect.
    if discard_stale:
        serial_port.reset_input()
    deadline = time.time() + timeout
    c_count = 0
    text_tail = b""
    press_x_seen = False
    last_x = 0.0
    while time.time() < deadline:
        data = serial_port.read(4096, 0.5)
        if data:
            _uart_log_write(log, data)
            text_tail = (text_tail + data)[-4096:]
            if b"press x" in text_tail.lower():
                press_x_seen = True
        now = time.time()
        if press_x_seen and c_count == 0 and now - last_x >= 2.0:
            print(tr("\n[UART] Найдено Press x; отправляю x.", "\n[UART] Press x detected; sending x."))
            serial_port.write(b"x")
            last_x = now
        for byte in data:
            if byte == 0x43:
                c_count += 1
                if c_count >= 3:
                    print(tr(
                        f"\n[UART] BootROM выдаёт C: готов к XMODEM ({phase}).",
                        f"\n[UART] BootROM is sending C and is ready for XMODEM ({phase}).",
                    ))
                    return
            elif byte in (9, 10, 13, 32) or byte < 0x20:
                continue
            else:
                c_count = 0
    raise Error(tr(
        f"тайм-аут: BootROM не перешёл в XMODEM для {phase}",
        f"timeout: BootROM did not enter XMODEM for {phase}",
    ))


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def xmodem_send(serial_port: RecoverySerial, path: Path, label: str, log) -> None:
    SOH, EOT, ACK, NAK, CAN = 0x01, 0x04, 0x06, 0x15, 0x18
    size = path.stat().st_size
    total_blocks = (size + 127) // 128
    serial_port.reset_input()
    sequence = 1
    sent = 0
    try:
        with path.open("rb") as fh:
            for index in range(total_blocks):
                payload = fh.read(128)
                payload += b"\x1a" * (128 - len(payload))
                crc = crc16_xmodem(payload)
                packet = bytes((SOH, sequence, 0xFF - sequence)) + payload + struct.pack(">H", crc)
                accepted = False
                for attempt in range(1, 11):
                    serial_port.write(packet)
                    deadline = time.time() + 12
                    cancel_count = 0
                    while time.time() < deadline:
                        response = serial_port.read(256, 0.4)
                        if not response:
                            continue
                        _uart_log_write(log, response, echo=False)
                        for byte in response:
                            if byte == ACK:
                                accepted = True
                                break
                            if byte == CAN:
                                cancel_count += 1
                                if cancel_count >= 2:
                                    raise Error(f"BootROM отменил XMODEM {label}")
                            if byte in (NAK, 0x43):
                                break
                        if accepted or NAK in response:
                            break
                    if accepted:
                        break
                    print(f"\n[XMODEM] Повтор блока {index + 1}/{total_blocks}, попытка {attempt}/10")
                if not accepted:
                    raise Error(f"XMODEM {label}: блок {index + 1} не подтверждён")
                sent += min(128, size - index * 128)
                sequence = (sequence + 1) & 0xFF
                if index == 0 or (index + 1) % 32 == 0 or index + 1 == total_blocks:
                    print(f"\r[XMODEM] {label}: {sent}/{size} байт ({index + 1}/{total_blocks} блоков)", end="", flush=True)
        for _ in range(10):
            serial_port.write(bytes((EOT,)))
            deadline = time.time() + 10
            while time.time() < deadline:
                response = serial_port.read(64, 0.4)
                if response:
                    _uart_log_write(log, response, echo=False)
                if ACK in response:
                    print(f"\n[XMODEM] {label} передан и подтверждён.")
                    return
                if NAK in response:
                    break
        raise Error(f"XMODEM {label}: EOT не подтверждён")
    except BaseException:
        # Abort the peer-side receiver explicitly. Without CAN, BootROM can remain
        # inside the current XMODEM session and make the next wizard run ambiguous.
        try:
            serial_port.write(bytes((CAN, CAN, CAN)))
        except Exception:
            pass
        raise


def _uboot_prompt_present(data: bytes) -> bool:
    """Return True when a real interactive RAM U-Boot prompt is visible.

    AN7581 Nokia builds commonly use ``AN7581>`` while the AN7583 OpenWrt
    reference U-Boot used by MF recovery has been hardware-observed to use
    ``U-Boot>``.  During prompt acquisition a Ctrl-C can already be in flight,
    so accept ``<INTERRUPT>`` immediately after the prompt as well and stop
    sending breaks at once.
    """
    tail = data[-2048:]
    named = re.search(
        rb"(?:^|[\r\n])(?:AN7581|AN7583|U-Boot)>[ \t]*(?=$|[\r\n]|<INTERRUPT>)",
        tail,
    )
    if named is not None:
        return True
    # Generic fallback for U-Boot builds that use the default ``=>`` prompt.
    # Keep the same line-boundary requirement to avoid matching arrows in
    # ordinary command output.
    return re.search(
        rb"(?:^|[\r\n])=>[ \t]*(?=$|[\r\n]|<INTERRUPT>)",
        tail,
    ) is not None


def _uboot_send_break(serial_port: RecoverySerial, menu_visible: bool = False) -> None:
    """Interrupt autoboot without sending CR/LF.

    RC14 periodically sent Enter while waiting for the prompt. With the Airoha
    boot menu, Enter selects the highlighted "Run default boot command" item.
    RC15 sends Ctrl-C and ESC instead: Ctrl-C interrupts a running command and
    ESC exits bootmenu. Neither selects a menu entry.
    """
    serial_port.write(b"\x03")
    if menu_visible:
        serial_port.write(b"\x1b")


def _uboot_wait_quiet(serial_port: RecoverySerial, log, quiet: float = 0.45, timeout: float = 4.0) -> bytes:
    """Drain late UART output until U-Boot has been quiet for ``quiet`` seconds.

    This is important after autoboot interception: Ctrl-C bytes already accepted by
    the router can still produce additional prompts even after the first prompt was
    seen.  No new break is sent here.
    """
    deadline = time.time() + timeout
    quiet_deadline = time.time() + quiet
    transcript = bytearray()
    while time.time() < deadline:
        data = serial_port.read(4096, min(0.10, max(0.01, quiet_deadline - time.time())))
        if data:
            _uart_log_write(log, data)
            transcript.extend(data)
            quiet_deadline = time.time() + quiet
            continue
        if time.time() >= quiet_deadline:
            break
    return bytes(transcript)


def wait_uboot_prompt(serial_port: RecoverySerial, log, timeout: int = 180) -> str:
    """Acquire deterministic control of RAM U-Boot.

    Break traffic starts only when U-Boot itself becomes visible (banner/menu), never
    while BL31/U-Boot is still initializing.  A paced Ctrl-C/ESC series continues until a prompt
    appears, the UART must remain quiet before commands are allowed.  This avoids
    the hardware-observed AN7583 failure where queued Ctrl-C bytes kept generating
    ``U-Boot>`` prompts and corrupted the first scripted command.
    """
    print("\nОжидаю U-Boot, запущенный из RAM, и останавливаю автоматическую загрузку...")
    print("[UART][UBOOT_SYNC] До banner UART не трогаю; после banner посылаю paced Ctrl-C до prompt. После prompt требуется тишина UART.")
    deadline = time.time() + timeout
    tail = b""
    uboot_seen = False
    menu_visible = False
    break_sent = False
    menu_break_sent = False
    production_break_sent = False
    last_break_at = 0.0
    break_count = 0

    while time.time() < deadline:
        data = serial_port.read(4096, 0.12)
        if data:
            _uart_log_write(log, data)
            tail = (tail + data)[-32768:]
            low = tail.lower()

            if _uboot_prompt_present(tail):
                # Do not return on the first prompt immediately.  Let any Ctrl-C
                # already received by the router drain and require a quiet console.
                _uboot_wait_quiet(serial_port, log, quiet=0.45, timeout=4.0)
                serial_port.reset_input()
                print("\n[UART][UBOOT_PROMPT] Получено устойчивое приглашение U-Boot; очередь break очищена, загрузка с NAND не запускалась.")
                return "prompt"

            if b"u-boot 20" in low or b"hit any key to stop autoboot" in low:
                if not uboot_seen:
                    print("\n[UART][UBOOT_BANNER] Обнаружен RAM U-Boot; начинаю страховочную серию Ctrl-C до устойчивого prompt.")
                uboot_seen = True
                if not break_sent:
                    _uboot_send_break(serial_port)
                    break_sent = True
                    last_break_at = time.time()
                    break_count = 1

            if (b"press up/down to move" in low or
                    b"run default boot command" in low or
                    b"boot system via tftp" in low):
                if not menu_visible:
                    print("\n[UART][UBOOT_MENU] Меню U-Boot обнаружено; отправляю Ctrl-C+ESC один раз, не Enter.")
                uboot_seen = True
                menu_visible = True
                if not menu_break_sent:
                    _uboot_send_break(serial_port, menu_visible=True)
                    menu_break_sent = True
                    break_sent = True

            if (b"read " in low and b" bytes from volume fit" in low) or b"## checking image at" in low:
                if not production_break_sent:
                    print("\n[UART][UBOOT_NAND_BOOT] Началось чтение production FIT; отправляю аварийный Ctrl-C один раз.")
                    _uboot_send_break(serial_port)
                    production_break_sent = True
                uboot_seen = True

            if uboot_seen and not _uboot_prompt_present(tail) and time.time() - last_break_at >= 0.20 and break_count < 40:
                _uboot_send_break(serial_port, menu_visible=menu_visible)
                last_break_at = time.time()
                break_count += 1

            if uboot_seen and (b"erasing 0x" in low or b"mtd erase ubi" in low):
                raise Error(tr(
                    "RAM U-Boot начал destructive autoboot до доказанного prompt. Этот FIP запрещён для recovery; NAND capability не выдавалась.",
                    "RAM U-Boot started destructive autoboot before a proven prompt. This FIP is forbidden for recovery; NAND capability was never granted.",
                ))

            if b"starting kernel" in low or b"booting linux on physical cpu" in low:
                print("\n[UART][PRODUCTION_FALLBACK] Обычная OpenWrt уже начала загрузку; продолжу через SSH и аварийный RAM-образ без повторного XMODEM.")
                return "production"

            if b"press x to load bl31" in low and not uboot_seen:
                raise Error("после передачи FIP устройство вернулось в BootROM вместо RAM U-Boot")

    raise Error("U-Boot prompt не появился после передачи FIP; autoboot не считается успешно перехваченным")


def _uboot_send_line(serial_port: RecoverySerial, line: str) -> None:
    """Send one U-Boot command as an isolated, paced UART line."""
    if not line or any(ch in line for ch in "\r\n"):
        raise Error("внутренняя ошибка: некорректная строка U-Boot-команды")
    encoded = line.encode("ascii")
    # Small chunks make the command path tolerant of shallow UART RX FIFOs and
    # keep CR separate from the payload.  The cost is negligible next to NAND/TFTP.
    for offset in range(0, len(encoded), 16):
        serial_port.write(encoded[offset:offset + 16])
        time.sleep(0.003)
    time.sleep(0.010)
    serial_port.write(b"\r")


def _uboot_read_until_prompt(serial_port: RecoverySerial, log, timeout: int, command: str) -> bytes:
    """Collect output generated after one command until a fresh prompt returns."""
    deadline = time.time() + timeout
    transcript = bytearray()
    while time.time() < deadline:
        data = serial_port.read(4096, 0.2)
        if not data:
            continue
        _uart_log_write(log, data)
        transcript.extend(data)
        if len(transcript) > 524288:
            del transcript[:-262144]
        raw = bytes(transcript)
        if b"starting kernel" in raw.lower() or b"booting linux on physical cpu" in raw.lower():
            raise Error(f"U-Boot command unexpectedly started Linux: {command}")
        if _uboot_prompt_present(raw):
            return raw
    raise Error(f"тайм-аут U-Boot-команды или prompt не вернулся: {command}")


def uboot_command(serial_port: RecoverySerial, log, command: str, timeout: int = 30) -> bytes:
    """Run one U-Boot command, then query its return code on a separate line.

    Do not chain ``command; echo marker``.  Real AN7583 hardware showed the first
    scripted line being corrupted after prompt acquisition.  Each command now gets
    its own CR-terminated line and prompt; only then is ``$?`` queried separately.
    """
    marker = f"__MEDVEFLASHER_RESTORE_{time.time_ns():x}__"
    print(f"[U-Boot] {command}")

    # There must be no leftover prompt/break traffic before the next command.
    _uboot_wait_quiet(serial_port, log, quiet=0.18, timeout=1.0)
    serial_port.reset_input()
    _uboot_send_line(serial_port, command)
    command_transcript = _uboot_read_until_prompt(serial_port, log, timeout, command)

    status_line = f"echo {marker}_RC_$?"
    _uboot_wait_quiet(serial_port, log, quiet=0.10, timeout=0.5)
    serial_port.reset_input()
    _uboot_send_line(serial_port, status_line)
    status_transcript = _uboot_read_until_prompt(serial_port, log, 10, f"status for {command}")

    marker_bytes = re.escape(marker.encode("ascii"))
    match = re.search(marker_bytes + rb"_RC_([0-9]+)(?:[\r\n]|$)", status_transcript)
    if match is None:
        raise Error(f"U-Boot не вернул код завершения отдельной status-командой: {command}")
    rc = int(match.group(1))
    if rc != 0:
        raise Error(f"U-Boot-команда завершилась с кодом {rc}: {command}")
    return command_transcript + status_transcript


def prove_recovery_safe_uboot(serial_port: RecoverySerial, log) -> None:
    """Grant recovery capabilities only to the RC18 SAFE RAM U-Boot.

    A banner or visual prompt is not sufficient.  The release-pinned BL33 must
    expose the compiled SAFE marker, negative bootdelay and inert bootcmd.  A
    fresh nonce command then proves that the PC owns the interactive prompt.
    Until this function returns, callers must not issue any NAND write/erase or
    saveenv command.
    """
    print(tr(
        "[GATE] Проверяю RC18 RECOVERY_SAFE BL33 до любых NAND-capability...",
        "[GATE] Proving the RC18 RECOVERY_SAFE BL33 before any NAND capability...",
    ))
    transcript = uboot_command(
        serial_port, log,
        "printenv medveflasher_recovery_safe bootdelay bootcmd preboot",
        timeout=20,
    )
    required = (
        rb"(?:^|[\r\n])medveflasher_recovery_safe=rc18(?:[\r\n]|$)",
        rb"(?:^|[\r\n])bootdelay=-1(?:[\r\n]|$)",
        rb"(?:^|[\r\n])bootcmd=echo RECOVERY_SAFE_RC18(?:[\r\n]|$)",
    )
    if not all(re.search(pattern, transcript) for pattern in required):
        raise Error(tr(
            "RAM U-Boot prompt найден, но RC18 RECOVERY_SAFE marker/bootdelay/bootcmd не доказаны; NAND write/erase запрещены.",
            "The RAM U-Boot prompt exists, but the RC18 RECOVERY_SAFE marker/bootdelay/bootcmd were not proven; NAND write/erase is blocked.",
        ))
    nonce = f"MEDVEFLASHER_RC18_PROMPT_{time.time_ns():x}"
    proof = uboot_command(serial_port, log, f"echo {nonce}", timeout=15)
    if re.search(rb"(?:^|[\r\n])" + re.escape(nonce.encode("ascii")) + rb"(?:[\r\n]|$)", proof) is None:
        raise Error(tr(
            "не удалось доказать владение интерактивным U-Boot prompt по nonce; NAND capability заблокирована",
            "failed to prove ownership of the interactive U-Boot prompt with a nonce; NAND capability is blocked",
        ))
    print(tr(
        "[OK][CAP_GATE] RC18 RECOVERY_SAFE BL33 + устойчивый prompt доказаны. Read-only geometry разрешена; NAND write остаётся gated дальнейшими проверками.",
        "[OK][CAP_GATE] RC18 RECOVERY_SAFE BL33 + stable prompt proven. Read-only geometry is allowed; NAND write remains gated by subsequent checks.",
    ))


def wait_recovery_kernel_layout(serial_port: RecoverySerial, log, timeout: int = 180) -> None:
    """Require the recovery DT's all_flash/bl2/ibu layout before using SSH."""
    deadline = time.time() + timeout
    tail = b""
    saw_kernel = False
    while time.time() < deadline:
        data = serial_port.read(4096, 0.25)
        if not data:
            continue
        _uart_log_write(log, data)
        tail = (tail + data)[-65536:]
        low = tail.lower()
        if b"starting kernel" in low:
            saw_kernel = True
        if re.search(rb'0x[0-9a-f]+-0x[0-9a-f]+\s+:\s+"ibu"', low):
            print("\n[UART][RECOVERY_LAYOUT] Подтверждена разметка системы восстановления: mtd2=ibu.")
            return
        if saw_kernel and re.search(rb'0x[0-9a-f]+-0x[0-9a-f]+\s+:\s+"ubi"', low):
            raise Error(tr(
                    "после bootm загрузилась production OpenWrt (mtd2=ubi), а не безопасная recovery-initramfs (mtd2=ibu)",
                    "production OpenWrt booted after bootm (mtd2=ubi), not the safe recovery initramfs (mtd2=ibu)",
                ))
        if _uboot_prompt_present(tail) and b"bad" in low:
            raise Error(tr(
                "bootm recovery FIT вернулся в U-Boot с ошибкой",
                "bootm of the recovery FIT returned to U-Boot with an error",
            ))
    raise Error("ядро recovery стартовало, но UART не подтвердил безопасную MTD-разметку mtd2=ibu")


def serve_uboot_recovery_fit(serial_port: RecoverySerial, log, local_ip: str, router_ip: str) -> None:
    name = "nokia-stock-recovery-initramfs.itb"
    ready = threading.Event()
    result = TftpResult()
    thread = threading.Thread(
        target=serve_tftp_get,
        args=(local_ip, 69, RECOVERY_INITRAMFS, name, router_ip, ready, result),
        kwargs={"timeout": 300, "maximum_block_size": 1468},
        daemon=True,
    )
    thread.start()
    if not ready.wait(10):
        raise Error("TFTP recovery server не запустился")
    if result.error:
        raise Error(f"TFTP recovery server: {result.error}")

    # Every setup command must complete and return to the prompt. This prevents
    # command concatenation when the serial console or U-Boot is still busy.
    uboot_command(serial_port, log, "setenv ethaddr 02:00:00:04:0d:10")
    uboot_command(serial_port, log, "setenv eth1addr 02:00:00:04:0d:11")
    uboot_command(serial_port, log, f"setenv ipaddr {router_ip}")
    uboot_command(serial_port, log, f"setenv serverip {local_ip}")
    uboot_command(serial_port, log, "setenv netmask 255.255.255.0")

    transcript = uboot_command(serial_port, log, f"tftpboot 0x90000000 {name}", timeout=360)
    thread.join(10)
    if thread.is_alive():
        raise Error("TFTP recovery FIT не завершился после возврата U-Boot prompt")
    if result.error:
        raise Error(f"TFTP recovery FIT: {result.error}")
    if result.bytes_transferred != RECOVERY_INITRAMFS.stat().st_size:
        raise Error("TFTP recovery FIT передан не полностью")
    if b"bytes transferred" not in transcript.lower() and b"done" not in transcript.lower():
        raise Error("TFTP передан сервером, но U-Boot не подтвердил успешную загрузку FIT")
    print(tr(
        f"[TFTP] recovery FIT передан и подтверждён U-Boot: {result.bytes_transferred} байт",
        f"[TFTP] Recovery FIT transferred and confirmed by U-Boot: {result.bytes_transferred} bytes",
    ))

    info = uboot_command(serial_port, log, "iminfo 0x90000000", timeout=60)
    low_info = info.lower()
    if b"fit image found" not in low_info or b"bad" in low_info:
        raise Error("iminfo не подтвердил корректный recovery FIT; bootm запрещён")
    print("[U-Boot] iminfo подтвердил recovery FIT; запускаю только RAM-образ.")
    serial_port.write(b"bootm 0x90000000\r")
    wait_recovery_kernel_layout(serial_port, log, timeout=240)


def uboot_command_with_progress(serial_port: RecoverySerial, log, command: str, timeout: int, label_ru: str, label_en: str) -> bytes:
    holder: dict[str, object] = {}
    def worker() -> None:
        try:
            holder["value"] = uboot_command(serial_port, log, command, timeout=timeout)
        except BaseException as exc:
            holder["error"] = exc
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    started = time.time()
    last = -15
    while thread.is_alive():
        elapsed = int(time.time() - started)
        if elapsed >= last + 15:
            print(tr(f"[WAIT] {label_ru}: прошло {elapsed}s...", f"[WAIT] {label_en}: elapsed {elapsed}s..."))
            last = elapsed
        thread.join(1)
    if "error" in holder:
        raise holder["error"]  # type: ignore[misc]
    return holder["value"]  # type: ignore[return-value]


def _file_crc32(path: Path) -> str:
    value = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            value = zlib.crc32(chunk, value)
    return f"{value & 0xffffffff:08x}"


def _uboot_require_crc32(transcript: bytes, expected_crc: str, label: str) -> None:
    expected = expected_crc.lower().encode("ascii")
    # U-Boot prints e.g. "CRC32 for 90000000 ... ==> deadbeef".  The
    # command itself does not contain the expected checksum, so an exact
    # 8-hex token match cannot be satisfied by UART echo alone.
    tokens = re.findall(rb"(?i)(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])", transcript)
    if expected not in [token.lower() for token in tokens]:
        raise Error(f"U-Boot CRC32 не совпал для {label}: ожидается {expected_crc}")


def _uboot_tftp_load(serial_port: RecoverySerial, log, local_ip: str, router_ip: str,
                      source: Path, remote_name: str, expected_sha: str) -> None:
    for attempt in range(1, 4):
        ready = threading.Event()
        result = TftpResult()
        thread = threading.Thread(
            target=serve_tftp_get,
            args=(local_ip, 69, source, remote_name, router_ip, ready, result),
            kwargs={"timeout": 180, "maximum_block_size": 1468}, daemon=True,
        )
        thread.start()
        if not ready.wait(10):
            raise Error("не удалось запустить TFTP/69")
        if result.error:
            raise Error(f"TFTP/69: {result.error}")
        transcript = uboot_command(serial_port, log, f"tftpboot 0x{UBOOT_LOAD_ADDRESS:x} {remote_name}", timeout=240)
        thread.join(10)
        if (not thread.is_alive() and not result.error and
                result.bytes_transferred == source.stat().st_size and
                (b"bytes transferred" in transcript.lower() or b"done" in transcript.lower())):
            if sha_file(source).lower() != expected_sha.lower():
                raise Error(f"PC SHA256 исходного файла изменился перед TFTP: {remote_name}")
            expected_crc = _file_crc32(source)
            digest = uboot_command(
                serial_port, log,
                f"crc32 0x{UBOOT_LOAD_ADDRESS:x} 0x{source.stat().st_size:x}",
                timeout=120,
            )
            _uboot_require_crc32(digest, expected_crc, remote_name)
            return
        print(tr(
            f"TFTP {remote_name} не завершился, повтор {attempt}/3.",
            f"TFTP {remote_name} did not complete, retry {attempt}/3.",
        ))
        if thread.is_alive():
            thread.join(190)
    raise Error(f"не удалось передать {remote_name} в RAM U-Boot")



def _parse_uboot_bad_blocks(transcript: bytes, partition: str, partition_size: int,
                            erase_size: int = UBOOT_ERASE_SIZE) -> list[int]:
    """Parse `mtd bad <partition>` without trusting echoed commands/nonces."""
    offsets: list[int] = []
    text = transcript.decode("utf-8", errors="replace")
    for line in text.splitlines():
        match = re.fullmatch(r"\s*0x([0-9a-fA-F]+)\s*", line)
        if not match:
            continue
        offset = int(match.group(1), 16)
        if offset < 0 or offset >= partition_size or offset % erase_size:
            raise Error(
                f"mtd bad {partition}: некорректное смещение bad block 0x{offset:x}; "
                "запись NAND запрещена"
            )
        offsets.append(offset)
    if len(offsets) != len(set(offsets)):
        raise Error(f"mtd bad {partition}: повторяющиеся bad-block offsets; запись NAND запрещена")
    return sorted(offsets)


def _uboot_bad_blocks(serial_port: RecoverySerial, log, partition: str,
                      partition_size: int) -> list[int]:
    transcript = uboot_command(serial_port, log, f"mtd bad {partition}", timeout=180)
    return _parse_uboot_bad_blocks(transcript, partition, partition_size)


def _validate_stock_ubi_bad_blocks(offsets: list[int]) -> None:
    """Allow bad blocks only where stock uses UBI-backed mutable storage.

    Offsets are relative to the RAM-U-Boot `ubi` partition, whose physical base
    is 0x20000. A block beyond the canonical stock mtd16 span is irrelevant to
    the restored stock image and is therefore allowed to remain bad/erased.
    """
    unsafe: list[int] = []
    for offset in offsets:
        if offset >= STOCK_IBU_SIZE:
            continue
        if STOCK_BADBLOCK_SAFE_UBI_START <= offset < STOCK_BADBLOCK_SAFE_UBI_END:
            continue
        unsafe.append(offset)
    if unsafe:
        rendered = ", ".join(f"ubi+0x{x:08x}/phys=0x{x + STOCK_BL2_SIZE:08x}" for x in unsafe)
        raise Error(tr(
            "Обнаружены bad blocks в raw-critical stock-области: " + rendered + ". "
            "OpenWrt RAM U-Boot не доказывает stock BMT mapping для этих адресов; "
            "автоматический restore остановлен fail-closed до записи BL2.",
            "Bad blocks were found in a raw-critical stock region: " + rendered + ". "
            "The OpenWrt RAM U-Boot does not prove stock BMT mapping for these addresses; "
            "automatic restore is stopped fail-closed before BL2 is written.",
        ))


def _chunk_good_spans(offset: int, size: int, bad_blocks: list[int],
                      erase_size: int = UBOOT_ERASE_SIZE) -> list[tuple[int, int]]:
    """Return absolute good NAND spans inside one physical-image chunk."""
    end = offset + size
    cursor = offset
    spans: list[tuple[int, int]] = []
    for bad in bad_blocks:
        if bad < offset or bad >= end:
            continue
        if bad > cursor:
            spans.append((cursor, bad - cursor))
        cursor = max(cursor, bad + erase_size)
    if cursor < end:
        spans.append((cursor, end - cursor))
    return spans


def _file_crc32_range(path: Path, offset: int, size: int) -> str:
    value = 0
    remaining = size
    with path.open("rb") as fh:
        fh.seek(offset)
        while remaining:
            chunk = fh.read(min(1024 * 1024, remaining))
            if not chunk:
                raise Error(f"неожиданный EOF при CRC32 диапазона {path.name} 0x{offset:x}+0x{size:x}")
            value = zlib.crc32(chunk, value)
            remaining -= len(chunk)
    return f"{value & 0xffffffff:08x}"


def _uboot_restore_physical_chunk(serial_port: RecoverySerial, log, chunk: dict,
                                  bad_blocks: list[int], index: int, total_chunks: int) -> None:
    """Write/readback a physical mtd16-derived IBU chunk without crossing bad PEBs."""
    offset = int(chunk["offset"])
    size = int(chunk["size"])
    path = Path(chunk["file"])
    spans = _chunk_good_spans(offset, size, bad_blocks)
    bad_here = [x for x in bad_blocks if offset <= x < offset + size]
    print(tr(
        f"[IBU {index}/{total_chunks}] Физическое смещение ubi+0x{offset:08x}, размер 0x{size:x}",
        f"[IBU {index}/{total_chunks}] Physical offset ubi+0x{offset:08x}, size 0x{size:x}",
    ))
    if bad_here:
        rendered = ", ".join(f"0x{x:08x}" for x in bad_here)
        print(tr(
            f"[BADBLOCK] IBU {index}/{total_chunks}: пропускаю {len(bad_here)} bad eraseblock(s) "
            f"без сдвига соседних данных: {rendered}",
            f"[BADBLOCK] IBU {index}/{total_chunks}: skipping {len(bad_here)} bad eraseblock(s) "
            f"without shifting adjacent data: {rendered}",
        ))
    if not spans and size:
        raise Error(f"IBU {index}: весь chunk попал в bad blocks; restore заблокирован")
    for span_index, (span_offset, span_size) in enumerate(spans, 1):
        local = span_offset - offset
        ram = UBOOT_LOAD_ADDRESS + local
        write_out = uboot_command_with_progress(
            serial_port, log,
            f"mtd write ubi 0x{ram:x} 0x{span_offset:x} 0x{span_size:x}",
            600,
            f"запись IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
            f"writing IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
        )
        low = write_out.lower()
        if b"skipping bad block" in low or b"skip bad block" in low or b"new bad block" in low:
            raise Error(tr(
                f"IBU {index}: во время записи появился новый bad block; BL2 не будет записан. "
                "Повторный restore разрешён только с новым bad-block scan после полного erase ubi.",
                f"IBU {index}: a new bad block appeared during write; BL2 will not be written. "
                "A retry is allowed only after a fresh bad-block scan and a full ubi erase.",
            ))
        uboot_command(serial_port, log, f"mw.b 0x{ram:x} 0x00 0x{span_size:x}", timeout=120)
        readback = uboot_command_with_progress(
            serial_port, log,
            f"mtd read ubi 0x{ram:x} 0x{span_offset:x} 0x{span_size:x}",
            600,
            f"чтение IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
            f"reading IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
        )
        low = readback.lower()
        if b"error" in low or b"failed" in low or b"failure while reading" in low:
            raise Error(f"U-Boot сообщил ошибку чтения IBU {index}, good-span {span_index}")
        expected_crc = _file_crc32_range(path, local, span_size)
        digest = uboot_command_with_progress(
            serial_port, log,
            f"crc32 0x{ram:x} 0x{span_size:x}",
            180,
            f"CRC32 IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
            f"CRC32 IBU {index}/{total_chunks}, good-span {span_index}/{len(spans)}",
        )
        _uboot_require_crc32(digest, expected_crc, f"IBU {index} good-span {span_index}")


def perform_stock_restore_in_uboot(serial_port: RecoverySerial, log, local_ip: str, router_ip: str,
                                    payload_dir: Path, manifest: dict) -> None:
    """Restore stock directly from RAM U-Boot, with no Linux recovery stage."""
    print(tr(
        "\nШтатная прошивка будет восстановлена непосредственно из U-Boot, запущенного в оперативной памяти.",
        "\nStock firmware will be restored directly from U-Boot running in memory.",
    ))
    print(tr(
        "Основная область NAND будет очищена целиком. Данные передаются блоками по 8 MiB, но запись разбивается по физическим good-span и никогда не пересекает известный bad eraseblock. Каждый good-span проверяется чтением обратно. Точный stock BL2 записывается последним без смещения 0x800.",
        "The main NAND area will be erased completely. Data is transferred in 8 MiB chunks, but writes are split into physical good spans and never cross a known bad eraseblock. Every good span is read back. The exact stock BL2 is written last without a 0x800 offset.",
    ))

    listing = uboot_command(serial_port, log, "mtd list", timeout=60)
    low = listing.lower()
    required_layout = (
        b'block size: 0x20000 bytes',
        b'0x000000000000-0x000000020000 : "bl2"',
        b'0x000000020000-0x000010000000 : "ubi"',
    )
    if not all(marker in low for marker in required_layout):
        raise Error(tr(
            "RAM U-Boot не показал точную геометрию bl2=0x20000, ubi=0xffe0000, erase=0x20000; запись запрещена",
            "RAM U-Boot did not report the exact bl2=0x20000, ubi=0xffe0000, erase=0x20000 geometry; writing is blocked",
        ))

    bl2_bad = _uboot_bad_blocks(serial_port, log, "bl2", STOCK_BL2_SIZE)
    if bl2_bad:
        raise Error(tr(
            "BL2 eraseblock помечен bad; автоматический stock restore запрещён до любых erase/write.",
            "The BL2 eraseblock is marked bad; automatic stock restore is blocked before any erase/write.",
        ))
    pre_erase_bad = _uboot_bad_blocks(serial_port, log, "ubi", PHYSICAL_NAND_SIZE - STOCK_BL2_SIZE)
    _validate_stock_ubi_bad_blocks(pre_erase_bad)
    if pre_erase_bad:
        rendered = ", ".join(f"0x{x:08x}" for x in pre_erase_bad)
        print(tr(
            f"[BADBLOCK] До erase обнаружено {len(pre_erase_bad)} bad eraseblock(s) в ubi: {rendered}",
            f"[BADBLOCK] Before erase, {len(pre_erase_bad)} bad eraseblock(s) were found in ubi: {rendered}",
        ))
    else:
        print(tr("[OK] До erase bad blocks в ubi не обнаружены.", "[OK] No bad blocks were found in ubi before erase."))

    uboot_command(serial_port, log, "setenv ethaddr 02:00:00:04:0d:10")
    uboot_command(serial_port, log, "setenv eth1addr 02:00:00:04:0d:11")
    uboot_command(serial_port, log, f"setenv ipaddr {router_ip}")
    uboot_command(serial_port, log, f"setenv serverip {local_ip}")
    uboot_command(serial_port, log, "setenv netmask 255.255.255.0")
    uboot_command(serial_port, log, "setenv autoload no")

    chunks = prepare_uboot_restore_chunks(payload_dir, manifest)
    print(tr(f"Подготавливаю {len(chunks)} проверяемых блоков stock IBU...", f"Preparing {len(chunks)} verifiable stock IBU chunks..."))
    first = chunks[0]
    print(tr("Сначала проверяю TFTP и первый блок, пока NAND ещё не изменена.", "Testing TFTP and the first chunk before changing NAND."))
    _uboot_tftp_load(serial_port, log, local_ip, router_ip, first["file"], first["remote_name"], first["sha256"])

    print(tr("\nВНИМАНИЕ: следующая команда начнёт восстановление исходной разметки stock NAND.", "\nWARNING: the next command starts restoration of the original stock NAND layout."))
    print(tr("Не отключайте питание. После очистки ubi устройство сможет загрузиться только после полного завершения этой процедуры.", "Do not remove power. After erasing ubi, the device can boot only after this procedure completes."))
    confirm = input(tr("Введите точно RESTORE STOCK BACKUP: ", "Type exactly RESTORE STOCK BACKUP: ")).strip()
    if confirm != "RESTORE STOCK BACKUP":
        raise Error(tr("восстановление stock отменено", "stock restoration cancelled"))

    print(tr("[1/3] Полностью очищаю раздел ubi, чтобы удалить остатки all-in-UBI за концом stock-образа.", "[1/3] Erasing the complete ubi partition to remove all-in-UBI remnants beyond the stock image."))
    uboot_command_with_progress(serial_port, log, "mtd erase ubi", 1200, "стирание ubi", "erasing ubi")

    post_erase_bad = _uboot_bad_blocks(serial_port, log, "ubi", PHYSICAL_NAND_SIZE - STOCK_BL2_SIZE)
    _validate_stock_ubi_bad_blocks(post_erase_bad)
    if not set(pre_erase_bad).issubset(post_erase_bad):
        raise Error(tr(
            "Bad-block map после erase потерял ранее отмеченный блок; запись IBU запрещена.",
            "The bad-block map lost a previously marked block after erase; IBU writing is blocked.",
        ))
    added = sorted(set(post_erase_bad) - set(pre_erase_bad))
    if added:
        rendered = ", ".join(f"0x{x:08x}" for x in added)
        print(tr(
            f"[BADBLOCK] Erase обнаружил новые bad eraseblock(s): {rendered}. Карта пересчитана до первой записи IBU.",
            f"[BADBLOCK] Erase discovered new bad eraseblock(s): {rendered}. The map was rebuilt before the first IBU write.",
        ))

    print(tr(
        "[2/3] Записываю физические диапазоны mtd16 без пересечения bad blocks и проверяю каждый good-span чтением/CRC32.",
        "[2/3] Writing physical mtd16 ranges without crossing bad blocks and verifying every good span by readback/CRC32.",
    ))
    for index, chunk in enumerate(chunks):
        if index != 0:
            _uboot_tftp_load(serial_port, log, local_ip, router_ip, chunk["file"], chunk["remote_name"], chunk["sha256"])
        _uboot_restore_physical_chunk(serial_port, log, chunk, post_erase_bad, index + 1, len(chunks))

    final_bad = _uboot_bad_blocks(serial_port, log, "ubi", PHYSICAL_NAND_SIZE - STOCK_BL2_SIZE)
    if final_bad != post_erase_bad:
        added = sorted(set(final_bad) - set(post_erase_bad))
        removed = sorted(set(post_erase_bad) - set(final_bad))
        detail = []
        if added:
            detail.append("new=" + ",".join(f"0x{x:08x}" for x in added))
        if removed:
            detail.append("missing=" + ",".join(f"0x{x:08x}" for x in removed))
        raise Error(tr(
            "Bad-block map изменился во время IBU write/readback (" + "; ".join(detail) + "); "
            "BL2 остаётся нетронутым. Требуется новый полный restore с новой картой bad blocks.",
            "The bad-block map changed during IBU write/readback (" + "; ".join(detail) + "); "
            "BL2 remains untouched. A fresh full restore with a new bad-block map is required.",
        ))
    print(tr(
        f"[OK] IBU readback PASS; bad-block map стабильна ({len(final_bad)} block(s)); BL2 всё ещё не изменён.",
        f"[OK] IBU readback PASS; bad-block map is stable ({len(final_bad)} block(s)); BL2 is still unchanged.",
    ))

    bl2_path = Path(manifest["uboot_restore"]["bl2_file"])
    bl2_sha = manifest["uboot_restore"]["bl2_sha256"]
    print(tr("[3/3] Загружаю точный исходный stock BL2. Смещение 0x800 к нему не применяется.", "[3/3] Loading the exact original stock BL2. No 0x800 offset is applied."))
    _uboot_tftp_load(serial_port, log, local_ip, router_ip, bl2_path, "nokia-stock-bl2.bin", bl2_sha)
    uboot_command(serial_port, log, "mtd erase bl2", timeout=180)
    uboot_command(serial_port, log, f"mtd write bl2 0x{UBOOT_LOAD_ADDRESS:x} 0x0 0x{STOCK_BL2_SIZE:x}", timeout=180)
    uboot_command(serial_port, log, f"mw.b 0x{UBOOT_LOAD_ADDRESS:x} 0x00 0x{STOCK_BL2_SIZE:x}", timeout=60)
    uboot_command(serial_port, log, f"mtd read bl2 0x{UBOOT_LOAD_ADDRESS:x} 0x0 0x{STOCK_BL2_SIZE:x}", timeout=180)
    digest = uboot_command(serial_port, log, f"crc32 0x{UBOOT_LOAD_ADDRESS:x} 0x{STOCK_BL2_SIZE:x}", timeout=60)
    _uboot_require_crc32(digest, _file_crc32(bl2_path), "stock BL2")

    print(tr(
        "[OK] Все good-span IBU и stock BL2 совпали при чтении обратно по CRC32; known bad blocks были физически пропущены без сдвига соседних данных; исходные файлы на ПК закреплены SHA256.",
        "[OK] Every good IBU span and stock BL2 matched by readback CRC32; known bad blocks were physically skipped without shifting adjacent data; source files on the PC remain SHA256-pinned.",
    ))
    return _request_uboot_reset_and_confirm(serial_port, log)

def _uboot_reboot_evidence(data: bytes) -> bool:
    """Recognize fresh boot output after a reset command.

    A U-Boot prompt or the echoed word ``reset`` is deliberately not evidence:
    RC17 could remain at RAM U-Boot while the PC incorrectly reported success.
    """
    low = data.lower()
    markers = (
        b"secure key does not exist",
        b"hwconf is",
        b"dram flow done",
        b"an7583dramc",
        b"notice:  bl21",
        b"notice: bl21",
    )
    return any(marker in low for marker in markers)

def _request_uboot_reset_and_confirm(serial_port: RecoverySerial, log, timeout: float = 15.0) -> bool:
    """Send a paced U-Boot reset and require fresh UART boot evidence.

    This is intentionally separate from NAND success.  If reset cannot be
    confirmed, restoration remains successful but the operator is explicitly
    told to power-cycle after all writes/readbacks are complete.
    """
    print(tr(
        "[REBOOT] Отправляю reset в RAM U-Boot и отдельно подтверждаю начало новой загрузки по UART.",
        "[REBOOT] Sending reset to RAM U-Boot and independently confirming a fresh boot on UART.",
    ))
    _uboot_wait_quiet(serial_port, log, quiet=0.18, timeout=1.0)
    serial_port.reset_input()
    print("[U-Boot] reset")
    _uboot_send_line(serial_port, "reset")
    deadline = time.time() + timeout
    tail = bytearray()
    while time.time() < deadline:
        data = serial_port.read(4096, 0.25)
        if not data:
            continue
        _uart_log_write(log, data)
        tail.extend(data)
        if len(tail) > 65536:
            del tail[:-32768]
        raw = bytes(tail)
        if _uboot_reboot_evidence(raw):
            print(tr(
                "[OK] UART подтвердил выполнение reset: началась новая загрузка Nokia.",
                "[OK] UART confirmed reset execution: a fresh Nokia boot has started.",
            ))
            return True
        if _uboot_prompt_present(raw):
            print(tr(
                "[WARN] После команды reset снова получено приглашение U-Boot; автоматический reboot не подтверждён.",
                "[WARN] A U-Boot prompt returned after reset; automatic reboot was not confirmed.",
            ))
            return False
    print(tr(
        "[WARN] За 15 секунд UART не подтвердил новый boot после команды reset.",
        "[WARN] UART did not confirm a fresh boot within 15 seconds after the reset command.",
    ))
    return False

def _probe_stock_web_fingerprint(host: str) -> tuple[bool, str]:
    """Require the actual Nokia stock login page, not merely an open TCP port."""
    try:
        module = _load_stock_web_module()
        client = module.StockWeb(host, timeout=1.5)
        client.fetch_public_key()
        return True, "stock-login-pubkey"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

_RESTORE_SSH_MINIMAL_AUTH: dict[str, bool] = {}

_RESTORE_SESSION_KEY: dict[str, Path] = {}
_RESTORE_SESSION_KEY_MATERIAL: list[tuple[Path, str]] = []


def _restore_session_keypair() -> tuple[Path, str] | None:
    """One throwaway keypair per run, used to stop asking for the password.

    ssh reads a password from the terminal and cannot be told to remember it, so
    an interactive probe inside a polling loop means one prompt per iteration.
    Authenticating once and leaving a key behind turns every later probe, and
    every scp, into an ordinary deterministic batch call.

    The key is generated on the PC, lives in a temporary directory for the length
    of the run, and never reaches the session log. On the device it goes to
    /etc/dropbear/authorized_keys, which the stock restore overwrites along with
    the rest of the flash.
    """
    if _RESTORE_SESSION_KEY_MATERIAL:
        return _RESTORE_SESSION_KEY_MATERIAL[0]
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        return None
    try:
        directory = Path(tempfile.mkdtemp(prefix="medveflasher-restore-"))
        private = directory / "session_key"
        subprocess.run([keygen, "-q", "-t", "ed25519", "-N", "", "-C",
                        "medveflasher-restore", "-f", str(private)],
                       check=True, capture_output=True, text=True, timeout=60)
        public = (directory / "session_key.pub").read_text(encoding="utf-8").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        _write_session_only(f"[RESTORE-KEY] ssh-keygen unavailable: {exc}")
        return None
    if not public:
        return None
    _RESTORE_SESSION_KEY_MATERIAL.append((private, public))
    return _RESTORE_SESSION_KEY_MATERIAL[0]


def _restore_authorized_key_command(public: str) -> str:
    """Append the run's public key to Dropbear's authorized_keys, once."""
    quoted = shlex.quote(public)
    return (
        "mkdir -p /etc/dropbear; "
        f"grep -qxF {quoted} /etc/dropbear/authorized_keys 2>/dev/null || "
        f"echo {quoted} >> /etc/dropbear/authorized_keys; "
        "chmod 600 /etc/dropbear/authorized_keys 2>/dev/null; "
    )



def _restore_root_password_hint(errors: list[str]) -> bool:
    """True when the probe reached SSH and only authentication was refused."""
    text = " ".join(errors).lower()
    if "permission denied" in text or "authentication" in text:
        return True
    # A router that is simply not there fails earlier and differently.
    return not any(token in text for token in (
        "connection refused", "no route to host", "timed out", "timeout",
        "network is unreachable", "тайм-аут"))


def _restore_probe_ssh(host: str, command: str, timeout: int = 120, quiet: bool = True,
                       allow_interactive: bool = False) -> tuple[int, str]:
    """Deterministic SSH probe for transient recovery/production detection.

    Recovery root is intentionally blank and Dropbear is pinned with -B in RC19.
    Try the protocol-level none-auth path first, then one ordinary BatchMode path.
    Host keys never come from the operator known_hosts file.

    Both of those modes are deliberately non-interactive, which is right for the
    polling loops but wrong for the first contact with an *installed* OpenWrt: a
    production system may legitimately have a root password, and BatchMode makes
    ssh refuse to ask for it rather than prompt. The probe then failed and the
    restore ended before reaching ``arm_one_shot_recovery_boot``, which has always
    been able to prompt. ``allow_interactive`` lets the single detection probe ask
    once, when an operator is actually at the console.
    """
    preferred = _RESTORE_SSH_MINIMAL_AUTH.get(host)
    modes = [preferred] if preferred is not None else [True, False]
    errors=[]
    for minimal in modes:
        try:
            rc,out=ssh_run(host,command,timeout=timeout,quiet=quiet,batch_mode=True,minimal_auth=bool(minimal))
            _RESTORE_SSH_MINIMAL_AUTH[host]=bool(minimal)
            return rc,out
        except Error as exc:
            errors.append(str(exc).replace("\n"," ")[-700:])
    if preferred is not None:
        other=not preferred
        try:
            rc,out=ssh_run(host,command,timeout=timeout,quiet=quiet,batch_mode=True,minimal_auth=other)
            _RESTORE_SSH_MINIMAL_AUTH[host]=other
            return rc,out
        except Error as exc:
            errors.append(str(exc).replace("\n"," ")[-700:])

    if allow_interactive and _restore_root_password_hint(errors) and _console_can_prompt():
        print(tr(
            f"[INFO] SSH на {host} отвечает, но root без пароля не пускает — у установленной OpenWrt он задан.",
            f"[INFO] SSH on {host} responds but refuses a passwordless root: the installed OpenWrt has a password set.",
        ))
        print(tr(
            "[INFO] Пароль сейчас запросит сам ssh. Он не сохраняется и в журнал не попадает.",
            "[INFO] ssh will now ask for it. The password is not stored and never reaches the log.",
        ))
        keypair = _restore_session_keypair()
        effective = command
        if keypair:
            effective = _restore_authorized_key_command(keypair[1]) + command
            print(tr(
                "[INFO] После входа мастер оставит одноразовый ключ в /etc/dropbear/authorized_keys, "
                "чтобы больше не спрашивать пароль. Возврат на сток перезаписывает его вместе со всей флеш-памятью.",
                "[INFO] After the login the wizard leaves a one-off key in /etc/dropbear/authorized_keys "
                "so it never has to ask again. The stock restore overwrites it along with the whole flash.",
            ))
        try:
            # The timeout now has to cover a human typing, not just a link.
            rc, out = ssh_run(host, effective, timeout=max(timeout, 180), quiet=quiet,
                              password_prompts=3)
        except Error as exc:
            errors.append(str(exc).replace("\n", " ")[-700:])
        else:
            if keypair:
                # Registering the key is a claim; a batch probe through it is the
                # proof. If it does not hold, drop it rather than carry a broken
                # assumption into the polling loops.
                _RESTORE_SESSION_KEY[host] = keypair[0]
                try:
                    ssh_run(host, "true", timeout=30, quiet=True, batch_mode=True)
                    _RESTORE_SSH_MINIMAL_AUTH[host] = False
                    _write_session_only(f"[RESTORE-KEY] session key accepted by {host}")
                except Error as exc:
                    _RESTORE_SESSION_KEY.pop(host, None)
                    _write_session_only(f"[RESTORE-KEY] session key rejected by {host}: {exc}")
            return rc, out

    detail = " | ".join(errors)[-1600:]
    if _restore_root_password_hint(errors):
        raise Error(tr(
            "SSH отвечает, но аутентификация root не прошла. У установленной OpenWrt задан пароль root, "
            "а автоматические проверки идут без интерактивного ввода.\n"
            "  Варианты: снять пароль root в OpenWrt (passwd -d root), либо добавить свой ключ в "
            "/etc/dropbear/authorized_keys, либо восстанавливать через BootROM/UART.\n"
            "  Подробности ssh: " + detail,
            "SSH responds but root authentication failed. The installed OpenWrt has a root password, "
            "while the automatic checks run without interactive input.\n"
            "  Options: clear the root password in OpenWrt (passwd -d root), add your key to "
            "/etc/dropbear/authorized_keys, or restore through BootROM/UART.\n"
            "  ssh detail: " + detail,
        ))
    raise Error("restore SSH probe failed: " + detail)


# Board identity as the device reports it, kept apart from what the device is
# currently running. Conflating the two is what made the restore gate answer
# "does not match" to four different situations.
MD_SOC_COMPATIBLE = "airoha,an7581"
MF_SOC_COMPATIBLE = "airoha,an7583"


def classify_restore_identity(output: str) -> dict[str, object]:
    """Split what the board *is* from what it is currently *running*.

    ``family`` comes from the board/SoC compatible strings and holds for any image
    on that hardware. ``kit_built`` is true only for the ``-ubi`` board this kit
    installs, because that suffix is this project's convention, not the vendor's
    or upstream's. ``state`` names the system in flash from the MTD shape.
    """
    low = output.lower()
    board = ""
    match = re.search(r"(?im)^board=(.*)$", output)
    if match:
        board = match.group(1).strip().lower()
    compat = ""
    match = re.search(r"(?im)^compat=(.*)$", output)
    if match:
        compat = match.group(1).strip().lower()
    identity = f"{board} {compat}"

    family = "unknown"
    if "xg-040g-mf" in identity or MF_SOC_COMPATIBLE in identity:
        family = "mf"
    elif "xg-040g-md" in identity or MD_SOC_COMPATIBLE in identity:
        family = "md"
    kit_built = board.endswith("-ubi")

    shape = _all_in_ubi_shape(output)
    if shape in ("recovery", "production"):
        state = shape
    elif 'mtd14: 02880000 00020000 "nsb_master"' in low or '"bootloader"' in low:
        state = "stock-layout"
    elif "ubi" in low or "all_flash" in low:
        state = "foreign-ubi"
    else:
        state = "unknown"
    return {"family": family, "kit_built": kit_built, "state": state,
            "board": board or "(пусто)", "compat": compat or "(пусто)"}


_PROC_MTD_LINE = re.compile(r'(?im)^\s*mtd(\d+):\s+([0-9a-f]+)\s+([0-9a-f]+)\s+"([^"]*)"')


def parse_proc_mtd_shape(output: str) -> dict[int, tuple[int, int, str]]:
    """Structured /proc/mtd from a probe transcript: number -> (size, erase, name)."""
    shape: dict[int, tuple[int, int, str]] = {}
    for number, size, erase, name in _PROC_MTD_LINE.findall(output):
        shape[int(number)] = (int(size, 16), int(erase, 16), name.strip().lower())
    return shape


def _all_in_ubi_shape(output: str) -> str:
    """Recognise the all-in-UBI layout without gating on the UBI partition size.

    What is fixed by the hardware and by the boot contract is checked exactly: the
    whole 256 MiB chip published as ``all_flash``, one ``0x20000`` boot block as
    ``bl2``, and the ``0x20000`` erase size. The size of the ``ubi``/``ibu``
    partition is not: a device observed in the field carries ``0x0FF00000`` where
    this kit's own build publishes ``0x0FFE0000`` — seven eraseblocks left unused
    at the end of the chip by a different build of the same board.

    That number is recorded as evidence rather than enforced, because no step of
    this operation depends on it. Restoring from a running system rewrites the
    U-Boot environment, verifies it by read-back, reboots and TFTPs the recovery
    image; the UBI partition is never touched. Authorization stays with the facts
    that do describe the operation — the verified environment write, the
    content-revalidated backup, and the geometry the recovery system pins itself.
    """
    shape = parse_proc_mtd_shape(output)
    zero, one, two = shape.get(0), shape.get(1), shape.get(2)
    if not zero or not one or not two:
        return "incomplete"
    if zero[0] != PHYSICAL_NAND_SIZE or zero[1] != UBOOT_ERASE_SIZE or zero[2] != "all_flash":
        return "other"
    if one[0] != UBOOT_ERASE_SIZE or one[1] != UBOOT_ERASE_SIZE or one[2] != "bl2":
        return "other"
    if two[1] != UBOOT_ERASE_SIZE:
        return "other"
    if two[2] == "ibu":
        return "recovery"
    if two[2] == "ubi":
        return "production"
    return "other"


def _restore_environment_diagnostic(output: str, family: str, board_ok: bool,
                                    recovery_markers: tuple[str, ...],
                                    production_markers: tuple[str, ...]) -> str:
    """Say what was actually seen when the restore gate refuses.

    The probe already collected the board name and /proc/mtd, but the refusal
    used to report none of it, so an operator holding a device that needs
    restoring was told "does not match" and left to guess which half was wrong.
    The gate stays exactly as strict; it just stops being silent about why.
    """
    low = output.lower()
    board = "(пусто)"
    match = re.search(r"(?im)^board=(.*)$", output)
    if match:
        board = match.group(1).strip() or "(пусто)"
    root = "(не определён)"
    match = re.search(r"(?im)^root=(.*)$", output)
    if match:
        root = match.group(1).strip() or "(не определён)"
    observed = [line.strip() for line in output.splitlines()
                if re.match(r"(?i)^\s*mtd\d+:", line.strip())][:4]

    lines = [
        f"  наблюдалось: BOARD={board}; ROOT={root}",
        f"  ожидалось:   BOARD=nokia,xg-040g-{family}-ubi",
    ]
    if not board_ok:
        lines.append("  -> имя платы не совпало: это не установленная этим комплектом all-in-UBI система и не её recovery.")
    else:
        missing_recovery = [m for m in recovery_markers if m not in low]
        missing_production = [m for m in production_markers if m not in low]
        closer = missing_recovery if len(missing_recovery) <= len(missing_production) else missing_production
        label = "recovery" if closer is missing_recovery else "production"
        lines.append(f"  -> имя платы совпало, но разметка не сошлась; ближе к {label}, не хватает:")
        lines.extend(f"       {marker}" for marker in closer)
    if observed:
        lines.append("  фактический /proc/mtd (первые строки):")
        lines.extend(f"       {line}" for line in observed)
    identity = classify_restore_identity(output)
    lines.append(f"  распознано: семейство={identity['family'].upper()}; собрано этим комплектом={'да' if identity['kit_built'] else 'нет'}; система={identity['state']}")
    advice = {
        "stock-layout": "  -> в NAND стоковая разметка: это transition-система этапа 1. Нужен пункт «подготовка / продолжение установки», а не откат.",
        "foreign-ubi": "  -> UBI есть, но это не образ этого комплекта. Откат без UART опирается на env и разметку, которые ставит он сам, поэтому путь закрыт. Используйте BootROM/UART с полным backup.",
        "recovery": None,
        "production": None,
        "unknown": "  -> определить систему по /proc/mtd не удалось; полный ответ смотрите в логе.",
    }.get(str(identity["state"]))
    if identity["state"] in ("recovery", "production") and not identity["kit_built"]:
        # The flash is already in the all-in-UBI shape this path drives, but the
        # board name says another builder produced it. That is a deliberate
        # decision, not a detection bug: the no-UART restore rewrites the boot
        # environment this kit installs, and a foreign builder may lay it out
        # differently even when /proc/mtd looks identical.
        advice = ("  -> разметка совпадает с all-in-UBI, но имя платы без суффикса -ubi: систему собрал не этот комплект.\n"
                  "     Откат без UART правит boot environment, который ставит именно он, поэтому путь закрыт по решению, а не по ошибке.\n"
                  "     Безопасный путь с полным backup — BootROM/UART.")
    if advice:
        lines.append(advice)
    lines.append("  Полный ответ устройства — в work/logs/session-*.log по метке [SSH-RAW].")
    return "\n".join(lines)


def inspect_restore_environment(host: str, expected_family: str | None = None, quiet: bool = False,
                                allow_interactive: bool = False) -> tuple[str, str]:
    command = (
        "echo BOARD=$(cat /tmp/sysinfo/board_name 2>/dev/null || true); "
        # board_name is a derived label; the device-tree compatible list is the
        # primary evidence and carries the SoC as well as the board.
        "echo COMPAT=$(tr '\\0' ' ' < /proc/device-tree/compatible 2>/dev/null || true); "
        "echo STATE=$(cat /tmp/NOKIA_AUTOFLASH_STATE 2>/dev/null || true); "
        "echo ROOT=$(awk '$2==\"/\" {print $3; exit}' /proc/mounts); "
        "cat /proc/mtd; "
        "for c in mtd gzip sha256sum fw_printenv fw_setenv nc scp; do "
        "command -v $c >/dev/null 2>&1 && echo TOOL_$c=1 || echo TOOL_$c=0; done; "
        'if [ -x /usr/bin/nokia-tftp ] && [ "$(command -v tftp 2>/dev/null)" = /usr/bin/tftp ]; then '
        "echo TOOL_tftp=1; echo TFTP_IMPL=nokia-tftp-rc19; echo TFTP_PROBE_RC=0; "
        "elif command -v tftp >/dev/null 2>&1; then "
        "echo TOOL_tftp=1; echo TFTP_IMPL=standalone-other; echo TFTP_PROBE_RC=0; "
        "elif [ -x /bin/busybox ]; then "
        "/bin/busybox tftp --help >/dev/null 2>&1; bb_tftp_rc=$?; "
        "if [ \"$bb_tftp_rc\" -ne 127 ]; then "
        "echo TOOL_tftp=1; echo TFTP_IMPL=busybox-applet; echo TFTP_PROBE_RC=$bb_tftp_rc; "
        "else echo TOOL_tftp=0; echo TFTP_IMPL=missing; echo TFTP_PROBE_RC=$bb_tftp_rc; fi; "
        "else echo TOOL_tftp=0; echo TFTP_IMPL=missing; echo TFTP_PROBE_RC=127; fi"
    )
    _, output = _restore_probe_ssh(host, command, timeout=120, quiet=quiet,
                                   allow_interactive=allow_interactive)
    low = output.lower()
    family = (expected_family or "").strip().lower()
    if family not in ("md", "mf"):
        if "board=nokia,xg-040g-mf-ubi" in low:
            family = "mf"
        elif "board=nokia,xg-040g-md-ubi" in low:
            family = "md"
    if family not in ("md", "mf"):
        raise Error(tr("OpenWrt обнаружен, но family MD/MF не определён", "OpenWrt was detected, but the MD/MF family could not be determined"))
    board_ok = f"board=nokia,xg-040g-{family}-ubi" in low
    recovery_markers = (
        'mtd0: 10000000 00020000 "all_flash"',
        'mtd1: 00020000 00020000 "bl2"',
        'mtd2 named "ibu"',
    )
    production_markers = (
        'mtd0: 10000000 00020000 "all_flash"',
        'mtd1: 00020000 00020000 "bl2"',
        'mtd2 named "ubi"',
    )
    shape = _all_in_ubi_shape(output)
    if board_ok and shape in ("recovery", "production"):
        observed = parse_proc_mtd_shape(output).get(2)
        if observed:
            _write_session_only(
                f"[RESTORE-SHAPE] {shape}: mtd2 name={observed[2]} size=0x{observed[0]:08X} "
                f"erase=0x{observed[1]:X} (size is evidence, not a gate)")
        return shape, output
    raise Error(tr(
        f"OpenWrt обнаружен, но board/MTD не соответствует Nokia XG-040G-{family.upper()} recovery или all-in-UBI production.\n"
        + _restore_environment_diagnostic(output, family, board_ok, recovery_markers, production_markers),
        f"OpenWrt was detected, but its board/MTD layout does not match Nokia XG-040G-{family.upper()} recovery or all-in-UBI production.\n"
        + _restore_environment_diagnostic(output, family, board_ok, recovery_markers, production_markers),
    ))

def transition_preflight_for_restore(host: str, backup_ri_sha: str, expected_family: str, timeout: int = 180) -> str:
    deadline = time.time() + timeout; last_output = ""; consecutive = 0
    while time.time() < deadline:
        try:
            mode, output = inspect_restore_environment(host, expected_family=expected_family, quiet=True); last_output = output
            consecutive = consecutive + 1 if mode == "recovery" else 0
            if consecutive >= 2: break
        except (Error, OSError, subprocess.SubprocessError) as exc:
            last_output = str(exc); consecutive = 0
        time.sleep(3)
    else:
        raise Error(tr("recovery не перешла в устойчивое состояние\n" + last_output[-6000:], "recovery did not reach a stable state\n" + last_output[-6000:]))
    low=last_output.lower(); required=("tool_mtd=1","tool_gzip=1","tool_sha256sum=1")
    missing=[x.removeprefix("tool_").removesuffix("=1") for x in required if x not in low]
    if missing: raise Error(tr("в recovery отсутствуют: "+", ".join(missing), "recovery is missing: "+", ".join(missing)))
    if "tool_tftp=1" in low and "tftp_impl=nokia-tftp-rc19" in low:
        transport="tftp"; print(tr("[OK] Система восстановления проверена. Способ передачи: встроенный AArch64 nokia-tftp.", "[OK] The recovery system is verified. Transfer method: bundled AArch64 nokia-tftp."))
    elif "tool_nc=1" in low:
        transport="tcp-nc"; print(tr("[ПРЕДУПРЕЖДЕНИЕ] Закреплённый nokia-tftp недоступен; используется TCP/nc.", "[WARNING] The pinned nokia-tftp client is unavailable; using TCP/nc."))
    elif "tool_scp=1" in low:
        scp_executable(); transport="scp"; print(tr("[ПРЕДУПРЕЖДЕНИЕ] nokia-tftp и nc недоступны; используется SCP staging.", "[WARNING] nokia-tftp and nc are unavailable; using SCP staging."))
    else:
        raise Error(tr("в recovery нет закреплённого nokia-tftp, nc или scp", "recovery has no pinned nokia-tftp, nc, or scp transport"))
    if "state=recovery_ready" not in low:
        _write_session_only("[RESTORE] recovery state file is absent; exact MTD layout confirmed")
    command=("printf RI_RAW_SHA=; if grep -q \"\"ri-stock\"\" /proc/mtd; then mtd -q -l 262144 dump ri-stock 2>/dev/null | sha256sum | awk '{print $1}'; else echo unavailable; fi")
    _,output=_restore_probe_ssh(host,command,timeout=120,quiet=True); match=re.search(r"RI_RAW_SHA=([0-9a-f]{64})",output)
    if match and match.group(1)==backup_ri_sha: print(tr("[OK] RI совпадает с выбранным backup.", "[OK] RI matches the selected backup."))
    else:
        print(tr("[ПРЕДУПРЕЖДЕНИЕ] Не удалось подтвердить backup по RI. После перехода на UBI это ожидаемо; убедитесь, что выбран backup именно этого роутера.", "[WARNING] The backup could not be confirmed by RI. This is expected after migration to UBI; make sure the backup belongs to this router."))
    return transport

def serve_tcp_get(bind_ip: str, port: int, source: Path, allowed_client_ip: str,
                  ready: threading.Event, result: TftpResult, timeout: int = 1800) -> None:
    """Send one file over a single TCP connection for the recovery nc fallback."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((bind_ip, port))
        server.listen(1)
        server.settimeout(timeout)
        ready.set()
        conn, address = server.accept()
        if allowed_client_ip and address[0] != allowed_client_ip:
            raise Error(f"unexpected TCP restore client {address[0]}")
        with conn, source.open("rb") as fh:
            conn.settimeout(timeout)
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                conn.sendall(chunk)
                result.bytes_transferred += len(chunk)
            try:
                conn.shutdown(socket.SHUT_WR)
            except OSError:
                pass
    except Exception as exc:
        result.error = exc
        ready.set()
    finally:
        server.close()


def _verify_restore_readback(host: str, target: str, raw_size: int, raw_sha: str) -> None:
    print(tr(f"[VERIFY] {target}: считаю SHA256 прочитанной NAND-области 0x{raw_size:x}...", f"[VERIFY] {target}: hashing the 0x{raw_size:x}-byte NAND readback..."))
    cmd=f"mtd -q -l {raw_size} dump {shlex.quote(target)} | sha256sum | awk '{{print $1}}'"
    _,output=ssh_run_with_progress(host,cmd,1200,f"VERIFY {target.upper()}",restore_auth=True)
    match=re.search(r"([0-9a-f]{64})",output)
    if not match or match.group(1)!=raw_sha:
        raise Error(tr(
            f"readback SHA256 {target} не совпал; не перезагружайте и не отключайте питание",
            f"readback SHA256 mismatch for {target}; do not reboot or remove power",
        ))
    print(f"[OK] {target} readback SHA256: {raw_sha}")


def _restore_write_unknown(host: str, target: str, detail: str, expected_family: str | None = None) -> WriteStateUnknownError:
    """Fail closed after an issued NAND write and record read-only post-failure identity."""
    assessment="unavailable"
    try:
        mode,out=inspect_restore_environment(host,expected_family=expected_family,quiet=True)
        mtd_lines="; ".join(line.strip() for line in out.splitlines() if line.lower().startswith("mtd"))
        assessment=f"mode={mode}; {mtd_lines}"[-1800:]
    except Exception as exc:
        assessment=f"router could not be re-identified read-only: {exc}"[-1800:]
    return WriteStateUnknownError(tr(
        f"{target}: NAND write был запущен, но завершение/readback не доказаны. Автоматический fallback ЗАПРЕЩЁН. {detail}. После сбоя: {assessment}. Не запускайте второй write автоматически; если recovery не подтверждается, используйте BootROM/UART RECOVERY_SAFE full restore.",
        f"{target}: the NAND write was started, but completion/readback is unproven. Automatic fallback is FORBIDDEN. {detail}. Post-failure: {assessment}. Do not start a second write automatically; if recovery cannot be proven, use BootROM/UART RECOVERY_SAFE full restore.",
    ))


def _restore_stream_transport(host: str, local_ip: str, port: int, source: Path, remote_name: str,
                              target: str, transport: str, expected_family: str | None = None) -> None:
    """Stream a gzip payload directly into mtd.

    Only local server startup failures are pre-write transport failures.  Once
    the SSH pipeline is issued, mtd may have started and any disconnect/error is
    WRITE_STATE_UNKNOWN; no second transport may be attempted automatically.
    """
    ready=threading.Event(); result=TftpResult()
    if transport=="tftp":
        thread=threading.Thread(target=serve_tftp_get,args=(local_ip,port,source,remote_name,host,ready,result),kwargs={"timeout":1800,"maximum_block_size":4096},daemon=True); label="TFTP"
        receive=(f"tftp -g -l /tmp/nokia-restore-{target}.fifo -r {shlex.quote(remote_name)} -b 4096 {shlex.quote(local_ip)} {port} & tp=$!; ")
    elif transport=="tcp-nc":
        thread=threading.Thread(target=serve_tcp_get,args=(local_ip,port,source,host,ready,result),kwargs={"timeout":1800},daemon=True); label="TCP/nc"
        receive=(f"nc {shlex.quote(local_ip)} {port} >/tmp/nokia-restore-{target}.fifo & tp=$!; ")
    else: raise TransportError(f"unsupported stream transport {transport}")
    thread.start()
    if not ready.wait(10): raise TransportError(f"{label} server did not start")
    if result.error: raise TransportError(f"{label} server: {result.error}")
    fifo=f"/tmp/nokia-restore-{target}.fifo"
    # Marker is emitted before mtd is invoked.  From this point on the write state
    # must be considered unknown on any channel loss.
    command=(f"set +e; echo RESTORE_STAGE={target}; rm -f {fifo}; mkfifo {fifo}; "+receive+
             f"echo RESTORE_WRITE_STARTED={target}; gzip -dc <{fifo} | mtd -f write - {shlex.quote(target)}; "
             f"wr=$?; wait $tp; trc=$?; rm -f {fifo}; echo RESTORE_WRITE_FINISHED={target} RESTORE_PIPELINE_TRANSPORT_RC=$trc RESTORE_PIPELINE_WRITE_RC=$wr; "
             f"[ $trc -eq 0 ] && [ $wr -eq 0 ]")
    try:
        ssh_run_with_progress(host,command,2400,f"{label} {target}",result,source.stat().st_size,restore_auth=True)
    except BaseException as exc:
        raise _restore_write_unknown(host,target,f"{label} pipeline lost: {exc}",expected_family) from exc
    thread.join(30)
    if thread.is_alive(): raise _restore_write_unknown(host,target,f"{label} server did not stop after write command",expected_family)
    if result.error: raise _restore_write_unknown(host,target,f"{label} server error after write command: {result.error}",expected_family)
    if result.bytes_transferred!=source.stat().st_size:
        raise _restore_write_unknown(host,target,f"{label} transferred {result.bytes_transferred}, expected {source.stat().st_size}",expected_family)
    print(tr(f"[FLASH] {target}: сжатый поток принят и записан.", f"[FLASH] {target}: compressed stream received and written."))


def _restore_scp_transport(host: str, source: Path, target: str, expected_family: str | None = None) -> None:
    remote=f"/tmp/nokia-restore-{target}.gz"; size=source.stat().st_size
    try:
        _,mem=_restore_probe_ssh(host,"awk '/MemAvailable:/ {print $2; exit}' /proc/meminfo",timeout=30,quiet=True)
    except Error as exc:
        raise TransportError(f"SCP preflight failed: {exc}") from exc
    m=re.search(r"([0-9]+)",mem); available=int(m.group(1))*1024 if m else 0
    if available and available < size + 32*1024*1024:
        raise TransportError(tr(
            f"SCP: недостаточно RAM: available={available}, need={size + 32*1024*1024}",
            f"SCP: insufficient RAM: available={available}, need={size + 32*1024*1024}",
        ))
    # Copy + compressed SHA verification are pre-write and may fall back safely.
    scp_copy_to_recovery(host,source,remote)
    expected=sha_file(source); _,out=_restore_probe_ssh(host,f"sha256sum {shlex.quote(remote)} | awk '{{print $1}}'",timeout=300,quiet=True)
    if expected not in out:
        try: _restore_probe_ssh(host,f"rm -f {shlex.quote(remote)}",timeout=30,quiet=True)
        except Error: pass
        raise TransportError("SCP compressed-file SHA256 mismatch")
    print(tr(f"[FLASH] {target}: распаковываю SCP-файл и записываю NAND...", f"[FLASH] {target}: decompressing the SCP file and writing NAND..."))
    cmd=(f"echo RESTORE_WRITE_STARTED={target}; gzip -dc {shlex.quote(remote)} | mtd -f write - {shlex.quote(target)}; "
         f"rc=$?; rm -f {shlex.quote(remote)}; echo RESTORE_WRITE_FINISHED={target} RC=$rc; exit $rc")
    try:
        ssh_run_with_progress(host,cmd,2400,f"FLASH {target.upper()}",restore_auth=True)
    except BaseException as exc:
        raise _restore_write_unknown(host,target,f"SCP write pipeline lost: {exc}",expected_family) from exc


def serve_restore_payload(host: str, local_ip: str, port: int, source: Path, remote_name: str,
                          target: str, raw_size: int, raw_sha: str, transport: str,
                          expected_family: str | None = None) -> None:
    # RC19: fallback is legal only while NAND has not been touched.  Streaming
    # transports become non-retryable as soon as their SSH mtd pipeline is issued.
    order={"tftp":["tftp","tcp-nc","scp"],"tcp-nc":["tcp-nc","scp"],"scp":["scp"]}.get(transport,[transport])
    failures=[]
    for index,candidate in enumerate(order,1):
        print()
        print(tr(f"[TRANSFER] {target}: попытка {index}/{len(order)}, транспорт {candidate}.", f"[TRANSFER] {target}: attempt {index}/{len(order)}, transport {candidate}."))
        try:
            if candidate=="scp": _restore_scp_transport(host,source,target,expected_family)
            else: _restore_stream_transport(host,local_ip,port,source,remote_name,target,candidate,expected_family)
            _verify_restore_readback(host,target,raw_size,raw_sha); return
        except WriteStateUnknownError:
            raise
        except TransportError as exc:
            failures.append(f"{candidate}: {exc}")
            print(tr(f"[WARNING] {candidate} не сработал ДО начала NAND write: {exc}", f"[WARNING] {candidate} failed BEFORE NAND write started: {exc}"))
    raise Error(tr("все безопасные pre-write транспорты восстановления отказали: ", "all safe pre-write restore transports failed: ") + " | ".join(failures))

def perform_stock_restore_over_ssh(router_ip: str, local_ip: str, restore_port: int,
                                   backup_dir: Path, payload_dir: Path, manifest: dict) -> None:
    stage_header("R1", "Проверка системы восстановления", "Recovery-system checks")
    backup_ri_sha, _ = raw_sha256(Path(verify_backup(backup_dir)["files"]["7"]))
    expected_family = str(manifest.get("source_validation", {}).get("device_family", "")).lower()
    if expected_family not in ("md", "mf"):
        raise Error(tr("backup family MD/MF не определён", "backup MD/MF family is not determined"))
    transport = transition_preflight_for_restore(router_ip, backup_ri_sha, expected_family)
    print()
    print(tr("ПЕРЕД НАЧАЛОМ ПРОВЕРЬТЕ:", "CHECK BEFORE STARTING:"))
    print(tr("  • Стабильное питание до окончательной перезагрузки.", "  • Stable power until the final reboot."))
    print(tr("  • Прямое Ethernet-соединение: ПК 192.168.1.254/24, Nokia 192.168.1.1.", "  • Direct Ethernet connection: PC 192.168.1.254/24, Nokia 192.168.1.1."))
    print(tr("  • Разрешите Python и OpenSSH в брандмауэре.", "  • Allow Python and OpenSSH through the firewall."))
    print(tr("  • Не нажимайте Reset и не закрывайте окно мастера.", "  • Do not press Reset or close the wizard window."))
    print(tr("  • Полная диагностика сохраняется в work/logs/LATEST.log.", "  • Full diagnostics are saved in work/logs/LATEST.log."))
    print(tr("  • Транспорт: nokia-tftp → TCP/nc → SCP; fallback разрешён только ДО запуска mtd write.", "  • Transport: nokia-tftp → TCP/nc → SCP; fallback is allowed only BEFORE mtd write is started."))
    print()
    print(tr("ВНИМАНИЕ: выбранный полный backup будет записан во флеш-память роутера.", "WARNING: the selected complete backup will be written to the router flash."))
    print(tr("Основная область записывается и проверяется первой; загрузчик — строго последним.", "The main area is written and verified first; the bootloader is written strictly last."))
    confirm=input(tr("Введите точно RESTORE STOCK BACKUP: ", "Type exactly RESTORE STOCK BACKUP: ")).strip()
    if confirm!="RESTORE STOCK BACKUP": raise Error(tr("stock restore отменён", "stock restore cancelled"))
    stage_header("R2", "Передача, запись и проверка IBU", "Transfer, write, and verify IBU")
    serve_restore_payload(router_ip,local_ip,restore_port,payload_dir/manifest["ibu"]["file"],manifest["ibu"]["file"],"ibu",manifest["ibu"]["raw_size"],manifest["ibu"]["raw_sha256"],transport,expected_family)
    print(tr(
        "[OK] IBU полностью восстановлена и проверена. BL2 ещё не изменялся.",
        "[OK] IBU has been fully restored and verified. BL2 has not been modified yet.",
    ))
    stage_header("R3", "Запись stock BL2 последним", "Write stock BL2 last")
    serve_restore_payload(router_ip,local_ip,restore_port,payload_dir/manifest["bl2"]["file"],manifest["bl2"]["file"],"bl2",manifest["bl2"]["raw_size"],manifest["bl2"]["raw_sha256"],transport,expected_family)
    stage_header("R4", "Финальная проверка полного all_flash", "Final full all_flash verification")
    full_cmd=f"mtd -q -l {STOCK_RESTORE_SPAN} dump all_flash | sha256sum | awk '{{print $1}}'"
    _,output=ssh_run_with_progress(router_ip,full_cmd,1800,"VERIFY ALL_FLASH",restore_auth=True)
    match=re.search(r"([0-9a-f]{64})",output)
    if not match or match.group(1)!=manifest["all_flash_sha256"]:
        raise Error(tr(
            "финальный SHA256 all_flash не совпал; не перезагружайте Nokia",
            "final all_flash SHA256 mismatch; do not reboot the Nokia",
        ))
    print(tr(
        f"[OK] Полный stock all_flash совпал: {manifest['all_flash_sha256']}",
        f"[OK] Complete stock all_flash matches: {manifest['all_flash_sha256']}",
    ))
    stage_header("R5", "Перезагрузка в штатную прошивку", "Reboot into stock firmware")
    print(tr("[OK] Все записи подтверждены. Отправляю sync и reboot.", "[OK] All writes are verified. Sending sync and reboot."))
    try:
        _restore_probe_ssh(router_ip,"sync; reboot -f",timeout=30,quiet=True)
    except Error:
        # Expected: the verified stock reboot can close SSH before a status is returned.
        pass



def parse_shell_assignments(output: str, names: tuple[str, ...]) -> dict[str, str]:
    """Parse only complete KEY=value lines from remote shell output.

    SSH diagnostics and CR/LF variants are ignored. This deliberately avoids a
    regex spanning line endings, which in RC12 could append the next marker to
    SERVERIP and produce a false address mismatch.
    """
    wanted = set(names)
    values: dict[str, str] = {}
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            values[key] = value.strip()
    return values

def wait_for_stable_openwrt(host: str, timeout: int, expected_mode: str | None = None) -> str | None:
    """Wait for a usable SSH shell, not merely an open TCP port.

    RC15 treated the first successful TCP handshake as a returned OpenWrt.  On
    hardware, Dropbear could close that connection while boot was still in
    progress.  The restore workflow requires two successful SSH probes and, when requested, the
    expected MTD layout.
    """
    deadline = time.time() + timeout
    consecutive = 0
    last_mode: str | None = None
    while time.time() < deadline:
        try:
            probe_command = "echo __NOKIA_SSH_READY__; cat /tmp/sysinfo/board_name 2>/dev/null; cat /proc/mtd 2>/dev/null"
            if expected_mode == "recovery":
                rc, output = _restore_probe_ssh(host, probe_command, timeout=25, quiet=True)
            else:
                # Deterministic like the recovery branch. A production OpenWrt may
                # have a root password, and an interactive ssh_run here would ask
                # for it on every one of this loop's iterations -- twice per call,
                # three calls per transition attempt. The single prompt belongs to
                # detection, which then installs the session key this probe uses.
                rc, output = _restore_probe_ssh(
                    host, probe_command, timeout=25, quiet=True
                )
            if rc == 0 and "__NOKIA_SSH_READY__" in output:
                # The same structural check the restore gate uses. This loop used
                # to compare two whole /proc/mtd lines literally, including the
                # UBI partition size, so a field build publishing 0x0FF00000
                # where this kit publishes 0x0FFE0000 never matched: the mode
                # stayed unknown, the loop ran to the deadline, and the restore
                # died reporting that SSH had not become stable -- while SSH had
                # been answering correctly the whole time.
                shape = _all_in_ubi_shape(output)
                mode = shape if shape in ("recovery", "production") else None
                if expected_mode is None or mode == expected_mode:
                    consecutive += 1
                    last_mode = mode
                    if consecutive >= 2:
                        return last_mode
                    time.sleep(3)
                    continue
            consecutive = 0
        except (Error, OSError, subprocess.SubprocessError):
            consecutive = 0
        time.sleep(3)
    return None


def arm_one_shot_recovery_boot(host: str, expected_bootcmd: str, local_ip: str, router_ip: str, bootfile: str) -> None:
    """Install a one-boot recovery command and verify it over stable SSH.

    The saved command restores the normal bootcmd before trying the network.
    Network variables are then changed only in RAM.  U-Boot retries TFTP twenty
    times before returning to the installed OpenWrt.
    """
    retry_numbers = " ".join(str(i) for i in range(1, 21))
    temporary = (
        f"setenv bootcmd '{expected_bootcmd}'; saveenv; "
        "setenv ethaddr 02:00:00:04:0d:10; setenv eth1addr 02:00:00:04:0d:11; "
        f"setenv ipaddr {router_ip}; setenv serverip {local_ip}; setenv netmask 255.255.255.0; "
        "setenv autoload no; "
        f"for n in {retry_numbers}; do echo NOKIA_RECOVERY_TFTP_ATTEMPT_$n; "
        f"tftpboot 0x90000000 {bootfile} && bootm 0x90000000#config-1; sleep 2; done; "
        "run boot_ubi"
    )
    command = (
        f"fw_setenv bootcmd {shlex.quote(temporary)} && sync && "
        "printf 'ARMED_BOOTCMD='; fw_printenv -n bootcmd"
    )
    last_output = ""
    for attempt in range(1, 6):
        rc, output = ssh_run(host, command, timeout=120, allow_disconnect=True, quiet=True)
        last_output = output
        values = parse_shell_assignments(output, ("ARMED_BOOTCMD",))
        if rc == 0 and values.get("ARMED_BOOTCMD") == temporary:
            print(tr(
                "[OK] Временная загрузка подготовлена; перезагружаю роутер.",
                "[OK] Temporary boot prepared; rebooting the router.",
            ))
            return
        if attempt < 5:
            print(tr(
                f"SSH ещё нестабилен после загрузки OpenWrt; повторяю проверку ({attempt}/5)...",
                f"SSH is not stable yet after OpenWrt boot; retrying verification ({attempt}/5)...",
            ))
            wait_for_stable_openwrt(host, 45, expected_mode="production")
    raise Error(tr(
        "не удалось записать и проверить одноразовую команду U-Boot; перезагрузка отменена\n" + last_output[-4000:],
        "failed to install and verify the one-boot U-Boot command; reboot cancelled\n" + last_output[-4000:],
    ))


def boot_recovery_from_production_openwrt(host: str, local_ip: str, router_ip: str, ask_before_reboot: bool = True) -> None:
    """Load the safe recovery image from an installed all-in-UBI OpenWrt."""
    if wait_for_stable_openwrt(host, 120, expected_mode="production") != "production":
        raise Error(tr(
            "SSH OpenWrt не стал устойчиво доступен; одноразовую загрузку recovery запускать небезопасно",
            "OpenWrt SSH did not become stably available; starting the one-boot recovery would be unsafe",
        ))

    env_cmd = (
        "echo BOOTFILE=$(fw_printenv -n bootfile 2>/dev/null || true); "
        "echo SERVERIP=$(fw_printenv -n serverip 2>/dev/null || true); "
        "echo IPADDR=$(fw_printenv -n ipaddr 2>/dev/null || true); "
        "echo BOOTCMD=$(fw_printenv -n bootcmd 2>/dev/null || true)"
    )
    _, env_out = ssh_run(host, env_cmd, timeout=60, quiet=True)
    env_values = parse_shell_assignments(env_out, ("BOOTFILE", "SERVERIP", "IPADDR", "BOOTCMD"))
    bootfile = env_values.get("BOOTFILE") or UBOOT_DEFAULT_RECOVERY_FILENAME
    normal_bootcmd = env_values.get("BOOTCMD", "")
    expected_normal_bootcmd = "run check_buttons ; run boot_ubi"
    if normal_bootcmd != expected_normal_bootcmd:
        raise Error(tr(
            "текущее значение bootcmd отличается от штатного для этой сборки; автоматическая перезагрузка отменена\n"
            f"Получено: {normal_bootcmd or '[пусто]'}\nОжидалось: {expected_normal_bootcmd}",
            "the current bootcmd differs from the expected value for this build; automatic reboot was cancelled\n"
            f"Received: {normal_bootcmd or '[empty]'}\nExpected: {expected_normal_bootcmd}",
        ))

    _write_session_only(f"[RESTORE] recovery bootfile={bootfile} server={local_ip}:69 router={router_ip}")
    print(tr("Система восстановления будет временно загружена через TFTP.", "The recovery system will be loaded temporarily over TFTP."))
    print(tr("Не нажимайте Reset. Обычная команда загрузки будет восстановлена автоматически.", "Do not press Reset. The normal boot command will be restored automatically."))

    for attempt in range(1, 4):
        if wait_for_stable_openwrt(host, 120, expected_mode="production") != "production":
            raise Error(tr("обычная OpenWrt не готова к следующей попытке", "the installed OpenWrt is not ready for the next attempt"))
        ready = threading.Event()
        result = TftpResult()
        thread = threading.Thread(
            target=serve_tftp_get,
            args=(local_ip, 69, RECOVERY_INITRAMFS, bootfile, router_ip, ready, result),
            kwargs={"timeout": 360, "maximum_block_size": 1468}, daemon=True,
        )
        thread.start()
        if not ready.wait(10):
            raise Error(tr("не удалось запустить TFTP-сервер для аварийного образа", "failed to start the TFTP server for the recovery image"))
        if result.error:
            raise Error(f"TFTP: {result.error}")
        print(tr(
            f"[WAIT] Попытка {attempt}/3: TFTP-сервер готов; ожидаю запрос U-Boot.",
            f"[WAIT] Attempt {attempt}/3: TFTP server ready; waiting for U-Boot.",
        ))
        if ask_before_reboot:
            input(tr(
                "Нажмите Enter, чтобы перезагрузить роутер в систему восстановления: ",
                "Press Enter to reboot the router into the recovery system: ",
            ))
        else:
            print(tr(
                "[WAIT] OpenWrt снова доступна; повторяю переход в систему восстановления.",
                "[WAIT] OpenWrt is available again; retrying the transition to the recovery system.",
            ))
        arm_one_shot_recovery_boot(host, expected_normal_bootcmd, local_ip, router_ip, bootfile)
        # The router is going down, so no exit status is coming. A raised timeout
        # here would unwind this function together with the TFTP server thread it
        # started, precisely while U-Boot is asking for the image.
        ssh_run(host, "sync; reboot -f", timeout=30,
                allow_disconnect=True, allow_timeout=True, quiet=True)

        announced = False
        while thread.is_alive() and not result.error:
            if result.bytes_transferred > 0 and not announced:
                print(tr("[TRANSFER] U-Boot запросил систему восстановления; передача началась.", "[TRANSFER] U-Boot requested the recovery system; transfer started."))
                announced = True
            thread.join(0.5)

        if not result.error and result.bytes_transferred == RECOVERY_INITRAMFS.stat().st_size:
            print(tr(
                f"[OK] Система восстановления передана: {result.bytes_transferred / 1048576:.1f} MiB.",
                f"[OK] Recovery system transferred: {result.bytes_transferred / 1048576:.1f} MiB.",
            ))
            if wait_for_stable_openwrt(router_ip, 480, expected_mode="recovery") == "recovery":
                print(tr("[OK] Система восстановления запущена; её образ не записывался во флеш-память.", "[OK] The recovery system is running; its image was not written to flash."))
                return
            raise Error(tr(
                "TFTP завершился, но recovery-система с разделом mtd2=ibu не появилась",
                "TFTP completed, but the recovery system with mtd2=ibu did not appear",
            ))

        detail = str(result.error) if result.error else f"передано {result.bytes_transferred} из {RECOVERY_INITRAMFS.stat().st_size}"
        print(tr(
            f"ПРЕДУПРЕЖДЕНИЕ: попытка {attempt}/3 не загрузила аварийный образ: {detail}",
            f"WARNING: attempt {attempt}/3 did not load the recovery image: {detail}",
        ))
        print(tr(
            "Жду, пока обычная OpenWrt полностью загрузится и SSH дважды ответит без ошибок...",
            "Waiting for the installed OpenWrt to finish booting and for SSH to answer successfully twice...",
        ))
        if wait_for_stable_openwrt(router_ip, 420, expected_mode="production") == "production":
            print(tr("[OK] Обычная OpenWrt снова полностью доступна; backup повторно не проверяется.", "[OK] Installed OpenWrt is fully available again; the backup will not be revalidated."))
            if attempt < 3:
                if ask_before_reboot:
                    answer = input(tr("Повторить попытку? [Y/n]: ", "Retry? [Y/n]: ")).strip().lower()
                    if answer in ("", "y", "yes", "д", "да"):
                        continue
                else:
                    continue
            raise Error(tr("аварийный образ не был загружен; Nokia вернулась в обычную OpenWrt", "the recovery image was not loaded; Nokia returned to the installed OpenWrt"))
        raise Error(tr(
            "после неудачной попытки не появилась ни recovery-система, ни обычная OpenWrt. Проверьте UART",
            "after the failed attempt neither the recovery system nor the installed OpenWrt appeared. Check UART",
        ))

    raise Error(tr("исчерпаны три попытки загрузки аварийного образа", "all three recovery-image attempts were exhausted"))


def stock_restore_running_wizard() -> None:
    verify_kit()
    print(tr("\n=== Возврат к штатной прошивке ===", "\n=== Return to stock firmware ==="))
    print(tr("Подходит для установленной OpenWrt и уже запущенной системы восстановления.", "Use this with installed OpenWrt or an already running recovery system."))
    print(tr("Если работает обычная OpenWrt, мастер временно запустит систему восстановления; сам образ во флеш-память не записывается.", "If installed OpenWrt is running, the wizard temporarily starts the recovery system; the image itself is not written to flash."))
    print()
    transition_lan_policy_notice()
    print(tr("Подключите стабильное питание и Ethernet напрямую к ПК через LAN2/LAN3/LAN4. Задайте ПК 192.168.1.254/24; Wi-Fi/VPN временно отключите.", "Connect stable power and Ethernet directly to the PC through LAN2/LAN3/LAN4. Set the PC to 192.168.1.254/24; temporarily disable Wi-Fi/VPN."))
    print(tr("Не нажимайте Reset. Окно остаётся открытым; прогресс и диагностика сохраняются в work/logs/LATEST.log.", "Do not press Reset. The window stays open; progress and diagnostics are saved in work/logs/LATEST.log."))
    print(tr("Способ передачи: TFTP → TCP/nc → SCP. Fallback разрешён только ДО начала NAND write.", "Transfer order: TFTP → TCP/nc → SCP. Fallback is allowed only BEFORE NAND write starts."))
    ssh_executable()
    local_ip = input(tr("Статический IP компьютера [192.168.1.254]: ", "Static PC IP [192.168.1.254]: ")).strip() or "192.168.1.254"
    router_ip = input(tr("IP Nokia [192.168.1.1]: ", "Nokia IP [192.168.1.1]: ")).strip() or "192.168.1.1"
    warn_if_lan1_uplink(router_ip, "восстановление stock", "stock restore")
    port_text = input(tr("Порт передачи файлов [1069]: ", "File-transfer port [1069]: ")).strip()
    restore_port = int(port_text) if port_text else 1069
    backup_dir = Path(input(tr("Путь к полному backup, снятому до установки OpenWrt: ", "Path to the complete backup made before installing OpenWrt: ")).strip().strip('"')).expanduser()
    print(tr(
        "Проверяю mtd0..mtd16, размеры, gzip, SHA256 и статические области внутри mtd16...",
        "Checking mtd0..mtd16, sizes, gzip integrity, SHA256, and static areas inside mtd16...",
    ))
    payload_dir, manifest = prepare_stock_restore_payloads(backup_dir)
    live_differences = manifest.get("source_validation", {}).get("live_slice_differences", [])
    if live_differences:
        names = ", ".join(f"mtd{number}" for number in live_differences)
        print(tr(
            f"[INFO] {names} изменились между отдельным дампом и mtd16; для изменяемых разделов это нормально. Для восстановления используется mtd16.",
            f"[INFO] {names} changed between the individual dump and mtd16; this is normal for changing partitions. mtd16 is used for restoration.",
        ))
    _write_session_only(f"[RESTORE] verified working files: {payload_dir}")
    print(tr("[OK] Backup проверен.", "[OK] Backup verified."))
    print(tr("[WAIT] Проверяю состояние роутера по SSH...", "[WAIT] Checking the router state over SSH..."))
    backup_family = str(manifest.get("source_validation", {}).get("device_family", "")).lower()
    if backup_family not in ("md", "mf"):
        raise Error(tr("backup family MD/MF не определён", "backup MD/MF family is not determined"))
    print(tr(f"[OK] Backup family: {backup_family.upper()}; применяю только соответствующий recovery/production gate.", f"[OK] Backup family: {backup_family.upper()}; only the matching recovery/production gate will be used."))
    mode, _ = inspect_restore_environment(router_ip, expected_family=backup_family, quiet=True,
                                          allow_interactive=True)
    if mode == "production":
        print(tr("[OK] Установленная OpenWrt и разметка Nokia подтверждены.", "[OK] Installed OpenWrt and the Nokia layout are confirmed."))
        print(tr("[WAIT] Подготавливаю временный запуск системы восстановления.", "[WAIT] Preparing a temporary recovery-system boot."))
        try:
            boot_recovery_from_production_openwrt(router_ip, local_ip, router_ip)
        except PermissionError as exc:
            raise Error(tr("нет прав на UDP/69; в Linux запустите мастер через sudo", "permission denied for UDP/69; on Linux run the wizard with sudo")) from exc
    else:
        print(tr("[OK] Система восстановления уже запущена.", "[OK] The recovery system is already running."))
    perform_stock_restore_over_ssh(router_ip, local_ip, restore_port, backup_dir, payload_dir, manifest)
    print(tr("Возврат завершён. Проверьте штатный Web-интерфейс или Telnet по адресу 192.168.1.1.", "Restore completed. Check the stock Web interface or Telnet at 192.168.1.1."))


def stock_restore_selector_wizard() -> None:
    print("\nСпособ перехода в режим восстановления stock:")
    print("1 — OpenWrt/recovery уже загружается: продолжить по SSH без UART")
    print("2 — кирпич, в UART повторяется C: BootROM → XMODEM → recovery → stock")
    while True:
        choice = input("Выберите 1/2: ").strip().lower()
        if choice in ("1", "ssh", "openwrt", "recovery"):
            stock_restore_running_wizard()
            return
        if choice in ("2", "uart", "brick", "xmodem"):
            stock_recovery_wizard()
            return
        print(tr("Неверный выбор. Введите 1 или 2.", "Invalid selection. Enter 1 or 2."))



BOOTROM_BACKUP_NAMES = {
    0: "bootloader", 1: "romfile", 2: "kernel", 3: "rootfs",
    4: "kernel_slave", 5: "rootfs_slave", 6: "bosa", 7: "ri",
    8: "flag", 9: "flagback", 10: "config", 11: "data",
    12: "oopsfs", 13: "log", 14: "nsb_master", 15: "nsb_slave",
    16: "all_flash",
}


def _gzip_raw_info(path: Path) -> tuple[int, str]:
    total = 0
    digest = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
    except (OSError, EOFError) as exc:
        raise Error(f"повреждён gzip {path.name}: {exc}") from exc
    return total, digest.hexdigest()


def _gzip_slice(raw_path: Path, offset: int, size: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("rb") as src, output.open("wb") as raw_out:
        src.seek(offset)
        with gzip.GzipFile(filename="", mode="wb", compresslevel=1, fileobj=raw_out, mtime=0) as gz:
            remaining = size
            while remaining:
                data = src.read(min(1024 * 1024, remaining))
                if not data:
                    raise Error(f"неожиданный EOF при создании {output.name}")
                gz.write(data)
                remaining -= len(data)


def _bootrom_slot_geometry(slot: bytes, family: str, label: str) -> tuple[int, int, int]:
    small_kernel = 0x003AF6DA if family == "md" else 0x003B6CC0
    small_rootfs = 0x01CC0000 if family == "md" else 0x01D00000
    candidates = (
        (small_kernel, small_rootfs),
        (0x00480000, 0x02400000),
    )
    squash_offsets: list[int] = []
    start = 0x100000
    while True:
        pos = slot.find(b"hsqs", start, min(len(slot), 0x00800000))
        if pos < 0:
            break
        squash_offsets.append(pos)
        start = pos + 4
    best: tuple[int, int, int, int] | None = None
    for rootfs_offset in squash_offsets:
        for kernel_size, rootfs_size in candidates:
            delta = abs(rootfs_offset - kernel_size)
            if delta <= 0x2000:
                item = (delta, kernel_size, rootfs_offset, rootfs_size)
                if best is None or item < best:
                    best = item
    if best is None:
        raise Error(tr(
            f"{label}: не найден известный stock kernel/rootfs split; backup сохранён, но полный набор mtd0..mtd16 не сформирован",
            f"{label}: no known stock kernel/rootfs split was found; the all_flash backup was saved but mtd0..mtd16 could not be synthesized",
        ))
    _, kernel_size, rootfs_offset, rootfs_size = best
    if rootfs_offset + rootfs_size > len(slot):
        raise Error(f"{label}: rootfs выходит за границы stock slot")
    return kernel_size, rootfs_offset, rootfs_size


def _synthesize_bootrom_backup(destination: Path, family: str, chunk_files: list[Path], source_info: dict) -> dict:
    """Build a conventional MedveFlasher backup from verified read-only chunks."""
    full_gz = destination / "mtd16_all_flash.bin.gz"
    with full_gz.open("wb") as out:
        for chunk in chunk_files:
            with chunk.open("rb") as fh:
                shutil.copyfileobj(fh, out, 1024 * 1024)
    full_size, full_sha = _gzip_raw_info(full_gz)
    if full_size != STOCK_RESTORE_SPAN:
        raise Error(f"BootROM backup all_flash: размер {full_size}, ожидается {STOCK_RESTORE_SPAN}")

    raw_tmp = destination / ".mtd16-all-flash.raw.part"
    try:
        with gzip.open(full_gz, "rb") as src, raw_tmp.open("wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)
        if raw_tmp.stat().st_size != STOCK_RESTORE_SPAN:
            raise Error("внутренняя ошибка сборки raw all_flash")

        # Fixed physical stock slices.
        for number, (offset, size) in STOCK_RAW_SLICES.items():
            name = BOOTROM_BACKUP_NAMES[number]
            _gzip_slice(raw_tmp, offset, size, destination / f"mtd{number}_{name}.bin.gz")

        # mtd2..mtd5 are parser-created overlapping views inside nsb_master/
        # nsb_slave. A BootROM capture has no stock /proc/mtd, and the raw NSB
        # images contain overlapping vendor views, so the active A/B view cannot
        # be recovered reliably from raw bytes alone. Emit canonical accepted
        # layout A for compatibility; mtd14/mtd15/mtd16 remain authoritative.
        small_kernel = 0x003AF6DA if family == "md" else 0x003B6CC0
        small_rootfs = 0x01CC0000 if family == "md" else 0x01D00000
        master_base = STOCK_RAW_SLICES[14][0]
        with raw_tmp.open("rb") as fh:
            fh.seek(master_base)
            master = fh.read(STOCK_RAW_SLICES[14][1])
        # The vendor-reported small kernel size is not exactly the SquashFS
        # byte offset on observed stock; locate the actual hsqs start so the
        # synthesized mtd3 payload matches a normal stock dump byte-for-byte.
        _, small_rootfs_offset, _ = _bootrom_slot_geometry(master, family, "mtd14")
        slot_specs = [
            (14, 2, 3, small_kernel, small_rootfs_offset, small_rootfs),
            (15, 4, 5, 0x00480000, 0x00480000, 0x02400000),
        ]
        for slot_number, kernel_number, rootfs_number, kernel_size, rootfs_offset, rootfs_size in slot_specs:
            slot_base = STOCK_RAW_SLICES[slot_number][0]
            _gzip_slice(raw_tmp, slot_base, kernel_size, destination / f"mtd{kernel_number}_{BOOTROM_BACKUP_NAMES[kernel_number]}.bin.gz")
            _gzip_slice(raw_tmp, slot_base + rootfs_offset, rootfs_size, destination / f"mtd{rootfs_number}_{BOOTROM_BACKUP_NAMES[rootfs_number]}.bin.gz")

        # Convenience raw board-data copies.
        with raw_tmp.open("rb") as fh:
            for number, convenience in ((6, "bosa.bin"), (7, "ri.bin")):
                offset, size = STOCK_RAW_SLICES[number]
                fh.seek(offset)
                (destination / convenience).write_bytes(fh.read(size))

        sizes: dict[int, int] = dict(FIXED_EXPECTED)
        for slot_number, kernel_number, rootfs_number, kernel_size, rootfs_offset, rootfs_size in slot_specs:
            sizes[kernel_number] = kernel_size
            sizes[rootfs_number] = rootfs_size
        proc_lines = [
            f'dev:    size   erasesize  name',
        ]
        for number in EXPECTED_NUMBERS:
            proc_lines.append(f'mtd{number}: {sizes[number]:08x} 00020000 "{BOOTROM_BACKUP_NAMES[number]}"')
        write_text(destination / "proc_mtd.txt", "\n".join(proc_lines) + "\n")

        metadata = {
            "format": "medveflasher-bootrom-backup-v1",
            "kit_version": APP_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device_family": family,
            "model": "Nokia XG-040G-MD" if family == "md" else "Nokia XG-040G-MF",
            "soc": "AN7581" if family == "md" else "AN7583",
            "capture": "BootROM -> XMODEM RAM U-Boot -> rdinit=/bin/sh RAM shell -> read-only all_flash chunks -> TFTP",
            "nand_writes": False,
            "all_flash_size": full_size,
            "all_flash_sha256": full_sha,
            "recovery_probe": source_info,
            "chunks": [p.name for p in chunk_files],
            "synthetic_slot_views": "normalized accepted layout A; raw NSB bytes contain overlapping vendor views, while mtd14/mtd15/mtd16 are authoritative",
        }
        write_text(destination / "BOOTROM_BACKUP.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        write_text(destination / "BACKUP_COMPLETE", f"Nokia {family.upper()} BootROM read-only backup complete\n")

        sums = []
        for path in sorted(x for x in destination.iterdir() if x.is_file() and x.name not in ("SHA256SUMS.txt",) and not x.name.startswith(".")):
            sums.append(f"{sha_file(path)}  {path.name}")
        write_text(destination / "SHA256SUMS.txt", "\n".join(sums) + "\n")

        validation = verify_backup(destination, require_md_slot_layout=False)
        if validation.get("stock_family") != family:
            raise Error(tr(
                f"синтезированный backup определился как {validation.get('stock_family')}, ожидался {family}",
                f"the synthesized backup was detected as {validation.get('stock_family')}, expected {family}",
            ))
        return metadata
    finally:
        raw_tmp.unlink(missing_ok=True)


def _ram_shell_send_line(serial_port: RecoverySerial, line: str) -> None:
    """Send one ASCII command to the recovery ash console with conservative pacing."""
    if any(ch in line for ch in "\r\n"):
        raise Error("RAM shell command contains a newline")
    encoded = line.encode("ascii")
    for offset in range(0, len(encoded), 24):
        serial_port.write(encoded[offset:offset + 24])
        time.sleep(0.002)
    serial_port.write(b"\r")


def _assert_bootrom_backup_shell_safe(command: str) -> None:
    """Fail closed if a BootROM-backup RAM-shell command can modify flash/NAND.

    This is a runtime firewall, not a source-code grep.  Every command actually
    sent through the minimal rdinit shell is checked immediately before UART TX.
    """
    normalized = re.sub(r"\s+", " ", command.strip().lower())
    forbidden = (
        r"\bmtd\s+(?:write|erase)\b",
        r"\bnand\s+(?:write|erase)\b",
        r"\bflash(?:cp)?\s+(?:write|erase)\b",
        r"\bsaveenv\b",
        r"\bubiformat\b",
        r"\bubi(?:attach|detach|updatevol|mkvol|rmvol)\b",
        r"\bsysupgrade\b",
        r"\bdd\b[^;|\n]*\bof=/dev/(?:mtd|ubi|mmc|sd)",
    )
    for pattern in forbidden:
        if re.search(pattern, normalized, re.I):
            raise Error(tr(
                f"BootROM backup safety gate заблокировал потенциально деструктивную RAM-shell команду: {command}",
                f"BootROM backup safety gate blocked a potentially destructive RAM-shell command: {command}",
            ))


def _restore_transport_safety_selftest() -> None:
    """Prove that fallback stops permanently once a NAND write may have started."""
    global _restore_stream_transport, _restore_scp_transport, _verify_restore_readback
    orig_stream = _restore_stream_transport
    orig_scp = _restore_scp_transport
    orig_verify = _verify_restore_readback
    calls: list[str] = []
    dummy = Path(__file__)
    try:
        def prewrite_then_ok(host, local_ip, port, source, remote_name, target, transport, expected_family=None):
            calls.append(transport)
            if transport == "tftp":
                raise TransportError("synthetic pre-write failure")
        def scp_ok(host, source, target, expected_family=None):
            calls.append("scp")
        def verify_ok(host, target, raw_size, raw_sha):
            calls.append("verify")
        _restore_stream_transport = prewrite_then_ok
        _restore_scp_transport = scp_ok
        _verify_restore_readback = verify_ok
        serve_restore_payload("192.0.2.1", "192.0.2.2", 1069, dummy, "dummy.gz", "ibu", 1, "00"*32, "tftp", "md")
        if calls != ["tftp", "tcp-nc", "verify"]:
            raise Error(f"restore fallback selftest unexpected pre-write path: {calls}")

        calls.clear()
        def unknown_immediately(host, local_ip, port, source, remote_name, target, transport, expected_family=None):
            calls.append(transport)
            raise WriteStateUnknownError("synthetic post-write disconnect")
        _restore_stream_transport = unknown_immediately
        try:
            serve_restore_payload("192.0.2.1", "192.0.2.2", 1069, dummy, "dummy.gz", "ibu", 1, "00"*32, "tftp", "md")
        except WriteStateUnknownError:
            pass
        else:
            raise Error("restore fallback selftest accepted post-write retry")
        if calls != ["tftp"]:
            raise Error(f"restore fallback selftest retried after WRITE_STATE_UNKNOWN: {calls}")
    finally:
        _restore_stream_transport = orig_stream
        _restore_scp_transport = orig_scp
        _verify_restore_readback = orig_verify



def _uboot_badblock_restore_safety_selftest() -> None:
    transcript = b"""MTD device ubi bad blocks list:\r\n\t0x05d00000\r\n\t0x05d20000\r\n\t0x05de0000\r\n"""
    bad = _parse_uboot_bad_blocks(transcript, "ubi", PHYSICAL_NAND_SIZE - STOCK_BL2_SIZE)
    expected_bad = [0x05D00000, 0x05D20000, 0x05DE0000]
    if bad != expected_bad:
        raise Error(f"bad-block parser selftest mismatch: {bad}")
    _validate_stock_ubi_bad_blocks(bad)
    spans = _chunk_good_spans(0x05800000, 0x00800000, bad)
    expected_spans = [
        (0x05800000, 0x00500000),
        (0x05D40000, 0x000A0000),
        (0x05E00000, 0x00200000),
    ]
    if spans != expected_spans:
        raise Error(f"bad-block span selftest mismatch: {spans}")
    # The next nominal 8-MiB chunk must remain at 0x06000000; skipped bad PEBs
    # must never advance its physical start or compact the mtd16 image.
    next_spans = _chunk_good_spans(0x06000000, 0x00800000, bad)
    if not next_spans or next_spans[0][0] != 0x06000000:
        raise Error(f"bad-block boundary selftest shifted next chunk: {next_spans}")
    try:
        _validate_stock_ubi_bad_blocks([0x00100000])
    except Error:
        pass
    else:
        raise Error("bad-block safety selftest accepted a raw-critical stock bad block")
    try:
        _parse_uboot_bad_blocks(b"0x00000800\n", "ubi", PHYSICAL_NAND_SIZE - STOCK_BL2_SIZE)
    except Error:
        pass
    else:
        raise Error("bad-block parser accepted a non-erase-aligned offset")
    source = Path(__file__).read_text(encoding="utf-8")
    start = source.index("def perform_stock_restore_in_uboot")
    end = source.index("def _uboot_reboot_evidence", start)
    body = source[start:end]
    if "_uboot_restore_physical_chunk" not in body:
        raise Error("bad-block-aware restore helper is not wired into BootROM restore")
    legacy = 'mtd write ubi 0x{UBOOT_LOAD_ADDRESS:x} 0x{offset:x} 0x{size:x}'
    if legacy in body:
        raise Error("legacy fixed-offset whole-chunk U-Boot write returned")


def _rc23_timestamp_backup_identity_selftest() -> None:
    global _LOG_AT_LINE_START
    saved_column = _LOG_AT_LINE_START
    try:
        _LOG_AT_LINE_START = True
        stamped = _stamp_log_text("[OK] one\n[WAIT] two\n")
        lines = [line for line in stamped.splitlines() if line]
        if len(lines) != 2 or not all(
                re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ", line) for line in lines):
            raise Error(f"RC23 timestamp selftest mismatch: {stamped!r}")
        _LOG_AT_LINE_START = True
        if _stamp_log_text("\n") != "\n":
            raise Error("RC23 timestamp selftest changed blank separator lines")
    finally:
        _LOG_AT_LINE_START = saved_column
    agent = BACKUP_AGENT.read_text(encoding="utf-8")
    for token in ("DEVICE_MAC.txt", "primary_interface=", "primary_mac=", "NOKIA_BACKUP_FAMILY"):
        if token not in agent:
            raise Error(f"RC23 USB backup identity token missing: {token}")
    source = Path(__file__).read_text(encoding="utf-8")
    for token in ("_write_backup_device_mac(destination, telnet", "Backup source MAC", "DEVICE_MAC.txt"):
        if token not in source:
            raise Error(f"RC23 TFTP backup identity token missing: {token}")


def _rc24_interactive_navigation_selftest() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    required = (
        "_interactive_navigation_prompt",
        "_run_interactive_action",
        "[NAV] Задание завершено. Скрипт остаётся запущенным.",
        "[NAV] Задание завершилось ошибкой. Скрипт остаётся запущенным.",
        "_INTERACTIVE_DESTRUCTIVE_LATCH",
        "[SAFETY-LATCH]",
        "if choice == \"4\" and ok:",
        "if nav == \"exit\":",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise Error("RC24 interactive navigation selftest missing: " + ", ".join(missing))
    legacy_tokens = (
        "if firmware_" + "menu(): return",
        "if backup_" + "menu(): return",
        "if service_" + "menu(): return",
        "stock_recovery_" + "wizard()\n                return 0",
        "raise Error(tr(" + "\"неверный режим запуска\"",
    )
    present = [token for token in legacy_tokens if token in source]
    if present:
        raise Error("RC24 interactive navigation selftest found exit-on-action legacy: " + ", ".join(present))
    helper_start = source.index("def _run_interactive_action")
    helper_end = source.index("def sha_file", helper_start)
    helper = source[helper_start:helper_end]
    if "except KeyboardInterrupt" in helper or "except BaseException" in helper:
        raise Error("RC24 interactive wrapper must not swallow KeyboardInterrupt/BaseException during possible NAND activity")


def _stage1_handoff_safety_selftest() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    required = (
        "STAGE1_HANDOFF_UNKNOWN",
        "_stage1_rearm_after_confirmation",
        "automatically retrying --flash is forbidden",
        "read-only preflight after confirmation",
    )
    missing = [item for item in required if item not in source]
    if missing:
        raise Error("stage1 handoff safety selftest missing: " + ", ".join(missing))
    forbidden = "4 — Установить свой образ " + "OpenWrt (экспертный режим)"
    # Ignore this selftest's own construction and reject an actual menu print.
    if ('print(tr(\n            "' + forbidden + '"') in source:
        raise Error("duplicate custom-sysupgrade access-menu entry returned")
    menu = (
        '1 — прямой TFTP между Nokia и ПК, USB не требуется (рекомендуется)',
        '1 — полный backup напрямую на ПК через TFTP (рекомендуется)',
    )
    for text in menu:
        if text not in source:
            raise Error("TFTP-first menu invariant missing: " + text)


def _bootrom_backup_safety_selftest() -> None:
    safe = (
        "/bin/busybox cat /proc/mtd",
        "/bin/busybox dd if=/dev/mtd0 bs=4096 count=1 2>/dev/null | /bin/busybox sha256sum",
        "/bin/busybox mount -t proc proc /proc",
        "/bin/busybox ifconfig eth0 192.168.1.1 netmask 255.255.255.0 up",
    )
    blocked = (
        "mtd erase ubi",
        "mtd write image ubi",
        "nand erase 0 0x20000",
        "saveenv",
        "ubiformat /dev/mtd2",
        "ubiupdatevol /dev/ubi0_0 x",
        "sysupgrade /tmp/x.itb",
        "dd if=/tmp/x of=/dev/mtd0",
    )
    for command in safe:
        _assert_bootrom_backup_shell_safe(command)
    for command in blocked:
        try:
            _assert_bootrom_backup_shell_safe(command)
        except Error:
            continue
        raise Error(f"BootROM safety selftest failed to block: {command}")
    if _uboot_reboot_evidence(b"reset\r\nU-Boot>"):
        raise Error("post-restore reboot selftest accepted a U-Boot prompt as reboot evidence")
    if not _uboot_reboot_evidence(b"Secure key does not exist\r\nHWCONF is 1f\r\nAN7583DRAMC V0.6"):
        raise Error("post-restore reboot selftest rejected known AN7583 boot evidence")
    _verify_recovery_safe_fip(RECOVERY_FIP, "a81dbbe98acb1dabc2afcbf72e73ad87e24efa8dd88e559612a024c28ece920e", "df4803b9f70bb35050555947268fc35d61f1724814a1ea59b480689f056fa123", "AN7581 RC18 RECOVERY_SAFE FIP")
    _verify_recovery_safe_fip(MF_RECOVERY_FIP, "6d97815b5cdf905eff874062f9364ebe41a2a11f4b25944a82aea4fcbdd71e35", "3bb4cf1aa950dd212e1b5781abf55c239ff61326d5ca0c19e9f2c010285f5bb1", "AN7583 RC18 RECOVERY_SAFE FIP")


def _stock_slot_tolerance_selftest() -> None:
    """Vendor revision drift classifies family; it never becomes a write veto."""
    def variant(kernel: int, rootfs: int, kernel_slave: int, rootfs_slave: int) -> str:
        return detect_stock_backup_variant(
            {2: kernel, 3: rootfs, 4: kernel_slave, 5: rootfs_slave})

    def family(kernel: int, rootfs: int, kernel_slave: int, rootfs_slave: int) -> str:
        return detect_stock_backup_family(
            {2: kernel, 3: rootfs, 4: kernel_slave, 5: rootfs_slave})

    # Exact labels remain stable as stock evidence.
    if variant(0x003AF6DA, 0x01CC0000, 0x00480000, 0x02400000) != "MD-A":
        raise Error("stock slot selftest changed the exact MD-A label")
    if variant(0x00480000, 0x02400000, 0x003AF6DA, 0x01CC0000) != "MD-A-MIRROR":
        raise Error("stock slot selftest changed the exact MD-A-MIRROR label")
    if variant(0x003B6CC0, 0x01D00000, 0x00480000, 0x02400000) != "MF-A":
        raise Error("stock slot selftest changed the exact MF-A label")

    # Both field-observed and neighbouring in-window MD revisions remain MD.
    for image in (0x003AF742, 0x003AF61F, 0x003AF700):
        if family(0x00480000, 0x02400000, image, 0x01CB0000) != "md":
            raise Error(f"stock slot selftest rejected MD revision 0x{image:08X}")
        if variant(0x00480000, 0x02400000, image, 0x01CB0000) != "MD-A-MIRROR-REV":
            raise Error(f"stock slot selftest mislabelled MD revision 0x{image:08X}")

    # MF is symmetric: a tolerated revision remains MF evidence and is not
    # downgraded merely because its vendor image byte count differs.
    if family(0x003B6CE0, 0x01D00000, 0x00480000, 0x02400000) != "mf":
        raise Error("stock slot selftest rejected an in-window MF revision")
    if variant(0x003B6CE0, 0x01D00000, 0x00480000, 0x02400000) != "MF-A-REV":
        raise Error("stock slot selftest mislabelled a tolerated MF revision")

    # Family confusion and malformed layouts still fail closed.
    if family(0x003AF6DA, 0x01D00000, 0x00480000, 0x02400000) != "unknown":
        raise Error("stock slot selftest accepted a crossed MD/MF slot pair")
    if family(0x003AF6DA, 0x01CC0000, 0x00480000, 0x02000000) != "unknown":
        raise Error("stock slot selftest accepted a missing canonical slot pair")
    if family(0x00480000, 0x02400000, 0x003AF742, 0x01CB0001) != "unknown":
        raise Error("stock slot selftest accepted an unaligned rootfs slot size")
    if family(0x00480000, 0x02400000, 0x00390000, 0x01A00000) != "unknown":
        raise Error("stock slot selftest accepted an out-of-window revision pair")

    diagnostic = _slot_layout_diagnostic({2: 0x00480000, 3: 0x02400000, 4: 0x003AF61F, 5: 0x01CB0000})
    if "inside the MD recognition window" not in diagnostic or "outside every family window" in diagnostic:
        raise Error("stock slot selftest produced a contradictory in-window diagnostic")

    handoff = {
        0: (0x00080000, UBOOT_ERASE_SIZE, "bootloader"),
        14: (0x02880000, UBOOT_ERASE_SIZE, "nsb_master"),
        15: (0x02880000, UBOOT_ERASE_SIZE, "nsb_slave"),
        16: (STOCK_RESTORE_SPAN, UBOOT_ERASE_SIZE, "all_flash"),
    }
    _validate_install_handoff_targets(handoff)
    broken = dict(handoff)
    broken[14] = (0x02860000, UBOOT_ERASE_SIZE, "nsb_master")
    try:
        _validate_install_handoff_targets(broken)
    except Error:
        pass
    else:
        raise Error("install handoff selftest accepted a changed mtd14 target")
    broken = dict(handoff)
    broken[16] = (STOCK_RESTORE_SPAN, 0x10000, "all_flash")
    try:
        _validate_install_handoff_targets(broken)
    except Error:
        pass
    else:
        raise Error("install handoff selftest accepted a changed erase geometry")

    # Regression: neither Python install gate nor the generated launcher may
    # reintroduce a byte-exact slot allowlist for destructive authorization.
    source = Path(__file__).read_text(encoding="utf-8")
    live_start = source.index("\ndef _install_live_gate(") + 1
    live_end = source.index("\ndef _install_transport(", live_start)
    live_body = source[live_start:live_end]
    for forbidden in ("PERMANENT_WRITE_LAYOUTS", "allowed_stock_variant", "hardware-observed layouts"):
        if forbidden in live_body:
            raise Error(f"install policy selftest found stale slot write gate: {forbidden}")
    launcher = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    for forbidden in (
        "permanent write is enabled only for hardware-confirmed MF-A",
        "permanent write is enabled only for hardware-observed layouts",
    ):
        if forbidden in launcher:
            raise Error(f"launcher policy selftest found stale slot write gate: {forbidden}")

def _readonly_flow_selftest() -> None:
    """Flows declared read-only must not be able to enable stock services."""
    source = Path(__file__).read_text(encoding="utf-8")
    for wizard in ("stock_audit_wizard", "firmware_capabilities_wizard"):
        start = source.index(f"def {wizard}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        if "allow_service_provisioning=True" in body:
            raise Error(f"read-only selftest: {wizard} enables stock service provisioning")
    for wizard in ("stock_audit_wizard", "firmware_capabilities_wizard"):
        start = source.index(f"def {wizard}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        if "_stock_operational_web_access()" in body:
            raise Error(f"read-only selftest: {wizard} retained an operational Web session")
    backup_start = source.index("def backup_only_wizard(")
    backup_end = source.find("\ndef ", backup_start + 1)
    backup_body = source[backup_start:backup_end if backup_end != -1 else len(source)]
    if "_stock_operational_web_access()" not in backup_body:
        raise Error("operational Web selftest: backup no longer retains the provisioning session")
    install_start = source.index("def _install_access(")
    install_end = source.find("\ndef ", install_start + 1)
    install_body = source[install_start:install_end if install_end != -1 else len(source)]
    if "_stock_operational_web_access()" not in install_body:
        raise Error("operational Web selftest: MF install no longer retains the provisioning session")
    # The opt-in must stay opt-in: a True default would silently re-arm every
    # caller that does not pass the flag.  Check each entry point's own
    # signature rather than a global count, which this selftest's source would
    # itself perturb.
    for name in ("login_root_profile_dynamic", "login_root_md", "login_root_family"):
        start = source.index(f"def {name}(")
        signature = source[start:source.index(") -> Telnet:", start)]
        if "allow_service_provisioning: bool = False" not in signature:
            raise Error(f"read-only selftest: {name} no longer defaults service provisioning to off")


def _rc25_readonly_by_fact_selftest() -> None:
    """Reading must not depend on recognising a vendor slot revision."""
    source = Path(__file__).read_text(encoding="utf-8")

    start = source.index("\ndef _stock_live_geometry_preflight(")
    end = source.find("\ndef ", start + 1)
    preflight = source[start:end if end != -1 else len(source)]
    if "require_slot_family: bool = True" not in preflight:
        raise Error("read-by-fact selftest: the preflight lost its require_slot_family switch")
    if "if require_slot_family:" not in preflight:
        raise Error("read-by-fact selftest: an unrecognised slot revision is unconditionally fatal again")
    # The evidence a read-only capture actually relies on must stay mandatory.
    for token in ("FIXED_EXPECTED", "sysfs", "0x20000"):
        if token not in preflight:
            raise Error(f"read-by-fact selftest: the preflight stopped proving {token}")

    # Capture and diagnostics read; only the installer chooses a payload.
    for name, expected in (
        ("backup_tftp", False),
        ("backup_only_wizard", False),
        ("firmware_capabilities_wizard", False),
        ("_install_live_gate", True),
    ):
        start = source.index(f"\ndef {name}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        if "_stock_live_geometry_preflight(" not in body:
            raise Error(f"read-by-fact selftest: {name} no longer runs the live geometry preflight")
        relaxed = "require_slot_family=False" in body
        if relaxed == expected:
            state = "reads by fact" if expected else "requires a recognised family"
            raise Error(f"read-by-fact selftest: {name} unexpectedly {state}")

    # Device identity comes from the MAC, so it must be recorded even when the
    # slot revision is unknown.
    start = source.index("\ndef backup_tftp(")
    end = source.find("\ndef ", start + 1)
    capture = source[start:end if end != -1 else len(source)]
    if "_write_backup_device_mac(" not in capture:
        raise Error("read-by-fact selftest: the capture stopped recording DEVICE_MAC.txt")

    # An older release left an exact-MD table behind that rejected every MF
    # backup, including the hardware-confirmed exact MF-A. It must not come back.
    # The token is assembled so this check does not match its own source.
    stale_gate = "rc" + "12"
    if stale_gate in source.replace('"rc" + "12"', ""):
        raise Error("read-by-fact selftest: a stale release-gate reference is present again")
    start = source.index("\ndef verify_backup(")
    end = source.find("\ndef ", start + 1)
    validator = source[start:end if end != -1 else len(source)]
    if 'family in ("md", "mf")' not in validator:
        raise Error("read-by-fact selftest: verify_backup pins observed slots for one family only")


def _rc25a_recovery_reachability_selftest() -> None:
    """A fire-and-forget reboot, an honest slot label, and a verified write target."""
    source = Path(__file__).read_text(encoding="utf-8")

    # A. The recovery reboot must not be able to unwind its own TFTP server.
    start = source.index("\ndef ssh_run(")
    end = source.find("\ndef ", start + 1)
    runner = source[start:end if end != -1 else len(source)]
    if "allow_timeout" not in runner:
        raise Error("recovery selftest: ssh_run lost its allow_timeout switch")
    if "if not allow_timeout:" not in runner:
        raise Error("recovery selftest: an SSH timeout raises unconditionally again")
    start = source.index("\ndef boot_recovery_from_production_openwrt(")
    end = source.find("\ndef ", start + 1)
    recovery = source[start:end if end != -1 else len(source)]
    if "reboot -f" not in recovery:
        raise Error("recovery selftest: the recovery reboot command is gone")
    reboot_call = recovery[recovery.index("reboot -f"):]
    reboot_call = reboot_call[:reboot_call.index(")") + 1]
    if "allow_timeout=True" not in reboot_call:
        raise Error("recovery selftest: the recovery reboot can raise a timeout into its caller")

    # B. A tolerated label names the profile it resembles, not the slot orientation.
    def variant(kernel: int, rootfs: int, kernel_slave: int, rootfs_slave: int) -> str:
        return detect_stock_backup_variant(
            {2: kernel, 3: rootfs, 4: kernel_slave, 5: rootfs_slave})
    near_b = 0x003B6D40 + 0x20
    if variant(near_b, 0x01D10000, 0x00480000, 0x02400000) != "MF-B-REV":
        raise Error("recovery selftest: a revision beside MF-B is not labelled MF-B-REV")
    if variant(0x00480000, 0x02400000, near_b, 0x01D10000) != "MF-B-MIRROR-REV":
        raise Error("recovery selftest: a mirrored revision beside MF-B lost its profile")
    near_a = 0x003B6CC0 + 0x20
    if variant(near_a, 0x01D00000, 0x00480000, 0x02400000) != "MF-A-REV":
        raise Error("recovery selftest: a revision beside MF-A changed label")
    if variant(0x00480000, 0x02400000, 0x003AF61F, 0x01CB0000) != "MD-A-MIRROR-REV":
        raise Error("recovery selftest: the observed MD revision changed label")

    # C. The launcher proves the partition it is about to erase, not only the
    # slot it happens to be running from.
    launcher = (Path(__file__).resolve().parent / "stock-launcher.sh.in").read_text(encoding="utf-8")
    if "verify_slot_alias master 'transition-target'" not in launcher:
        raise Error("launcher selftest: the transition target is unverified when the slave slot is active")
    start = launcher.index("verify_stock_boot_path()")
    end = launcher.index("\n}", start)
    boot_path = launcher[start:end]
    if boot_path.count("verify_slot_alias") < 2:
        raise Error("launcher selftest: only one slot alias is proven before the destructive stage")
    if 'if [ "$active_slot" != master ]' not in boot_path:
        raise Error("launcher selftest: the write-target check is no longer conditional on the active slot")


def _rc26_restore_diagnostic_selftest() -> None:
    """A fail-closed gate must say what it saw, not only that it refused."""
    recovery = ('mtd0: 10000000 00020000 "all_flash"', 'mtd1: 00020000 00020000 "bl2"',
                'mtd2: 0ffe0000 00020000 "ibu"')
    production = ('mtd0: 10000000 00020000 "all_flash"', 'mtd1: 00020000 00020000 "bl2"',
                  'mtd2: 0ffe0000 00020000 "ubi"')

    # A third-party snapshot: the board name never matches, so the layout is not
    # the interesting half and must not be blamed.
    foreign = ('BOARD=nokia,xg-040g-md\nROOT=ubifs\n'
               'mtd0: 10000000 00020000 "all_flash"\nmtd2: 0ffe0000 00020000 "ubi"\n')
    text = _restore_environment_diagnostic(foreign, "md", False, recovery, production)
    for token in ("nokia,xg-040g-md", "nokia,xg-040g-md-ubi", "ROOT=ubifs", "[SSH-RAW]"):
        if token not in text:
            raise Error(f"restore diagnostic selftest: refusal does not report {token}")
    if "не хватает" in text:
        raise Error("restore diagnostic selftest: a board-name mismatch was reported as a layout mismatch")

    # Right board, wrong layout: name the markers that are missing.
    staged = ('BOARD=nokia,xg-040g-md-ubi\nROOT=tmpfs\n'
              'mtd0: 00080000 00020000 "bootloader"\nmtd2: 003af61f 00020000 "kernel"\n')
    text = _restore_environment_diagnostic(staged, "md", True, recovery, production)
    if 'mtd2: 0ffe0000 00020000 "ibu"' not in text:
        raise Error("restore diagnostic selftest: the missing layout markers are not listed")
    if '"bootloader"' not in text:
        raise Error("restore diagnostic selftest: the observed /proc/mtd is not shown")

    # Board identity and running system are separate questions.
    md_upstream = ('BOARD=nokia,xg-040g-md\nCOMPAT=nokia,xg-040g-md airoha,an7581\n'
                   'mtd0: 10000000 00020000 "all_flash"\nmtd1: 00020000 00020000 "bl2"\n'
                   'mtd2: 0ffe0000 00020000 "ubi"\n')
    identity = classify_restore_identity(md_upstream)
    if identity["family"] != "md":
        raise Error("restore diagnostic selftest: an upstream MD board is no longer recognised as MD")
    if identity["kit_built"]:
        raise Error("restore diagnostic selftest: a board without the -ubi suffix was claimed as kit-built")
    if identity["state"] != "production":
        raise Error("restore diagnostic selftest: an all-in-UBI layout was not recognised as production")
    text = _restore_environment_diagnostic(md_upstream, "md", False, recovery, production)
    if "по решению, а не по ошибке" not in text:
        raise Error("restore diagnostic selftest: a matching layout from another builder is reported as a detection failure")

    soc_only = 'BOARD=\nCOMPAT=airoha,an7581\nmtd0: 10000000 00020000 "all_flash"\n'
    if classify_restore_identity(soc_only)["family"] != "md":
        raise Error("restore diagnostic selftest: the SoC alone no longer identifies the MD family")
    staged_identity = classify_restore_identity(
        'BOARD=nokia,xg-040g-md-ubi\nCOMPAT=nokia,xg-040g-md-ubi airoha,an7581\n'
        'mtd14: 02880000 00020000 "nsb_master"\n')
    if staged_identity["state"] != "stock-layout":
        raise Error("restore diagnostic selftest: a stage-1 transition is not recognised by its stock layout")

    # A field device published mtd2=0x0FF00000 where this kit's own build
    # publishes 0x0FFE0000 — seven eraseblocks the other build leaves unused. The
    # restore never touches that partition, so its size is evidence, not a gate.
    field = ('BOARD=nokia,xg-040g-md-ubi\nCOMPAT=nokia,xg-040g-md-ubi airoha,an7581\n'
             'mtd0: 10000000 00020000 "all_flash"\nmtd1: 00020000 00020000 "bl2"\n'
             'mtd2: 0ff00000 00020000 "ubi"\n')
    if _all_in_ubi_shape(field) != "production":
        raise Error("restore shape selftest: a field all-in-UBI size is rejected again")
    kit = field.replace("0ff00000", "0ffe0000")
    if _all_in_ubi_shape(kit) != "production":
        raise Error("restore shape selftest: the kit's own all-in-UBI size is rejected")
    if _all_in_ubi_shape(field.replace('"ubi"', '"ibu"')) != "recovery":
        raise Error("restore shape selftest: the recovery partition is no longer recognised")

    # What the hardware and the boot contract fix stays exact.
    for broken, why in (
            (field.replace("mtd0: 10000000", "mtd0: 08000000"), "a chip that is not 256 MiB"),
            (field.replace('mtd1: 00020000 00020000 "bl2"', 'mtd1: 00040000 00020000 "bl2"'), "a BL2 block that is not 0x20000"),
            (field.replace('mtd2: 0ff00000 00020000', 'mtd2: 0ff00000 00040000'), "a foreign erase size"),
            (field.replace('"ubi"', '"rootfs"'), "a partition that is neither ubi nor ibu")):
        if _all_in_ubi_shape(broken) != "other":
            raise Error(f"restore shape selftest: {why} is accepted as all-in-UBI")

    # The refusal itself must carry the diagnostic, not just build one.
    source = Path(__file__).read_text(encoding="utf-8")
    start = source.index("\ndef inspect_restore_environment(")
    end = source.find("\ndef ", start + 1)
    body = source[start:end if end != -1 else len(source)]
    if body.count("_restore_environment_diagnostic(") < 2:
        raise Error("restore diagnostic selftest: the refusal no longer includes what was observed")


def _ram_worker_autonomy_selftest() -> None:
    """After the first destructive operation nothing may come from stock NAND.

    mtd3 is a view inside mtd14, so erasing the transition target takes the stock
    rootfs with it. Every executable, library, shell helper and logging primitive
    the worker still needs after that point must already be in tmpfs — including
    the channel that would carry the explanation if something goes wrong.
    """
    launcher = (Path(__file__).resolve().parent / "stock-launcher.sh.in").read_text(encoding="utf-8")
    start = launcher.index("\nram_flash() {")
    end = launcher.index("\nusage() {", start)
    worker = launcher[start:end]

    # The worker must not start a mirror: tee and mkfifo resolve through PATH
    # from the rootfs that is about to disappear.
    for token in ("mkfifo", "nokia_begin_output_mirror", "tee -a"):
        if token in worker:
            raise Error(f"RAM worker selftest: {token} runs inside the destructive path")
    if 'if [ "${1:-}" != --ram-flash ]; then' not in launcher:
        raise Error("RAM worker selftest: the output mirror is started for --ram-flash again")

    # Its log must live in tmpfs, never under the bundle directory on stock NAND.
    if "SCRIPT_DIR" in worker:
        raise Error("RAM worker selftest: the worker references the stock-NAND bundle directory")
    if '>> "$ramlog" 2>&1 < /dev/null &' not in launcher:
        raise Error("RAM worker selftest: worker output no longer lands in the tmpfs log")
    if "> /dev/null 2>&1 < /dev/null &" in launcher:
        raise Error("RAM worker selftest: worker output is discarded again")
    if ': > "$ramlog"' not in launcher:
        raise Error("RAM worker selftest: the tmpfs log is not created before the worker starts")

    # Every command after staging goes through the staged BusyBox/mtd_debug.
    forbidden = []
    for line in worker.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for bare in ("dd ", "sha256sum ", "sync", "sleep ", "reboot", "tr ", "wc "):
            if stripped.startswith(bare):
                forbidden.append(stripped[:60])
    if forbidden:
        raise Error("RAM worker selftest: bare stock-NAND commands in the worker: " + "; ".join(forbidden))

    # The dispatcher and the launch must agree on the worker contract.
    launches = re.findall(r"--ram-flash ([^\n]*)", launcher)
    argument_counts = {len(entry.split()) for entry in launches if entry.strip().startswith('"$STAGE_RAM"')}
    if argument_counts != {8}:
        raise Error(f"RAM worker selftest: the launch passes {argument_counts} arguments, expected 8")
    if '[ "$#" -eq 9 ] || exit 2' not in launcher:
        raise Error("RAM worker selftest: the dispatcher no longer matches the launch arity")


def _rc26_console_log_split_selftest() -> None:
    """The console shows what was printed; work/logs/*.log carries the clock."""
    source = Path(__file__).read_text(encoding="utf-8")

    # Nothing on the console path may stamp. RC23 added the prefix so PC output
    # could be lined up against UART events, which is a job for the file read
    # afterwards, not for the screen the operator is working on.
    start = source.index("\ndef _localized_print(")
    end = source.find("\ndef ", start + 1)
    printer = source[start:end if end != -1 else len(source)]
    if "_stamp_log_text" in printer:
        raise Error("console/log selftest: the console print stamps again")
    for name in ("_localized_input", "_localized_getpass"):
        start = source.index(f"\ndef {name}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        if "_stamp_log_text" in body or "_timestamp_text" in body:
            raise Error(f"console/log selftest: {name} stamps the prompt on screen")

    # The log side must stamp, and diagnostics that bypass the tee stamp themselves.
    start = source.index("class _ConsoleTee:")
    end = source.index("\ndef _write_session_only(")
    tee = source[start:end]
    if "_stamp_log_text(clean)" not in tee:
        raise Error("console/log selftest: the log copy is no longer timestamped")
    if "self.console.write(text)" not in tee:
        raise Error("console/log selftest: the console no longer receives the raw text")
    start = source.index("\ndef _write_session_only(")
    end = source.find("\ndef ", start + 1)
    diagnostics = source[start:end if end != -1 else len(source)]
    if "_stamp_log_text(" not in diagnostics:
        raise Error("console/log selftest: session-only diagnostics lost their timestamp")

    # The console-side suppression machinery is gone; nothing may reintroduce it.
    for token in ("menu_ui", "_MENU_RENDERING", "_stamp_stream", "_timestamp_text"):
        if token in source.replace('"' + token + '"', "").replace("(\"" + token + "\")", ""):
            raise Error(f"console/log selftest: {token} came back")

    # A stamp is a line prefix: live mirrors write partial chunks, and stamping
    # each one cut the device's own output apart — "Press x" arrived as
    # "P[12:24:31] ress x".
    global _LOG_AT_LINE_START
    saved_column = _LOG_AT_LINE_START
    try:
        _LOG_AT_LINE_START = True
        if not _stamp_log_text("P").startswith("["):
            raise Error("console/log selftest: a line beginning mid-buffer lost its timestamp")
        for chunk in ("ress", " x"):
            if _stamp_log_text(chunk) != chunk:
                raise Error("console/log selftest: a chunk continuing a line was timestamped")
        if _stamp_log_text("\n") != "\n":
            raise Error("console/log selftest: a bare line terminator gained a timestamp")
        if not _stamp_log_text("next line\n").startswith("["):
            raise Error("console/log selftest: a fresh line lost its timestamp")
        if not _LOG_AT_LINE_START:
            raise Error("console/log selftest: the column was not reset by a line terminator")
        _stamp_log_text("[XMODEM] 1/887")
        if _stamp_log_text("\r[XMODEM] 2/887").startswith("["):
            raise Error("console/log selftest: a progress redraw collected a timestamp")
    finally:
        _LOG_AT_LINE_START = saved_column


def _rc25_release_identity_selftest() -> None:
    """One release identity, declared in several files, must never drift apart.

    The kit ships the version in six places because different consumers read
    different files; this selftest is what keeps the duplication honest.
    """
    root = Path(__file__).resolve().parent
    declarations: dict[str, str] = {
        "APP_VERSION": APP_VERSION,
        "BUILD_TAG": BUILD_TAG.replace("medveflasher-", ""),
    }
    for label, path in (("data/VERSION", root / "VERSION"), ("VERSION", root.parent / "VERSION")):
        if path.is_file():
            declarations[label] = path.read_text(encoding="utf-8").strip()

    manifest_path = root / "MANIFEST.json"
    if manifest_path.is_file():
        release = json.loads(manifest_path.read_text(encoding="utf-8")).get("release") or {}
        if release.get("version"):
            declarations["MANIFEST.release.version"] = str(release["version"])
        if release.get("build_tag"):
            declarations["MANIFEST.release.build_tag"] = str(release["build_tag"]).replace("medveflasher-", "")

    capabilities_path = root / "FIRMWARE_CAPABILITIES.json"
    if capabilities_path.is_file():
        version = json.loads(capabilities_path.read_text(encoding="utf-8")).get("version")
        if version:
            declarations["FIRMWARE_CAPABILITIES.version"] = str(version)

    launcher_path = root / "stock-launcher.sh.in"
    if launcher_path.is_file():
        match = re.search(r"RELEASE_VERSION='([^']+)'", launcher_path.read_text(encoding="utf-8"))
        if match:
            declarations["stock-launcher.sh.in"] = match.group(1)

    distinct = sorted(set(declarations.values()))
    if len(distinct) != 1:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(declarations.items()))
        raise Error(f"release identity selftest: version declarations disagree: {detail}")
    if re.search(r"fix\d*$", distinct[0]):
        raise Error(f"release identity selftest: repository releases carry no fix suffix, got {distinct[0]}")


def _rc29_restore_ssh_auth_selftest() -> None:
    """A restore over a running OpenWrt must ask for root's password, once.

    Both deterministic probe modes pass ``batch_mode=True``, and ssh_run gives a
    batch probe ``/dev/null`` on stdin. That is correct for the polling loops --
    a detector must succeed or fail, never wait invisibly -- but on first contact
    with an *installed* OpenWrt it turned a password-protected root into
    "timed out": ssh was told to refuse to ask. The restore then ended before
    reaching arm_one_shot_recovery_boot, which could always have prompted.

    So: batch first, one interactive retry, and only where an operator is really
    at the console. Anything else keeps the non-interactive path.
    """
    # What separates "authentication was refused" from "nothing answered".
    for message, expected, why in (
            ("ssh: connect to host 192.168.1.1 port 22: Connection refused", False, "a refused connection"),
            ("\u0442\u0430\u0439\u043c-\u0430\u0443\u0442 SSH-\u043a\u043e\u043c\u0430\u043d\u0434\u044b", False, "an SSH timeout"),
            ("ssh: connect to host 192.168.1.1 port 22: No route to host", False, "an absent host"),
            ("Permission denied (publickey,password).", True, "a refused password"),
            ("root@192.168.1.1: Permission denied", True, "a refused root login")):
        if _restore_root_password_hint([message]) is not expected:
            raise Error(f"restore SSH auth selftest: {why} is classified wrong")

    # An interactive prompt is only offered to an operator who can answer it.
    real_stdin, real_stdout = sys.stdin, sys.stdout

    class _FakeStream:
        def __init__(self, tty): self._tty = tty
        def isatty(self): return self._tty

    try:
        sys.stdin, sys.stdout = _FakeStream(False), _FakeStream(True)
        if _console_can_prompt():
            raise Error("restore SSH auth selftest: a piped stdin is treated as an operator console")
        sys.stdin, sys.stdout = _FakeStream(True), _FakeStream(False)
        if _console_can_prompt():
            raise Error("restore SSH auth selftest: a redirected stdout is treated as an operator console")
        sys.stdin, sys.stdout = _FakeStream(True), _FakeStream(True)
        if not _console_can_prompt():
            raise Error("restore SSH auth selftest: a real console is refused the prompt")
        os.environ["NOKIA_NONINTERACTIVE"] = "1"
        try:
            if _console_can_prompt():
                raise Error("restore SSH auth selftest: NOKIA_NONINTERACTIVE no longer suppresses the prompt")
        finally:
            os.environ.pop("NOKIA_NONINTERACTIVE", None)
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout

    source = Path(__file__).read_text(encoding="utf-8")

    def _body(name: str) -> str:
        start = source.index(f"\ndef {name}(")
        end = source.find("\ndef ", start + 1)
        return source[start:end if end != -1 else len(source)]

    probe = _body("_restore_probe_ssh")
    if "batch_mode=True" not in probe:
        raise Error("restore SSH auth selftest: the deterministic probes no longer run in batch mode")
    loop_at = probe.index("for minimal in modes")
    guard = "allow_interactive and _restore_root_password_hint(errors) and _console_can_prompt()"
    if guard not in probe:
        raise Error("restore SSH auth selftest: the interactive retry lost one of its three guards")
    if probe.index(guard) < loop_at:
        raise Error("restore SSH auth selftest: the interactive retry runs before the batch probes")
    # Exactly one attempt may inherit the console, so a wrong password cannot
    # turn the detector into an unbounded chain of prompts.
    interactive_calls = [line for line in probe.splitlines()
                         if "ssh_run(" in line and "batch_mode" not in line]
    if len(interactive_calls) != 1:
        raise Error(f"restore SSH auth selftest: expected one interactive ssh_run, found {len(interactive_calls)}")

    inspect = _body("inspect_restore_environment")
    if "allow_interactive: bool = False" not in inspect:
        raise Error("restore SSH auth selftest: detection no longer defaults to non-interactive")
    if "allow_interactive=allow_interactive" not in inspect:
        raise Error("restore SSH auth selftest: detection no longer forwards the operator's console")

    # Only the operator-facing detection may opt in. The polling loops run while
    # the device reboots, with nobody watching and nothing to type into.
    opt_in = "allow_interactive" + "=True"
    marker = "\ndef " + "_rc29_restore_ssh_auth_selftest("
    outside = source[:source.index(marker)] + source[source.find("\ndef ", source.index(marker) + 1):]
    if outside.count(opt_in) != 1:
        raise Error(f"restore SSH auth selftest: {outside.count(opt_in)} call sites enable the prompt, expected 1")
    if opt_in not in _body("stock_restore_running_wizard"):
        raise Error("restore SSH auth selftest: the operator-facing detection is no longer the one that may prompt")

    # The reason batch probes cannot hang: ssh never sees the console.
    if "elif batch_mode or minimal_auth:\n        stdin_target = subprocess.DEVNULL" not in source:
        raise Error("restore SSH auth selftest: batch probes may inherit console input again")

    # The readiness loop must classify with the shared structural check. It used
    # to compare whole /proc/mtd lines literally, so the field device that
    # publishes 0x0FF00000 for its UBI partition never matched "production": the
    # loop ran to its deadline and the restore reported that SSH was not stable,
    # while SSH had been answering all along. That is the timeout the operator saw.
    ready = _body("wait_for_stable_openwrt")
    stale = "0ff" + "e0000"
    if stale in ready:
        raise Error("restore SSH auth selftest: the readiness loop gates on a literal UBI size again")
    if "_all_in_ubi_shape(output)" not in ready:
        raise Error("restore SSH auth selftest: the readiness loop no longer uses the shared shape check")
    field = ('mtd0: 10000000 00020000 "all_flash"\nmtd1: 00020000 00020000 "bl2"\n'
             'mtd2: 0ff00000 00020000 "ubi"\n')
    if _all_in_ubi_shape(field) != "production":
        raise Error("restore SSH auth selftest: the field UBI size is not recognised as production")
    # Both branches of that loop are deterministic: one prompt belongs to
    # detection, not to a loop that runs it twice per call, three times per attempt.
    if "ssh_run(" in ready and "_restore_probe_ssh(" not in ready:
        raise Error("restore SSH auth selftest: the readiness loop probes interactively again")
    for line in ready.splitlines():
        if "ssh_run(" in line and "_restore_probe_ssh(" not in line:
            raise Error("restore SSH auth selftest: the readiness loop can prompt on every iteration")

    # Authenticating once and leaving a key is what makes that possible.
    key_command = _restore_authorized_key_command("ssh-ed25519 AAAAC3Nz test@pc")
    if "grep -qxF" not in key_command or "authorized_keys" not in key_command:
        raise Error("restore SSH auth selftest: the key install is no longer idempotent")
    if "'ssh-ed25519 AAAAC3Nz test@pc'" not in key_command:
        raise Error("restore SSH auth selftest: the public key reaches the device shell unquoted")
    fallback = probe[probe.index(guard):]
    if "_restore_authorized_key_command(" not in fallback:
        raise Error("restore SSH auth selftest: the one interactive login no longer installs the session key")
    if "_RESTORE_SESSION_KEY.pop(host, None)" not in fallback:
        raise Error("restore SSH auth selftest: an unverified session key is kept instead of dropped")
    run = _body("ssh_run")
    if '"-o", "IdentitiesOnly=yes", "-i", str(identity)' not in run:
        raise Error("restore SSH auth selftest: later calls no longer offer the session key")


def _rc25_lan1_advisory_selftest() -> None:
    """LAN1 detection must classify correctly and must stay advisory."""
    if _lan1_verdict_from_speed(2500) != "lan1":
        raise Error("LAN1 selftest: a 2.5G link was not attributed to LAN1")
    if _lan1_verdict_from_speed(5000) != "lan1":
        raise Error("LAN1 selftest: a 5G link was not attributed to LAN1")
    # A fantasy speed is a tunnel, not a 2.5G port. An observed throne-tun
    # advertised 100000 Mbit/s and was announced as LAN1.
    for absurd in (10000, 100000):
        if _lan1_verdict_from_speed(absurd) != "virtual":
            raise Error(f"LAN1 selftest: {absurd} Mbit/s was attributed to a cabled port")
    if _lan1_verdict_from_speed(1000) != "other":
        raise Error("LAN1 selftest: a gigabit link was misattributed to LAN1")
    for value in (None, 0, -1):
        if _lan1_verdict_from_speed(value) != "unknown":
            raise Error(f"LAN1 selftest: speed {value!r} must stay unknown rather than guess a port")

    # Unreachable hosts and missing interfaces must degrade to an advisory, not
    # an exception raised into a restore path.
    verdict, evidence = detect_lan1_uplink("192.0.2.1")
    if verdict not in ("lan1", "other", "virtual", "unknown"):
        raise Error(f"LAN1 selftest: unexpected verdict {verdict!r}")
    if set(evidence) != {"host", "local_ip", "interface", "speed_mbit", "hardware"}:
        raise Error("LAN1 selftest: evidence keys changed")

    source = Path(__file__).read_text(encoding="utf-8")
    for name in (
        "install_openwrt_wizard",
        "backup_only_wizard",
        "stock_restore_running_wizard",
        "stock_recovery_wizard",
        "bootrom_backup_wizard",
        "resume_stage2_wizard",
    ):
        start = source.index(f"\ndef {name}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        if "warn_if_lan1_uplink(" not in body:
            raise Error(f"LAN1 selftest: {name} starts without the LAN1 advisory")

    start = source.index("\ndef warn_if_lan1_uplink(")
    end = source.find("\ndef ", start + 1)
    advisory = source[start:end if end != -1 else len(source)]
    # An operator declining is a cancellation; a detected LAN1 on its own must
    # never raise, or the advisory would have become a gate. Exactly one raise
    # may exist, and it must be the one guarded by the operator's answer.
    raises = [line.strip() for line in advisory.splitlines() if line.strip().startswith("raise ")]
    if len(raises) != 1:
        raise Error(f"LAN1 selftest: the advisory must contain exactly one raise, found {len(raises)}")
    if "операция отменена оператором" not in advisory:
        raise Error("LAN1 selftest: the advisory's only raise is no longer the operator cancellation")
    if 'if answer in {"n", "no", "н", "нет"}:' not in advisory:
        raise Error("LAN1 selftest: cancellation is no longer gated on the operator's answer")
    if "[Y/n]" not in advisory:
        raise Error("LAN1 selftest: the prompt no longer defaults to continuing")


def _ram_shell_command(serial_port: RecoverySerial, log, command: str, timeout: int = 120, *, echo_label: bool = True) -> bytes:
    """Run a command in the PID1 BusyBox ash recovery shell and return its transcript.

    BootROM backup deliberately does not use SSH.  A unique marker is emitted on
    the UART after each command, so command completion and the shell exit status
    are deterministic even when no visible prompt is printed.
    """
    _assert_bootrom_backup_shell_safe(command)
    marker = f"__MEDVEFLASHER_RAMSH_{time.time_ns():x}__"
    if echo_label:
        print(f"[RAM-SHELL] {command}")
    # Do not reset RX here: late kernel diagnostics are valuable evidence and do
    # not confuse the unique completion marker.
    line = f"{command}; __mf_rc=$?; echo {marker}_RC_$__mf_rc"
    _ram_shell_send_line(serial_port, line)
    deadline = time.time() + timeout
    transcript = bytearray()
    pattern = re.compile(re.escape(marker.encode("ascii")) + rb"_RC_([0-9]+)(?:[\r\n]|$)")
    while time.time() < deadline:
        data = serial_port.read(4096, 0.25)
        if not data:
            continue
        _uart_log_write(log, data)
        transcript.extend(data)
        if len(transcript) > 2 * 1024 * 1024:
            del transcript[:-1024 * 1024]
        match = pattern.search(bytes(transcript))
        if match is None:
            continue
        rc = int(match.group(1))
        if rc != 0:
            raise Error(f"RAM shell command failed with code {rc}: {command}")
        return bytes(transcript)
    raise Error(f"тайм-аут RAM shell-команды: {command}")


def _wait_backup_recovery_shell(serial_port: RecoverySerial, log, timeout: int = 180) -> None:
    """Wait for the rdinit=/bin/sh recovery shell and prove command execution."""
    deadline = time.time() + timeout
    tail = bytearray()
    saw_kernel = False
    saw_rdinit = False
    while time.time() < deadline:
        data = serial_port.read(4096, 0.25)
        if data:
            _uart_log_write(log, data)
            tail.extend(data)
            if len(tail) > 131072:
                del tail[:-65536]
            low = bytes(tail).lower()
            if b"starting kernel" in low or b"booting linux on physical cpu" in low:
                saw_kernel = True
            if b"run /bin/sh as init process" in low or b"starting init: /bin/sh" in low:
                saw_rdinit = True
            if b"kernel panic" in low:
                raise Error("RAM recovery kernel panic before shell")
        if saw_rdinit:
            break
    if not saw_kernel:
        raise Error("не подтверждён запуск RAM recovery kernel")
    if not saw_rdinit:
        raise Error("RAM recovery kernel не подтвердил rdinit=/bin/sh")
    time.sleep(0.4)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            out = _ram_shell_command(serial_port, log, "/bin/busybox echo MEDVEFLASHER_RAM_SHELL_READY", timeout=6, echo_label=False)
            if b"MEDVEFLASHER_RAM_SHELL_READY" in out:
                break
        except Error as exc:
            last_error = exc
            _write_session_only(f"[RAM-SHELL] readiness attempt={attempt}/3 error={exc}")
            time.sleep(0.5)
    else:
        raise Error(f"RAM recovery shell marker not returned: {last_error or 'no marker'}")
    print(tr(
        "[OK] Минимальная RAM shell готова; procd/Dropbear/UBI init не запускались.",
        "[OK] Minimal RAM shell is ready; procd/Dropbear/UBI init were not started.",
    ))


def _boot_backup_recovery_fit(serial_port: RecoverySerial, log, local_ip: str, router_ip: str, profile: dict[str, object]) -> None:
    source = Path(profile["backup_initramfs"])
    expected_sha = str(profile["backup_initramfs_sha"])
    if not source.is_file() or sha_file(source) != expected_sha:
        raise Error(f"backup recovery FIT повреждён или отсутствует: {source}")
    family = str(profile["family"])
    remote_name = f"nokia-{family}-bootrom-backup-recovery.itb"
    ready = threading.Event()
    result = TftpResult()
    thread = threading.Thread(
        target=serve_tftp_get,
        args=(local_ip, 69, source, remote_name, router_ip, ready, result),
        kwargs={"timeout": 300, "maximum_block_size": 1468}, daemon=True,
    )
    thread.start()
    if not ready.wait(10) or result.error:
        raise Error(f"TFTP RAM recovery server не запустился: {result.error or 'timeout'}")
    for command in (
        "setenv ethaddr 02:00:00:04:0d:10",
        "setenv eth1addr 02:00:00:04:0d:11",
        f"setenv ipaddr {router_ip}",
        f"setenv serverip {local_ip}",
        "setenv netmask 255.255.255.0",
        "setenv autoload no",
        # Use only the initramfs as a minimal command environment.  In
        # particular, do not pass ubi.mtd/root and do not run OpenWrt /init.
        "setenv bootargs console=ttyS0,115200 rdinit=/bin/sh",
    ):
        uboot_command(serial_port, log, command)
    transcript = uboot_command(serial_port, log, f"tftpboot 0x{UBOOT_LOAD_ADDRESS:x} {remote_name}", timeout=360)
    thread.join(10)
    if thread.is_alive() or result.error or result.bytes_transferred != source.stat().st_size:
        raise Error(f"RAM recovery FIT передан не полностью: {result.error or result.bytes_transferred}")
    if b"bytes transferred" not in transcript.lower() and b"done" not in transcript.lower():
        raise Error("U-Boot не подтвердил TFTP RAM recovery FIT")
    info = uboot_command(serial_port, log, f"iminfo 0x{UBOOT_LOAD_ADDRESS:x}", timeout=60)
    if b"fit image found" not in info.lower() or b"bad" in info.lower():
        raise Error("iminfo не подтвердил RAM recovery FIT")
    print(tr(
        "[U-Boot] FIT проверен; запускаю минимальную read-only RAM shell (rdinit=/bin/sh).",
        "[U-Boot] FIT verified; booting the minimal read-only RAM shell (rdinit=/bin/sh).",
    ))
    serial_port.write(f"bootm 0x{UBOOT_LOAD_ADDRESS:x}\r".encode("ascii"))
    _wait_backup_recovery_shell(serial_port, log)


def _probe_backup_recovery(serial_port: RecoverySerial, log, router_ip: str, local_ip: str, family: str, port: int) -> dict:
    expected_model = "Nokia XG-040G-MD" if family == "md" else "Nokia XG-040G-MF"
    # Mount pseudo filesystems only.  No NAND filesystem/UBI volume is mounted.
    for command in (
        "/bin/busybox mount -t proc proc /proc 2>/dev/null || /bin/busybox true",
        "/bin/busybox mount -t sysfs sysfs /sys 2>/dev/null || /bin/busybox true",
        "/bin/busybox mount -t devtmpfs devtmpfs /dev 2>/dev/null || /bin/busybox true",
        f"/bin/busybox ifconfig eth0 {router_ip} netmask 255.255.255.0 up",
    ):
        _ram_shell_command(serial_port, log, command, timeout=30)
    probe_cmd = (
        "/bin/busybox echo MODEL_BEGIN; "
        "/bin/busybox cat /sys/firmware/devicetree/base/model 2>/dev/null || /bin/busybox true; "
        "/bin/busybox echo; /bin/busybox echo MODEL_END; "
        "/bin/busybox cat /proc/mtd; "
        "for x in dd gzip tftp sha256sum ifconfig; do "
        "/bin/busybox --list | /bin/busybox grep -qx \"$x\" && /bin/busybox echo APPLET_$x=1 || /bin/busybox echo APPLET_$x=0; "
        "done"
    )
    out = _ram_shell_command(serial_port, log, probe_cmd, timeout=45)
    text = out.decode("utf-8", "replace").replace("\x00", "")
    low = text.lower()
    if expected_model.lower() not in low:
        raise Error(tr(
            f"RAM recovery model mismatch: ожидался {expected_model}",
            f"RAM recovery model mismatch: expected {expected_model}",
        ))
    if 'mtd0: 10000000 00020000 "all_flash"' not in low:
        raise Error("RAM recovery не подтвердила all_flash=256MiB")
    for applet in ("dd", "gzip", "tftp", "sha256sum", "ifconfig"):
        if f"applet_{applet}=1" not in low:
            raise Error(f"BusyBox RAM recovery не содержит обязательный applet: {applet}")

    # Prove the Ethernet/TFTP PUT path using a tiny RAM-only payload before the
    # first NAND read.  This is the transport gate for the whole backup.
    remote_name = "medveflasher-ram-shell-probe.txt"
    probe_target = WORK / remote_name
    probe_target.unlink(missing_ok=True)
    ready = threading.Event(); cancel = threading.Event(); result = TftpResult()
    receiver = threading.Thread(
        target=receive_tftp_put,
        args=("0.0.0.0", port, probe_target, remote_name, router_ip, ready, result, cancel, 30, 1468),
        daemon=True,
    )
    receiver.start()
    if not ready.wait(5) or result.error:
        cancel.set(); receiver.join(2)
        raise Error(f"не удалось запустить TFTP probe receiver UDP/{port}: {result.error or 'timeout'}")
    try:
        _ram_shell_command(
            serial_port, log,
            f"/bin/busybox echo MEDVEFLASHER_TFTP_OK | /bin/busybox tftp -p -l - -r {remote_name} {local_ip} {port}",
            timeout=30,
        )
        receiver.join(5)
        if receiver.is_alive():
            cancel.set(); receiver.join(2)
            raise Error("RAM shell TFTP probe timeout")
        if result.error or not probe_target.is_file() or b"MEDVEFLASHER_TFTP_OK" not in probe_target.read_bytes():
            raise Error(f"RAM shell TFTP PUT probe failed: {result.error or 'invalid payload'}")
    finally:
        cancel.set(); receiver.join(1); probe_target.unlink(missing_ok=True)
    print(tr(
        f"[OK] {expected_model}: all_flash=256 MiB; UART shell и TFTP PUT UDP/{port} готовы.",
        f"[OK] {expected_model}: all_flash=256 MiB; UART shell and TFTP PUT UDP/{port} are ready.",
    ))
    return {"model": expected_model, "transport": "UART shell + TFTP PUT", "raw_probe": text[-5000:]}


def _capture_bootrom_chunks(serial_port: RecoverySerial, log, router_ip: str, local_ip: str, destination: Path, port: int = BOOTROM_BACKUP_TFTP_PORT) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    chunk_blocks = UBOOT_RESTORE_CHUNK_SIZE // 0x20000
    total_blocks = STOCK_RESTORE_SPAN // 0x20000
    chunks: list[Path] = []
    index = 0
    start_block = 0
    while start_block < total_blocks:
        count_blocks = min(chunk_blocks, total_blocks - start_block)
        raw_size = count_blocks * 0x20000
        remote_name = f"bootrom-allflash-{index:02d}.bin.gz"
        target = destination / remote_name
        sidecar = destination / f"bootrom-allflash-{index:02d}.raw.sha256"
        retained = False
        if target.is_file() and sidecar.is_file():
            try:
                size, digest = _gzip_raw_info(target)
                recorded = sidecar.read_text(encoding="ascii", errors="ignore").strip().lower()
                if size == raw_size and digest == recorded:
                    resume_verify = (
                        f"/bin/busybox dd if=/dev/mtd0 bs=131072 skip={start_block} count={count_blocks} 2>/dev/null | "
                        "/bin/busybox sha256sum"
                    )
                    resume_out = _ram_shell_command(serial_port, log, resume_verify, timeout=600, echo_label=False)
                    current_hashes = re.findall(rb"(?i)\b[0-9a-f]{64}\b", resume_out)
                    if current_hashes and current_hashes[-1].decode("ascii").lower() == recorded:
                        print(tr(
                            f"[BACKUP {index + 1:02d}] resume: блок совпадает с текущим NAND, повторная передача не нужна",
                            f"[BACKUP {index + 1:02d}] resume: chunk matches the current NAND; retransmission is not needed",
                        ))
                        retained = True
                    else:
                        print(tr(
                            f"[BACKUP {index + 1:02d}] resume-файл не совпадает с текущим NAND; блок будет снят заново",
                            f"[BACKUP {index + 1:02d}] resume file does not match the current NAND; recapturing it",
                        ))
            except Exception:
                retained = False
        if not retained:
            target.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            partial = target.with_suffix(target.suffix + ".part")
            for attempt in range(1, 4):
                partial.unlink(missing_ok=True)
                ready = threading.Event(); cancel = threading.Event(); result = TftpResult()
                receiver = threading.Thread(
                    target=receive_tftp_put,
                    args=("0.0.0.0", port, partial, remote_name, router_ip, ready, result, cancel, 300, 4096),
                    daemon=True,
                )
                receiver.start()
                if not ready.wait(5) or result.error:
                    cancel.set(); receiver.join(2)
                    raise Error(f"не удалось запустить TFTP receiver UDP/{port}: {result.error or 'timeout'}")
                print(tr(
                    f"[BACKUP {index + 1:02d}] NAND blocks {start_block}..{start_block + count_blocks - 1}, попытка {attempt}/3",
                    f"[BACKUP {index + 1:02d}] NAND blocks {start_block}..{start_block + count_blocks - 1}, attempt {attempt}/3",
                ))
                remote = (
                    f"/bin/busybox dd if=/dev/mtd0 bs=131072 skip={start_block} count={count_blocks} 2>/tmp/bootrom-dd.log | "
                    f"/bin/busybox gzip -1 | /bin/busybox tftp -p -l - -r {shlex.quote(remote_name)} -b 4096 {shlex.quote(local_ip)} {port}"
                )
                holder: dict[str, object] = {}
                def run_remote() -> None:
                    try:
                        holder["value"] = _ram_shell_command(serial_port, log, remote, timeout=1200)
                    except BaseException as exc:
                        holder["error"] = exc
                shell_thread = threading.Thread(target=run_remote, daemon=True)
                shell_thread.start()
                started = time.time(); last = -10
                while receiver.is_alive() or shell_thread.is_alive():
                    elapsed = int(time.time() - started)
                    if elapsed >= last + 10:
                        print(tr(
                            f"[TRANSFER] block {index + 1:02d}: принято {result.bytes_transferred / 1048576:.1f} MiB gzip, {elapsed}s",
                            f"[TRANSFER] chunk {index + 1:02d}: received {result.bytes_transferred / 1048576:.1f} MiB gzip, {elapsed}s",
                        ))
                        last = elapsed
                    receiver.join(0.5); shell_thread.join(0)
                    if elapsed > 1200:
                        cancel.set(); raise Error("BootROM backup chunk timeout")
                if result.error or "error" in holder:
                    print(tr(f"[WARN] передача блока не удалась: {result.error or holder.get('error')}", f"[WARN] chunk transfer failed: {result.error or holder.get('error')}"))
                    continue
                try:
                    raw_len, local_sha = _gzip_raw_info(partial)
                except Error as exc:
                    print(f"[WARN] {exc}")
                    continue
                if raw_len != raw_size:
                    print(tr(f"[WARN] блок распаковывается в {raw_len}, ожидается {raw_size}", f"[WARN] chunk expands to {raw_len}, expected {raw_size}"))
                    continue
                verify_cmd = (
                    f"/bin/busybox dd if=/dev/mtd0 bs=131072 skip={start_block} count={count_blocks} 2>/dev/null | "
                    "/bin/busybox sha256sum"
                )
                verify_out = _ram_shell_command(serial_port, log, verify_cmd, timeout=600)
                remote_hashes = re.findall(rb"(?i)\b[0-9a-f]{64}\b", verify_out)
                if not remote_hashes or remote_hashes[-1].decode("ascii").lower() != local_sha.lower():
                    print(tr("[WARN] SHA256 блока на ПК не совпал с повторным чтением NAND", "[WARN] PC chunk SHA256 did not match the second NAND read"))
                    continue
                partial.replace(target)
                sidecar.write_text(local_sha + "\n", encoding="ascii")
                print(tr(f"[OK] block {index + 1:02d}: {local_sha}", f"[OK] chunk {index + 1:02d}: {local_sha}"))
                break
            else:
                raise Error(f"не удалось надёжно снять NAND block chunk {index + 1}")
        chunks.append(target)
        start_block += count_blocks
        index += 1
    return chunks


def bootrom_backup_wizard() -> None:
    verify_kit()
    print(tr("\n=== Read-only backup через BootROM/UART ===", "\n=== Read-only backup through BootROM/UART ==="))
    print(tr(
        "Режим не выполняет erase/write/saveenv. Reset используется только для входа в BootROM; preloader, U-Boot и минимальная recovery shell работают из RAM.",
        "This mode never runs erase/write/saveenv. Reset is used only to enter BootROM; preloader, U-Boot, and the minimal recovery shell run from RAM.",
    ))
    transition_lan_policy_notice()
    # The device is not up yet, so this only measures the PC side of the link.
    warn_if_lan1_uplink("192.168.1.1", "read-only backup через BootROM/UART", "read-only BootROM/UART backup")
    print(tr("1 — Nokia XG-040G-MD / AN7581", "1 — Nokia XG-040G-MD / AN7581"))
    print(tr("2 — Nokia XG-040G-MF / AN7583", "2 — Nokia XG-040G-MF / AN7583"))
    model_choice = input(tr("Модель [1/2]: ", "Model [1/2]: ")).strip()
    if model_choice == "1": family = "md"
    elif model_choice == "2": family = "mf"
    else: raise Error(tr("неверная модель", "invalid model selection"))
    profile = recovery_profile_for_family(family)
    recovery_dependency_preflight(require_ssh=False)
    ports = list_serial_ports()
    if ports:
        print(tr("Обнаруженные UART-порты:", "Detected UART ports:"))
        for index, item in enumerate(ports, 1): print(f"  {index}. {item}")
    entered = input(tr("UART-порт или номер в списке: ", "UART port or list number: ")).strip()
    if entered.isdigit() and ports and 1 <= int(entered) <= len(ports): uart_port = ports[int(entered) - 1]
    else: uart_port = entered.upper() if os.name == "nt" else entered
    if not uart_port: raise Error(tr("UART-порт не указан", "UART port was not specified"))
    probe_serial_port(uart_port)
    local_ip = input(tr("Статический IP компьютера [192.168.1.254]: ", "Static PC IP [192.168.1.254]: ")).strip() or "192.168.1.254"
    router_ip = input(tr("Временный IP recovery [192.168.1.1]: ", "Temporary recovery IP [192.168.1.1]: ")).strip() or "192.168.1.1"
    port_text = input(tr(f"UDP-порт TFTP backup [{BOOTROM_BACKUP_TFTP_PORT}]: ", f"Backup TFTP UDP port [{BOOTROM_BACKUP_TFTP_PORT}]: ")).strip()
    port = int(port_text) if port_text else BOOTROM_BACKUP_TFTP_PORT
    stamp = time.strftime("%Y%m%d-%H%M%S")
    default_dest = WORK / "backups" / f"nokia-{family}-bootrom-backup-{stamp}"
    raw_dest = input(tr(f"Каталог backup [{default_dest}]: ", f"Backup directory [{default_dest}]: ")).strip().strip('"')
    destination = Path(raw_dest).expanduser() if raw_dest else default_dest
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / "uart-bootrom-backup.log"
    serial_port = RecoverySerial(uart_port)
    try:
        with log_path.open("ab", buffering=0) as log:
            print(tr(
                "UART открыт. Зажмите Reset и включите Nokia — вывод UART показывается сразу; Press x / C будет пойман автоматически, Enter не нужен.",
                "UART is open. Hold Reset and power on Nokia — UART output is shown live; Press x / C is detected automatically, no Enter is required.",
            ))
            wait_bootrom_xmodem(serial_port, log, "preloader", discard_stale=False)
            xmodem_send(serial_port, Path(profile["preloader"]), f"OpenWrt {profile['soc']} preloader (RAM)", log)
            wait_bootrom_xmodem(serial_port, log, "BL31 + U-Boot FIP")
            xmodem_send(serial_port, Path(profile["fip"]), f"RC18 RECOVERY_SAFE {profile['soc']} BL31 + U-Boot FIP (RAM)", log)
            if wait_uboot_prompt(serial_port, log) != "prompt":
                raise Error("для read-only backup требуется захваченное приглашение RAM U-Boot")
            prove_recovery_safe_uboot(serial_port, log)
            listing = uboot_command(serial_port, log, "mtd list", timeout=60).lower()
            required = (b"block size: 0x20000 bytes", b'0x000000000000-0x000000020000 : "bl2"', b'0x000000020000-0x000010000000 : "ubi"')
            if not all(x in listing for x in required):
                raise Error("RAM U-Boot не подтвердил NAND 256 MiB / erase 0x20000 / bl2+ubi; backup запрещён")
            _boot_backup_recovery_fit(serial_port, log, local_ip, router_ip, profile)
            probe = _probe_backup_recovery(serial_port, log, router_ip, local_ip, family, port)
            chunks = _capture_bootrom_chunks(serial_port, log, router_ip, local_ip, destination, port)
            metadata = _synthesize_bootrom_backup(destination, family, chunks, probe)
            print(tr(
                f"[OK] BootROM backup готов: {destination}\nSHA256 all_flash: {metadata['all_flash_sha256']}",
                f"[OK] BootROM backup completed: {destination}\nall_flash SHA256: {metadata['all_flash_sha256']}",
            ))
            print(tr("NAND не изменялась ни на одном этапе backup.", "NAND was not modified at any point during backup."))
    finally:
        serial_port.close()

def stock_recovery_wizard() -> None:
    verify_kit()
    print(tr("\n=== Восстановление кирпича через BootROM C и XMODEM ===", "\n=== Brick recovery through BootROM C and XMODEM ==="))
    print(tr("Нужен USB-UART 3.3 V: подключайте только GND, TX и RX. VCC к Nokia не подключайте.", "A 3.3 V USB-UART adapter is required: connect only GND, TX, and RX. Do not connect VCC to Nokia."))
    transition_lan_policy_notice()
    print(tr("[RECOVERY SAFE] RC18 загружает RAM U-Boot с bootdelay=-1. До SAFE marker + nonce запрещены любые NAND write/erase/saveenv.", "[RECOVERY SAFE] RC18 loads a RAM U-Boot with bootdelay=-1. All NAND write/erase/saveenv operations are blocked until SAFE marker + nonce proof."))
    print(tr("Ethernet должен соединять компьютер с Nokia через LAN2/LAN3/LAN4; компьютеру задайте 192.168.1.254/24.", "Connect the PC to Nokia through LAN2/LAN3/LAN4 and assign 192.168.1.254/24 to the PC."))
    print(tr("Preloader и U-Boot временно загружаются в оперативную память; штатная прошивка восстанавливается непосредственно из U-Boot.", "The preloader and U-Boot are loaded temporarily into memory; stock firmware is restored directly from U-Boot."))
    # The device is not up yet, so this only measures the PC side of the link.
    warn_if_lan1_uplink("192.168.1.1", "BootROM/UART recovery", "BootROM/UART recovery")
    if os.name == "nt":
        print(tr("В Windows COM обслуживается встроенным Win32-кодом; pyserial и pip не нужны.", "On Windows the COM port uses the built-in Win32 backend; pyserial and pip are not required."))
    recovery_dependency_preflight()
    ports = list_serial_ports()
    if ports:
        print(tr("Обнаруженные UART-порты:", "Detected UART ports:"))
        for index, item in enumerate(ports, 1):
            print(f"  {index}. {item}")
    else:
        print(tr("UART-порты не обнаружены. Проверьте драйвер USB-UART и Диспетчер устройств.", "No UART ports were detected. Check the USB-UART driver and Device Manager."))
    entered = input(tr("UART-порт или номер в списке (например COM10 или /dev/ttyUSB0): ", "UART port or list number (for example COM10 or /dev/ttyUSB0): ")).strip()
    if entered.isdigit() and ports and 1 <= int(entered) <= len(ports):
        uart_port = ports[int(entered) - 1]
    else:
        uart_port = entered.upper() if os.name == "nt" else entered
    if not uart_port:
        raise Error(tr("UART-порт не указан", "UART port was not specified"))
    print(tr(f"Проверяю доступ к {uart_port}...", f"Checking access to {uart_port}..."))
    probe_serial_port(uart_port)
    print(tr(f"[OK] {uart_port}: 115200 8N1, управление потоком отключено.", f"[OK] {uart_port}: 115200 8N1, flow control disabled."))
    local_ip = input(tr("Статический IP компьютера [192.168.1.254]: ", "Static PC IP [192.168.1.254]: ")).strip() or "192.168.1.254"
    router_ip = input(tr("Временный IP U-Boot Nokia [192.168.1.1]: ", "Temporary Nokia U-Boot IP [192.168.1.1]: ")).strip() or "192.168.1.1"
    backup_dir = Path(input(tr("Путь к полному stock backup, снятому до установки OpenWrt: ", "Path to the complete stock backup made before installing OpenWrt: ")).strip().strip('"')).expanduser()
    print(tr(
        "Проверяю mtd0..mtd16, статические области mtd16 и исключаю OpenWrt preloader в BL2...",
        "Checking mtd0..mtd16, static mtd16 areas, and rejecting an OpenWrt preloader in BL2...",
    ))
    payload_dir, manifest = prepare_stock_restore_payloads(backup_dir)
    live_differences = manifest.get("source_validation", {}).get("live_slice_differences", [])
    if live_differences:
        names = ", ".join(f"mtd{number}" for number in live_differences)
        print(tr(
            f"[INFO] {names} изменились между отдельным дампом и mtd16; restore использует канонический mtd16.",
            f"[INFO] {names} changed between the individual dump and mtd16; restore uses the canonical mtd16 image.",
        ))
    family = str(manifest.get("source_validation", {}).get("device_family", "unknown"))
    recovery_profile = recovery_profile_for_family(family)
    print(tr(
        f"[OK] Backup распознан как {recovery_profile['model']} / {recovery_profile['soc']}. Рабочие файлы: {payload_dir}",
        f"[OK] Backup identified as {recovery_profile['model']} / {recovery_profile['soc']}. Working files: {payload_dir}",
    ))
    log_path = payload_dir / "uart-recovery.log"
    serial_port = RecoverySerial(uart_port)
    try:
        with log_path.open("ab", buffering=0) as log:
            print(tr("\n[READY] COM-порт открыт; мониторинг BootROM начинается сразу, Enter не нужен.", "\n[READY] COM port is open; BootROM monitoring starts immediately, no Enter is required."))
            print(tr("Закройте PuTTY, Tera Term и другие программы, если они ещё держат COM-порт.", "Close PuTTY, Tera Term, and other programs if they still hold the COM port."))
            print(tr("[READY] Если Nokia выключена: удерживайте Reset, включите питание и держите Reset до Press x / C.", "[READY] If Nokia is powered off: hold Reset, power it on, and keep Reset held until Press x / C."))
            print(tr("Если UART уже показывает Press x или повторяющиеся C, питание не отключайте — приглашение будет поймано автоматически.", "If UART already shows Press x or repeated C characters, do not remove power — the prompt will be captured automatically."))
            wait_bootrom_xmodem(serial_port, log, "preloader", discard_stale=False)
            xmodem_send(serial_port, Path(recovery_profile["preloader"]), f"OpenWrt {recovery_profile['soc']} preloader (RAM)", log)
            wait_bootrom_xmodem(serial_port, log, "BL31 + U-Boot FIP")
            xmodem_send(serial_port, Path(recovery_profile["fip"]), f"RC18 RECOVERY_SAFE {recovery_profile['soc']} BL31 + U-Boot FIP (RAM)", log)
            uboot_state = wait_uboot_prompt(serial_port, log)
            if uboot_state == "prompt":
                prove_recovery_safe_uboot(serial_port, log)
                try:
                    reboot_confirmed = perform_stock_restore_in_uboot(serial_port, log, local_ip, router_ip, payload_dir, manifest)
                except PermissionError as exc:
                    raise Error(tr("нет прав на UDP/69; в Linux запустите через sudo", "permission denied for UDP/69; on Linux run with sudo")) from exc
            else:
                if not bool(recovery_profile.get("allow_linux_fallback")):
                    raise Error(tr(
                        "RC18 запрещает Linux fallback для BootROM recovery: RECOVERY_SAFE RAM U-Boot prompt не захвачен. "
                        "NAND не изменялась; повторите XMODEM recovery и дождитесь U-Boot>, AN7583> или =>.",
                        "RC18 disables Linux fallback for BootROM recovery: the RECOVERY_SAFE RAM U-Boot prompt was not captured. "
                        "NAND was not modified; retry XMODEM recovery and wait for U-Boot>, AN7583> or =>.",
                    ))
                print(tr("Обычная OpenWrt успела загрузиться. Жду устойчивый SSH и продолжаю через recovery-систему без нового XMODEM.", "Installed OpenWrt started before U-Boot was captured. Waiting for stable SSH and continuing through the recovery system without another XMODEM session."))
                if wait_for_stable_openwrt(router_ip, 480, expected_mode="production") != "production":
                    raise Error(tr("обычная OpenWrt не появилась по SSH после пропущенного U-Boot", "installed OpenWrt did not become available over SSH after U-Boot was missed"))
                boot_recovery_from_production_openwrt(router_ip, local_ip, router_ip, ask_before_reboot=False)
                perform_stock_restore_over_ssh(router_ip, local_ip, 1069, backup_dir, payload_dir, manifest)
                reboot_confirmed = True  # SSH restore owns its own recovery reboot path.
            print(tr(
                "[OK] Запись IBU и BL2 подтверждена readback CRC32 при SHA256-закреплённых исходниках. Результат записи и результат загрузки считаются разными проверками.",
                "[OK] IBU and BL2 writes were confirmed by readback CRC32 against SHA256-pinned source files. Write success and boot success are treated as separate checks.",
            ))
            if not reboot_confirmed:
                print(tr(
                    "[ACTION] NAND уже полностью восстановлена и проверена. Автоматический reboot НЕ подтверждён. Безопасно один раз выключить питание Nokia на 5 секунд и включить снова; мониторинг продолжится автоматически, Enter не нужен.",
                    "[ACTION] NAND is fully restored and verified. Automatic reboot was NOT confirmed. It is now safe to power-cycle Nokia once for 5 seconds; monitoring continues automatically and Enter is not required.",
                ))

            deadline = time.time() + 180
            bootrom_window_seen = False
            reboot_seen = bool(reboot_confirmed)
            stock_verified = False
            last_probe = 0.0
            last_web_error = "not probed"
            uart_tail = bytearray()
            while time.time() < deadline:
                data = serial_port.read(4096, 0.5)
                if data:
                    _uart_log_write(log, data)
                    uart_tail.extend(data)
                    if len(uart_tail) > 65536:
                        del uart_tail[:-32768]
                    raw_tail = bytes(uart_tail)
                    low = raw_tail.lower()
                    if _uboot_reboot_evidence(raw_tail) and not reboot_seen:
                        reboot_seen = True
                        print(tr(
                            "[OK] UART подтвердил новую загрузку после ручного/автоматического reboot.",
                            "[OK] UART confirmed a fresh boot after the manual/automatic reboot.",
                        ))
                    if b"press x" in low and not bootrom_window_seen:
                        bootrom_window_seen = True
                        print(tr(
                            "[UART] Штатное окно Press x после reboot обнаружено; x не отправляется.",
                            "[UART] The normal Press x window after reboot was detected; x will not be sent.",
                        ))
                now = time.time()
                if now - last_probe >= 5.0:
                    last_probe = now
                    stock_verified, last_web_error = _probe_stock_web_fingerprint(router_ip)
                    if stock_verified:
                        break
            if stock_verified:
                print(tr(
                    f"[OK] На {router_ip} подтверждена именно Nokia stock Web login page; восстановление и загрузка stock успешны.",
                    f"[OK] The actual Nokia stock Web login page was verified at {router_ip}; restore and stock boot succeeded.",
                ))
            else:
                print(tr(
                    "[WARN] NAND restore PASS, но загрузка stock НЕ подтверждена. Скрипт больше не считает открытый TCP/80 или TCP/443 доказательством stock Web.",
                    "[WARN] NAND restore PASS, but stock boot was NOT confirmed. An open TCP/80 or TCP/443 is no longer accepted as proof of the stock Web UI.",
                ))
                if not reboot_seen:
                    print(tr(
                        "[ACTION] UART так и не показал новый boot. Если питание ещё не передёргивали после сообщения ACTION выше, сделайте один power-cycle сейчас; запись NAND уже завершена и readback проверен.",
                        "[ACTION] UART still did not show a fresh boot. If you have not power-cycled since the ACTION message above, do one power-cycle now; NAND writing is complete and readback-verified.",
                    ))
                print(tr(
                    f"[DIAG] Последняя проверка stock Web fingerprint: {last_web_error}",
                    f"[DIAG] Last stock Web fingerprint probe: {last_web_error}",
                ))
                print(tr(
                    "[STATE] POST_RESTORE_BOOT_UNKNOWN — это не ошибка записи NAND и не SUCCESS загрузки stock.",
                    "[STATE] POST_RESTORE_BOOT_UNKNOWN — this is neither a NAND-write failure nor a stock-boot SUCCESS.",
                ))
            print(tr(f"\nПроцедура завершена. UART-лог: {log_path}", f"\nProcedure completed. UART log: {log_path}"))
    finally:
        serial_port.close()


def _label_password_error(value: str) -> str | None:
    if value == "":
        return tr("пароль с наклейки нельзя оставить пустым", "the label password cannot be empty")
    if len(value) > 128:
        return tr("пароль слишком длинный", "the password is too long")
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in value):
        return tr(
            "используйте английскую раскладку: разрешены только печатные ASCII-символы без пробелов",
            "use the English keyboard layout: only printable ASCII characters without spaces are allowed",
        )
    return None


def ask_label_password(prompt: str) -> str:
    while True:
        value = getpass.getpass(prompt)
        error = _label_password_error(value)
        if error is None:
            return value
        print(tr(f"ОШИБКА: {error}", f"ERROR: {error}"))


def ask_optional_ascii_password(prompt: str) -> str | None:
    while True:
        value = getpass.getpass(prompt)
        if value == "":
            return None
        error = _label_password_error(value)
        if error is None:
            return value
        print(tr(f"ОШИБКА: {error}", f"ERROR: {error}"))


_STOCK_WEB_MODULE = None


@dataclass
class StockAccess:
    host: str
    user: str
    password: str = field(repr=False)
    su_user: str = "auto"
    su_password: str | None = field(default=None, repr=False)
    telnet_port: int = 23
    ftp_user: str = ""
    ftp_password: str = field(default="", repr=False)
    ftp_port: int = 21
    ftp_enabled: bool = False
    model_verified: bool = False
    model_verification_source: str = ""
    family: str = "unknown"
    model_name: str = ""
    chipset: str = ""
    model_gate_policy: str = "strict"
    model_gate_accepted: bool = False
    force_tftp: bool = False
    custom_sysupgrade: bool = False
    web_client: object | None = field(default=None, repr=False)
    web_setup: object | None = field(default=None, repr=False)
    web_module: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _register_log_secret(self.password)
        _register_log_secret(self.su_password)
        _register_log_secret(self.ftp_password)

    def close_web(self, announce: bool = True) -> None:
        if self.web_client is None:
            return
        client = self.web_client
        self.web_client = None
        self.web_setup = None
        try:
            ok = bool(client.logout())
        except Exception:
            ok = False
        if announce:
            if ok:
                print(tr("[OK] Сессия штатного веб-интерфейса закрыта.",
                         "[OK] Stock web-interface session closed."))
            else:
                print(tr("[WARNING] Не удалось подтвердить выход из веб-сессии; она должна истечь автоматически.",
                         "[WARNING] Web-session logout was not confirmed; it should expire automatically."))


def _load_stock_web_module():
    global _STOCK_WEB_MODULE
    if _STOCK_WEB_MODULE is not None:
        return _STOCK_WEB_MODULE
    spec = importlib.util.spec_from_file_location("nokia_stock_web", STOCK_WEB)
    if spec is None or spec.loader is None:
        raise Error(tr(
            "не удалось загрузить модуль автоматизации штатного веб-интерфейса",
            "failed to load the stock web automation module",
        ))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _STOCK_WEB_MODULE = module
    return module


def _manual_stock_access(
    host: str,
    default_telnet_user: str | None = None,
    default_su_user: str | None = None,
) -> StockAccess:
    port_text = input(tr("Порт Telnet [23]: ", "Telnet port [23]: ")).strip()
    try:
        port = int(port_text) if port_text else 23
    except ValueError as exc:
        raise Error(tr("некорректный порт Telnet", "invalid Telnet port")) from exc
    if not 1 <= port <= 65535:
        raise Error(tr("порт Telnet вне диапазона 1..65535", "Telnet port is outside 1..65535"))
    env_default_user = os.environ.get("NOKIA_DEFAULT_TELNET_USER", "").strip()
    default_user = (default_telnet_user or env_default_user or "useradmin").strip() or "useradmin"
    user = input(tr(f"Пользователь Telnet [{default_user}]: ", f"Telnet user [{default_user}]: ")).strip() or default_user
    print(tr(
        "[INPUT] Переключите клавиатуру на ENG. Пароль обязателен; кириллица, пробелы и пустой ввод отклоняются.",
        "[INPUT] Switch the keyboard to ENG. The password is required; non-ASCII, spaces, and empty input are rejected.",
    ))
    password = ask_label_password(tr("Пароль Telnet/с наклейки: ", "Telnet/password from the label: "))
    env_default_su = os.environ.get("NOKIA_DEFAULT_SU_USER", "").strip()
    default_root_user = (default_su_user or env_default_su or "auto").strip() or "auto"
    su_user = input(tr(
        f"Учётная запись UID 0 [{default_root_user}]: ",
        f"UID 0 account [{default_root_user}]: ",
    )).strip() or default_root_user
    su_password = ask_optional_ascii_password(tr("Пароль UID 0 [тот же]: ", "UID 0 password [same]: "))
    return StockAccess(host, user, password, su_user, su_password, telnet_port=port)


def require_supported_model_over_telnet(access: StockAccess, telnet: Telnet) -> None:
    """Apply the selected stock-Telnet model policy before installation.

    The web gate remains preferred. This fallback exists for manual setup and
    already-enabled Telnet. Manual choices 2/3 reject an explicit AN/EN7583,
    accept AN/EN7581, and allow ambiguous output only after one warning. The
    explicit expert choice bypasses this probe entirely and forces TFTP.
    """
    if access.model_verified or access.model_gate_accepted:
        return
    if access.model_gate_policy == "bypass":
        access.model_gate_accepted = True
        access.model_verification_source = "expert-bypass-no-model-probe"
        print(tr(
            "[WARNING] ЭКСПЕРТНЫЙ РЕЖИМ: проверка модели полностью пропущена по явному выбору пользователя. Неверная модель может быть необратимо повреждена.",
            "[WARNING] EXPERT MODE: model verification was completely skipped by explicit user choice. A wrong model may be irreversibly damaged.",
        ))
        return
    command = (
        "{ for f in /sys/firmware/devicetree/base/model "
        "/sys/firmware/devicetree/base/compatible /proc/device-tree/model "
        "/proc/device-tree/compatible; do [ -r \"$f\" ] && "
        "{ tr '\\000' '\\n' <\"$f\"; echo; }; done; "
        "dmesg 2>/dev/null; } | grep -Ei '([AE]N)?758[13]' | tail -n 120"
    )
    rc, text = telnet.command(command, timeout=60, echo=False)
    has_7583 = bool(re.search(r"(?i)(?:AN|EN)7583(?:DT)?", text))
    has_7581 = bool(re.search(r"(?i)(?:AN|EN)7581(?:DT)?", text))
    if has_7583:
        raise Error(tr(
            "[СТОП] Telnet-проверка обнаружила чип AN/EN7583. Поддерживается только XG-040G-MD/AN7581. Backup и NAND-операции не начаты.",
            "[STOP] The Telnet model check detected an AN/EN7583 chipset. Only XG-040G-MD/AN7581 is supported. Backup and NAND operations were not started.",
        ))
    if has_7581:
        access.model_verified = True
        access.model_verification_source = "stock-telnet-dmesg/devicetree"
        print(tr(
            "[OK] Модель подтверждена через stock Telnet: чип AN/EN7581; ручной путь разрешён.",
            "[OK] Model confirmed over stock Telnet: AN/EN7581 chipset; the manual path is allowed.",
        ))
        return
    if access.model_gate_policy == "best-effort":
        print(tr(
            "[WARNING] Stock Telnet не дал однозначного маркера AN/EN7581 или AN/EN7583. В ручном режиме 2/3 можно продолжить, но ответственность за правильную модель лежит на пользователе.",
            "[WARNING] Stock Telnet did not expose an unambiguous AN/EN7581 or AN/EN7583 marker. Manual choices 2/3 may continue, but the user is responsible for confirming the correct model.",
        ))
        answer = input(tr(
            "Продолжить установку при неопределённой модели? [y/N]: ",
            "Continue installation with an unidentified model? [y/N]: ",
        )).strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            raise Error(tr(
                "ручная установка отменена пользователем после неопределённого результата проверки модели",
                "manual installation was cancelled after an inconclusive model check",
            ))
        access.model_gate_accepted = True
        access.model_verification_source = "stock-telnet-inconclusive-user-accepted"
        print(tr(
            "[WARNING] Неопределённый результат принят пользователем; установка продолжится в ручном режиме.",
            "[WARNING] The inconclusive result was accepted by the user; manual installation will continue.",
        ))
        return
    if rc or not has_7581:
        raise Error(tr(
            "[СТОП] Не удалось однозначно подтвердить AN/EN7581 через stock Telnet. Ручной путь закрыт fail-closed; backup и NAND-операции не начаты.",
            "[STOP] AN/EN7581 could not be confirmed unambiguously over stock Telnet. The manual path is closed fail-safe; backup and NAND operations were not started.",
        ))


def _startup_web_auth_for(host: str) -> tuple[str, str] | None:
    if not _STARTUP_DEVICE_PROFILE.get("verified"):
        return None
    if str(_STARTUP_WEB_AUTH.get("host") or "") != host:
        return None
    user = str(_STARTUP_WEB_AUTH.get("user") or "")
    password = str(_STARTUP_WEB_AUTH.get("password") or "")
    if not user:
        return None
    return user, password


def _automatic_stock_web_access(
    host: str,
    module,
    *,
    offer_interactive_plain_retry: bool = True,
) -> StockAccess:
    cached_auth = _startup_web_auth_for(host)
    env_password = os.environ.pop("NOKIA_WEB_PASSWORD", None)
    if cached_auth is not None and env_password is None:
        web_user, web_password = cached_auth
        print(tr(
            "[OK] Использую Web-реквизиты из успешного автоопределения; повторный ввод не требуется.",
            "[OK] Reusing Web credentials from successful startup auto-detection; no second prompt is required.",
        ))
    else:
        web_user = input(tr("Пользователь штатного веб-интерфейса [CMCCAdmin]: ",
                            "Stock web-interface user [CMCCAdmin]: ")).strip() or "CMCCAdmin"
        if env_password is not None:
            web_password = env_password
        else:
            default_web_password = str(getattr(module, "DEFAULT_WEB_PASSWORD", "") or "")
            if default_web_password:
                entered = _RAW_GETPASS(tr(
                    "Пароль штатного веб-интерфейса [стандартный — Enter]: ",
                    "Stock web-interface password [standard — Enter]: ",
                ))
                web_password = entered or default_web_password
            else:
                web_password = _RAW_GETPASS(tr(
                    "Пароль штатного веб-интерфейса: ",
                    "Stock web-interface password: ",
                ))
    _register_log_secret(web_password)
    allow_plain = os.environ.get("NOKIA_ALLOW_PLAIN_WEB_LOGIN", "").strip().lower() in ("1", "yes", "true")
    client = module.StockWeb(host)
    try:
        print(tr("[WAIT] Вход в штатный веб-интерфейс...",
                 "[WAIT] Logging in to the stock web interface..."))
        while True:
            try:
                mode = client.login(web_user, web_password, allow_plain=allow_plain)
                break
            except module.LoginError as exc:
                if allow_plain or not offer_interactive_plain_retry:
                    raise
                print(tr(
                    f"[WARNING] Зашифрованная форма входа не принята: {_web_failure_detail(exc)}",
                    f"[WARNING] The encrypted login form was not accepted: {_web_failure_detail(exc)}",
                ))
                print(tr(
                    "На некоторых stock firmware это означает, что принимается только обычная HTTP-форма. Plain-login защищает не сильнее локальной сети: пароль будет отправлен открытым текстом.",
                    "On some stock firmware this means that only the ordinary HTTP form is accepted. Plain login provides no protection beyond the local network: the password will be sent in clear text.",
                ))
                print(tr(
                    "1 — заново ввести пароль и повторить зашифрованный вход",
                    "1 — re-enter the password and retry encrypted login",
                ))
                print(tr(
                    "2 — один раз повторить с текущими данными через plain HTTP",
                    "2 — retry once with the current credentials over plain HTTP",
                ))
                print(tr(
                    "3 — отказаться от web-автоматики и перейти к ручному Telnet",
                    "3 — stop web automation and continue with manual Telnet",
                ))
                while True:
                    retry = input(tr("Выберите 1/2/3 [2]: ", "Select 1/2/3 [2]: ")).strip() or "2"
                    if retry in ("1", "2", "3"):
                        break
                    print(tr("Неверный выбор. Введите 1, 2 или 3.", "Invalid choice. Enter 1, 2, or 3."))
                try:
                    client.logout()
                except Exception:
                    pass
                client = module.StockWeb(host)
                if retry == "1":
                    web_password = _RAW_GETPASS(tr(
                        "Пароль штатного веб-интерфейса: ",
                        "Stock web-interface password: ",
                    ))
                    continue
                if retry == "2":
                    allow_plain = True
                    continue
                raise
        setup = module.StockSetup(client)
        supported = getattr(module, "SUPPORTED_INSTALL_MODELS", ("XG-040G-MD",))
        info = setup.require_model(supported)
        print(tr(
            f"[OK] Модель подтверждена: {info['model']}"
            + (f" (чип {info['chipset']})" if info["chipset"] else "") + ".",
            f"[OK] Model confirmed: {info['model']}"
            + (f" (chipset {info['chipset']})" if info["chipset"] else "") + ".",
        ))
        credentials = setup.read_credentials()
        telnet_password = str(credentials["telnet_password"])
        _register_log_secret(telnet_password)
        _register_log_secret(credentials.get("ftp_password"))
        password_error = _label_password_error(telnet_password)
        if password_error is not None:
            raise module.SetupError(tr(
                "веб-интерфейс вернул непригодный Telnet-пароль",
                "the web interface returned an unusable Telnet password",
            ))
        telnet_port = int(credentials["telnet_port"])
        setup.enable_telnet(port=telnet_port)
        if not _tcp_open(host, telnet_port, timeout=2.0):
            raise module.SetupError(f"Telnet port {telnet_port} remains closed")
        print(tr(
            "[OK] Вход в штатный Web UI выполнен; сессионная cookie подтверждена.",
            "[OK] Stock Web UI login succeeded; the session cookie was confirmed.",
        ))
        if mode == "plain":
            print(tr(
                "[WARNING] Использована открытая HTTP-форма входа. Пароль был передан по локальной сети без шифрования.",
                "[WARNING] Plain HTTP login was used. The password was sent over the local network without encryption.",
            ))
        else:
            print(tr("[OK] Зашифрованная форма входа принята штатной веб-мордой.",
                     "[OK] The encrypted login form was accepted by the stock web UI."))
        print(tr(
            f"[OK] Telnet включён; порт {telnet_port} открыт. Реквизиты получены из stock web UI и не выводятся в журнал.",
            f"[OK] Telnet is enabled; port {telnet_port} is open. Credentials were read from the stock web UI and are not printed to the log.",
        ))
        return StockAccess(
            host=host,
            user=str(credentials["telnet_user"]),
            password=telnet_password,
            su_user="auto",
            su_password=None,
            telnet_port=telnet_port,
            ftp_user=str(credentials.get("ftp_user") or ""),
            ftp_password=str(credentials.get("ftp_password") or ""),
            ftp_port=int(credentials.get("ftp_port") or 21),
            ftp_enabled=bool(credentials.get("ftp_enabled")),
            model_verified=True,
            model_verification_source="stock-web-device_status.cgi",
            web_client=client,
            web_setup=setup,
            web_module=module,
        )
    except Exception:
        try:
            client.logout()
        except Exception:
            pass
        raise
    finally:
        web_password = None
        env_password = None


def _web_failure_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    return f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__


def ask_credentials(
    *,
    default_telnet_user: str | None = None,
    default_su_user: str | None = None,
    offer_interactive_plain_retry: bool = False,
    require_model_gate: bool = False,
) -> StockAccess:
    startup_host = str(_STARTUP_DEVICE_PROFILE.get("host") or "192.168.1.1")
    host = input(tr(f"IP Nokia [{startup_host}]: ", f"Nokia IP [{startup_host}]: ")).strip() or startup_host
    # The configured Telnet port is available only after a successful web login.
    # Port 23 is therefore a deliberate low-cost heuristic for choosing the
    # default without consuming one of the stock firmware's limited web sessions.
    port23_open = _tcp_open(host, 23, timeout=1.0)
    default = "1" if require_model_gate else ("3" if port23_open else "1")
    print()
    print(tr("Как подключиться к роутеру:", "How should the router be accessed?"))
    if require_model_gate:
        print(tr(
            "1 — Автоматическая настройка (рекомендуется)",
            "1 — Automatic setup (recommended)",
        ))
    else:
        print(tr("1 — Автоматическая настройка", "1 — Automatic setup"))
    print(tr(
        "2 — Настроить Telnet вручную",
        "2 — Configure Telnet manually",
    ))
    print(tr(
        "3 — Использовать уже включённый Telnet",
        "3 — Use Telnet that is already enabled",
    ))
    # Sysupgrade selection is intentionally handled once, in _choose_install_mode().
    # Connection setup must not duplicate image-selection semantics or silently
    # turn a custom image into a model-gate bypass.
    allowed = ("1", "2", "3")
    choices_text = "1/2/3"
    prompt = tr(f"Выберите {choices_text} [{default}]: ", f"Select {choices_text} [{default}]: ")
    while True:
        choice = input(prompt).strip() or default
        if choice in allowed:
            break
        print(tr(
            f"Неверный выбор. Введите {choices_text}.",
            f"Invalid choice. Enter {choices_text}.",
        ))
    if choice == "1":
        try:
            module = _load_stock_web_module()
            access = _automatic_stock_web_access(
                host,
                module,
                offer_interactive_plain_retry=offer_interactive_plain_retry,
            )
            # The selected hardware profile knows its documented interactive
            # UID-0 account. Keep the web-derived Telnet credentials, but do
            # not replace the model-specific su target with generic auto scan.
            if default_su_user and access.su_user == "auto":
                access.su_user = default_su_user
            return access
        except OSError as exc:
            print(tr(
                f"[WARNING] HTTP/TCP-соединение со штатной веб-мордой не установлено: {_web_failure_detail(exc)}",
                f"[WARNING] The stock web UI could not be reached over HTTP/TCP: {_web_failure_detail(exc)}",
            ))
            print(tr(
                "[WARNING] Устройство может уже находиться в recovery/OpenWrt. Для transition OpenWrt используйте пункт 4 главного меню.",
                "[WARNING] The device may already be in recovery/OpenWrt. For transition OpenWrt, use main-menu item 4.",
            ))
        except Exception as exc:
            module = _STOCK_WEB_MODULE
            if module is not None and isinstance(exc, getattr(module, "UnsupportedModel", ())):
                # Другая модель Nokia — не откатываемся на ручной ввод.
                # Ручной путь позволил бы продолжить установку на
                # неподходящем устройстве тем же образом.
                raise Error(tr(
                    f"[СТОП] {exc}. Продолжать нельзя: снятая разметка NAND "
                    f"у моделей этой линейки может совпадать, поэтому проверка "
                    f"по /proc/mtd эту ошибку не поймает. Ничего не изменено.",
                    f"[STOP] {exc}. Cannot continue: NAND layout can match "
                    f"across models in this lineup, so the /proc/mtd check "
                    f"would not catch this. Nothing has been changed.",
                )) from exc
            if module is not None and isinstance(exc, module.UnsupportedFirmware):
                print(tr(
                    f"[WARNING] HTTP отвечает, но поддерживаемая stock web UI не распознана: {_web_failure_detail(exc)}",
                    f"[WARNING] HTTP responds, but a supported stock web UI was not recognized: {_web_failure_detail(exc)}",
                ))
            elif module is not None and isinstance(exc, module.LoginError):
                print(tr(
                    f"[WARNING] Автоматический вход в stock web UI не выполнен: {_web_failure_detail(exc)}",
                    f"[WARNING] Automatic stock web login failed: {_web_failure_detail(exc)}",
                ))
            else:
                print(tr(
                    f"[WARNING] Автоматическая настройка stock web UI не выполнена: {_web_failure_detail(exc)}",
                    f"[WARNING] Automatic stock web setup failed: {_web_failure_detail(exc)}",
                ))
        if require_model_gate:
            print(tr(
                "[WARNING] Web-проверка модели не завершена. Разрешён ручной Telnet-ввод, но перед backup/установкой мастер отдельно потребует однозначный AN/EN7581 и остановится при AN/EN7583 или неопределённости.",
                "[WARNING] Web model verification did not complete. Manual Telnet input is allowed, but before backup/installation the wizard will require an unambiguous AN/EN7581 marker and will stop on AN/EN7583 or ambiguity.",
            ))
        print(tr(
            "[PATH] Автоматика ничего больше не изменяет; продолжаем с ручным вводом Telnet-реквизитов.",
            "[PATH] Automation will make no further changes; continuing with manual Telnet credentials.",
        ))
        return _manual_stock_access(host, default_telnet_user, default_su_user)
    if choice == "2":
        print(tr(
            "[INPUT] Откройте штатную веб-морду, включите Telnet и нужный транспорт. После этого вернитесь сюда.",
            "[INPUT] Open the stock web UI, enable Telnet and the required transport, then return here.",
        ))
        input(tr("Нажмите Enter после ручной настройки: ", "Press Enter after manual setup: "))
        access = _manual_stock_access(host, default_telnet_user, default_su_user)
        if require_model_gate:
            access.model_gate_policy = "best-effort"
        return access
    if choice == "3":
        if not port23_open:
            print(tr(
                "[WARNING] Порт 23 сейчас закрыт. Можно указать другой Telnet-порт, но при неверных данных подключение не состоится.",
                "[WARNING] Port 23 is currently closed. You may specify another Telnet port, but incorrect settings will not connect.",
            ))
        access = _manual_stock_access(host, default_telnet_user, default_su_user)
        if require_model_gate:
            access.model_gate_policy = "best-effort"
        return access



def print_usb_requirements() -> None:
    print()
    print(tr("=== Требования к USB-флешке ===", "=== USB drive requirements ==="))
    print(tr("• Вставьте флешку непосредственно в USB-порт Nokia до подключения по Telnet.", "• Insert the drive directly into the Nokia USB port before the Telnet connection."))
    print(tr("• Флешка должна быть смонтирована Nokia как FAT/FAT32 и доступна для записи.", "• The drive must be mounted by the Nokia as FAT/FAT32 and be writable."))
    print(tr("• Не менее 2 ГиБ свободного места; флешку нельзя извлекать до завершения копирования.", "• At least 2 GiB free; do not remove the drive until copying is complete."))
    print(tr("• После входа мастер через Telnet проверит mount, тип FAT, реальную запись/удаление файла и свободное место.", "• After login, the wizard verifies the mount, FAT filesystem type, an actual write/delete test, and free space over Telnet."))
    print()


def _remote_error_line(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    for line in reversed(lines):
        if line.startswith(("ОШИБКА:", "ERROR:")):
            return line
    return ""


def verify_router_usb_storage(telnet: Telnet, mount: str) -> dict[str, str]:
    telnet.upload_text("/tmp/nokia-backup-agent.sh", BACKUP_AGENT.read_text())
    command = (
        f"NOKIA_LANG={shlex.quote(ensure_language())} NOKIA_USB_MARKERS=1 "
        f"ash /tmp/nokia-backup-agent.sh {shlex.quote(mount)} --preflight"
    )
    rc, text = telnet.command(command, timeout=120, echo=False)
    if rc:
        detail = _remote_error_line(text)
        raise Error(tr(
            "USB-флешка не прошла обязательную проверку" + (f": {detail}" if detail else ""),
            "The USB drive failed mandatory validation" + (f": {detail}" if detail else ""),
        ))
    def marker(name: str) -> str:
        values = _runtime_marker_values(text, name)
        return values[-1] if values else ""
    result = {
        "mount": marker("__USB_MOUNT__"),
        "source": marker("__USB_SOURCE__"),
        "filesystem": marker("__USB_FILESYSTEM__"),
        "free_kb": marker("__USB_FREE_KB__"),
    }
    if marker("__USB_PREFLIGHT_OK__") != "1" or result["mount"] != mount:
        raise Error(tr("USB preflight вернул неполные данные", "USB preflight returned incomplete data"))
    free_gib = int(result["free_kb"] or "0") / 1048576
    print(tr(f"[OK] USB mount: {result['mount']}", f"[OK] USB mount: {result['mount']}"))
    print(tr(
        f"[OK] FAT/FAT32: {result['filesystem']}; источник mount: {result['source']}",
        f"[OK] FAT/FAT32: {result['filesystem']}; mount source: {result['source']}",
    ))
    print(tr(f"[OK] Проверка записи пройдена; свободно {free_gib:.1f} ГиБ.", f"[OK] Write test passed; {free_gib:.1f} GiB free."))
    return result


def print_full_install_route(transport: str) -> None:
    routes = {
        "share": (
            "stock → полный backup на USB в Nokia → копирование backup и пакета через Samba → OpenWrt",
            "stock → complete backup to USB in the Nokia → backup/package transfer through Samba → OpenWrt",
        ),
        "ftp": (
            "stock → полный backup на USB в Nokia → копирование backup и пакета через stock FTP → OpenWrt",
            "stock → complete backup to USB in the Nokia → backup/package transfer through stock FTP → OpenWrt",
        ),
        "tftp": (
            "stock → полный backup напрямую на ПК по TFTP → установка пакета по TFTP → OpenWrt",
            "stock → complete backup directly to the PC over TFTP → package installation over TFTP → OpenWrt",
        ),
    }
    ru, en = routes[transport]
    print(tr(f"[PATH] Полная прошивка с обязательным backup: {ru}", f"[PATH] Full installation with mandatory backup: {en}"))


def choose_transport(
    router_host: str,
    install_only: bool = False,
    access: StockAccess | None = None,
    force_tftp: bool = False,
) -> tuple[str, dict]:
    if force_tftp:
        print(tr(
            "\n[WARNING] ЭКСПЕРТНЫЙ РЕЖИМ: пакет на stock передаётся прямым TFTP. После загрузки ручного transition sysupgrade использует TFTP → SCP → SSH fallback.",
            "\n[WARNING] EXPERT MODE: the stock-side package uses direct TFTP. After the manual transition boots, sysupgrade uses TFTP → SCP → SSH fallback.",
        ))
        local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
        port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
        port = int(port_text) if port_text else 1069
        return "tftp", {"local_ip": local_ip, "tftp_port": port, "block_size": 4096}
    if install_only:
        print(tr("\nТранспорт установочного пакета:", "\nInstallation-package transport:"))
    else:
        print(tr("\nТранспорт backup и установочного пакета:", "\nBackup and installation-package transport:"))
    print(tr("1 — прямой TFTP между Nokia и ПК, USB не требуется (рекомендуется)", "1 — direct TFTP between Nokia and the PC; no USB required (recommended)"))
    print(tr("2 — USB-накопитель подключён к Nokia: Samba/сетевая папка (флешку не вынимать)", "2 — USB drive connected to the Nokia: Samba/network share (do not remove the drive)"))
    print(tr("3 — USB-накопитель подключён к Nokia: FTP штатной прошивки", "3 — USB drive connected to the Nokia: stock-firmware FTP"))
    choice = input(tr("Выберите 1/2/3 [1]: ", "Select 1/2/3 [1]: ")).strip() or "1"
    if choice == "2":
        print_usb_requirements()
        if access is not None and access.web_setup is not None:
            try:
                access.web_setup.enable_samba()
                if access.web_module.samba_ports_open(router_host):
                    print(tr("[OK] Samba включена через штатный веб-интерфейс; порт 445/139 отвечает.",
                             "[OK] Samba was enabled through the stock web UI; port 445/139 responds."))
                else:
                    print(tr("[WARNING] Samba включена в настройках, но порты 445/139 пока не отвечают.",
                             "[WARNING] Samba is enabled in settings, but ports 445/139 do not respond yet."))
            except Exception as exc:
                print(tr(
                    f"[WARNING] Автоматически включить Samba не удалось: {_web_failure_detail(exc)}",
                    f"[WARNING] Samba could not be enabled automatically: {_web_failure_detail(exc)}",
                ))
                access.close_web()
                print(tr("[INPUT] При необходимости включите Samba вручную в штатной веб-морде.",
                         "[INPUT] Enable Samba manually in the stock web UI if needed."))
                input(tr("Нажмите Enter для продолжения: ", "Press Enter to continue: "))
        default_share = rf"\\{router_host}\mnt\USB_disc1\nokia-openwrt-install"
        share = input(tr(
            f"Папка установки Samba [{default_share}]: ",
            f"Samba installation folder [{default_share}]: ",
        )).strip().strip('"') or default_share
        share_user = ""
        share_password = ""
        if os.name == "nt" and share.startswith("\\\\"):
            # The protected stock share uses the label account. Automatic web
            # access already supplied the same per-device password through the
            # Telnet credentials; manual modes collected it from the label.
            default_samba_user = "useradmin"
            share_user = input(tr(
                f"Пользователь Samba [{default_samba_user}]: ",
                f"Samba user [{default_samba_user}]: ",
            )).strip() or default_samba_user
            automatic_password = access.password if access is not None else ""
            if automatic_password:
                share_password = automatic_password
                _register_log_secret(share_password)
                print(tr(
                    "[WAIT] Проверяю Samba с паролем, уже введённым для Telnet; пароль не выводится в журнал.",
                    "[WAIT] Testing Samba with the password already entered for Telnet; the password is not written to the log.",
                ))
            else:
                print(tr(
                    "[INPUT] Введите пароль пользователя useradmin с наклейки роутера.",
                    "[INPUT] Enter the useradmin password from the router label.",
                ))
                share_password = ask_label_password(tr(
                    "Пароль Samba/с наклейки: ",
                    "Samba/password from the label: ",
                ))
                _register_log_secret(share_password)
            try:
                connect_samba_share(share, share_user, share_password)
            except Error as first_error:
                _write_session_only(f"[TECH] Initial Samba authentication failed: {first_error}")
                print(tr(
                    "[WARNING] Samba не приняла сохранённый пароль. Введите пароль useradmin с наклейки ещё раз.",
                    "[WARNING] Samba rejected the stored password. Re-enter the useradmin password from the label.",
                ))
                share_password = ask_label_password(tr(
                    "Пароль Samba/с наклейки: ",
                    "Samba/password from the label: ",
                ))
                _register_log_secret(share_password)
                connect_samba_share(share, share_user, share_password)
            print(tr(
                f"[OK] Доступ к Samba подтверждён для пользователя {share_user}.",
                f"[OK] Samba access was confirmed for user {share_user}.",
            ))
        remote = input(tr(
            "Путь USB внутри Nokia [автоопределение: /mnt/USB_disc1]: ",
            "USB path inside Nokia [auto-detect: /mnt/USB_disc1]: ",
        )).strip() or None
        return "share", {
            "share_path": share,
            "share_user": share_user,
            "share_password": share_password,
            "remote_mount": remote,
        }
    if choice == "3":
        print_usb_requirements()
        user = access.ftp_user if access is not None else ""
        password = access.ftp_password if access is not None else ""
        ftp_port = access.ftp_port if access is not None else 21
        if user and password:
            print(tr(f"[OK] FTP-реквизиты и порт {ftp_port} получены из stock web UI; пароль не выводится.",
                     f"[OK] FTP credentials and port {ftp_port} were read from the stock web UI; the password is not displayed."))
            if not _tcp_open(router_host, ftp_port, timeout=1.5):
                enabled_automatically = False
                if access is not None and access.web_setup is not None:
                    try:
                        access.web_setup.enable_ftp()
                        enabled_automatically = _tcp_open(router_host, ftp_port, timeout=2.0)
                        if enabled_automatically:
                            print(tr(
                                f"[OK] FTP включён через штатный веб-интерфейс; порт {ftp_port} открыт.",
                                f"[OK] FTP was enabled through the stock web UI; port {ftp_port} is open.",
                            ))
                    except Exception as exc:
                        print(tr(
                            f"[WARNING] Автоматически включить FTP не удалось: {_web_failure_detail(exc)}",
                            f"[WARNING] FTP could not be enabled automatically: {_web_failure_detail(exc)}",
                        ))
                if not enabled_automatically:
                    if access is not None:
                        access.close_web()
                    print(tr(
                        f"[INPUT] FTP-порт {ftp_port} закрыт. Включите FTP вручную в штатной веб-морде.",
                        f"[INPUT] FTP port {ftp_port} is closed. Enable FTP manually in the stock web UI.",
                    ))
                    input(tr("Нажмите Enter после включения FTP: ", "Press Enter after enabling FTP: "))
                    if not _tcp_open(router_host, ftp_port, timeout=2.0):
                        raise Error(tr(f"FTP-порт {ftp_port} остаётся закрыт", f"FTP port {ftp_port} remains closed"))
        else:
            user = input(tr("FTP user: ", "FTP user: ")).strip()
            password = getpass.getpass(tr("FTP password: ", "FTP password: "))
            _register_log_secret(password)
            port_text = input(tr("FTP port [21]: ", "FTP port [21]: ")).strip()
            ftp_port = int(port_text) if port_text else 21
        remote = input(tr(
            "Путь USB внутри Nokia [автоопределение: /mnt/USB_disc1]: ",
            "USB path inside Nokia [auto-detect: /mnt/USB_disc1]: ",
        )).strip() or None
        return "ftp", {"ftp_user": user, "ftp_password": password, "ftp_port": ftp_port, "remote_mount": remote}
    if choice == "1":
        local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
        port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
        port = int(port_text) if port_text else 1069
        return "tftp", {"local_ip": local_ip, "tftp_port": port, "block_size": 4096}
    raise Error("неверный выбор транспорта")


def _active_install_profile() -> InstallProfile:
    prof = _STARTUP_DEVICE_PROFILE
    family = str(prof.get("family") or "") if prof.get("verified") else ""
    if family in INSTALL_PROFILES:
        return INSTALL_PROFILES[family]
    # Historical fallback remains MD-only because MF destructive write requires
    # a VERIFIED stock-Web fingerprint.
    return MD_INSTALL_PROFILE


def _choose_install_mode(profile: InstallProfile) -> bool | None:
    print(tr(
        f"\n=== Установка OpenWrt UBI — {profile.model} ===",
        f"\n=== OpenWrt UBI installation — {profile.model} ===",
    ))
    print(tr("1 — автоматически (встроенный sysupgrade)", "1 — automatic (bundled sysupgrade)"))
    print(tr("2 — выбрать свой sysupgrade", "2 — select a custom sysupgrade"))
    print(tr("3 — назад", "3 — back"))
    mode = input(tr("Выберите 1/2/3: ", "Select 1/2/3: ")).strip()
    if mode == "3":
        return None
    if mode not in ("1", "2"):
        raise Error(tr("неверный выбор", "invalid selection"))
    return mode == "2"


def _install_access(profile: InstallProfile) -> StockAccess:
    # MF permanent write is never authorized from a manual model choice.
    if profile.family == "mf":
        access, meta = _stock_operational_web_access()
        if str(meta.get("family") or "") != "mf":
            access.close_web(announce=False)
            raise Error(tr("live Web fingerprint не подтвердил MF", "live Web fingerprint did not confirm MF"))
        return access
    return ask_credentials(require_model_gate=True)


def _validate_install_handoff_targets(proc: dict[int, tuple[int, int, str]]) -> None:
    """Require exact stock-side stage-1 targets, independent of slot revision."""
    for number, (expected_size, expected_name) in INSTALL_STOCK_HANDOFF.items():
        if number not in proc:
            raise Error(tr(f"mtd{number}: stock handoff target отсутствует", f"mtd{number}: stock handoff target is missing"))
        size, erase, name = proc[number]
        if size != expected_size or erase != UBOOT_ERASE_SIZE or name != expected_name:
            raise Error(tr(
                f"mtd{number}: stock handoff target mismatch: name={name}, size=0x{size:08X}, erase=0x{erase:X}",
                f"mtd{number}: stock handoff target mismatch: name={name}, size=0x{size:08X}, erase=0x{erase:X}",
            ))


def _install_live_gate(profile: InstallProfile, access: StockAccess, telnet: Telnet) -> tuple[str, str]:
    """Authorize stock->transition handoff without binding writes to slot revision.

    mtd2..mtd5 are only the vendor kernel/rootfs views used to classify MD/MF.
    The destructive path is authorized by the fixed stock handoff geometry and
    /proc<->sysfs agreement proven by ``_stock_live_geometry_preflight``.  The
    RAM transition then independently requires the exact physical NAND target
    for its board before ``ubiformat`` is reachable.
    """
    if profile.family == "md":
        require_supported_model_over_telnet(access, telnet)
    proc, family, variant = _stock_live_geometry_preflight(
        telnet, profile.family, require_ro=(profile.family == "mf")
    )
    if family != profile.family:
        raise Error(tr(
            f"live stock family mismatch: ожидалось {profile.family.upper()}, получено {family.upper()}",
            f"live stock family mismatch: expected {profile.family.upper()}, got {family.upper()}",
        ))
    # These are the stock-side handoff targets that stage 1 actually touches or
    # uses as the canonical device span. Their exact identity remains a hard
    # gate for both MD and MF; revision-dependent mtd2..mtd5 sizes do not.
    _validate_install_handoff_targets(proc)
    print(tr(
        f"[OK] Install policy: {family.upper()} / {variant}; slot revision accepted as family evidence; exact stock handoff target verified.",
        f"[OK] Install policy: {family.upper()} / {variant}; slot revision accepted as family evidence; exact stock handoff target verified.",
    ))
    return family, variant

def _install_transport(profile: InstallProfile, access: StockAccess, install_only: bool = False) -> tuple[str, dict]:
    if profile.force_tftp:
        print(tr(
            "[INFO] Для этого профиля backup/установочный пакет передаются напрямую по TFTP.",
            "[INFO] This profile transfers the backup/installation package directly over TFTP.",
        ))
        local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
        port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
        port = int(port_text) if port_text else 1069
        return "tftp", {"local_ip": local_ip, "tftp_port": port, "block_size": 4096}
    return choose_transport(
        access.host,
        install_only=install_only,
        access=access,
        force_tftp=access.force_tftp,
    )


def _capture_install_backup(
    profile: InstallProfile, access: StockAccess, transport: str, transport_args: dict,
) -> tuple[Path, Telnet | None]:
    host = access.host
    telnet: Telnet | None = None
    gate_telnet = login_root_family(access, profile.family, allow_service_provisioning=True)
    try:
        _install_live_gate(profile, access, gate_telnet)
    finally:
        gate_telnet.close()

    if transport == "tftp":
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = WORK / "backups" / f"nokia-xg040g{profile.family}-backup-{stamp}"
        backup_tftp(
            access, host, backup_dir, transport_args.get("local_ip"),
            transport_args.get("tftp_port", 1069), transport_args.get("block_size", 4096),
            expected_family=profile.family,
        )
        telnet = login_root_family(access, profile.family, allow_service_provisioning=True)
        _install_live_gate(profile, access, telnet)
        _validate_install_backup(profile, backup_dir)
        return backup_dir, telnet

    # Non-TFTP installation transport is retained for MD for compatibility.
    # MF still forces TFTP as an implementation/transport choice, not as a
    # destructive authorization distinction.  Backup content policy is shared.
    telnet = login_root_family(access, profile.family, allow_service_provisioning=True)
    _install_live_gate(profile, access, telnet)
    if transport == "share":
        usb_root, _ = _share_usb_and_install_paths(
            transport_args["share_path"],
            transport_args.get("share_user", ""),
            transport_args.get("share_password", ""),
        )
        remote_mount = resolve_router_usb_mount(
            telnet, transport_args.get("remote_mount"), transport_args.get("share_path")
        )
        transport_args["remote_mount"] = remote_mount
    else:
        usb_root = None
        remote_mount = resolve_router_usb_mount(telnet, transport_args.get("remote_mount"))
        transport_args["remote_mount"] = remote_mount
    verify_router_usb_storage(telnet, remote_mount)
    cleanup_incomplete_router_backups(telnet, remote_mount)
    remote_backup = backup_to_usb(telnet, remote_mount, family=profile.family)
    folder_name = PurePosixPath(remote_backup).name
    backup_dir = WORK / "backups" / folder_name
    if transport == "share":
        source = usb_root / folder_name
        if not source.is_dir():
            raise Error(f"backup не виден через share: {source}")
        copy_tree_verified(source, backup_dir, tr("Samba: backup с Nokia на ПК", "Samba: backup from Nokia to PC"))
    else:
        with ftp_connect(host, transport_args["ftp_user"], transport_args["ftp_password"], transport_args.get("ftp_port", 21)) as ftp:
            ftp_source = ftp_resolve_router_dir(ftp, remote_backup)
            total_bytes, total_files, sizes_complete = ftp_tree_stats(ftp, ftp_source)
            progress = TransferProgress(
                tr("FTP: backup с Nokia на ПК", "FTP: backup from Nokia to PC"),
                total_bytes if sizes_complete else 0, total_files,
            )
            ftp_walk_download(ftp, ftp_source, backup_dir, progress)
            progress.finish()
    _validate_install_backup(profile, backup_dir)
    return backup_dir, telnet


def install_openwrt_wizard(profile: InstallProfile, from_existing_backup: bool = False) -> None:
    """Shared MD/MF orchestration. Board differences live in InstallProfile/gates only."""
    verify_kit()
    manual = _choose_install_mode(profile)
    if manual is None:
        return
    if profile.family == "mf":
        print(tr(
            "[DANGER] Будет изменена разметка NAND и установлен OpenWrt UBI. Откат: UART + полный stock backup.",
            "[DANGER] NAND layout will be changed and OpenWrt UBI installed. Rollback: UART + full stock backup.",
        ))
    transition_lan_policy_notice()

    access = _install_access(profile)
    access.custom_sysupgrade = manual
    host = access.host
    warn_if_lan1_uplink(host, "установка OpenWrt", "OpenWrt installation")
    telnet: Telnet | None = None
    info: dict | None = None
    transport_args: dict = {}
    stage1_handoff = "not-started"
    try:
        if from_existing_backup:
            default = ""
            if profile.family == "mf":
                latest = _latest_mf_hw_backup()
                default = str(latest) if latest else ""
            prompt = tr(
                f"Путь к полному stock backup{f' [{default}]' if default else ''}: ",
                f"Path to the complete stock backup{f' [{default}]' if default else ''}: ",
            )
            entered = input(prompt).strip().strip('"')
            backup_dir = Path(entered or default).expanduser() if (entered or default) else Path()
            if not backup_dir.is_dir():
                raise Error(tr("каталог backup не найден", "backup directory not found"))
            print(tr("[WAIT] Проверяю выбранный stock backup до подготовки установочного пакета...", "[WAIT] Validating the selected stock backup before preparing the installation package..."))
            backup_validation = _validate_install_backup(profile, backup_dir)
            _print_install_backup_validation(profile, backup_dir, backup_validation)
            transport, transport_args = _install_transport(profile, access, install_only=True)
            telnet = login_root_family(access, profile.family, allow_service_provisioning=True)
            _install_live_gate(profile, access, telnet)
        else:
            transport, transport_args = _install_transport(profile, access, install_only=False)
            backup_dir, telnet = _capture_install_backup(profile, access, transport, transport_args)
            print(tr(
                f"[OK] Полный backup сохранён на ПК: {backup_dir}",
                f"[OK] Complete backup saved on the PC: {backup_dir}",
            ))
            backup_validation = _validate_install_backup(profile, backup_dir)
            _print_install_backup_validation(profile, backup_dir, backup_validation)

        install_dir, info = personalize_transition(profile, backup_dir, manual_transition=manual)
        print(tr(
            f"[OK] Персональный пакет создан: {install_dir}",
            f"[OK] Device-specific package created: {install_dir}",
        ))
        assert telnet is not None
        remote_dir = deploy_install(telnet, host, install_dir, transport, **transport_args)
        device_state = WORK / info["device_id"] / "state.json"
        save_state(device_state, {
            "phase": "deployed", "family": profile.family, "router": host,
            "remote_dir": remote_dir, "backup_dir": str(backup_dir),
            "manual_transition": manual,
        })
        stage1_handoff = run_stage1(
            telnet, remote_dir, nand_unknown=False,
            manual_transition=manual, profile=profile, access=access,
        )
        save_state(device_state, {
            "phase": "stage1_handoff_unknown" if stage1_handoff == "handoff-unknown" else "stage1_started",
            "stage1_handoff": stage1_handoff,
            "session_log": str(SESSION_LOG_PATH or ""),
        })
    finally:
        if telnet is not None:
            telnet.close()
        access.close_web(announce=False)

    if manual:
        final_result = run_custom_stage2(
            host, transport_args.get("local_ip"), transport_args.get("tftp_port", 1069),
            transport_args.get("block_size", 4096), expected_board=profile.expected_board,
        )
    else:
        final_result = run_stage2(
            host, expected_board=profile.expected_board,
            initial_handoff_unknown=(stage1_handoff == "handoff-unknown"),
        )
    stage_header("9" if manual else "7", "Итог установки", "Installation result")
    print(tr(f"[OK] Финальный статус: {final_result}", f"[OK] Final status: {final_result}"))
    assert info is not None
    save_state(WORK / info["device_id"] / "state.json", {
        "phase": "complete" if final_result != "post-install-unverified" else "post-install-unverified",
        "final_result": final_result, "session_log": str(SESSION_LOG_PATH or ""),
    })


def full_wizard() -> None:
    return install_openwrt_wizard(_active_install_profile(), from_existing_backup=False)


def install_from_existing_backup_wizard() -> None:
    return install_openwrt_wizard(_active_install_profile(), from_existing_backup=True)

def _console_only(text: str = "") -> None:
    """Write sensitive operator output to the physical console, never session logs."""
    stream = sys.stdout
    console = getattr(stream, "console", stream)
    console.write(text + ("" if text.endswith("\n") else "\n"))
    console.flush()


def _show_secret(label: str, value: object | None) -> None:
    text = "" if value is None else str(value)
    _register_log_secret(text)
    _console_only(f"  {label}: {text if text else '<empty>'}")
    _write_session_only(f"[CREDENTIALS] {label}: [SECRET OMITTED FROM LOG]")


def _parse_passwd_group_inventory(text: str) -> list[dict[str, object]]:
    pm = re.search(r"__MEDVE_PASSWD_BEGIN__\s*(.*?)\s*__MEDVE_PASSWD_END__", text, re.S)
    gm = re.search(r"__MEDVE_GROUP_BEGIN__\s*(.*?)\s*__MEDVE_GROUP_END__", text, re.S)
    if not pm:
        raise Error(tr("не удалось прочитать /etc/passwd", "failed to read /etc/passwd"))
    groups_by_gid: dict[int, str] = {}
    secondary: dict[str, list[str]] = {}
    if gm:
        for line in gm.group(1).replace("\r", "").splitlines():
            parts = line.strip().split(":")
            if len(parts) < 4 or not parts[2].isdigit():
                continue
            gname, gid, members = parts[0], int(parts[2]), parts[3]
            groups_by_gid[gid] = gname
            for member in filter(None, (x.strip() for x in members.split(","))):
                secondary.setdefault(member, []).append(gname)
    result: list[dict[str, object]] = []
    for line in pm.group(1).replace("\r", "").splitlines():
        parts = line.strip().split(":")
        if len(parts) < 7 or not parts[2].isdigit() or not parts[3].isdigit():
            continue
        name, uid, gid = parts[0], int(parts[2]), int(parts[3])
        home, shell = parts[5], parts[6]
        interactive = not bool(re.search(r"(?:nologin|false)$", shell))
        if uid == 0:
            privilege = "ROOT / UID 0"
        elif not interactive:
            privilege = "SERVICE / no-login"
        elif uid < 1000:
            privilege = "SYSTEM"
        else:
            privilege = "USER"
        groups = []
        if gid in groups_by_gid:
            groups.append(groups_by_gid[gid])
        groups.extend(x for x in secondary.get(name, []) if x not in groups)
        result.append({
            "name": name, "uid": uid, "gid": gid, "privilege": privilege,
            "groups": ",".join(groups) or "-", "home": home or "-", "shell": shell or "-",
        })
    return result


def _read_device_user_inventory(host: str, port: int, user: str, password: str) -> list[dict[str, object]]:
    telnet = _telnet_open_logged_in(host, port, user, password, 3)
    try:
        cmd = (
            "printf '__MEDVE_PASSWD_BEGIN__\\n'; cat /etc/passwd 2>/dev/null; "
            "printf '__MEDVE_PASSWD_END__\\n__MEDVE_GROUP_BEGIN__\\n'; "
            "cat /etc/group 2>/dev/null; printf '__MEDVE_GROUP_END__\\n'"
        )
        rc, out = telnet.command_clean(cmd, timeout=30)
        if rc:
            raise Error(tr("чтение пользователей через Telnet завершилось ошибкой", "reading users over Telnet failed"))
        return _parse_passwd_group_inventory(out)
    finally:
        telnet.close()


def _verify_device_uid0_secrets(access: StockAccess, inventory: list[dict[str, object]]) -> list[tuple[str, str, str]]:
    roots = [str(x["name"]) for x in inventory if int(x["uid"]) == 0]
    ordered = _ordered_uid0_candidates(roots, ("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "telecomadmin", "root"))
    labeled: list[tuple[str, str]] = []
    for label, secret in (("Telnet", access.password), ("FTP", access.ftp_password), ("empty", "")):
        if secret is None:
            continue
        secret = str(secret)
        if all(secret != existing for _label, existing in labeled):
            labeled.append((label, secret))
    matches: list[tuple[str, str, str]] = []
    for account in ordered[:12]:
        for source, secret in labeled:
            telnet = None
            try:
                telnet = _telnet_open_logged_in(access.host, access.telnet_port, access.user, access.password, 1)
                if _telnet_probe_uid(telnet) == 0:
                    matches.append((access.user, "direct Telnet", access.password))
                    return matches
                _telnet_su_root(telnet, account, secret, attempts=1)
                if _telnet_probe_uid(telnet) == 0:
                    matches.append((account, source, secret))
                    break
            except Exception as exc:
                _write_session_only(f"[CREDENTIALS] su probe account={account} source={source} result={exc.__class__.__name__}")
            finally:
                if telnet is not None:
                    telnet.close()
    return matches


def _credentials_telnet_fallback(host: str) -> None:
    """Optional read-only /etc/passwd inventory when stock Web is unavailable."""
    port_text = input(tr("Telnet port [23]: ", "Telnet port [23]: ")).strip()
    try:
        port = int(port_text) if port_text else 23
    except ValueError:
        print(tr("[INFO] Некорректный Telnet port; fallback пропущен.", "[INFO] Invalid Telnet port; fallback skipped."))
        return
    if not _tcp_open(host, port, timeout=1.5):
        print(tr(f"[INFO] Telnet {port} закрыт; /etc/passwd без Web-доступа прочитать нельзя.", f"[INFO] Telnet {port} is closed; /etc/passwd cannot be read without Web access."))
        return
    answer = input(tr("Telnet открыт. Выполнить read-only аудит с вручную введёнными credentials? [y/N]: ", "Telnet is open. Run a read-only audit with manually entered credentials? [y/N]: ")).strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        return
    user = input(tr("Telnet user [useradmin]: ", "Telnet user [useradmin]: ")).strip() or "useradmin"
    password = ask_label_password(tr("Telnet password: ", "Telnet password: "))
    _register_log_secret(password)
    try:
        inventory = _read_device_user_inventory(host, port, user, password)
    except Exception as exc:
        print(tr(f"[WARNING] Telnet inventory не выполнен: {exc}", f"[WARNING] Telnet inventory failed: {exc}"))
        return
    print(tr("\nВсе локальные пользователи из /etc/passwd (Telnet fallback):", "\nAll local users from /etc/passwd (Telnet fallback):"))
    print("  USER                     UID   GID   PRIVILEGE              GROUPS                  HOME                 SHELL")
    for row in inventory:
        print(f"  {str(row['name'])[:24]:24} {int(row['uid']):5} {int(row['gid']):5} {str(row['privilege'])[:22]:22} {str(row['groups'])[:23]:23} {str(row['home'])[:20]:20} {row['shell']}")
    roots = [str(x['name']) for x in inventory if int(x['uid']) == 0]
    print(tr(f"\nUID 0 accounts: {', '.join(roots) if roots else 'нет'}", f"\nUID-0 accounts: {', '.join(roots) if roots else 'none'}"))


def _load_stock_audit_parser():
    spec = importlib.util.spec_from_file_location("medveflasher_stock_audit_parse", STOCK_AUDIT_PARSER)
    if spec is None or spec.loader is None:
        raise Error(tr("не удалось загрузить parser stock audit", "failed to load the stock-audit parser"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stock_web_access(*, retain_web_session: bool) -> tuple[StockAccess, dict[str, object]]:
    """Read device-specific access data; optionally retain the authenticated Web session.

    Read-only audit/capability flows call this with ``False`` and the session is
    always logged out before the function returns.  Backup/install call the
    operational wrapper with ``True`` so an explicit
    ``allow_service_provisioning=True`` root flow can later enable exactly one
    stock service when a usable UID-0 account does not yet exist.
    """
    module = _load_stock_web_module()
    default_user = str(getattr(module, "DEFAULT_WEB_USER", "CMCCAdmin") or "CMCCAdmin")
    default_password = str(getattr(module, "DEFAULT_WEB_PASSWORD", "") or "")
    startup_host = str(_STARTUP_DEVICE_PROFILE.get("host") or "192.168.1.1")
    host = input(tr(f"IP Nokia [{startup_host}]: ", f"Nokia IP [{startup_host}]: ")).strip() or startup_host
    cached_auth = _startup_web_auth_for(host)
    if cached_auth is not None:
        web_user, web_password = cached_auth
        entered = None
        print(tr("[OK] Использую Web-реквизиты из стартового автоопределения.", "[OK] Reusing Web credentials from startup auto-detection."))
    else:
        web_user = input(tr(f"Web user [{default_user}]: ", f"Web user [{default_user}]: ")).strip() or default_user
        entered = _RAW_GETPASS(tr("Web password [hardcoded default - Enter]: ", "Web password [hardcoded default - Enter]: "))
        web_password = entered or default_password
    if not web_password:
        raise Error(tr("Web password не указан", "Web password was not provided"))
    _register_log_secret(web_password)
    client = module.StockWeb(host)
    keep_client = False
    try:
        mode = client.login(web_user, web_password, allow_plain=True)
        setup = module.StockSetup(client)
        info = setup.read_device_info()
        creds = setup.read_credentials()
        for key in ("telnet_password", "ftp_password"):
            _register_log_secret(creds.get(key))
        model_text = str(info.get("model") or "")
        chipset = str(info.get("chipset") or "")
        low = (model_text + " " + chipset).lower()
        if "040g-mf" in low or "7583" in low:
            family = "mf"
            model_label = "MF"
        elif "040g-md" in low or "7581" in low:
            family = "md"
            model_label = "MD"
        else:
            family = "unknown"
            model_label = "UNKNOWN"
        access = StockAccess(
            host=host,
            user=str(creds.get("telnet_user") or ""),
            password=str(creds.get("telnet_password") or ""),
            telnet_port=int(creds.get("telnet_port") or 23),
            ftp_user=str(creds.get("ftp_user") or ""),
            ftp_password=str(creds.get("ftp_password") or ""),
            ftp_port=int(creds.get("ftp_port") or 21),
            ftp_enabled=bool(creds.get("ftp_enabled")),
            model_verified=family in ("md", "mf"),
            model_verification_source=("stock-operational-web" if retain_web_session else "stock-audit-web"),
            family=family,
            model_name=model_text,
            chipset=chipset,
            web_client=client if retain_web_session else None,
            web_setup=setup if retain_web_session else None,
            web_module=module if retain_web_session else None,
        )
        if not _tcp_open(host, access.telnet_port, timeout=2.0):
            if retain_web_session:
                raise Error(tr(
                    f"Telnet {access.telnet_port} закрыт. Backup/install не включает Telnet скрытно; включите его штатным способом и повторите.",
                    f"Telnet {access.telnet_port} is closed. Backup/install does not enable Telnet silently; enable it through the stock UI and retry.",
                ))
            raise Error(tr(
                f"Telnet {access.telnet_port} закрыт. Stock Audit ничего не включает автоматически; откройте Telnet штатным способом и повторите.",
                f"Telnet {access.telnet_port} is closed. Stock Audit does not enable services automatically; enable Telnet through the stock UI and retry.",
            ))
        meta: dict[str, object] = {
            "family": family,
            "model_label": model_label,
            "model": model_text,
            "chipset": chipset,
            "web_mode": mode,
            "web_creds": "verified",
        }
        keep_client = retain_web_session
        return access, meta
    finally:
        if not keep_client:
            try:
                client.logout()
            except Exception:
                pass
        web_password = None
        entered = None


def _stock_audit_web_access() -> tuple[StockAccess, dict[str, object]]:
    """Read-only stock Web access; authenticated session is closed before return."""
    return _stock_web_access(retain_web_session=False)


def _stock_operational_web_access() -> tuple[StockAccess, dict[str, object]]:
    """Backup/install stock Web access; retains the session for explicit provisioning."""
    return _stock_web_access(retain_web_session=True)


def _audit_run(telnet: Telnet, report: list[str], command: str, timeout: int = 30) -> tuple[int, str]:
    report.append(f"$ {command}")
    try:
        rc, out = telnet.command_clean(command, timeout=timeout)
    except Exception as exc:
        report.append(f"AUDIT_COMMAND_ERROR type={exc.__class__.__name__} detail={str(exc).replace(chr(10), ' ')[:500]}")
        report.append("--- rc=255 ---")
        return 255, ""
    clean = out.replace("\x00", "").strip()
    if clean:
        report.extend(clean.splitlines())
    report.append(f"--- rc={rc} ---")
    return rc, clean


def _audit_section(report: list[str], name: str) -> None:
    report.append("")
    report.append(f"==={name}===")


def _collect_stock_audit(telnet: Telnet, access: StockAccess, meta: dict[str, object]) -> str:
    """Collect a reproducible stock snapshot after PC-side UID-0 proof."""
    report: list[str] = ["===MF-STOCK-AUDIT===", "audit_version=3", f"generated_epoch={int(time.time())}"]
    uid = _telnet_probe_uid(telnet)
    root_rc = 0 if uid == 0 else 1
    _audit_section(report, "CAPABILITY-EVIDENCE")
    report.extend([
        "web_creds=verified",
        "transport=telnet",
        "telnet=verified",
        f"root_uid={uid if uid is not None else 'UNKNOWN'}",
        f"root_probe_rc={root_rc}",
        f"root_via={access.su_user if access.su_user != 'auto' else ('direct-telnet' if uid == 0 else 'unknown')}",
        f"web_model={meta.get('model') or 'unknown'}",
        f"web_chipset={meta.get('chipset') or 'unknown'}",
    ])
    _audit_section(report, "ROOT-STATUS")
    report.append(f"AUDIT_ROOT_UID={uid if uid is not None else 'UNKNOWN'}")
    report.append(f"AUDIT_ROOT_RC={root_rc}")
    _audit_run(telnet, report, "id")
    _audit_run(telnet, report, "whoami")

    _audit_section(report, "IDENTITY")
    for cmd in (
        "uname -a",
        "cat /proc/version",
        "cat /proc/cpuinfo",
        "cat /proc/device-tree/model 2>/dev/null; echo",
        "cat /tmp/sysinfo/model 2>/dev/null",
        "cat /tmp/sysinfo/board_name 2>/dev/null",
        "cat /etc/board.json 2>/dev/null",
        "for f in /etc/version /etc/openwrt_release /etc/os-release /etc/*version* /usr/etc/version; do [ -f \"$f\" ] && { echo \"# $f\"; cat \"$f\"; }; done",
        "cat /proc/device-tree/serial-number 2>/dev/null; echo",
        "cat /sys/class/net/eth0/address 2>/dev/null",
    ):
        _audit_run(telnet, report, cmd, 30)

    _audit_section(report, "USERS")
    _audit_run(telnet, report, "cat /etc/passwd", 20)
    _audit_run(telnet, report, "cat /etc/group", 20)

    _audit_section(report, "SU-IMPLEMENTATION")
    for cmd in (
        "command -v su || which su",
        "readlink -f \"$(command -v su 2>/dev/null)\" 2>/dev/null",
        "ls -l \"$(command -v su 2>/dev/null)\" 2>/dev/null",
        "stat \"$(command -v su 2>/dev/null)\" 2>/dev/null",
        "busybox --list 2>/dev/null | grep '^su$'",
        "su --help </dev/null 2>&1 | head -8",
    ):
        _audit_run(telnet, report, cmd, 20)

    _audit_section(report, "MTD")
    _audit_run(telnet, report, "cat /proc/mtd", 20)
    _audit_run(telnet, report, "ls -l /dev/mtd* 2>/dev/null", 20)
    _audit_run(telnet, report,
        "for d in /sys/class/mtd/mtd*; do [ -d \"$d\" ] || continue; dev=$(basename \"$d\"); n=$(cat \"$d/name\" 2>/dev/null); s=$(cat \"$d/size\" 2>/dev/null); e=$(cat \"$d/erasesize\" 2>/dev/null); echo \"SYSFS_MTD dev=$dev name=$n size=$s erasesize=$e\"; done",
        45)

    _audit_section(report, "NAND-UBI")
    for cmd, timeout in (
        ("cat /proc/cmdline 2>/dev/null", 20),
        ("dmesg 2>/dev/null | head -400", 40),
        ("dmesg 2>/dev/null | grep -Ei 'nand|spi-nand|mtd|ubi|bmt|bad *block' | head -240", 30),
        (r"find /sys \( -iname '*nand*' -o -iname '*spi*nand*' -o -iname '*ubi*' \) 2>/dev/null | head -160", 45),
        ("for f in /sys/class/ubi/ubi*/mtd_num /sys/class/ubi/ubi*/total_eraseblocks /sys/class/ubi/ubi*/eraseblock_size /sys/class/ubi/ubi*/avail_eraseblocks; do [ -r \"$f\" ] && echo \"SYSFS_UBI path=$f value=$(cat \"$f\" 2>/dev/null)\"; done", 30),
        ("ubinfo -a 2>/dev/null", 40),
        ("cat /proc/mounts", 20),
        ("df -h 2>/dev/null", 20),
    ):
        _audit_run(telnet, report, cmd, timeout)

    _audit_section(report, "READ-PRIMITIVES")
    _audit_run(telnet, report,
        "for x in cat dd gzip tftp sha256sum mtd ubinfo strings od; do if command -v \"$x\" >/dev/null 2>&1; then echo \"AUDIT_TOOL name=$x present=1 path=$(command -v \"$x\")\"; else echo \"AUDIT_TOOL name=$x present=0\"; fi; done",
        30)
    _audit_run(telnet, report, "tftp --help 2>&1 | head -20", 20)

    _audit_section(report, "STOCK-UPGRADE-MECHANISM")
    find_expr = "find /etc /usr /bin /sbin -type f \\( -iname '*upgrade*' -o -iname '*update*' -o -iname '*flash*' -o -iname '*ubi*' \\) 2>/dev/null | head -250"
    _audit_run(telnet, report, find_expr + " | while IFS= read -r f; do echo \"AUDIT_FILE path=$f\"; done", 90)
    # Result lines are machine-marked. The parser ignores the echoed scanner
    # expression and accepts only output lines starting with AUDIT_HIT.
    scan = (
        find_expr + " | while IFS= read -r f; do "
        "grep -nEi 'mtd +write|nand +write|ubiupdatevol|ubiformat|ubimkvol|ubirmvol|flashcp|sysupgrade|mtd_write' \"$f\" 2>/dev/null | head -40 | "
        "while IFS= read -r hit; do echo \"AUDIT_HIT path=$f hit=$hit\"; done; done"
    )
    _audit_run(telnet, report, scan, 180)
    details = (
        find_expr + " | while IFS= read -r f; do "
        "sz=$(wc -c < \"$f\" 2>/dev/null | tr -d ' '); sha=$(sha256sum \"$f\" 2>/dev/null | awk '{print $1}'); "
        "link=$(readlink -f \"$f\" 2>/dev/null); echo \"AUDIT_META path=$f size=${sz:-unknown} sha256=${sha:-unknown} real=${link:-$f}\"; "
        "head -c 4 \"$f\" 2>/dev/null | od -An -tx1 2>/dev/null | grep -q '7f 45 4c 46' && { "
        "echo \"AUDIT_BINARY path=$f\"; strings \"$f\" 2>/dev/null | grep -Ei 'nand|mtd|ubi|ioctl|flash|kernel|rootfs|slave|active|boot' | head -80 | while IFS= read -r z; do echo \"AUDIT_STRING path=$f text=$z\"; done; "
        "} || { head -120 \"$f\" 2>/dev/null | while IFS= read -r z; do echo \"AUDIT_TEXT path=$f text=$z\"; done; }; done"
    )
    _audit_run(telnet, report, details, 240)
    _audit_section(report, "END")
    report.append("===MF-STOCK-AUDIT-END===")
    return "\n".join(report) + "\n"


def stock_audit_wizard() -> None:
    verify_kit()
    print(tr("\n=== Полный stock audit MD/MF (без записи flash/NAND) ===", "\n=== Full MD/MF stock audit (no flash/NAND writes) ==="))
    print(tr(
        "Web используется только для чтения device-specific credentials. Telnet должен быть уже открыт. su выполняется интерактивно на стороне ПК и принимается только после id -u = 0.",
        "Web is used only to read device-specific credentials. Telnet must already be open. su is driven interactively by the PC and accepted only after id -u = 0.",
    ))
    access, meta = _stock_audit_web_access()
    if str(meta.get("family")) not in ("md", "mf"):
        raise Error(tr("Web не подтвердил XG-040G-MD/MF; audit остановлен.", "Web did not confirm XG-040G-MD/MF; audit stopped."))
    model_label = str(meta.get("model_label") or "UNKNOWN")
    telnet = login_root_profile_dynamic(
        access,
        model=model_label,
        sessions=3,
        connect_attempts=3,
        preferred_accounts=("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "telecomadmin", "root"),
    )
    try:
        if _telnet_probe_uid(telnet) != 0:
            raise Error(tr("UID 0 не подтверждён; audit не запускается.", "UID 0 was not confirmed; audit will not run."))
        text = _collect_stock_audit(telnet, access, meta)
    finally:
        telnet.close()
        access.close_web(announce=False)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    family = str(meta.get("family") or "unknown")
    out_dir = WORK / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"nokia-{family}-stock-audit-{stamp}.log"
    log_path.write_text(text, encoding="utf-8")
    parser = _load_stock_audit_parser()
    profile = parser.build_profile(text)
    rendered = parser.render(profile)
    profile_path = out_dir / f"nokia-{family}-stock-profile-{stamp}.txt"
    profile_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(tr(f"[OK] Audit log: {log_path}", f"[OK] Audit log: {log_path}"))
    print(tr(f"[OK] Derived profile: {profile_path}", f"[OK] Derived profile: {profile_path}"))
    print(tr(
        "[POLICY] MD/MF используют одинаковое правило install: slot revision подтверждает family, но не является write allowlist. Перед destructive stage выбранный full backup перечитывается restore-validator'ом, stock handoff target проверяется точно, а RAM transition отдельно проверяет физическую UBI-геометрию.",
        "[POLICY] MD/MF use the same install rule: the slot revision proves the family but is not a write allowlist. Before the destructive stage the selected full backup is re-read by the restore validator, the stock handoff target is checked exactly, and the RAM transition independently checks physical UBI geometry.",
    ))


def parse_stock_audit_wizard() -> None:
    verify_kit()
    path = Path(input(tr("Путь к stock-audit .log: ", "Path to stock-audit .log: ")).strip().strip('"')).expanduser()
    if not path.is_file():
        raise Error(tr(f"audit log не найден: {path}", f"audit log not found: {path}"))
    parser = _load_stock_audit_parser()
    text = path.read_text(encoding="utf-8", errors="replace")
    print(parser.render(parser.build_profile(text)))


def credentials_menu() -> str:
    while True:
        print(tr("\n=== Credentials / диагностика stock ===", "\n=== Credentials / stock diagnostics ==="))
        print(tr("1 — показать credentials, всех пользователей и привилегии", "1 — show credentials, all users, and privileges"))
        print(tr("2 — полный stock audit MD/MF (Web → Telnet → доказанный UID 0 → MTD/UBI/upgrade inventory)", "2 — full MD/MF stock audit (Web -> Telnet -> proven UID 0 -> MTD/UBI/upgrade inventory)"))
        print(tr("3 — разобрать сохранённый stock-audit log", "3 — parse a saved stock-audit log"))
        print(tr("4 — назад", "4 — back"))
        choice = input(tr("Выберите 1/2/3/4: ", "Select 1/2/3/4: ")).strip()
        action = None
        label_ru = label_en = ""
        if choice == "1":
            action = credentials_wizard
            label_ru, label_en = "Credentials / пользователи: завершено", "Credentials / users: complete"
        elif choice == "2":
            action = stock_audit_wizard
            label_ru, label_en = "Stock audit: завершён", "Stock audit: complete"
        elif choice == "3":
            action = parse_stock_audit_wizard
            label_ru, label_en = "Разбор stock-audit log: завершён", "Stock-audit log parsing: complete"
        elif choice == "4":
            return "main"
        else:
            print(tr("Неверный выбор. Меню остаётся открытым.", "Invalid selection. The menu remains open."))
            continue
        nav, _ok = _run_interactive_action(
            action, label_ru=label_ru, label_en=label_en,
            section_ru="Credentials / диагностика stock", section_en="Credentials / stock diagnostics",
        )
        if nav == "section":
            continue
        return nav


def credentials_wizard() -> None:
    """Show known defaults plus device-derived credentials and local users.

    Secrets intentionally bypass _ConsoleTee and therefore never land in
    LATEST.log/session logs.  Device interrogation is GET/read-only except when
    the operator explicitly permits enabling Telnet to enumerate /etc/passwd.
    """
    verify_kit()
    module = _load_stock_web_module()
    default_user = str(getattr(module, "DEFAULT_WEB_USER", "CMCCAdmin") or "CMCCAdmin")
    default_password = str(getattr(module, "DEFAULT_WEB_PASSWORD", "") or "")
    print()
    print(tr("=== Credentials / пользователи / привилегии ===", "=== Credentials / users / privileges ==="))
    print(tr("Секреты показываются только в консоли и намеренно НЕ записываются в LATEST.log/session log.", "Secrets are shown only on the console and are intentionally NOT written to LATEST.log/session logs."))
    print(tr("\nHardcoded/default, входящие в текущий kit:", "\nHardcoded/default values shipped by the current kit:"))
    print(f"  Web user: {default_user}")
    if default_password:
        _show_secret("Web password", default_password)
    print(tr("  UART/console: отдельный пароль telecomadmin для XG-040G-MD/MF в kit не зашит; существование такого пользователя проверяется ниже по /etc/passwd.", "  UART/console: no separate telecomadmin password for XG-040G-MD/MF is hardcoded in the kit; the account is checked below from /etc/passwd."))

    host = input(tr("IP Nokia [192.168.1.1]: ", "Nokia IP [192.168.1.1]: ")).strip() or "192.168.1.1"
    web_user = input(tr(f"Web user [{default_user}]: ", f"Web user [{default_user}]: ")).strip() or default_user
    entered = _RAW_GETPASS(tr("Web password [hardcoded default — Enter]: ", "Web password [hardcoded default — Enter]: "))
    web_password = entered or default_password
    if not web_password:
        raise Error(tr("Web password не указан", "Web password was not provided"))
    _register_log_secret(web_password)
    client = module.StockWeb(host)
    try:
        print(tr("[WAIT] Проверяю stock Web UI; transient disconnects автоматически повторяются...", "[WAIT] Probing the stock Web UI; transient disconnects are retried automatically..."))
        mode = client.login(web_user, web_password, allow_plain=True)
        setup = module.StockSetup(client)
        info = setup.read_device_info()
        creds = setup.read_credentials()
        for key in ("telnet_password", "ftp_password"):
            _register_log_secret(creds.get(key))
        print(tr(
            f"[OK] Устройство: {info.get('model') or 'unknown'}" + (f" / {info.get('chipset')}" if info.get('chipset') else ""),
            f"[OK] Device: {info.get('model') or 'unknown'}" + (f" / {info.get('chipset')}" if info.get('chipset') else ""),
        ))
        if mode == "plain":
            print(tr("[WARN] Web UI потребовала/приняла plain HTTP login.", "[WARN] The Web UI required/accepted plain HTTP login."))
        _console_only(tr("\nСчитано с конкретного устройства:", "\nRead from this specific device:"))
        _console_only(f"  Telnet user: {creds['telnet_user']}  port {creds['telnet_port']}  enabled={creds['telnet_enabled']}")
        _show_secret("Telnet password", creds["telnet_password"])
        _console_only(f"  FTP user: {creds['ftp_user'] or '<empty>'}  port {creds['ftp_port']}  enabled={creds['ftp_enabled']}")
        _show_secret("FTP password", creds["ftp_password"])
        try:
            _cfg, samba_accounts, _csrf = setup.samba_state()
        except Exception as exc:
            samba_accounts = {}
            print(tr(f"[WARN] Samba accounts не прочитаны: {exc}", f"[WARN] Samba accounts could not be read: {exc}"))
        if samba_accounts:
            _console_only(tr("\nSamba accounts из Web UI:", "\nSamba accounts from Web UI:"))
            items = samba_accounts.values() if isinstance(samba_accounts, dict) else []
            for index, row in enumerate(items, 1):
                if not isinstance(row, dict):
                    continue
                visible=[]
                for key, value in row.items():
                    if re.search(r"pass|pwd|secret", str(key), re.I):
                        _show_secret(f"Samba[{index}] {key}", value)
                    else:
                        visible.append(f"{key}={value}")
                if visible:
                    _console_only(f"  Samba[{index}] " + ", ".join(visible))

        telnet_port = int(creds["telnet_port"])
        port_open_now = _tcp_open(host, telnet_port, timeout=1.5)
        if not port_open_now:
            print(tr(
                f"\n[INFO] Telnet {telnet_port} закрыт. Для полного списка /etc/passwd и привилегий его нужно включить через stock Web UI.",
                f"\n[INFO] Telnet {telnet_port} is closed. It must be enabled through the stock Web UI to enumerate /etc/passwd and privileges.",
            ))
            answer = input(tr("Включить Telnet и продолжить аудит? [y/N]: ", "Enable Telnet and continue the audit? [y/N]: ")).strip().lower()
            if answer in ("y", "yes", "д", "да"):
                print(tr("[WRITE] Включаю только Telnet через штатный Web UI; NAND не изменяется.", "[WRITE] Enabling Telnet only through the stock Web UI; NAND is not modified."))
                setup.enable_telnet(port=telnet_port)
                port_open_now = _tcp_open(host, telnet_port, timeout=2.0)
        if not port_open_now:
            print(tr("[INFO] Полный OS user inventory пропущен: Telnet закрыт.", "[INFO] Full OS user inventory skipped: Telnet is closed."))
            return

        access = StockAccess(
            host=host, user=str(creds["telnet_user"]), password=str(creds["telnet_password"]),
            telnet_port=telnet_port, ftp_user=str(creds.get("ftp_user") or ""),
            ftp_password=str(creds.get("ftp_password") or ""), ftp_port=int(creds.get("ftp_port") or 21),
            ftp_enabled=bool(creds.get("ftp_enabled")), model_verified=True,
            model_verification_source="credentials-audit-web",
        )
        inventory = _read_device_user_inventory(host, telnet_port, access.user, access.password)
        print(tr("\nВсе локальные пользователи из /etc/passwd:", "\nAll local users from /etc/passwd:"))
        print("  USER                     UID   GID   PRIVILEGE              GROUPS                  HOME                 SHELL")
        for row in inventory:
            print(f"  {str(row['name'])[:24]:24} {int(row['uid']):5} {int(row['gid']):5} {str(row['privilege'])[:22]:22} {str(row['groups'])[:23]:23} {str(row['home'])[:20]:20} {row['shell']}")
        roots = [str(x['name']) for x in inventory if int(x['uid']) == 0]
        print(tr(f"\nUID 0 accounts: {', '.join(roots) if roots else 'нет'}", f"\nUID-0 accounts: {', '.join(roots) if roots else 'none'}"))
        if any(str(x['name']).lower() == 'telecomadmin' for x in inventory):
            print(tr("[FOUND] telecomadmin реально присутствует на этом устройстве.", "[FOUND] telecomadmin is actually present on this device."))
        else:
            print(tr("[INFO] telecomadmin в /etc/passwd этого устройства не найден.", "[INFO] telecomadmin was not found in this device's /etc/passwd."))

        matches = _verify_device_uid0_secrets(access, inventory)
        if matches:
            _console_only(tr("\nПроверенные UID-0 credentials (только device-provided пароли, без перебора словаря):", "\nVerified UID-0 credentials (device-provided passwords only; no dictionary guessing):"))
            for account, source, secret in matches:
                _console_only(f"  {account}  <= password source: {source}")
                _show_secret(f"{account} password", secret)
        else:
            print(tr("[INFO] Ни один UID-0 su credential из Telnet/FTP паролей устройства не подтверждён.", "[INFO] No UID-0 su credential matched the device's Telnet/FTP passwords."))
    except (module.LoginError, module.SetupError, module.UnsupportedFirmware, OSError) as exc:
        detail = _web_failure_detail(exc)
        print(tr(
            f"[WARNING] Stock Web UI сейчас недоступен или закрыл соединение: {detail}",
            f"[WARNING] The stock Web UI is unavailable or closed the connection: {detail}",
        ))
        _write_session_only(f"[CREDENTIALS] web audit unavailable: {exc.__class__.__name__}: {detail}")
        print(tr(
            "[INFO] Hardcoded/default credentials выше уже показаны. Device-specific Telnet/FTP/Samba secrets через Web не считаны; master не завершается аварийно.",
            "[INFO] Hardcoded/default credentials were already shown above. Device-specific Telnet/FTP/Samba secrets were not read from Web; the master will not abort.",
        ))
        _credentials_telnet_fallback(host)
    finally:
        try:
            client.logout()
        except Exception:
            pass
        web_password = None
        entered = None


def backup_only_wizard() -> None:
    verify_kit()
    print(tr(
        "=== Stock backup MD/MF через работающую прошивку ===",
        "=== MD/MF stock backup through running firmware ===",
    ))
    print(tr(
        "Модель определяется заново через stock Web и подтверждается реальной MTD-разметкой. Ручной выбор при старте программы не является разрешением на backup.",
        "The model is re-detected through the stock Web UI and confirmed by the live MTD map. A manual startup selection is not authorization for backup.",
    ))
    access, meta = _stock_operational_web_access()
    try:
        family = str(meta.get("family") or "unknown")
        if family not in ("md", "mf"):
            raise Error(tr("Web не подтвердил MD/MF; backup заблокирован", "Web did not confirm MD/MF; backup is blocked"))
        host = access.host
        warn_if_lan1_uplink(host, "снятие stock backup", "stock backup")
        model_name = str(meta.get("model") or ("XG-040G-MF" if family == "mf" else "XG-040G-MD"))
        print(tr(f"[OK] Backup target: {model_name} / {str(meta.get('chipset') or '?')}", f"[OK] Backup target: {model_name} / {str(meta.get('chipset') or '?')}"))
        print(tr("1 — полный backup напрямую на ПК через TFTP (рекомендуется)", "1 — complete backup directly to the PC over TFTP (recommended)"))
        print(tr("2 — полный backup на USB-флешку в порту Nokia", "2 — complete backup to a USB drive in the Nokia USB port"))
        choice = input(tr("Выберите 1/2 [1]: ", "Select 1/2 [1]: ")).strip() or "1"
        if choice == "2":
            print_usb_requirements()
            telnet = login_root_family(access, family, allow_service_provisioning=True)
            try:
                if family == "mf":
                    # New MF backend: require the same strict live geometry proof as TFTP.
                    # Keep the established MD USB backup behavior unchanged.
                    _stock_live_geometry_preflight(telnet, family, require_slot_family=False)
                mount = input(tr("Путь USB внутри Nokia [автоопределение: /mnt/USB_disc1]: ", "USB path inside Nokia [auto-detect: /mnt/USB_disc1]: ")).strip() or None
                mount = resolve_router_usb_mount(telnet, mount)
                verify_router_usb_storage(telnet, mount)
                cleanup_incomplete_router_backups(telnet, mount)
                result = backup_to_usb(telnet, mount, family=family)
                print(tr(f"[OK] Backup готов на USB-флешке: {result}", f"[OK] Backup completed on the USB drive: {result}"))
                print(tr("Скопируйте весь каталог на ПК и запустите verify-stock-restore перед любой записью NAND.", "Copy the whole directory to the PC and run verify-stock-restore before any NAND write."))
            finally:
                telnet.close()
        elif choice == "1":
            stamp = time.strftime("%Y%m%d-%H%M%S")
            destination = WORK / "backups" / f"nokia-xg040g{family}-backup-{stamp}"
            local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
            port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
            port = int(port_text) if port_text else 1069
            result = backup_tftp(access, host, destination, local_ip, port, 4096, expected_family=family)
            print(tr(f"[OK] Backup готов и аппаратно провалидирован на ПК: {result}", f"[OK] Backup completed and hardware-validated on the PC: {result}"))
            if family == "mf":
                print(tr("[OK] MF normal stock backup HW gate пройден для этой копии: root + MTD/sysfs + TFTP + transport-stream SHA256 + restore-validator.", "[OK] The MF normal stock-backup HW gate passed for this copy: root + MTD/sysfs + TFTP + transport-stream SHA256 + restore validator."))
        else:
            raise Error(tr("неверный выбор", "invalid selection"))
    finally:
        access.close_web(announce=False)


def personalize_wizard() -> None:
    verify_kit()
    profile = _active_install_profile()
    manual = _choose_install_mode(profile)
    if manual is None:
        return
    path = Path(input(tr("Путь к каталогу полного backup: ", "Path to the complete backup directory: ")).strip().strip('"')).expanduser()
    output, info = personalize_transition(profile, path, manual_transition=manual)
    print(tr(f"[OK] Персональный пакет создан: {output}", f"[OK] Device-specific package created: {output}"))
    for warning in info["backup"].get("warnings", []):
        print("WARNING:", warning)

def resume_stage2_wizard() -> None:
    print(tr(
        "=== Продолжение установки после transition OpenWrt ===\nЭтап 2 означает: transition уже загружен в RAM; мастер проверяет его состояние, затем форматирует целевой NAND в UBI, передаёт и записывает постоянный sysupgrade OpenWrt и контролирует первый запуск.",
        "=== Continue installation after transition OpenWrt ===\nStage 2 means: transition is already running in RAM; the wizard checks its state, then formats the target NAND as UBI, transfers and flashes the persistent OpenWrt sysupgrade, and monitors first boot.",
    ))
    host = input("IP transition OpenWrt [192.168.1.1]: ").strip() or "192.168.1.1"
    warn_if_lan1_uplink(host, "продолжение установки (этап 2)", "installation continuation (stage 2)")
    manual = False
    manual_state = ""
    expected_board = "nokia,xg-040g-md-ubi"
    board_name = ""
    if _tcp_open(host, 22):
        manual, manual_state, board_name, probe_error = _manual_transition_probe(host, timeout=8)
        if board_name == "nokia,xg-040g-mf-ubi":
            expected_board = board_name
        if probe_error:
            _write_session_only(f"[MANUAL-SSH] resume probe failed: {probe_error}")
            raise Error(tr(
                f"SSH 22 открыт, но режим transition определить не удалось: {probe_error[-500:]}",
                f"SSH 22 is open, but the transition mode could not be identified: {probe_error[-500:]}",
            ))
        elif manual and board_name not in ("nokia,xg-040g-md-ubi", "nokia,xg-040g-mf-ubi"):
            _write_session_only(f"[MANUAL-SSH] resume marker accepted; board_name={board_name!r}")
    if manual:
        print(tr(f"[OK] Обнаружен ручной transition; состояние: {manual_state or 'unknown'}.", f"[OK] Manual transition detected; state: {manual_state or 'unknown'}."))
        if manual_state in ("STARTING", "CHECKING", "FORMATTING_AND_FLASHING", "WAITING_FOR_SYSTEM", "FAILED"):
            result = run_stage2(host, manual_mode=True, expected_board=expected_board)
        else:
            local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
            port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
            result = run_custom_stage2(host, local_ip, int(port_text) if port_text else 1069, 4096, expected_board=expected_board)
    else:
        # Automatic transition board is learned once SSH comes up in run_stage2;
        # when startup was a VERIFIED MF, monitor the MF production identity.
        prof = _STARTUP_DEVICE_PROFILE
        if prof.get("verified") and prof.get("family") == "mf":
            expected_board = "nokia,xg-040g-mf-ubi"
        result = run_stage2(host, expected_board=expected_board)
    stage_header("9" if manual else "7", "Итог ожидания", "Monitoring result")
    print(tr(f"[OK] Финальный статус: {result}", f"[OK] Final status: {result}"))



def _latest_mf_hw_backup() -> Path | None:
    root = WORK / "backups"
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    for path in root.iterdir():
        marker = path / "BACKUP_HW_VALIDATED"
        if not path.is_dir() or not marker.is_file():
            continue
        evidence = marker.read_text(encoding="utf-8", errors="replace").lower()
        if "family=mf" in evidence and "variant=mf-a" in evidence:
            candidates.append(path)
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _wait_mf_ram_openwrt(host: str, timeout: int = 360) -> str:
    print(tr("[WAIT] Ожидаю reboot в MF initramfs/RAM OpenWrt; UBI/sysupgrade не запускаются...", "[WAIT] Waiting for reboot into the MF initramfs/RAM OpenWrt; no UBI/sysupgrade operation is started..."))
    deadline = time.time() + timeout
    seen_down = False
    last_status = 0.0
    while time.time() < deadline:
        port80 = _tcp_open(host, 80, timeout=1.0)
        port443 = _tcp_open(host, 443, timeout=1.0)
        port22 = _tcp_open(host, 22, timeout=1.0)
        if not (port80 or port443 or port22):
            seen_down = True
        if seen_down and ((_probe_luci(host, 80) if port80 else False) or (_probe_luci(host, 443) if port443 else False)):
            return "luci"
        if seen_down and port22:
            try:
                rc, out = ssh_run(host, "cat /tmp/sysinfo/board_name 2>/dev/null; uname -a", timeout=25, quiet=True, batch_mode=True, minimal_auth=True)
                low = out.lower()
                if rc == 0 and ("xg-040g-mf" in low or "an7583" in low):
                    return "ssh"
            except Exception:
                pass
        now = time.time()
        if now - last_status >= 15:
            print(tr(f"[WAIT] RAM OpenWrt: tcp22={int(port22)} http={int(port80)} https={int(port443)}; прошло {int(timeout-(deadline-now))}s...", f"[WAIT] RAM OpenWrt: tcp22={int(port22)} http={int(port80)} https={int(port443)}; elapsed {int(timeout-(deadline-now))}s..."))
            last_status = now
        time.sleep(3)
    raise Error(tr(
        "MF initramfs не удалось однозначно подтвердить по сети. NAND/UBI stage 2 НЕ запускался. Сохраните UART-лог перед дальнейшими действиями.",
        "The MF initramfs could not be proven unambiguously over the network. NAND/UBI stage 2 was NOT started. Save the UART log before taking further action.",
    ))


def _firmware_capability_rows(family: str, variant: str, live_root: bool, geometry_ok: bool, backup_io_ok: bool = True) -> list[tuple[str, str]]:
    """Render release capability plus current live gates without authorizing writes.

    MD and MF use the same destructive-policy semantics: the vendor slot
    revision is family evidence only.  A permanent install still requires a
    restore-grade full backup, exact stock handoff geometry, and the exact
    board-specific physical UBI target checks in the transition RAM system.
    """
    family = (family or "unknown").lower()
    variant = variant or "UNKNOWN"
    live = live_root and geometry_ok
    backup_live = live and backup_io_ok
    rows: list[tuple[str, str]] = [
        ("CAP_STOCK_ROOT", "YES - live UID 0" if live_root else "BLOCKED - live UID 0 not proven"),
        ("CAP_MTD_GEOMETRY", f"YES - {variant}; /proc == sysfs" if geometry_ok else "BLOCKED - geometry not proven"),
    ]
    if family == "md":
        rows.extend([
            ("CAP_FULL_BACKUP", "YES - restore-grade MD backend available" if backup_live else "BLOCKED - live root/geometry/transport gate"),
            ("CAP_MF_TRANSITION_BOOT", "N/A - MD uses the hardware-confirmed MD transition path"),
            ("CAP_RAM_OPENWRT", "YES - HW CONFIRMED MD transition path" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_UBI_FORMAT", "READY - RAM stage requires exact 256MiB/0x20000/0x0FFE0000 target" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_UBI_VOLUME_WRITE", "READY - canonical UBI volumes with readback in MD stage 2" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_BOOTLOADER_REPLACE", "EXPERIMENTAL - tcboot research only; not enabled"),
            ("CAP_PERMANENT_INSTALL", "READY - HW-confirmed MD path; full backup + exact target gates still mandatory" if backup_live else "BLOCKED - full backup/live target prerequisites"),
            ("CAP_UART_RECOVERY", "RC18 RECOVERY_SAFE - exact FIP HW regression pending"),
        ])
    elif family == "mf":
        rows.extend([
            ("CAP_FULL_BACKUP", "YES - restore-grade MF backend available" if backup_live else "BLOCKED - live root/geometry/transport gate"),
            ("CAP_MF_TRANSITION_BOOT", "YES - HW CONFIRMED AN7583 transition path" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_RAM_OPENWRT", "YES - HW CONFIRMED MF transition initramfs path" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_UBI_FORMAT", "READY - RAM stage requires exact 256MiB/0x20000/0x0FFE0000 target" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_UBI_VOLUME_WRITE", "READY - canonical UBI volumes with readback in MF stage 2" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_BOOTLOADER_REPLACE", "READY - pinned MF BL2 written last after UBI readbacks" if live else "BLOCKED - live family/geometry gate"),
            ("CAP_PERMANENT_INSTALL", "READY - HW-confirmed MF path; full backup + exact target gates still mandatory" if backup_live else "BLOCKED - full backup/live target prerequisites"),
            ("CAP_UART_RECOVERY", "RC18 RECOVERY_SAFE - base path HW confirmed; exact safe FIP pending"),
        ])
    else:
        rows.extend([
            ("CAP_FULL_BACKUP", "BLOCKED - family unknown"),
            ("CAP_MF_TRANSITION_BOOT", "BLOCKED - family unknown"),
            ("CAP_RAM_OPENWRT", "BLOCKED - family unknown"),
            ("CAP_UBI_FORMAT", "BLOCKED - family unknown"),
            ("CAP_UBI_VOLUME_WRITE", "BLOCKED - family unknown"),
            ("CAP_BOOTLOADER_REPLACE", "BLOCKED - family unknown"),
            ("CAP_PERMANENT_INSTALL", "BLOCKED - family unknown"),
            ("CAP_UART_RECOVERY", "AVAILABLE ONLY AFTER SoC-specific recovery gate"),
        ])
    return rows

def _print_firmware_capability_report(model: str, chipset: str, family: str, variant: str, rows: list[tuple[str, str]]) -> None:
    print(tr("\n=== Прошивочные capabilities (read-only report) ===", "\n=== Firmware capabilities (read-only report) ==="))
    print(f"Device                 {model or '?'}" + (f" / {chipset}" if chipset else ""))
    print(f"Family / variant       {family.upper() if family in ('md','mf') else '?'} / {variant}")
    print("")
    for key, value in rows:
        print(f"  {key:<26} {value}")
    print("")
    if family in ("md", "mf"):
        print(tr(
            "[POLICY] MD/MF симметричны: stock slot revision определяет family, но не разрешает и не запрещает UBI-format. Install отдельно требует полный revalidated backup, точный stock handoff target и точную физическую UBI-геометрию в RAM transition.",
            "[POLICY] MD/MF are symmetric: the stock slot revision identifies the family but neither authorizes nor vetoes UBI format. Install separately requires a fully revalidated backup, the exact stock handoff target, and exact physical UBI geometry in the RAM transition.",
        ))


def firmware_capabilities_wizard() -> None:
    """Prove current stock access/geometry and render release flashing gates.

    Web is read-only here, Telnet must already be enabled, and no discovered
    upgrade utility is executed. No flash/NAND/UBI write command is sent.
    """
    verify_kit()
    print(tr(
        "\n=== Проверка прошивочных capabilities MD/MF (без записи flash/NAND) ===",
        "\n=== MD/MF firmware capability probe (no flash/NAND writes) ===",
    ))
    access, meta = _stock_audit_web_access()
    family = str(meta.get("family") or "unknown")
    if family not in ("md", "mf"):
        access.close_web(announce=False)
        raise Error(tr("Web не подтвердил MD/MF", "Web did not confirm MD/MF"))
    telnet: Telnet | None = None
    try:
        telnet = login_root_profile_dynamic(
            access,
            model=str(meta.get("model_label") or family.upper()),
            sessions=3,
            connect_attempts=3,
            preferred_accounts=("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "telecomadmin", "root"),
        )
        uid = _telnet_probe_uid(telnet)
        root_ok = uid == 0
        if not root_ok:
            raise Error(tr("CAP_STOCK_ROOT: UID 0 не доказан", "CAP_STOCK_ROOT: UID 0 was not proven"))
        _proc, detected_family, variant = _stock_live_geometry_preflight(
            telnet, family, require_ro=False, require_slot_family=False)
        geometry_ok = detected_family == family
        rc, io_text = telnet.command(
            'ok=1; n=0; while [ $n -le 16 ]; do '
            'if [ "' + detected_family + '" = mf ]; then [ -r /dev/mtd${n}ro ] || ok=0; '
            'else { [ -r /dev/mtd${n} ] || [ -r /dev/mtd${n}ro ]; } || ok=0; fi; '
            'n=$((n+1)); done; '
            'for x in gzip tftp sha256sum tee; do command -v "$x" >/dev/null 2>&1 || ok=0; done; echo CAP_BACKUP_IO_OK=$ok',
            timeout=30, echo=False,
        )
        backup_io_ok = rc == 0 and "CAP_BACKUP_IO_OK=1" in io_text
        rows = [
            ("CAP_WEB_CREDS", "YES - live Web login"),
            ("CAP_TELNET", "YES - live Telnet"),
        ] + _firmware_capability_rows(detected_family, variant, root_ok, geometry_ok, backup_io_ok)
        _print_firmware_capability_report(
            str(meta.get("model") or access.model_name or ""),
            str(meta.get("chipset") or access.chipset or ""),
            detected_family,
            variant,
            rows,
        )
    finally:
        if telnet is not None:
            telnet.close()
        access.close_web(announce=False)


def _selftest_mf_transition_release() -> None:
    """Static regression for the shared profile-driven MD/MF installer."""
    verify_kit()
    md_auto = transition_release_metadata(MD_INSTALL_PROFILE, MD_INSTALL_PROFILE.auto_bundle)
    md_manual = transition_release_metadata(MD_INSTALL_PROFILE, MD_INSTALL_PROFILE.manual_bundle)
    mf_auto = transition_release_metadata(MF_INSTALL_PROFILE, MF_INSTALL_PROFILE.auto_bundle)
    mf_manual = transition_release_metadata(MF_INSTALL_PROFILE, MF_INSTALL_PROFILE.manual_bundle)
    assert md_auto["production_size"] > 0 and md_manual["production_size"] == 0
    assert mf_auto["production_sha"] == MF_UBI_SYSUPGRADE_SHA and mf_auto["production_size"] == MF_UBI_SYSUPGRADE_SIZE
    assert mf_manual["production_size"] == 0 and mf_manual["bundle_size"] == 0x800000
    text = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    assert "PROFILE_FAMILY=" in text and "PROFILE_LABEL=" in text
    assert "MF-A-MIRROR" in text and "MF-B" in text
    assert "003af6da:01cc0000:00480000:02400000" in text
    assert '"$STAGE_RAM/busybox" sh "$STAGE_RAM/flash.sh"' in text
    assert "RAM BusyBox applet missing: ash" not in text
    assert "rbb awk" not in text
    assert "for applet in dd reboot sha256sum sleep sync tr wc; do" in text
    assert "permanent write is enabled only for hardware-confirmed MF-A" not in text
    assert "permanent write is enabled only for hardware-observed layouts" not in text
    # The slot policy is intentionally permissive only at the vendor-view layer.
    # Both board-specific RAM installers must still pin the actual physical NAND
    # format target before ubiformat can run.
    md_stage2 = (DATA / "recovery" / "transition-control-source" / "shipped-md-nokia-ubi-installer.sh").read_text(encoding="utf-8")
    mf_stage2 = (DATA / "recovery" / "transition-control-source" / "shipped-mf-nokia-ubi-installer.sh").read_text(encoding="utf-8")
    for stage2 in (md_stage2, mf_stage2):
        assert "require_mtd all_flash 268435456" in stage2
        assert "require_mtd bl2 131072" in stage2
        assert "268304384" in stage2
        assert "ubiformat -y" in stage2
    assert "require_mtd ibu 268304384" in md_stage2
    assert "require_mtd ubi 268304384" in mf_stage2
    assert not (MF_RECOVERY_DIR / "openwrt-airoha-an7583-nokia_xg-040g-mf-ubi-preloader.bin").exists()
    assert not (MF_RECOVERY_DIR / "openwrt-airoha-an7583-nokia_xg-040g-mf-ubi-bl31-uboot.fip").exists()
    assert not (MF_RECOVERY_DIR / "openwrt-airoha-an7583-nokia_xg-040g-mf-ubi-squashfs-sysupgrade.itb").exists()
    assert not (MF_RECOVERY_DIR / "nokia-xg040gmf-medveflasher-auto-initramfs.itb").exists()
    assert not (MF_RECOVERY_DIR / "nokia-xg040gmf-medveflasher-manual-initramfs.itb").exists()
    print("shared MD/MF transition installer selftest: PASS")

def _selftest_firmware_capabilities() -> None:
    md_rev = dict(_firmware_capability_rows("md", "MD-A-MIRROR-REV", True, True))
    mf_a = dict(_firmware_capability_rows("mf", "MF-A", True, True))
    mf_b = dict(_firmware_capability_rows("mf", "MF-B", True, True))
    mf_rev = dict(_firmware_capability_rows("mf", "MF-A-REV", True, True))
    blocked = dict(_firmware_capability_rows("mf", "MF-A-REV", False, True))
    no_io = dict(_firmware_capability_rows("md", "MD-A-MIRROR-REV", True, True, False))
    assert md_rev["CAP_PERMANENT_INSTALL"].startswith("READY")
    assert md_rev["CAP_UBI_FORMAT"].startswith("READY")
    assert mf_a["CAP_FULL_BACKUP"].startswith("YES")
    assert mf_a["CAP_MF_TRANSITION_BOOT"].startswith("YES")
    assert mf_a["CAP_PERMANENT_INSTALL"].startswith("READY")
    # Exact MF-A, MF-B and tolerated MF revisions share the same install policy.
    assert mf_b["CAP_PERMANENT_INSTALL"] == mf_a["CAP_PERMANENT_INSTALL"]
    assert mf_rev["CAP_PERMANENT_INSTALL"] == mf_a["CAP_PERMANENT_INSTALL"]
    assert blocked["CAP_PERMANENT_INSTALL"].startswith("BLOCKED")
    assert no_io["CAP_PERMANENT_INSTALL"].startswith("BLOCKED")
    print("firmware-capabilities selftest: PASS")

def firmware_menu() -> str:
    while True:
        startup_family = str(_STARTUP_DEVICE_PROFILE.get("family") or "")
        profile = INSTALL_PROFILES.get(startup_family)
        profile_label = profile.model if profile is not None else tr("профиль не выбран (MD/MF)", "no profile selected (MD/MF)")
        print(tr(
            f"\n=== Прошивка / восстановление — {profile_label} ===",
            f"\n=== Flashing / recovery — {profile_label} ===",
        ))
        if _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
            print(tr(
                "[SAFETY-LATCH] Есть незавершённый/неподтверждённый NAND write. Пункты 1/2/3 блокируются до успешного полного BootROM/UART recovery.",
                "[SAFETY-LATCH] A NAND write is incomplete/unproven. Options 1/2/3 are blocked until a successful full BootROM/UART recovery.",
            ))
        print(tr("1 — установить OpenWrt UBI (с обязательным backup)", "1 — install OpenWrt UBI (mandatory backup)"))
        print(tr("2 — установить OpenWrt UBI из готового stock backup", "2 — install OpenWrt UBI from an existing stock backup"))
        print(tr("3 — восстановить stock без UART", "3 — restore stock without UART"))
        print(tr("4 — восстановить через BootROM/UART", "4 — recover through BootROM/UART"))
        print(tr("5 — проверить capabilities", "5 — probe capabilities"))
        print(tr("6 — назад", "6 — back"))
        choice = input(tr("Выберите 1/2/3/4/5/6: ", "Select 1/2/3/4/5/6: ")).strip()
        if choice in {"1", "2", "3"} and _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
            print(tr(
                "[BLOCKED] Этот write-path заблокирован SAFETY-LATCH. Используйте 4 для полного RECOVERY_SAFE BootROM/UART restore либо read-only диагностику.",
                "[BLOCKED] This write path is blocked by SAFETY-LATCH. Use option 4 for a full RECOVERY_SAFE BootROM/UART restore or use read-only diagnostics.",
            ))
            continue
        if choice in {"1", "2"} and profile is None:
            print(tr(
                "[BLOCKED] Для установки сначала выберите/определите профиль MD или MF. UART recovery можно запускать без профиля: семейство определяется по stock backup.",
                "[BLOCKED] Select/detect an MD or MF profile before installation. UART recovery may run without a profile: the family is determined from the stock backup.",
            ))
            continue
        if choice == "6":
            return "main"
        if choice == "1":
            action = lambda: install_openwrt_wizard(profile, from_existing_backup=False)
            label_ru, label_en = "Установка OpenWrt UBI: завершена", "OpenWrt UBI installation: complete"
        elif choice == "2":
            action = lambda: install_openwrt_wizard(profile, from_existing_backup=True)
            label_ru, label_en = "Установка OpenWrt UBI из готового backup: завершена", "OpenWrt UBI installation from existing backup: complete"
        elif choice == "3":
            action = stock_restore_running_wizard
            label_ru, label_en = "Восстановление stock без UART: завершено", "Stock restore without UART: complete"
        elif choice == "4":
            action = stock_recovery_wizard
            label_ru, label_en = "BootROM/UART recovery: завершён", "BootROM/UART recovery: complete"
        elif choice == "5":
            action = firmware_capabilities_wizard
            label_ru, label_en = "Проверка capabilities: завершена", "Capability probe: complete"
        else:
            print(tr("Неверный выбор. Меню остаётся открытым.", "Invalid selection. The menu remains open."))
            continue
        nav, ok = _run_interactive_action(
            action, label_ru=label_ru, label_en=label_en,
            section_ru="Прошивка / восстановление", section_en="Flashing / recovery",
        )
        if choice == "4" and ok:
            _clear_interactive_destructive_latch()
        if nav == "section":
            continue
        return nav


def backup_menu() -> str:
    while True:
        print(tr("\n=== Backup / резервные копии ===", "\n=== Backup ==="))
        print(tr("1 — снять stock backup через работающую прошивку/Telnet (MD/MF)", "1 — create a stock backup through running firmware/Telnet (MD/MF)"))
        print(tr("2 — снять read-only backup через BootROM/UART + RAM recovery (MD/MF)", "2 — create a read-only backup through BootROM/UART + RAM recovery (MD/MF)"))
        print(tr("3 — назад", "3 — back"))
        choice = input(tr("Выберите 1/2/3: ", "Select 1/2/3: ")).strip()
        if choice == "3":
            return "main"
        if choice == "1":
            action = backup_only_wizard
            label_ru, label_en = "Stock backup через работающую прошивку: завершён", "Stock backup through running firmware: complete"
        elif choice == "2":
            action = bootrom_backup_wizard
            label_ru, label_en = "Read-only BootROM/UART backup: завершён", "Read-only BootROM/UART backup: complete"
        else:
            print(tr("Неверный выбор. Меню остаётся открытым.", "Invalid selection. The menu remains open."))
            continue
        nav, _ok = _run_interactive_action(
            action, label_ru=label_ru, label_en=label_en,
            section_ru="Backup / резервные копии", section_en="Backup",
        )
        if nav == "section":
            continue
        return nav


def service_menu() -> str:
    while True:
        print(tr("\n=== Подготовка / продолжение установки ===", "\n=== Preparation / installation continuation ==="))
        if _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
            print(tr(
                "[SAFETY-LATCH] Продолжение destructive stage (пункт 2) заблокировано до успешного полного BootROM/UART recovery.",
                "[SAFETY-LATCH] Destructive-stage continuation (option 2) is blocked until a successful full BootROM/UART recovery.",
            ))
        print(tr("1 — подготовить персональный установочный пакет из полного stock backup", "1 — prepare a device-specific installation package from a full stock backup"))
        print(tr("2 — продолжить после transition OpenWrt: этап 2 = UBI format + запись sysupgrade + контроль первого запуска", "2 — continue after transition OpenWrt: stage 2 = UBI format + sysupgrade flash + first-boot monitoring"))
        print(tr("3 — назад", "3 — back"))
        choice = input(tr("Выберите 1/2/3: ", "Select 1/2/3: ")).strip()
        if choice == "3":
            return "main"
        if choice == "1":
            action = personalize_wizard
            label_ru, label_en = "Подготовка персонального пакета: завершена", "Device-specific package preparation: complete"
        elif choice == "2":
            if _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
                print(tr(
                    "[BLOCKED] SAFETY-LATCH запрещает продолжение destructive stage в текущем процессе.",
                    "[BLOCKED] SAFETY-LATCH forbids destructive-stage continuation in the current process.",
                ))
                continue
            action = resume_stage2_wizard
            label_ru, label_en = "Продолжение Stage 2: завершено", "Stage 2 continuation: complete"
        else:
            print(tr("Неверный выбор. Меню остаётся открытым.", "Invalid selection. The menu remains open."))
            continue
        nav, _ok = _run_interactive_action(
            action, label_ru=label_ru, label_en=label_en,
            section_ru="Подготовка / продолжение установки", section_en="Preparation / installation continuation",
        )
        if nav == "section":
            continue
        return nav


def _family_from_model_chipset(model: str, chipset: str) -> str:
    low = f"{model} {chipset}".lower()
    if "040g-mf" in low or "7583" in low:
        return "mf"
    if "040g-md" in low or "7581" in low:
        return "md"
    return "unknown"


def _startup_entry_mode() -> str:
    while True:
        print(tr("\nРежим запуска:", "\nStartup mode:"))
        print(tr("1 — обычный запуск / автоопределение stock", "1 — normal startup / stock auto-detection"))
        print(tr("2 — кирпич / BootROM-UART recovery без сетевого автоопределения", "2 — bricked device / BootROM-UART recovery without network auto-detection"))
        print(tr("3 — выход", "3 — exit"))
        choice = input(tr("Выберите 1/2/3 [1]: ", "Select 1/2/3 [1]: ")).strip() or "1"
        if choice == "1":
            return "normal"
        if choice == "2":
            return "brick"
        if choice == "3":
            return "exit"
        print(tr("Неверный выбор. Скрипт остаётся запущенным; выберите режим снова.", "Invalid selection. The script remains running; select a startup mode again."))


def _startup_device_autodetect() -> dict[str, object]:
    """Best-effort read-only Web fingerprint after language selection.

    A manual fallback only selects the UI profile. No destructive or backup gate
    trusts that selection; live Web/MTD checks are repeated inside operations.
    """
    global _STARTUP_DEVICE_PROFILE, _STARTUP_WEB_AUTH
    module = _load_stock_web_module()
    default_user = str(getattr(module, "DEFAULT_WEB_USER", "CMCCAdmin") or "CMCCAdmin")
    default_password = str(getattr(module, "DEFAULT_WEB_PASSWORD", "") or "")
    host = input(tr("IP Nokia для автоопределения [192.168.1.1]: ", "Nokia IP for auto-detection [192.168.1.1]: ")).strip() or "192.168.1.1"
    while True:
        client = None
        try:
            print(tr("[WAIT] Автоопределение XG-040G-MD/MF через stock Web...", "[WAIT] Auto-detecting XG-040G-MD/MF through the stock Web UI..."))
            web_user = input(tr(f"Web user [{default_user}]: ", f"Web user [{default_user}]: ")).strip() or default_user
            entered = _RAW_GETPASS(tr("Web password [standard - Enter]: ", "Web password [standard - Enter]: "))
            web_password = entered or default_password
            _register_log_secret(web_password)
            client = module.StockWeb(host)
            client.login(web_user, web_password, allow_plain=True)
            info = module.StockSetup(client).read_device_info()
            model = str(info.get("model") or "")
            chipset = str(info.get("chipset") or "")
            family = _family_from_model_chipset(model, chipset)
            if family not in ("md", "mf"):
                raise Error(tr(f"неизвестная модель: {model or '?'} / {chipset or '?'}", f"unknown model: {model or '?'} / {chipset or '?'}"))
            _STARTUP_DEVICE_PROFILE = {
                "family": family, "model": model, "chipset": chipset, "host": host,
                "verified": True, "source": "stock-web",
            }
            _STARTUP_WEB_AUTH = {"host": host, "user": web_user, "password": web_password}
            print(tr(f"[OK] Устройство: {model} / {chipset}; профиль {family.upper()}.", f"[OK] Device: {model} / {chipset}; profile {family.upper()}."))
            print(tr("[OK] Web-реквизиты сохранены только в памяти этого запуска и будут переиспользованы без повторного ввода.", "[OK] Web credentials are retained only in this process memory and will be reused without a second prompt."))
            return _STARTUP_DEVICE_PROFILE
        except Exception as exc:
            print(tr(f"[WARNING] Автоопределение не выполнено: {exc}", f"[WARNING] Auto-detection failed: {exc}"))
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass
            try:
                web_password = None
                entered = None
            except Exception:
                pass
        print(tr("Ручной fallback (не является доказательством модели):", "Manual fallback (not proof of the model):"))
        print("1 — Nokia XG-040G-MD")
        print("2 — Nokia XG-040G-MF")
        print(tr("3 — повторить автоопределение", "3 — retry auto-detection"))
        print(tr("4 — продолжить без выбранного профиля (например UART recovery)", "4 — continue without a selected profile (for example UART recovery)"))
        choice = input(tr("Выберите 1/2/3/4: ", "Select 1/2/3/4: ")).strip()
        if choice == "3":
            continue
        if choice in ("1", "2"):
            family = "md" if choice == "1" else "mf"
            model = "XG-040G-MD" if family == "md" else "XG-040G-MF"
            _STARTUP_DEVICE_PROFILE = {"family": family, "model": model, "chipset": "", "host": host, "verified": False, "source": "manual-unverified"}
            print(tr(f"[INFO] Выбран профиль {family.upper()} [UNVERIFIED]. Перед backup/write модель будет проверена заново.", f"[INFO] Selected profile {family.upper()} [UNVERIFIED]. The model will be re-verified before backup/write."))
            return _STARTUP_DEVICE_PROFILE
        if choice == "4":
            _STARTUP_DEVICE_PROFILE = {"family": "unknown", "model": "", "chipset": "", "host": host, "verified": False, "source": "none"}
            return _STARTUP_DEVICE_PROFILE
        print(tr("Неверный выбор.", "Invalid selection."))


def wizard() -> None:
    while True:
        print(tr("\n=== Главное меню ===", "\n=== Main menu ==="))
        prof = _STARTUP_DEVICE_PROFILE
        if prof.get("family") in ("md", "mf"):
            state = "VERIFIED" if prof.get("verified") else "UNVERIFIED"
            print(tr(
                f"[DEVICE] {prof.get('model') or prof.get('family','').upper()}" + (f" / {prof.get('chipset')}" if prof.get('chipset') else "") + f" [{state}]",
                f"[DEVICE] {prof.get('model') or prof.get('family','').upper()}" + (f" / {prof.get('chipset')}" if prof.get('chipset') else "") + f" [{state}]",
            ))
        if _INTERACTIVE_DESTRUCTIVE_LATCH.get("blocked"):
            print(tr(
                "[SAFETY-LATCH] Неизвестное состояние предыдущего NAND write: destructive пункты ограничены, но скрипт и диагностика остаются доступны.",
                "[SAFETY-LATCH] A previous NAND write has unknown state: destructive options are restricted, but the script and diagnostics remain available.",
            ))
        print(tr("1 — прошивка / установка / восстановление", "1 — flashing / installation / recovery"))
        print(tr("2 — backup / резервные копии", "2 — backup"))
        print(tr("3 — credentials / пользователи / stock audit", "3 — credentials / users / stock audit"))
        print(tr("4 — подготовка / продолжение установки", "4 — preparation / continue installation"))
        print(tr("5 — выход", "5 — exit"))
        choice = input(tr("Выберите 1/2/3/4/5: ", "Select 1/2/3/4/5: ")).strip()
        if choice == "1":
            nav = firmware_menu()
        elif choice == "2":
            nav = backup_menu()
        elif choice == "3":
            nav = credentials_menu()
        elif choice == "4":
            nav = service_menu()
        elif choice == "5":
            return
        else:
            print(tr("Неверный выбор. Скрипт остаётся в главном меню.", "Invalid selection. The script remains in the main menu."))
            continue
        if nav == "exit":
            return
        # "main" returns here; section navigation is consumed inside submenus.
        continue


def main(argv: list[str] | None = None) -> int:
    already_logging = SESSION_LOG_PATH is not None
    start_session_logging()
    ensure_language()
    if not already_logging:
        print_app_banner()
        print(f"[LOG] work/logs/LATEST.log — build {BUILD_TAG}", flush=True)
    parser = argparse.ArgumentParser(description=tr("Nokia Router MedveFlasher: установка OpenWrt без UART и восстановление стока", "Nokia Router MedveFlasher: no-UART OpenWrt installation and stock recovery"))
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("wizard")
    p = sub.add_parser("verify-backup")
    p.add_argument("path", type=Path)
    p = sub.add_parser("personalize")
    p.add_argument("path", type=Path)
    p = sub.add_parser("verify-stock-restore")
    p.add_argument("path", type=Path)
    p = sub.add_parser("prepare-stock-restore")
    p.add_argument("path", type=Path)
    sub.add_parser("stock-recovery")
    sub.add_parser("bootrom-backup")
    sub.add_parser("verify-mf-recovery")
    sub.add_parser("stock-restore-running")
    sub.add_parser("stock-restore")
    sub.add_parser("stock-audit")
    sub.add_parser("firmware-capabilities")
    sub.add_parser("selftest-capabilities")
    sub.add_parser("selftest-mf-transition")
    p = sub.add_parser("parse-stock-audit")
    p.add_argument("path", type=Path)
    sub.add_parser("selftest-safety")
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "wizard"):
            while True:
                startup_mode = _startup_entry_mode()
                if startup_mode == "exit":
                    break
                if startup_mode == "brick":
                    _STARTUP_DEVICE_PROFILE.clear()
                    _STARTUP_DEVICE_PROFILE.update({
                        "family": "unknown", "model": "", "chipset": "", "host": "192.168.1.1",
                        "verified": False, "source": "brick-startup",
                    })
                    nav, ok = _run_interactive_action(
                        stock_recovery_wizard,
                        label_ru="BootROM/UART recovery: завершён",
                        label_en="BootROM/UART recovery: complete",
                        section_ru="выбор режима запуска",
                        section_en="startup mode selection",
                    )
                    if ok:
                        _clear_interactive_destructive_latch()
                    if nav == "section":
                        continue
                    if nav == "main":
                        wizard()
                    break
                _startup_device_autodetect()
                wizard()
                break
        elif args.command == "verify-backup":
            print(json.dumps(verify_backup(args.path), ensure_ascii=False, indent=2))
        elif args.command == "personalize":
            output, _ = personalize(args.path)
            print(output)
        elif args.command == "verify-stock-restore":
            print(json.dumps(verify_stock_restore_backup(args.path), ensure_ascii=False, indent=2))
        elif args.command == "prepare-stock-restore":
            output, manifest = prepare_stock_restore_payloads(args.path)
            print(output)
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        elif args.command == "stock-recovery":
            stock_recovery_wizard()
        elif args.command == "bootrom-backup":
            bootrom_backup_wizard()
        elif args.command == "verify-mf-recovery":
            profile = recovery_profile_for_family("mf")
            print(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in profile.items()}, ensure_ascii=False, indent=2))
        elif args.command == "stock-restore-running":
            stock_restore_running_wizard()
        elif args.command == "stock-restore":
            stock_restore_selector_wizard()
        elif args.command == "stock-audit":
            stock_audit_wizard()
        elif args.command == "firmware-capabilities":
            firmware_capabilities_wizard()
        elif args.command == "selftest-capabilities":
            _selftest_firmware_capabilities()
        elif args.command == "selftest-mf-transition":
            _selftest_mf_transition_release()
        elif args.command == "parse-stock-audit":
            parser_module = _load_stock_audit_parser()
            text = args.path.read_text(encoding="utf-8", errors="replace")
            print(parser_module.render(parser_module.build_profile(text)))
        elif args.command == "selftest-safety":
            _bootrom_backup_safety_selftest()
            _restore_transport_safety_selftest()
            _uboot_badblock_restore_safety_selftest()
            _rc23_timestamp_backup_identity_selftest()
            _rc24_interactive_navigation_selftest()
            _stage1_handoff_safety_selftest()
            _stock_slot_tolerance_selftest()
            _readonly_flow_selftest()
            _ram_worker_autonomy_selftest()
            _rc26_console_log_split_selftest()
            _rc26_restore_diagnostic_selftest()
            _rc25_readonly_by_fact_selftest()
            _rc25a_recovery_reachability_selftest()
            _rc25_release_identity_selftest()
            _rc25_lan1_advisory_selftest()
            _rc29_restore_ssh_auth_selftest()
            print("BootROM + bad-block restore + restore transport + RC23 timestamp/backup identity + RC24 interactive navigation + stage1 handoff + stock slot tolerance + read-only flow + RAM worker autonomy + RC26 console/log split + restore diagnostic + read-by-fact backup + recovery reachability + release identity + LAN1 advisory + restore SSH auth safety selftest: OK")
        rc = 0
    except KeyboardInterrupt:
        print(tr("\n[ПРЕДУПРЕЖДЕНИЕ] Остановлено пользователем.", "\n[WARNING] Stopped by user."), file=sys.stderr)
        rc = 130
    except (Error, OSError, EOFError, ftplib.Error, subprocess.SubprocessError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        rc = 1
    print()
    print(f"[LOG] Session log saved: {SESSION_LOG_PATH}")
    print(f"[LOG] Latest log: {LATEST_LOG_PATH}")
    _STARTUP_WEB_AUTH.clear()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
