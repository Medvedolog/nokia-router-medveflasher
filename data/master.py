#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import ftplib
import gzip
import getpass
import hashlib
import importlib.util
import json
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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

APP_VERSION = "1.0.0-rc7"
BUILD_TAG = "medveflasher-1.0.0-rc7"
BOOTCMD = "flash read 0xc0000 0x800000 0x92000000; bootm 0x92000000"
KIT = Path(__file__).resolve().parent.parent
DATA = KIT / "data"
WORK = KIT / "work"
BUNDLE = DATA / "transition-bundle.bin"
MANUAL_BUNDLE = DATA / "transition-manual-bundle.bin"
LAUNCHER_TEMPLATE = DATA / "stock-launcher.sh.in"
BACKUP_AGENT = DATA / "backup-agent.sh"
STOCK_WEB = DATA / "stock_web.py"
RECOVERY_DIR = DATA / "recovery"
RECOVERY_PRELOADER = RECOVERY_DIR / "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-preloader.bin"
RECOVERY_FIP = RECOVERY_DIR / "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-bl31-uboot-ethfix.fip"
RECOVERY_INITRAMFS = RECOVERY_DIR / "nokia-xg040gmd-stock-recovery-initramfs.itb"
UBOOT_DEFAULT_RECOVERY_FILENAME = "openwrt-airoha-an7581-nokia_xg-040g-md-ubi-initramfs-recovery.itb"
RECOVERY_PRELOADER_SHA = "6c3b2339d036340396730a13adfe35c0d2a4dddedeffb6f9965a24e0c7908808"
RECOVERY_FIP_SHA = "9c29cdbcc3f9c00070cc72262c83dcd1eb212f89f6fb84806ad8657eadec2b8b"
RECOVERY_INITRAMFS_SHA = "5fe4a4508da8107c7a10a670d120a01eb9f2aec677514bc650f9dc809013e088"
STOCK_ALL_FLASH_SIZE = 0x0EBA0000
STOCK_BL2_SIZE = 0x00020000
STOCK_IBU_SIZE = STOCK_ALL_FLASH_SIZE - STOCK_BL2_SIZE
UBOOT_RESTORE_CHUNK_SIZE = 0x00800000
UBOOT_LOAD_ADDRESS = 0x90000000
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
EXPECTED_BUNDLE_SHA = "e19ff00652a7a581f418badc998d21baed78949dd82c4f54764d993dbb39f8a0"
EXPECTED_BUNDLE_SIZE = 17_956_864
EXPECTED_MANUAL_BUNDLE_SHA = "3b7b89508da309a45d02002a972a3a554231b12d5839bb1f812d655c29ef347f"
EXPECTED_MANUAL_BUNDLE_SIZE = 8_388_608
EXPECTED_PROD_SHA = "95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6"
FIXED_EXPECTED = {
    0: 524288, 1: 262144, 6: 262144, 7: 262144, 8: 262144,
    9: 262144, 10: 10485760, 11: 135135232, 12: 4194304,
    13: 10485760, 14: 42467328, 15: 42467328, 16: 247070720,
}
SLOT_LAYOUTS = (
    {2: 0x003AF6DA, 3: 0x01CC0000, 4: 0x00480000, 5: 0x02400000},
    {2: 0x00480000, 3: 0x02400000, 4: 0x003AF6DA, 5: 0x01CC0000},
)
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


class _ConsoleTee:
    def __init__(self, console, files):
        self.console = console
        self.files = files

    def write(self, text):
        written = self.console.write(text)
        clean = _redact_log_text(ANSI_RE.sub("", text))
        for fh in self.files:
            fh.write(clean)
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
    """Append technical diagnostics to PC logs without cluttering the console."""
    if not text:
        return
    clean = _redact_log_text(ANSI_RE.sub("", text))
    if not clean.endswith("\n"):
        clean += "\n"
    for fh in _SESSION_FILES:
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
    ("в stock firmware отсутствует nc; используйте USB через Samba/FTP", "stock firmware has no usable nc; use USB through Samba/FTP"),
    ("в stock firmware отсутствует BusyBox tftp; используйте USB через Samba/FTP", "stock firmware has no BusyBox tftp; use USB through Samba/FTP"),
    ("stock tftp не поддерживает PUT/GET; используйте USB через Samba/FTP", "stock tftp does not support PUT/GET; use USB through Samba/FTP"),
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
    ("USB через Samba/смонтированную папку, флешку вынимать не нужно", "USB through Samba/a mounted directory; do not remove the drive"),
    ("USB через FTP stock Nokia", "USB through stock Nokia FTP"),
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
    ('Если UART уже показывает Press x или повторяющийся C, Nokia НЕ выключайте: мастер продолжит с текущего состояния.', 'If UART already shows Press x or repeated C, do NOT power off Nokia: the wizard will continue from the current state.'),
    ('Закройте PuTTY/Tera Term/другой serial-терминал, чтобы освободить COM-порт.', 'Close PuTTY/Tera Term/any other serial terminal to release the COM port.'),
    ('Только если приглашения BootROM ещё нет: выключите Nokia, удерживайте Reset, включите питание и дождитесь Press x.', 'Only when the BootROM prompt is not already present: power off Nokia, hold Reset, power on, and wait for Press x.'),
    ('Нажмите Enter, когда COM-порт свободен и BootROM готов или Nokia подготовлена к включению', 'Press Enter when the COM port is free and BootROM is ready, or Nokia is prepared for power-on'),
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
    return _RAW_PRINT(*values, **kwargs)


def _localized_input(prompt: str = "") -> str:
    return _RAW_INPUT(colorize_text(str(localize_text(prompt))))


def _localized_getpass(prompt: str = "Password: ", stream=None) -> str:
    localized = colorize_text(str(localize_text(prompt)))
    if os.environ.get("NOKIA_HIDE_PASSWORDS", "").strip().lower() in ("1", "yes", "true"):
        return _RAW_GETPASS(localized, stream=stream)
    # Passwords are visible while typed by request. Terminal echo is not
    # generated by Python and therefore is not copied into PC session logs.
    return _RAW_INPUT(localized)


print = _localized_print
input = _localized_input
getpass.getpass = _localized_getpass


class Error(RuntimeError):
    def __str__(self) -> str:
        return str(localize_text(super().__str__()))


class TransportError(Error):
    """A payload transport failed before readback validation."""


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def verify_kit() -> None:
    required = (BUNDLE, MANUAL_BUNDLE, LAUNCHER_TEMPLATE, BACKUP_AGENT, STOCK_WEB, DATA / "env_patcher.py", RECOVERY_PRELOADER, RECOVERY_FIP, RECOVERY_INITRAMFS)
    for path in required:
        if not path.is_file():
            raise Error(f"повреждён комплект: отсутствует {path.relative_to(KIT)}")
    if BUNDLE.stat().st_size != EXPECTED_BUNDLE_SIZE:
        raise Error("размер transition bundle не совпадает с релизом")
    if sha_file(BUNDLE) != EXPECTED_BUNDLE_SHA:
        raise Error("SHA256 transition bundle не совпадает с релизом")
    if MANUAL_BUNDLE.stat().st_size != EXPECTED_MANUAL_BUNDLE_SIZE:
        raise Error("размер manual transition bundle не совпадает с релизом")
    if sha_file(MANUAL_BUNDLE) != EXPECTED_MANUAL_BUNDLE_SHA:
        raise Error("SHA256 manual transition bundle не совпадает с релизом")
    metadata = bundle_release_metadata()
    expected_template_values = {
        "BUNDLE_SIZE": str(metadata["bundle_size"]),
        "BUNDLE_SHA": f"'{metadata['bundle_sha']}'",
        "TRANSITION_TOTALSIZE": str(metadata["transition_fit_size"]),
        "TRANSITION_FIT_SHA": f"'{metadata['transition_fit_sha']}'",
        "TRANSITION_WINDOW_SHA": f"'{metadata['transition_window_sha']}'",
        "SYSUPGRADE_SIZE": str(metadata["production_size"]),
        "SYSUPGRADE_SHA": f"'{metadata['production_sha']}'",
    }
    launcher_template = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    for key, expected in expected_template_values.items():
        match = re.search(rf"^{key}=(.+)$", launcher_template, flags=re.M)
        if not match or match.group(1).strip() != expected:
            raise Error(tr(
                f"metadata {key} во внутреннем launcher не совпадает с transition bundle",
                f"metadata {key} in the internal launcher does not match the transition bundle",
            ))
    recovery_expected = {
        RECOVERY_PRELOADER: RECOVERY_PRELOADER_SHA,
        RECOVERY_FIP: RECOVERY_FIP_SHA,
        RECOVERY_INITRAMFS: RECOVERY_INITRAMFS_SHA,
    }
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


def verify_backup(directory: Path) -> dict:
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

    selected: dict[int, int] | None = None
    for layout in SLOT_LAYOUTS:
        if all(sizes.get(n) == size for n, size in layout.items()):
            selected = layout
            break
    if selected is None:
        raise Error(f"неподдерживаемые размеры stock-слотов: { {n:sizes[n] for n in (2,3,4,5)} }")
    expected = dict(FIXED_EXPECTED)
    expected.update(selected)
    for number, size in sizes.items():
        if size != expected[number]:
            raise Error(f"mtd{number}: размер {size}, ожидается {expected[number]}")
    if proc:
        for number, expected_size in expected.items():
            if number not in proc or proc[number][0] != expected_size:
                raise Error(f"proc_mtd не совпадает с dump для mtd{number}")
    return {
        "directory": str(directory),
        "files": {str(k): str(v) for k, v in files.items()},
        "sizes": {str(k): v for k, v in sizes.items()},
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


def personalize(backup_dir: Path, force: bool = True, manual_transition: bool = False) -> tuple[Path, dict]:
    validation = verify_backup(backup_dir)
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

    selected_bundle = MANUAL_BUNDLE if manual_transition else BUNDLE
    # The on-device launcher always uses this stable filename. The content and
    # embedded metadata are selected by the PC wizard.
    shutil.copy2(selected_bundle, output / BUNDLE.name)
    (output / "OpenWrt.mtd2.u-boot-env.bin").write_bytes(env_data)
    template = LAUNCHER_TEMPLATE.read_text(encoding="utf-8")
    metadata = bundle_release_metadata(selected_bundle)
    substitutions = {
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
                f"не удалось записать {key} во внутренний stock launcher",
                f"failed to write {key} into the internal stock launcher",
            ))
    if "@ENV_" in template:
        raise Error("не удалось персонализировать stock launcher")
    launcher = output / "INSTALL.sh"
    write_text(launcher, template)
    os.chmod(launcher, 0o755)

    info = {
        "kit_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_id": device_id,
        "backup": validation,
        "environment": report,
        "bundle_sha256": metadata["bundle_sha"],
        "manual_transition": manual_transition,
        "production_sha256": EXPECTED_PROD_SHA,
        "language": ensure_language(),
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
    write_text(
        output / "README.txt",
        tr(
            "Персональный пакет Nokia XG-040G-MD. Запускается мастером START; вручную: ",
            "Device-specific Nokia XG-040G-MD package. Use the START wizard; manual command: ",
        ) + "sha256sum -c SHA256SUMS && ash ./INSTALL.sh --preflight\n",
    )
    state = device_root / "state.json"
    save_state(state, {"version": APP_VERSION, "device_id": device_id, "phase": "personalized", "install_dir": str(output)})
    return output, info


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

def login_root_profile_dynamic(
    access,
    *,
    model: str,
    sessions: int,
    connect_attempts: int,
    preferred_accounts: tuple[str, ...],
) -> Telnet:
    """Discover and verify a working UID-0 account on fresh Telnet sessions.

    Stock builds do not expose a stable account name across devices.  The
    guide may say ``user_ftp`` while the actual firmware contains only service
    accounts such as ``samba_anony`` or ``osgi_admin``.  Account names are
    therefore discovered from /etc/passwd, then every candidate/password pair
    is tested on a new TCP session and accepted only after ``id -u`` returns 0.
    """
    total = max(1, sessions)
    last_error: Exception | None = None
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
    raise Error(tr(
        f"{model}: {summary_ru}. Backup не начат, NAND не изменялась. Последний результат: {detail}",
        f"{model}: {summary_en}. Backup did not start and NAND was not modified. Last result: {detail}",
    ))


def login_root_md(access, sessions: int = 3) -> Telnet:
    if access.su_user == "auto":
        return login_root_profile_dynamic(
            access,
            model="MD",
            sessions=sessions,
            connect_attempts=3,
            preferred_accounts=("useradmin_ftp", "user_ftp", "osgi_admin", "samba_anony", "root"),
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


def find_nc(telnet: Telnet) -> str:
    rc, text = telnet.command("command -v nc 2>/dev/null || command -v netcat 2>/dev/null || true", echo=False)
    candidates = re.findall(r"(?:^|\r?\n)(/[A-Za-z0-9_./-]+)(?:\r?\n|$)", text)
    if candidates:
        return candidates[-1]
    rc, text = telnet.command("busybox 2>&1 | tr ',' ' ' | awk '{for(i=1;i<=NF;i++) if($i==\"nc\") found=1} END{exit !found}'", echo=False)
    if rc == 0:
        return "busybox nc"
    raise Error("в stock firmware отсутствует nc; используйте USB через Samba/FTP")


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


def find_tftp(telnet: Telnet) -> str:
    rc, text = telnet.command("command -v tftp 2>/dev/null || true", echo=False)
    candidates = re.findall(r"(?:^|\r?\n)(/[A-Za-z0-9_./-]+)(?:\r?\n|$)", text)
    if not candidates:
        raise Error("в stock firmware отсутствует BusyBox tftp; используйте USB через Samba/FTP")
    path = candidates[-1]
    _, help_text = telnet.command(f"{path} --help 2>&1 || true", timeout=10, echo=False)
    if "-p" not in help_text or "-g" not in help_text:
        raise Error("stock tftp не поддерживает PUT/GET; используйте USB через Samba/FTP")
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


def backup_direct(telnet: Telnet, router_host: str, destination: Path, local_ip: str | None = None, port: int = 19091) -> Path:
    nc = find_nc(telnet)
    local_ip = local_ip or local_ip_for(router_host)
    destination.mkdir(parents=True, exist_ok=True)
    rc, proc_text = telnet.command("cat /proc/mtd", timeout=15, echo=False)
    proc = parse_proc_mtd_text(proc_text)
    if rc or tuple(sorted(proc)) != EXPECTED_NUMBERS:
        raise Error("не удалось получить точную stock-разметку /proc/mtd")
    write_text(destination / "proc_mtd.txt", "\n".join(
        f'mtd{n}: {size:08x} {erase:08x} "{name}"' for n, (size, erase, name) in sorted(proc.items())
    ) + "\n")
    for meta_name, command in (("cmdline.txt", "cat /proc/cmdline"), ("uname.txt", "uname -a"), ("id.txt", "id")):
        _, text = telnet.command(command, timeout=15, echo=False)
        cleaned = re.sub(r"__NOKIA_RC_\d+_\d+__", "", text)
        write_text(destination / meta_name, cleaned.strip() + "\n")

    for number in EXPECTED_NUMBERS:
        size, _, name = proc[number]
        target = destination / f"mtd{number}_{name}.bin.gz"
        partial = target.with_suffix(target.suffix + ".part")
        for attempt in range(1, 4):
            partial.unlink(missing_ok=True)
            ready = threading.Event()
            result = ReceiverResult()
            thread = threading.Thread(target=receive_one, args=("0.0.0.0", port, partial, ready, result), daemon=True)
            thread.start()
            ready.wait(5)
            if result.error:
                raise Error(f"не удалось открыть TCP-порт {port}: {result.error}")
            print(f"[{number}/16] Приём mtd{number} ({name}), попытка {attempt}...")
            cmd = f"dd if=/dev/mtd{number} bs=131072 2>/tmp/nokia-dd-{number}.log | gzip -1 | {nc} {shlex.quote(local_ip)} {port}"
            telnet.send_line(cmd + f"; __rc=$?; echo __STREAM_{number}_${{__rc}}__")
            thread.join(timeout=max(300, size // 100000 + 120))
            if thread.is_alive():
                print("Тайм-аут потока; повтор раздела.")
                continue
            marker_text = telnet.wait_regex(rf"__STREAM_{number}_(\d+)__", 30, echo=False)
            marker = re.search(rf"__STREAM_{number}_(\d+)__", marker_text)
            if result.error or not marker or marker.group(1) != "0":
                print(f"Сетевая ошибка: {result.error or 'router rc != 0'}")
                continue
            try:
                validate_gzip_size(partial, size)
            except Error as exc:
                print(exc)
                continue
            partial.replace(target)
            print(f"  OK: {target.name}, {target.stat().st_size} байт, SHA256 {sha_file(target)}")
            break
        else:
            raise Error(f"не удалось надёжно снять mtd{number} после трёх попыток")

    # Convenience board-data files.
    (destination / "bosa.bin").write_bytes(read_dump(find_dump(destination, 6)))
    (destination / "ri.bin").write_bytes(read_dump(find_dump(destination, 7)))
    sums = []
    for path in sorted(p for p in destination.iterdir() if p.is_file() and p.name not in ("SHA256SUMS.txt", "BACKUP_COMPLETE")):
        sums.append(f"{sha_file(path)}  {path.name}")
    write_text(destination / "SHA256SUMS.txt", "\n".join(sums) + "\n")
    write_text(destination / "BACKUP_COMPLETE", "Nokia XG-040G-MD direct network backup complete\n")
    verify_backup(destination)
    return destination




def backup_tftp(
    access: StockAccess,
    router_host: str,
    destination: Path,
    local_ip: str | None = None,
    port: int = 1069,
    block_size: int = 4096,
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
        telnet = login_root_md(access)
        tftp = find_tftp(telnet)
        rc, proc_text = telnet.command("cat /proc/mtd", timeout=15, echo=False)
        proc = parse_proc_mtd_text(proc_text)
        if rc or tuple(sorted(proc)) != EXPECTED_NUMBERS:
            raise Error("не удалось получить точную stock-разметку /proc/mtd")
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
                    print(tr(
                        f"[{number}/16] Сохранён ранее проверенный {target.name}.",
                        f"[{number}/16] Existing validated {target.name} retained.",
                    ))
                    continue
                except Error:
                    target.unlink(missing_ok=True)

            for attempt in range(1, 4):
                partial.unlink(missing_ok=True)
                if telnet is None:
                    print(tr(
                        f"[WAIT] Открываю новый UID 0 Telnet-сеанс для повтора mtd{number}.",
                        f"[WAIT] Opening a new UID-0 Telnet session to retry mtd{number}.",
                    ))
                    telnet = login_root_md(access)

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
                try:
                    print(f"[{number}/16] TFTP mtd{number} ({name}), попытка {attempt}. Для mtd16 это может занять долго...")
                    command = (
                        f"dd if=/dev/mtd{number} bs=131072 2>/tmp/nokia-dd-{number}.log | gzip -1 | "
                        f"{shlex.quote(tftp)} -p -l - -r {shlex.quote(target.name)} -b {block_size} "
                        f"{shlex.quote(local_ip)} {port}"
                    )
                    telnet.send_line(command + f"; __rc=$?; echo __TFTP_PUT_{number}_${{__rc}}__")
                    started = time.time()
                    deadline = started + 7200
                    last_report = -15
                    last_bytes = -4 * 1024 * 1024
                    while thread.is_alive() and time.time() < deadline:
                        elapsed = int(time.time() - started)
                        done = int(result.bytes_transferred)
                        if elapsed >= last_report + 15 or done >= last_bytes + 4 * 1024 * 1024:
                            print(tr(
                                f"[TRANSFER] mtd{number}: принято {done / 1048576:.1f} MiB сжатых данных, прошло {elapsed}s...",
                                f"[TRANSFER] mtd{number}: received {done / 1048576:.1f} MiB compressed, elapsed {elapsed}s...",
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
                        marker_text = telnet.wait_regex(rf"__TFTP_PUT_{number}_(\d+)__", 90, echo=False)
                        marker_match = re.search(rf"__TFTP_PUT_{number}_(\d+)__", marker_text)
                        if marker_match:
                            marker_ok = marker_match.group(1) == "0"
                            if not marker_ok:
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
                partial.replace(target)
                print(f"  OK: {target.name}, {target.stat().st_size} bytes, SHA256 {sha_file(target)}")
                break
            else:
                raise Error(f"не удалось надёжно снять mtd{number} через TFTP после трёх попыток")

        (destination / "bosa.bin").write_bytes(read_dump(find_dump(destination, 6)))
        (destination / "ri.bin").write_bytes(read_dump(find_dump(destination, 7)))
        sums = []
        for path in sorted(p for p in destination.iterdir() if p.is_file() and p.name not in ("SHA256SUMS.txt", "BACKUP_COMPLETE")):
            sums.append(f"{sha_file(path)}  {path.name}")
        write_text(destination / "SHA256SUMS.txt", "\n".join(sums) + "\n")
        write_text(destination / "BACKUP_COMPLETE", "Nokia XG-040G-MD direct TFTP backup complete\n")
        verify_backup(destination)
        return destination
    finally:
        if telnet is not None:
            telnet.close()

def backup_to_usb(telnet: Telnet, usb_mount: str) -> str:
    telnet.upload_text("/tmp/nokia-backup-agent.sh", BACKUP_AGENT.read_text())
    # Disable terminal input echo while the agent command is entered. Runtime
    # output remains visible, but the shell command itself is not printed.
    telnet.command("stty -echo 2>/dev/null || true", timeout=10, echo=False)
    try:
        rc, text = telnet.command(
            f"NOKIA_LANG={shlex.quote(ensure_language())} NOKIA_USB_QUIET=1 ash /tmp/nokia-backup-agent.sh {shlex.quote(usb_mount)}",
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


def ssh_run(host: str, command: str, input_text: str | None = None, timeout: int = 900,
            allow_disconnect: bool = False, quiet: bool = False,
            batch_mode: bool = False, minimal_auth: bool = False) -> tuple[int, str]:
    ssh = ssh_executable()
    null = "NUL" if os.name == "nt" else "/dev/null"
    argv = [
        ssh, "-T", "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}",
        "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
        "-o", "NumberOfPasswordPrompts=1",
    ]
    if batch_mode:
        argv.extend(["-o", "BatchMode=yes"])
    if minimal_auth:
        # The corrected rc7 manual transition starts Dropbear with -B because
        # its root shadow password is intentionally empty. OpenSSH always sends
        # the protocol-level "none" request first; Dropbear may then accept the
        # blank-password account without an interactive prompt. Avoid local keys,
        # agents and password prompts so the detector stays deterministic.
        argv.extend([
            "-o", "ConnectionAttempts=1",
            "-o", "PubkeyAuthentication=no",
            "-o", "PasswordAuthentication=no",
        ])
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
        raise Error("тайм-аут SSH-команды\n" + output[-4000:])
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
                          counter=None, total: int | None = None) -> tuple[int, str]:
    holder: dict[str, object] = {}
    def worker() -> None:
        try:
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
        "-o", "ServerAliveCountMax=4", str(source), f"root@{host}:{remote_path}",
    ]
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


def run_stage1(telnet: Telnet, remote_dir: str, nand_unknown: bool, manual_transition: bool = False) -> None:
    rc, output = telnet.command_clean(
        f"cd {shlex.quote(remote_dir)} && NOKIA_LANG={shlex.quote(ensure_language())} ash ./INSTALL.sh --preflight",
        timeout=900,
    )
    if output:
        print(output)
    if rc or "PREFLIGHT PASSED" not in output:
        raise Error("stage 1 preflight не пройден")

    if manual_transition:
        print(tr(
            "\n[READY] Проверки завершены. Будет записан ручной transition; после перезагрузки мастер предложит выбрать sysupgrade на ПК.",
            "\n[READY] Checks passed. The manual transition will be written; after reboot the wizard will ask for a sysupgrade file on the PC.",
        ))
    else:
        print(tr(
            "\n[READY] Проверки завершены. Далее будет записан переходный образ, затем роутер автоматически установит OpenWrt.",
            "\n[READY] Checks passed. The transition image will be written, then the router will install OpenWrt automatically.",
        ))
    print(tr(
        "[ВАЖНО] Отключите оптику, обеспечьте стабильное питание и сохраните полный backup на ПК.",
        "[IMPORTANT] Disconnect fiber, use stable power, and keep the complete backup on the PC.",
    ))
    if nand_unknown:
        print(tr(
            "[ПРЕДУПРЕЖДЕНИЕ] NAND не распознана; совместимость подтверждает оператор.",
            "[WARNING] NAND was not identified; compatibility remains the operator's responsibility.",
        ))

    if manual_transition:
        confirm = input(tr(
            "Записать ручной transition и перезагрузить роутер? [y/N]: ",
            "Write the manual transition and reboot the router? [y/N]: ",
        )).strip().lower()
        if confirm not in ("y", "yes", "д", "да"):
            raise Error(tr("операция отменена", "operation cancelled"))
    else:
        confirm = input(tr(
            "[INPUT] Введите точно CONFIRM FORMAT AND FLASH: ",
            "[INPUT] Type exactly CONFIRM FORMAT AND FLASH: ",
        )).strip()
        if confirm != "CONFIRM FORMAT AND FLASH":
            raise Error(tr("операция отменена", "operation cancelled"))

    stage_header("5", "Запись переходного образа", "Writing the transition image")
    print(tr(
        "[WAIT] Подготавливаю RAM-worker и запускаю запись переходного образа. Не выключайте питание.",
        "[WAIT] Preparing the RAM worker and writing the transition image. Do not power off.",
    ))
    auth = shlex.quote("CONFIRM FORMAT AND FLASH")
    command = (
        f"cd {shlex.quote(remote_dir)} && "
        f"NOKIA_FORMAT_AND_FLASH_AUTH={auth} "
        f"NOKIA_LANG={shlex.quote(ensure_language())} ash ./INSTALL.sh --flash"
    )
    telnet.send_line(command + "; __rc=$?; printf '\\n__STAGE1_%s__\\n' \"$__rc\"")
    # The worker marker and launcher transcript are protocol details. Keep them
    # out of the operator console; show the transcript only when startup fails.
    stage_output = telnet.wait_regex(
        r"__NOKIA_RAM_WORKER_STARTED__\d+__|__STAGE1_\d+__",
        900,
        echo=False,
    )
    worker = re.search(r"__NOKIA_RAM_WORKER_STARTED__(\d+)__", stage_output)
    stage_rc = re.search(r"__STAGE1_(\d+)__", stage_output)
    if worker:
        if manual_transition:
            print(tr(
                "[OK] Ручной transition записывается. После перезагрузки автоматическая прошивка не начнётся.",
                "[OK] The manual transition is being written. Automatic flashing will not start after reboot.",
            ))
        else:
            print(tr(
                "[OK] Автономная прошивка запущена. Telnet может отключиться.",
                "[OK] Autonomous flashing started. Telnet may disconnect.",
            ))
        return
    if stage_rc and int(stage_rc.group(1)) == 0:
        print(tr(
            "[ПРЕДУПРЕЖДЕНИЕ] Launcher завершился без worker-маркера; продолжаю проверку загрузки.",
            "[WARNING] The launcher exited without a worker marker; continuing boot verification.",
        ))
        return

    diagnostic = re.sub(r"__NOKIA_RAM_WORKER_STARTED__\d+__|__STAGE1_\d+__", "", stage_output).strip()
    if diagnostic:
        print(diagnostic[-4000:])
    rc_text = stage_rc.group(1) if stage_rc else "unknown"
    raise Error(tr(
        f"RAM worker stage 1 не стартовал; launcher rc={rc_text}",
        f"stage 1 RAM worker did not start; launcher rc={rc_text}",
    ))


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
    """Probe the manual initramfs without letting one SSH attempt stall the wizard.

    The transition image has its own marker/state files. They are stronger evidence
    than an HTTP port or a board-name string inherited from our own DTB. First try a
    deterministic no-key/no-prompt OpenSSH path; if a platform needs the ordinary
    BatchMode path, try it once with the same short command timeout.
    """
    command = (
        "echo NOKIA_MANUAL_PROBE_BEGIN; "
        "[ -f /tmp/NOKIA_MANUAL_TRANSITION_READY ] && echo MANUAL_READY; "
        "printf 'STATE='; cat /tmp/NOKIA_MANUAL_STATE 2>/dev/null || true; echo; "
        "[ -x /usr/sbin/nokia-ubi-installer ] && echo INSTALLER=1 || echo INSTALLER=0; "
        "printf 'BOARD='; cat /tmp/sysinfo/board_name 2>/dev/null || true; echo; "
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
        state_match = re.search(r"(?:^|[\r\n])STATE=([^\r\n]*)", out)
        board_match = re.search(r"(?:^|[\r\n])BOARD=([^\r\n]*)", out)
        state = state_match.group(1).strip() if state_match else ""
        board = board_match.group(1).strip() if board_match else ""
        ready = "MANUAL_READY" in out and "INSTALLER=1" in out and bool(state)
        if ready:
            _MANUAL_SSH_MINIMAL_AUTH[host] = minimal
        return ready, state, board, ""
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


def wait_manual_transition(host: str, timeout: int = 600) -> None:
    stage_header("6", "Ожидание ручного transition", "Waiting for the manual transition")
    started=time.time(); next_report=started; next_error_report=started
    last_error = ""
    while time.time()-started < timeout:
        ports=(_tcp_open(host,22),_tcp_open(host,80),_tcp_open(host,443),_tcp_open(host,23))
        if ports[0]:
            ready, state, board, detail = _manual_transition_probe(host, timeout=8)
            if ready:
                print(tr(
                    f"[OK] Ручной transition готов; состояние {state}. Автоматическая запись NAND не запущена.",
                    f"[OK] Manual transition is ready; state {state}. No automatic NAND write has started.",
                ))
                if board and board != "nokia,xg-040g-md-ubi":
                    _write_session_only(f"[MANUAL-SSH] ready marker accepted; board_name={board!r}")
                return
            if detail:
                last_error = detail
                if time.time() >= next_error_report:
                    short = detail[-500:]
                    print(tr(
                        f"[WAIT] SSH 22 открыт, но служебная метка ручного transition пока не прочитана: {short}",
                        f"[WAIT] SSH 22 is open, but the transition marker is not readable yet: {short}",
                    ))
                    next_error_report = time.time() + 60
                    _write_session_only(f"[MANUAL-SSH] probe failed: {detail}")
        if time.time() >= next_report:
            elapsed=int(time.time()-started)
            print(tr(f"[WAIT] {elapsed//60:02d}:{elapsed%60:02d} — {_port_summary(*ports)}.", f"[WAIT] {elapsed//60:02d}:{elapsed%60:02d} — {_port_summary(*ports)}."))
            next_report=time.time()+30
        time.sleep(3)
    suffix = f"; последняя ошибка SSH: {last_error[-700:]}" if last_error else ""
    raise Error(tr(
        "ручной transition не появился по SSH" + suffix,
        "manual transition did not become available over SSH" + (f"; last SSH error: {last_error[-700:]}" if last_error else ""),
    ))


def run_custom_stage2(host: str, local_ip: str | None, port: int, block_size: int) -> str:
    wait_manual_transition(host)
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
    return run_stage2(host, manual_mode=True)

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
        "IMAGE_SIZE=9531670", f"IMAGE_SHA={EXPECTED_PROD_SHA}",
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
        "WAITING_FOR_SYSTEM": tr("установка основной OpenWrt и перезагрузка", "production sysupgrade and reboot"),
        "STARTING": tr("запуск проверки выбранного образа", "starting validation of the selected image"),
        "FAILED": tr("установка остановлена с ошибкой", "installation stopped with an error"),
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


def run_stage2(host: str, manual_mode: bool = False) -> str:
    if not manual_mode:
        stage_header("6", "Ожидание OpenWrt", "Waiting for OpenWrt")
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

    while True:
        now = time.time()
        port22 = _tcp_open(host, 22)
        port80 = _tcp_open(host, 80)
        port443 = _tcp_open(host, 443)
        port23 = _tcp_open(host, 23)
        ports = (port22, port80, port443, port23)
        if ports != previous_ports:
            previous_ports = ports
            print(tr("[NET] Порты: ", "[NET] Ports: ") + _port_summary(*ports) + ".")

        if transition_seen and not handoff_announced and not any(ports) and (
            highest_step >= 6 or previous_state in ("FORMATTING_AND_FLASHING", "WAITING_FOR_SYSTEM")
        ):
            handoff_announced = True
            handoff_outage_seen = True
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
        if port22:
            try:
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
                if manual_mode:
                    _, output = _manual_ssh_run(
                        host, probe_cmd, timeout=20, allow_disconnect=True, quiet=True,
                    )
                else:
                    _, output = ssh_run(
                        host, probe_cmd,
                        timeout=90, allow_disconnect=True, quiet=True, batch_mode=True,
                    )
            except Error as exc:
                output = f"SSH_PROBE_ERROR={exc}"

            if "MODE=PRODUCTION" in output:
                detected_mode = "production"
                current_phase = tr("проверка основной OpenWrt", "verifying production OpenWrt")
                if "BOARD=nokia,xg-040g-md-ubi" in output and "VOL=fit" in output:
                    print(tr(
                        "[OK] Перезагрузка завершена; основная OpenWrt подтверждена по SSH.",
                        "[OK] Reboot completed; production OpenWrt was verified over SSH.",
                    ))
                    return "production-ssh"
                print(tr(
                    "[ПРЕДУПРЕЖДЕНИЕ] OpenWrt отвечает, но итоговая проверка ещё не пройдена; продолжаю ждать.",
                    "[WARNING] OpenWrt responds, but final verification has not passed yet; continuing to wait.",
                ))

            if "MODE=TRANSITION" in output:
                detected_mode = "transition"
                if not transition_seen:
                    transition_seen = True
                    print(tr(
                        "[OK] Переходная система загружена; SSH доступен.",
                        "[OK] The transition system has booted; SSH is available.",
                    ))
                match = re.search(r"AUTO_STATE=([^\r\n]+)", output)
                state = match.group(1).strip() if match else "UNKNOWN"
                if state != previous_state:
                    previous_state = state
                    current_phase = _transition_state_label(state)
                    if state == "NOT_STARTED":
                        print(tr(
                            "[WAIT] Переходная система ожидает запуск установки.",
                            "[WAIT] The transition system is waiting for installation to start.",
                        ))
                    elif state == "WAITING_FOR_SYSTEM":
                        handoff_announced = True
                        handoff_explicit = True
                        print(tr(
                            "[WAIT] Загрузочные данные записаны; запущена установка основной OpenWrt и последующая перезагрузка.",
                            "[WAIT] Boot data has been written; production OpenWrt installation and the following reboot have started.",
                        ))
                    elif state != "FAILED":
                        print(tr(
                            f"[WAIT] Переходная система: {current_phase}.",
                            f"[WAIT] Transition system: {current_phase}.",
                        ))

                raw_log = _extract_autoflash_log(output)
                if raw_log and raw_log != last_raw_log:
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
                        "автоматическая прошивка не завершилась; переходная система оставлена доступной по SSH. Полный /tmp/nokia-autoflash.log сохранён в журнале сеанса на ПК.",
                        "installation of the selected image stopped; the manual transition remains available over SSH." if manual_mode else
                        "automatic flashing did not complete; the transition system remains available over SSH. The complete /tmp/nokia-autoflash.log was saved in the PC session log.",
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

        if now >= next_report:
            elapsed = int(now - started)
            print(tr(
                f"[WAIT] {elapsed // 60:02d}:{elapsed % 60:02d} — {current_phase}.",
                f"[WAIT] {elapsed // 60:02d}:{elapsed % 60:02d} — {current_phase}.",
            ))
            next_report = now + 30

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

    Besides cross-checking mtd16 against the individual stock partitions, RC16
    rejects the two known OpenWrt BL2 layouts.  A backup containing the OpenWrt
    preloader at offset 0 (the historical brick) or at offset 0x800 (the proper
    all-in-UBI BL2 container) is not an original stock backup and must never be
    used to restore stock firmware.
    """
    validation = verify_backup(directory)
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
    if total != STOCK_ALL_FLASH_SIZE:
        raise Error(f"mtd16/all_flash: распакованный размер {total}, ожидается {STOCK_ALL_FLASH_SIZE}")
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
    no_shift = hashlib.sha256(stock_bl2[:OPENWRT_PRELOADER_SIZE]).hexdigest()
    shifted = hashlib.sha256(stock_bl2[0x800:0x800 + OPENWRT_PRELOADER_SIZE]).hexdigest()
    if no_shift == OPENWRT_PRELOADER_SHA:
        raise Error(
            "выбранный backup содержит OpenWrt preloader в начале BL2 без смещения. "
            "Это копия повреждённого OpenWrt BL2, а не исходный stock backup"
        )
    if shifted == OPENWRT_PRELOADER_SHA and stock_bl2[:0x800] == b"\xff" * 0x800:
        raise Error(
            "выбранный backup содержит OpenWrt all-in-UBI BL2 (FF 0x800 + preloader), "
            "а не исходный stock BL2"
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
        "bl2_provenance": "does not match either known OpenWrt preloader placement",
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
    if total != STOCK_ALL_FLASH_SIZE:
        raise Error("mtd16 изменился во время подготовки файлов восстановления")
    manifest = {
        "kit_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backup_directory": str(Path(directory).resolve()),
        "all_flash_sha256": validation["stock_restore"]["all_flash_sha256"],
        "all_flash_size": STOCK_ALL_FLASH_SIZE,
        "bl2": {"file": bl2_gz.name, "raw_size": STOCK_BL2_SIZE, "raw_sha256": bl2_hash.hexdigest(), "gzip_sha256": sha_file(bl2_gz)},
        "ibu": {"file": ibu_gz.name, "raw_size": STOCK_IBU_SIZE, "raw_sha256": ibu_hash.hexdigest(), "gzip_sha256": sha_file(ibu_gz)},
        "write_order": ["ibu", "bl2"],
        "source_validation": {
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
        "method": "RAM U-Boot, whole ubi erase, aligned chunk write/readback, exact stock BL2 last",
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


def recovery_dependency_preflight() -> None:
    print("Проверяю программные зависимости recovery...")
    if os.name == "nt":
        print("[OK] COM/XMODEM: встроенный Win32-бэкенд, pyserial и pip не нужны.")
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


def wait_bootrom_xmodem(serial_port: RecoverySerial, log, phase: str, timeout: int = 180) -> None:
    print(tr(
        f"\nОжидание BootROM XMODEM для {phase}. Символ C означает готовность приёмника.",
        f"\nWaiting for BootROM XMODEM for {phase}. Character C means the receiver is ready.",
    ))
    # Discard stale ACK/C bytes from the preceding XMODEM phase. BootROM or the
    # preloader keeps transmitting C while it is genuinely ready.
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
    if b"AN7581>" in data:
        return True
    # Generic fallback for U-Boot builds that use the default prompt. Match it
    # only at a line boundary to avoid treating arrows or command output as a
    # prompt.
    return re.search(rb"(?:^|[\r\n])=>[ \t]*(?:\x1b\[[0-9;?]*[A-Za-z])*$", data[-1024:]) is not None


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


def wait_uboot_prompt(serial_port: RecoverySerial, log, timeout: int = 180) -> str:
    """Acquire deterministic control of RAM U-Boot.

    Returns ``prompt`` after a stable AN7581> prompt. Returns ``production``
    only when Linux has already started despite the break sequence, allowing
    the caller to use the production-OpenWrt fallback instead of abandoning the
    restore workflow.
    """
    print("\nОжидаю U-Boot, запущенный из RAM, и останавливаю автоматическую загрузку...")
    print("[UART][UBOOT_SYNC] Ctrl-C/ESC используются для остановки autoboot; Enter не отправляется.")
    deadline = time.time() + timeout
    tail = b""
    uboot_seen = False
    menu_visible = False
    production_read_started = False
    last_break = 0.0
    # Start breaking immediately after the XMODEM EOT ACK. U-Boot appears only
    # a moment later and its menu countdown is three seconds on this profile.
    _uboot_send_break(serial_port)
    last_break = time.time()

    while time.time() < deadline:
        data = serial_port.read(4096, 0.12)
        if data:
            _uart_log_write(log, data)
            tail = (tail + data)[-32768:]
            low = tail.lower()

            if _uboot_prompt_present(tail):
                print("\n[UART][UBOOT_PROMPT] Получено приглашение U-Boot; загрузка с NAND не запускалась.")
                return "prompt"

            if b"u-boot 20" in low or b"hit any key to stop autoboot" in low:
                if not uboot_seen:
                    print("\n[UART][UBOOT_BANNER] Обнаружен RAM U-Boot; прерываю autoboot.")
                uboot_seen = True

            if (b"press up/down to move" in low or
                    b"run default boot command" in low or
                    b"boot system via tftp" in low):
                if not menu_visible:
                    print("\n[UART][UBOOT_MENU] Меню U-Boot обнаружено; отправляю ESC, не Enter.")
                uboot_seen = True
                menu_visible = True

            if (b"read " in low and b" bytes from volume fit" in low) or b"## checking image at" in low:
                if not production_read_started:
                    print("\n[UART][UBOOT_NAND_BOOT] Началось чтение production FIT; посылаю Ctrl-C до передачи управления ядру.")
                production_read_started = True
                uboot_seen = True

            if b"starting kernel" in low or b"booting linux on physical cpu" in low:
                print("\n[UART][PRODUCTION_FALLBACK] Обычная OpenWrt уже начала загрузку; продолжу через SSH и аварийный RAM-образ без повторного XMODEM.")
                return "production"

            if b"press x to load bl31" in low and not uboot_seen:
                raise Error("после передачи FIP устройство вернулось в BootROM вместо RAM U-Boot")

        now = time.time()
        interval = 0.12 if (uboot_seen or production_read_started) else 0.25
        if now - last_break >= interval:
            _uboot_send_break(serial_port, menu_visible=menu_visible)
            last_break = now

    raise Error("U-Boot prompt не появился после передачи FIP; autoboot не считается успешно перехваченным")


def uboot_command(serial_port: RecoverySerial, log, command: str, timeout: int = 30) -> bytes:
    """Run one U-Boot command and require rc=0 plus the following prompt."""
    marker = f"__MEDVEFLASHER_RESTORE_{time.time_ns():x}__"
    wire = f"{command}; echo {marker}_RC_$?"
    print(f"[U-Boot] {command}")
    serial_port.write(wire.encode("ascii") + b"\r")
    deadline = time.time() + timeout
    transcript = bytearray()
    while time.time() < deadline:
        data = serial_port.read(4096, 0.2)
        if not data:
            continue
        _uart_log_write(log, data)
        transcript.extend(data)
        if len(transcript) > 262144:
            del transcript[:-131072]
        raw = bytes(transcript)
        marker_bytes = re.escape(marker.encode("ascii"))
        match = re.search(rb"(?:^|[\r\n])" + marker_bytes + rb"_RC_([0-9]+)(?:[\r\n])", raw)
        if match and _uboot_prompt_present(raw[match.end():]):
            rc = int(match.group(1))
            if rc != 0:
                raise Error(f"U-Boot-команда завершилась с кодом {rc}: {command}")
            return raw
        low = raw.lower()
        if b"starting kernel" in low or b"booting linux on physical cpu" in low:
            raise Error(f"U-Boot command unexpectedly started Linux: {command}")
    raise Error(f"тайм-аут U-Boot-команды или prompt не вернулся: {command}")


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


def _uboot_require_hash(transcript: bytes, expected_sha: str, label: str) -> None:
    if expected_sha.lower().encode("ascii") not in transcript.lower():
        raise Error(f"U-Boot SHA256 не совпал для {label}")


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
            digest = uboot_command(
                serial_port, log,
                f"hash sha256 0x{UBOOT_LOAD_ADDRESS:x} 0x{source.stat().st_size:x}",
                timeout=120,
            )
            _uboot_require_hash(digest, expected_sha, remote_name)
            return
        print(tr(
            f"TFTP {remote_name} не завершился, повтор {attempt}/3.",
            f"TFTP {remote_name} did not complete, retry {attempt}/3.",
        ))
        if thread.is_alive():
            thread.join(190)
    raise Error(f"не удалось передать {remote_name} в RAM U-Boot")


def perform_stock_restore_in_uboot(serial_port: RecoverySerial, log, local_ip: str, router_ip: str,
                                    payload_dir: Path, manifest: dict) -> None:
    """Restore stock directly from RAM U-Boot, with no Linux recovery stage."""
    print(tr(
        "\nШтатная прошивка будет восстановлена непосредственно из U-Boot, запущенного в оперативной памяти.",
        "\nStock firmware will be restored directly from U-Boot running in memory.",
    ))
    print(tr(
        "Основная область NAND будет очищена целиком, записана блоками по 8 MiB и проверена чтением обратно. Точный stock BL2 записывается последним без смещения 0x800.",
        "The main NAND area will be erased completely, written in 8 MiB chunks, and read back for verification. The exact stock BL2 is written last without a 0x800 offset.",
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

    print(tr("[2/3] Записываю и проверяю основную область stock NAND.", "[2/3] Writing and verifying the main stock NAND area."))
    for index, chunk in enumerate(chunks):
        if index != 0:
            _uboot_tftp_load(serial_port, log, local_ip, router_ip, chunk["file"], chunk["remote_name"], chunk["sha256"])
        offset = int(chunk["offset"])
        size = int(chunk["size"])
        print(tr(
            f"[IBU {index + 1}/{len(chunks)}] Смещение 0x{offset:08x}, размер 0x{size:x}",
            f"[IBU {index + 1}/{len(chunks)}] Offset 0x{offset:08x}, size 0x{size:x}",
        ))
        uboot_command_with_progress(serial_port, log, f"mtd write ubi 0x{UBOOT_LOAD_ADDRESS:x} 0x{offset:x} 0x{size:x}", 600, f"запись IBU {index + 1}/{len(chunks)}", f"writing IBU {index + 1}/{len(chunks)}")
        uboot_command(serial_port, log, f"mw.b 0x{UBOOT_LOAD_ADDRESS:x} 0x00 0x{size:x}", timeout=120)
        readback = uboot_command_with_progress(serial_port, log, f"mtd read ubi 0x{UBOOT_LOAD_ADDRESS:x} 0x{offset:x} 0x{size:x}", 600, f"чтение IBU {index + 1}/{len(chunks)}", f"reading IBU {index + 1}/{len(chunks)}")
        if b"error" in readback.lower() or b"failed" in readback.lower():
            raise Error(f"U-Boot сообщил ошибку чтения IBU-блока {index + 1}")
        digest = uboot_command_with_progress(serial_port, log, f"hash sha256 0x{UBOOT_LOAD_ADDRESS:x} 0x{size:x}", 180, f"SHA256 IBU {index + 1}/{len(chunks)}", f"SHA256 IBU {index + 1}/{len(chunks)}")
        _uboot_require_hash(digest, chunk["sha256"], f"IBU block {index + 1}")

    bl2_path = Path(manifest["uboot_restore"]["bl2_file"])
    bl2_sha = manifest["uboot_restore"]["bl2_sha256"]
    print(tr("[3/3] Загружаю точный исходный stock BL2. Смещение 0x800 к нему не применяется.", "[3/3] Loading the exact original stock BL2. No 0x800 offset is applied."))
    _uboot_tftp_load(serial_port, log, local_ip, router_ip, bl2_path, "nokia-stock-bl2.bin", bl2_sha)
    uboot_command(serial_port, log, "mtd erase bl2", timeout=180)
    uboot_command(serial_port, log, f"mtd write bl2 0x{UBOOT_LOAD_ADDRESS:x} 0x0 0x{STOCK_BL2_SIZE:x}", timeout=180)
    uboot_command(serial_port, log, f"mw.b 0x{UBOOT_LOAD_ADDRESS:x} 0x00 0x{STOCK_BL2_SIZE:x}", timeout=60)
    uboot_command(serial_port, log, f"mtd read bl2 0x{UBOOT_LOAD_ADDRESS:x} 0x0 0x{STOCK_BL2_SIZE:x}", timeout=180)
    digest = uboot_command(serial_port, log, f"hash sha256 0x{UBOOT_LOAD_ADDRESS:x} 0x{STOCK_BL2_SIZE:x}", timeout=60)
    _uboot_require_hash(digest, bl2_sha, "stock BL2")

    print(tr("[OK] Все IBU-блоки и stock BL2 совпали при чтении обратно. Перезагружаю Nokia.", "[OK] Every IBU chunk and the stock BL2 matched on readback. Rebooting Nokia."))
    serial_port.write(b"reset\r")

def inspect_restore_environment(host: str, quiet: bool = False) -> tuple[str, str]:
    command = (
        "echo BOARD=$(cat /tmp/sysinfo/board_name 2>/dev/null || true); "
        "echo STATE=$(cat /tmp/NOKIA_AUTOFLASH_STATE 2>/dev/null || true); "
        "echo ROOT=$(awk '$2==\"/\" {print $3; exit}' /proc/mounts); "
        "cat /proc/mtd; "
        "for c in mtd gzip sha256sum fw_printenv fw_setenv nc scp; do "
        "command -v $c >/dev/null 2>&1 && echo TOOL_$c=1 || echo TOOL_$c=0; done; "
        "if command -v tftp >/dev/null 2>&1; then "
        "echo TOOL_tftp=1; echo TFTP_IMPL=standalone; echo TFTP_PROBE_RC=0; "
        "elif [ -x /bin/busybox ]; then "
        "/bin/busybox tftp --help >/dev/null 2>&1; bb_tftp_rc=$?; "
        "if [ \"$bb_tftp_rc\" -ne 127 ]; then "
        "echo TOOL_tftp=1; echo TFTP_IMPL=busybox-applet; echo TFTP_PROBE_RC=$bb_tftp_rc; "
        "else echo TOOL_tftp=0; echo TFTP_IMPL=missing; echo TFTP_PROBE_RC=$bb_tftp_rc; fi; "
        "else echo TOOL_tftp=0; echo TFTP_IMPL=missing; echo TFTP_PROBE_RC=127; fi"
    )
    _, output = ssh_run(host, command, timeout=120, quiet=quiet)
    low = output.lower()
    board_ok = "board=nokia,xg-040g-md-ubi" in low
    recovery_markers = (
        'mtd0: 10000000 00020000 "all_flash"',
        'mtd1: 00020000 00020000 "bl2"',
        'mtd2: 0ffe0000 00020000 "ibu"',
    )
    production_markers = (
        'mtd0: 10000000 00020000 "all_flash"',
        'mtd1: 00020000 00020000 "bl2"',
        'mtd2: 0ffe0000 00020000 "ubi"',
    )
    if board_ok and all(marker in low for marker in recovery_markers):
        return "recovery", output
    if board_ok and all(marker in low for marker in production_markers):
        return "production", output
    raise Error("OpenWrt обнаружен, но его плата/MTD-разметка не соответствует Nokia XG-040G-MD recovery или all-in-UBI production")


def transition_preflight_for_restore(host: str, backup_ri_sha: str, timeout: int = 180) -> str:
    deadline = time.time() + timeout; last_output = ""; consecutive = 0
    while time.time() < deadline:
        try:
            mode, output = inspect_restore_environment(host, quiet=True); last_output = output
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
    if "tool_tftp=1" in low:
        transport="tftp"; print(tr("[OK] Система восстановления проверена. Способ передачи: TFTP.", "[OK] The recovery system is verified. Transfer method: TFTP."))
    elif "tool_scp=1" in low:
        scp_executable(); transport="scp"; print(tr("[ПРЕДУПРЕЖДЕНИЕ] TFTP недоступен; используется SCP.", "[WARNING] TFTP is unavailable; using SCP."))
    elif "tool_nc=1" in low:
        transport="tcp-nc"; print(tr("[ПРЕДУПРЕЖДЕНИЕ] TFTP и SCP недоступны; используется TCP.", "[WARNING] TFTP and SCP are unavailable; using TCP."))
    else:
        raise Error(tr("в recovery нет транспорта tftp, scp или nc", "recovery has no tftp, scp, or nc transport"))
    if "state=recovery_ready" not in low:
        _write_session_only("[RESTORE] recovery state file is absent; exact MTD layout confirmed")
    command=("printf RI_RAW_SHA=; if grep -q \"\"ri-stock\"\" /proc/mtd; then mtd -q -l 262144 dump ri-stock 2>/dev/null | sha256sum | awk '{print $1}'; else echo unavailable; fi")
    _,output=ssh_run(host,command,timeout=120,quiet=True); match=re.search(r"RI_RAW_SHA=([0-9a-f]{64})",output)
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
    _,output=ssh_run_with_progress(host,cmd,1200,f"VERIFY {target.upper()}")
    match=re.search(r"([0-9a-f]{64})",output)
    if not match or match.group(1)!=raw_sha:
        raise Error(tr(
            f"readback SHA256 {target} не совпал; не перезагружайте и не отключайте питание",
            f"readback SHA256 mismatch for {target}; do not reboot or remove power",
        ))
    print(f"[OK] {target} readback SHA256: {raw_sha}")


def _restore_stream_transport(host: str, local_ip: str, port: int, source: Path, remote_name: str, target: str, transport: str) -> None:
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
    command=(f"set +e; echo RESTORE_STAGE={target}; rm -f {fifo}; mkfifo {fifo}; "+receive+f"gzip -dc <{fifo} | mtd -f write - {shlex.quote(target)}; wr=$?; wait $tp; trc=$?; rm -f {fifo}; echo RESTORE_PIPELINE_TRANSPORT_RC=$trc RESTORE_PIPELINE_WRITE_RC=$wr; [ $trc -eq 0 ] && [ $wr -eq 0 ]")
    try:
        ssh_run_with_progress(host,command,2400,f"{label} {target}",result,source.stat().st_size)
    except BaseException as exc:
        raise TransportError(f"{label} pipeline failed: {exc}") from exc
    thread.join(30)
    if thread.is_alive(): raise TransportError(f"{label} server did not stop")
    if result.error: raise TransportError(f"{label}: {result.error}")
    if result.bytes_transferred!=source.stat().st_size: raise TransportError(f"{label}: transferred {result.bytes_transferred}, expected {source.stat().st_size}")
    print(tr(f"[FLASH] {target}: сжатый поток принят и записан.", f"[FLASH] {target}: compressed stream received and written."))


def _restore_scp_transport(host: str, source: Path, target: str) -> None:
    remote=f"/tmp/nokia-restore-{target}.gz"; size=source.stat().st_size
    try:
        _,mem=ssh_run(host,"awk '/MemAvailable:/ {print $2; exit}' /proc/meminfo",timeout=30,quiet=True)
    except Error as exc:
        raise TransportError(f"SCP preflight failed: {exc}") from exc
    m=re.search(r"([0-9]+)",mem); available=int(m.group(1))*1024 if m else 0
    if available and available < size + 32*1024*1024:
        raise TransportError(tr(
            f"SCP: недостаточно RAM: available={available}, need={size + 32*1024*1024}",
            f"SCP: insufficient RAM: available={available}, need={size + 32*1024*1024}",
        ))
    scp_copy_to_recovery(host,source,remote)
    expected=sha_file(source); _,out=ssh_run(host,f"sha256sum {shlex.quote(remote)} | awk '{{print $1}}'",timeout=300,quiet=True)
    if expected not in out: ssh_run(host,f"rm -f {shlex.quote(remote)}",timeout=30,quiet=True); raise TransportError("SCP compressed-file SHA256 mismatch")
    print(tr(f"[FLASH] {target}: распаковываю SCP-файл и записываю NAND...", f"[FLASH] {target}: decompressing the SCP file and writing NAND..."))
    cmd=f"gzip -dc {shlex.quote(remote)} | mtd -f write - {shlex.quote(target)}; rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    try: ssh_run_with_progress(host,cmd,2400,f"FLASH {target.upper()}")
    except BaseException as exc: raise TransportError(f"SCP write pipeline failed: {exc}") from exc


def serve_restore_payload(host: str, local_ip: str, port: int, source: Path, remote_name: str, target: str, raw_size: int, raw_sha: str, transport: str) -> None:
    order={"tftp":["tftp","scp","tcp-nc"],"scp":["scp","tcp-nc"],"tcp-nc":["tcp-nc","scp"]}.get(transport,[transport])
    failures=[]
    for index,candidate in enumerate(order,1):
        print()
        print(tr(f"[TRANSFER] {target}: попытка {index}/{len(order)}, транспорт {candidate}.", f"[TRANSFER] {target}: attempt {index}/{len(order)}, transport {candidate}."))
        try:
            if candidate=="scp": _restore_scp_transport(host,source,target)
            else: _restore_stream_transport(host,local_ip,port,source,remote_name,target,candidate)
            _verify_restore_readback(host,target,raw_size,raw_sha); return
        except TransportError as exc:
            failures.append(f"{candidate}: {exc}")
            print(tr(f"[WARNING] {candidate} не сработал: {exc}", f"[WARNING] {candidate} failed: {exc}"))
    raise Error(tr(
        "все транспорты восстановления отказали: ",
        "all restore transports failed: ",
    ) + " | ".join(failures))

def perform_stock_restore_over_ssh(router_ip: str, local_ip: str, restore_port: int,
                                   backup_dir: Path, payload_dir: Path, manifest: dict) -> None:
    stage_header("R1", "Проверка системы восстановления", "Recovery-system checks")
    backup_ri_sha, _ = raw_sha256(Path(verify_backup(backup_dir)["files"]["7"]))
    transport = transition_preflight_for_restore(router_ip, backup_ri_sha)
    print()
    print(tr("ПЕРЕД НАЧАЛОМ ПРОВЕРЬТЕ:", "CHECK BEFORE STARTING:"))
    print(tr("  • Стабильное питание до окончательной перезагрузки.", "  • Stable power until the final reboot."))
    print(tr("  • Прямое Ethernet-соединение: ПК 192.168.1.254/24, Nokia 192.168.1.1.", "  • Direct Ethernet connection: PC 192.168.1.254/24, Nokia 192.168.1.1."))
    print(tr("  • Разрешите Python и OpenSSH в брандмауэре.", "  • Allow Python and OpenSSH through the firewall."))
    print(tr("  • Не нажимайте Reset и не закрывайте окно мастера.", "  • Do not press Reset or close the wizard window."))
    print(tr("  • Полная диагностика сохраняется в work/logs/LATEST.log.", "  • Full diagnostics are saved in work/logs/LATEST.log."))
    print()
    print(tr("ВНИМАНИЕ: выбранный полный backup будет записан во флеш-память роутера.", "WARNING: the selected complete backup will be written to the router flash."))
    print(tr("Основная область записывается и проверяется первой; загрузчик — строго последним.", "The main area is written and verified first; the bootloader is written strictly last."))
    confirm=input(tr("Введите точно RESTORE STOCK BACKUP: ", "Type exactly RESTORE STOCK BACKUP: ")).strip()
    if confirm!="RESTORE STOCK BACKUP": raise Error(tr("stock restore отменён", "stock restore cancelled"))
    stage_header("R2", "Передача, запись и проверка IBU", "Transfer, write, and verify IBU")
    serve_restore_payload(router_ip,local_ip,restore_port,payload_dir/manifest["ibu"]["file"],manifest["ibu"]["file"],"ibu",manifest["ibu"]["raw_size"],manifest["ibu"]["raw_sha256"],transport)
    print(tr(
        "[OK] IBU полностью восстановлена и проверена. BL2 ещё не изменялся.",
        "[OK] IBU has been fully restored and verified. BL2 has not been modified yet.",
    ))
    stage_header("R3", "Запись stock BL2 последним", "Write stock BL2 last")
    serve_restore_payload(router_ip,local_ip,restore_port,payload_dir/manifest["bl2"]["file"],manifest["bl2"]["file"],"bl2",manifest["bl2"]["raw_size"],manifest["bl2"]["raw_sha256"],transport)
    stage_header("R4", "Финальная проверка полного all_flash", "Final full all_flash verification")
    full_cmd=f"mtd -q -l {STOCK_ALL_FLASH_SIZE} dump all_flash | sha256sum | awk '{{print $1}}'"
    _,output=ssh_run_with_progress(router_ip,full_cmd,1800,"VERIFY ALL_FLASH")
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
    ssh_run(router_ip,"sync; reboot -f",timeout=30,allow_disconnect=True)



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
            rc, output = ssh_run(
                host,
                "echo __NOKIA_SSH_READY__; cat /tmp/sysinfo/board_name 2>/dev/null; cat /proc/mtd 2>/dev/null",
                timeout=25,
                allow_disconnect=True,
                quiet=True,
            )
            if rc == 0 and "__NOKIA_SSH_READY__" in output:
                low = output.lower()
                mode = None
                if 'mtd2: 0ffe0000 00020000 "ibu"' in low:
                    mode = "recovery"
                elif 'mtd2: 0ffe0000 00020000 "ubi"' in low:
                    mode = "production"
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
        ssh_run(host, "sync; reboot -f", timeout=30, allow_disconnect=True, quiet=True)

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
    print(tr("Подключите стабильное питание и Ethernet напрямую к ПК. Задайте ПК 192.168.1.254/24; Wi-Fi/VPN временно отключите.", "Connect stable power and Ethernet directly to the PC. Set the PC to 192.168.1.254/24; temporarily disable Wi-Fi/VPN."))
    print(tr("Не нажимайте Reset. Окно остаётся открытым; прогресс и диагностика сохраняются в work/logs/LATEST.log.", "Do not press Reset. The window stays open; progress and diagnostics are saved in work/logs/LATEST.log."))
    print(tr("Способ передачи выбирается автоматически: TFTP, затем резервные варианты.", "The transfer method is selected automatically: TFTP, then fallback methods."))
    ssh_executable()
    local_ip = input(tr("Статический IP компьютера [192.168.1.254]: ", "Static PC IP [192.168.1.254]: ")).strip() or "192.168.1.254"
    router_ip = input(tr("IP Nokia [192.168.1.1]: ", "Nokia IP [192.168.1.1]: ")).strip() or "192.168.1.1"
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
    mode, _ = inspect_restore_environment(router_ip, quiet=True)
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


def stock_recovery_wizard() -> None:
    verify_kit()
    print(tr("\n=== Восстановление кирпича через BootROM C и XMODEM ===", "\n=== Brick recovery through BootROM C and XMODEM ==="))
    print(tr("Нужен USB-UART 3.3 V: подключайте только GND, TX и RX. VCC к Nokia не подключайте.", "A 3.3 V USB-UART adapter is required: connect only GND, TX, and RX. Do not connect VCC to Nokia."))
    print(tr("Ethernet должен соединять компьютер с Nokia; компьютеру задайте 192.168.1.254/24.", "Connect the PC to Nokia over Ethernet and assign 192.168.1.254/24 to the PC."))
    print(tr("Preloader и U-Boot временно загружаются в оперативную память; штатная прошивка восстанавливается непосредственно из U-Boot.", "The preloader and U-Boot are loaded temporarily into memory; stock firmware is restored directly from U-Boot."))
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
    print(tr(f"[OK] Исходный stock backup проверен. Рабочие файлы: {payload_dir}", f"[OK] Original stock backup verified. Working files: {payload_dir}"))
    log_path = payload_dir / "uart-recovery.log"
    serial_port = RecoverySerial(uart_port)
    try:
        with log_path.open("ab", buffering=0) as log:
            print(tr("\nЕсли UART уже показывает Press x или повторяющиеся C, питание не отключайте.", "\nIf UART already shows Press x or repeated C characters, do not remove power."))
            print(tr("Закройте PuTTY, Tera Term и другие программы, чтобы освободить COM-порт.", "Close PuTTY, Tera Term, and other programs to release the COM port."))
            print(tr("Только при отсутствии приглашения BootROM: выключите Nokia, удерживайте Reset, включите питание и дождитесь Press x.", "Only if the BootROM prompt is absent: power Nokia off, hold Reset, power it on, and wait for Press x."))
            input(tr("Нажмите Enter, когда COM-порт свободен и BootROM готов: ", "Press Enter when the COM port is free and BootROM is ready: "))
            wait_bootrom_xmodem(serial_port, log, "preloader")
            xmodem_send(serial_port, RECOVERY_PRELOADER, "OpenWrt preloader (RAM)", log)
            wait_bootrom_xmodem(serial_port, log, "BL31 + U-Boot FIP")
            xmodem_send(serial_port, RECOVERY_FIP, "OpenWrt BL31 + U-Boot FIP (RAM)", log)
            uboot_state = wait_uboot_prompt(serial_port, log)
            if uboot_state == "prompt":
                try:
                    perform_stock_restore_in_uboot(serial_port, log, local_ip, router_ip, payload_dir, manifest)
                except PermissionError as exc:
                    raise Error(tr("нет прав на UDP/69; в Linux запустите через sudo", "permission denied for UDP/69; on Linux run with sudo")) from exc
            else:
                print(tr("Обычная OpenWrt успела загрузиться. Жду устойчивый SSH и продолжаю через recovery-систему без нового XMODEM.", "Installed OpenWrt started before U-Boot was captured. Waiting for stable SSH and continuing through the recovery system without another XMODEM session."))
                if wait_for_stable_openwrt(router_ip, 480, expected_mode="production") != "production":
                    raise Error(tr("обычная OpenWrt не появилась по SSH после пропущенного U-Boot", "installed OpenWrt did not become available over SSH after U-Boot was missed"))
                boot_recovery_from_production_openwrt(router_ip, local_ip, router_ip, ask_before_reboot=False)
                perform_stock_restore_over_ssh(router_ip, local_ip, 1069, backup_dir, payload_dir, manifest)
            print(tr(
                "[OK] Запись IBU и BL2 подтверждена readback SHA256. Проверяю загрузку stock отдельно от результата записи.",
                "[OK] IBU and BL2 writes were confirmed by readback SHA256. Checking stock boot separately from the write result.",
            ))
            deadline = time.time() + 180
            bootrom_window_seen = False
            stock_reachable = False
            last_probe = 0.0
            while time.time() < deadline:
                data = serial_port.read(4096, 0.5)
                if data:
                    _uart_log_write(log, data)
                    low = data.lower()
                    if b"press x" in low and not bootrom_window_seen:
                        bootrom_window_seen = True
                        print(tr(
                            "[UART] Штатное окно Press x после reset обнаружено; это не ошибка. x не отправляется.",
                            "[UART] The normal Press x window after reset was detected; this is not an error. x will not be sent.",
                        ))
                now = time.time()
                if now - last_probe >= 2.0:
                    last_probe = now
                    for port in (80, 443):
                        try:
                            with socket.create_connection((router_ip, port), timeout=0.5):
                                stock_reachable = True
                                break
                        except OSError:
                            pass
                    if stock_reachable:
                        break
            if stock_reachable:
                print(tr(
                    f"[OK] Штатный Web-интерфейс доступен на {router_ip}; восстановление и загрузка stock успешны.",
                    f"[OK] The stock Web interface is reachable at {router_ip}; restore and stock boot succeeded.",
                ))
            else:
                print(tr(
                    "[WARN] Запись NAND успешно проверена, но stock Web-интерфейс не подтверждён за 180 секунд. Это POST_REBOOT_UNKNOWN, а не ошибка восстановления.",
                    "[WARN] NAND writing was verified, but the stock Web interface was not confirmed within 180 seconds. This is POST_REBOOT_UNKNOWN, not a restore failure.",
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


def _automatic_stock_web_access(
    host: str,
    module,
    *,
    offer_interactive_plain_retry: bool = True,
) -> StockAccess:
    web_user = input(tr("Пользователь штатного веб-интерфейса [CMCCAdmin]: ",
                        "Stock web-interface user [CMCCAdmin]: ")).strip() or "CMCCAdmin"
    env_password = os.environ.pop("NOKIA_WEB_PASSWORD", None)
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
    host = input(tr("IP Nokia [192.168.1.1]: ", "Nokia IP [192.168.1.1]: ")).strip() or "192.168.1.1"
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
    if require_model_gate:
        print(tr(
            "4 — Установить свой образ OpenWrt (экспертный режим)",
            "4 — Install a custom OpenWrt image (expert mode)",
        ))
    allowed = ("1", "2", "3", "4") if require_model_gate else ("1", "2", "3")
    choices_text = "1/2/3/4" if require_model_gate else "1/2/3"
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
    if choice == "4":
        print(tr(
            "[ОПАСНО] Мастер не будет проверять модель роутера. На другой модели прошивка может вывести устройство из строя.",
            "[DANGER] The wizard will not check the router model. Flashing a different model may make the device unusable.",
        ))
        print(tr(
            "[INFO] Модель не проверяется. После загрузки transition вы выберете sysupgrade на диске; до его проверки NAND не форматируется.",
            "[INFO] The model is not checked. After transition boots, you will select a sysupgrade file; NAND is not formatted before it is validated.",
        ))
        confirm = input(tr(
            "Продолжить? [y/N]: ",
            "Continue? [y/N]: ",
        )).strip().lower()
        if confirm not in ("y", "yes", "д", "да"):
            raise Error(tr(
                "установка без проверки модели отменена",
                "installation without a model check was cancelled",
            ))
        access = _manual_stock_access(host, default_telnet_user, default_su_user)
        access.model_gate_policy = "bypass"
        access.force_tftp = True
        access.custom_sysupgrade = True
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
    print(tr("1 — USB через Samba/смонтированную папку, флешку вынимать не нужно", "1 — USB through Samba/a mounted directory; do not remove the drive"))
    print(tr("2 — USB через FTP stock Nokia", "2 — USB through stock Nokia FTP"))
    print(tr("3 — прямой TFTP между Nokia и ПК, USB не требуется", "3 — direct TFTP between Nokia and the PC; no USB required"))
    choice = input(tr("Выберите 1/2/3: ", "Select 1/2/3: ")).strip()
    if choice == "1":
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
    if choice == "2":
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
    if choice == "3":
        local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
        port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
        port = int(port_text) if port_text else 1069
        return "tftp", {"local_ip": local_ip, "tftp_port": port, "block_size": 4096}
    raise Error("неверный выбор транспорта")


def full_wizard() -> None:
    stage_header("0", "Проверка комплекта и параметры", "Kit verification and parameters")
    verify_kit()
    access = ask_credentials(require_model_gate=True)
    try:
        transport, transport_args = choose_transport(
            access.host, access=access, force_tftp=access.force_tftp
        )
    finally:
        access.close_web()
    host = access.host
    if access.custom_sysupgrade:
        print(tr(
            "[PATH] Экспертная установка: stock → полный backup → ручной transition → выбор и проверка sysupgrade на ПК → OpenWrt",
            "[PATH] Expert installation: stock → complete backup → manual transition → select and validate sysupgrade on the PC → OpenWrt",
        ))
    else:
        print_full_install_route(transport)
    stage_header("1", "Полный stock backup", "Complete stock backup")
    telnet: Telnet | None = None
    backup_dir: Path
    try:
        # Apply the selected strict, best-effort, or explicit expert-bypass model policy.
        gate_telnet = login_root_md(access)
        try:
            require_supported_model_over_telnet(access, gate_telnet)
        finally:
            gate_telnet.close()

        if transport == "tftp":
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_dir = WORK / "backups" / f"nokia-xg040gmd-backup-{stamp}"
            backup_tftp(
                access, host, backup_dir, transport_args.get("local_ip"),
                transport_args.get("tftp_port", 1069), transport_args.get("block_size", 4096)
            )
            # The TFTP backup reuses one session until an actual transfer failure.
            telnet = login_root_md(access)
        else:
            telnet = login_root_md(access)
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
            remote_backup = backup_to_usb(telnet, remote_mount)
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
                    print(tr(
                        f"[TRANSFER] FTP backup скачивается из {ftp_source} (на Nokia: {remote_backup})",
                        f"[TRANSFER] Downloading the FTP backup from {ftp_source} (on Nokia: {remote_backup})",
                    ))
                    total_bytes, total_files, sizes_complete = ftp_tree_stats(ftp, ftp_source)
                    if not sizes_complete:
                        _write_session_only("[TECH] FTP SIZE unavailable for at least one backup file; byte percentage disabled.")
                    progress = TransferProgress(
                        tr("FTP: backup с Nokia на ПК", "FTP: backup from Nokia to PC"),
                        total_bytes if sizes_complete else 0,
                        total_files,
                    )
                    ftp_walk_download(ftp, ftp_source, backup_dir, progress)
                    progress.finish()
            verify_backup(backup_dir)

        print(f"\n[OK] Полный backup сохранён на ПК: {backup_dir}")
        stage_header("2", "Персонализация установочного пакета", "Device-specific package generation")
        install_dir, info = personalize(backup_dir, manual_transition=access.custom_sysupgrade)
        print(f"[OK] Персональный пакет создан: {install_dir}")
        stage_header("3", "Передача пакета на Nokia", "Deploy package to Nokia")
        assert telnet is not None
        remote_dir = deploy_install(telnet, host, install_dir, transport, **transport_args)
        device_state = WORK / info["device_id"] / "state.json"
        save_state(device_state, {"phase": "deployed", "router": host, "remote_dir": remote_dir, "backup_dir": str(backup_dir)})
        stage_header("4", "Проверка перед записью", "Pre-write checks")
        run_stage1(telnet, remote_dir, nand_unknown=False, manual_transition=access.custom_sysupgrade)
        save_state(device_state, {"phase": "stage1_started", "session_log": str(SESSION_LOG_PATH or "")})
    finally:
        if telnet is not None:
            telnet.close()
    if access.custom_sysupgrade:
        final_result = run_custom_stage2(
            host, transport_args.get("local_ip"), transport_args.get("tftp_port", 1069), transport_args.get("block_size", 4096)
        )
    else:
        final_result = run_stage2(host)
    stage_header("9" if access.custom_sysupgrade else "7", "Итог установки", "Installation result")
    print(tr(f"[OK] Финальный статус: {final_result}", f"[OK] Final status: {final_result}"))
    save_state(WORK / info["device_id"] / "state.json", {"phase": "complete" if final_result != "post-install-unverified" else "post-install-unverified", "final_result": final_result, "session_log": str(SESSION_LOG_PATH or "")})

def install_from_existing_backup_wizard() -> None:
    stage_header("0", "Проверка комплекта", "Kit verification")
    verify_kit()
    print(tr(
        "\n=== Установка OpenWrt из уже снятого полного backup, без повторного backup и без UART ===",
        "\n=== Install OpenWrt from an existing complete backup, without another backup or UART ===",
    ))
    backup_dir = Path(input(tr(
        "Путь к каталогу полного stock backup mtd0..mtd16: ",
        "Path to the complete stock backup directory containing mtd0..mtd16: ",
    )).strip().strip('"')).expanduser()
    access = ask_credentials(require_model_gate=True)
    stage_header("1", "Проверка готового backup", "Existing backup verification")
    print(tr("Проверяю backup и создаю новый персональный пакет...", "Verifying the backup and creating a new device-specific package..."))
    install_dir, info = personalize(backup_dir, manual_transition=access.custom_sysupgrade)
    print(tr(f"[OK] Персональный пакет создан: {install_dir}", f"[OK] Device-specific package created: {install_dir}"))
    try:
        transport, transport_args = choose_transport(
            access.host, install_only=True, access=access, force_tftp=access.force_tftp
        )
    finally:
        access.close_web()
    host = access.host
    stage_header("2", "Подключение и передача пакета", "Connection and package deployment")
    telnet = login_root_md(access)
    try:
        require_supported_model_over_telnet(access, telnet)
        remote_dir = deploy_install(telnet, host, install_dir, transport, **transport_args)
        device_state = WORK / info["device_id"] / "state.json"
        save_state(device_state, {
            "phase": "deployed_from_existing_backup",
            "router": host,
            "remote_dir": remote_dir,
            "backup_dir": str(backup_dir),
        })
        stage_header("3", "Проверка перед записью", "Pre-write checks")
        run_stage1(telnet, remote_dir, nand_unknown=False, manual_transition=access.custom_sysupgrade)
        save_state(device_state, {"phase": "stage1_started", "session_log": str(SESSION_LOG_PATH or "")})
    finally:
        telnet.close()
    if access.custom_sysupgrade:
        final_result = run_custom_stage2(
            host, transport_args.get("local_ip"), transport_args.get("tftp_port", 1069), transport_args.get("block_size", 4096)
        )
    else:
        final_result = run_stage2(host)
    stage_header("9" if access.custom_sysupgrade else "7", "Итог установки", "Installation result")
    print(tr(f"[OK] Финальный статус: {final_result}", f"[OK] Final status: {final_result}"))
    save_state(WORK / info["device_id"] / "state.json", {"phase": "complete" if final_result != "post-install-unverified" else "post-install-unverified", "final_result": final_result, "session_log": str(SESSION_LOG_PATH or "")})


def backup_only_wizard() -> None:
    verify_kit()
    access = ask_credentials()
    access.close_web()
    host = access.host
    print(tr("1 — полный backup на USB-флешку в порту Nokia", "1 — complete backup to a USB drive in the Nokia USB port"))
    print(tr("2 — полный backup напрямую на ПК через TFTP, без флешки", "2 — complete backup directly to the PC over TFTP, no USB drive"))
    choice = input(tr("Выберите 1/2: ", "Select 1/2: ")).strip()
    if choice == "1":
        print_usb_requirements()
        telnet = login_root_md(access)
        try:
            mount = input(tr("Путь USB внутри Nokia [автоопределение: /mnt/USB_disc1]: ", "USB path inside Nokia [auto-detect: /mnt/USB_disc1]: ")).strip() or None
            mount = resolve_router_usb_mount(telnet, mount)
            verify_router_usb_storage(telnet, mount)
            cleanup_incomplete_router_backups(telnet, mount)
            result = backup_to_usb(telnet, mount)
            print(tr(f"[OK] Backup готов на USB-флешке: {result}", f"[OK] Backup completed on the USB drive: {result}"))
            print(tr("Скопируйте весь каталог backup на компьютер до любых операций с NAND.", "Copy the entire backup directory to the PC before any NAND operation."))
        finally:
            telnet.close()
    elif choice == "2":
        stamp = time.strftime("%Y%m%d-%H%M%S")
        destination = WORK / "backups" / f"nokia-xg040gmd-backup-{stamp}"
        local_ip = input("IP этого ПК для Nokia [auto]: ").strip() or None
        port_text = input("UDP-порт TFTP [1069]: ").strip()
        port = int(port_text) if port_text else 1069
        backup_tftp(access, host, destination, local_ip, port, 4096)
        print(f"Backup готов на ПК: {destination}")
    else:
        raise Error("неверный выбор")

def personalize_wizard() -> None:
    verify_kit()
    path = Path(input("Путь к каталогу полного backup: ").strip().strip('"')).expanduser()
    output, info = personalize(path)
    print(f"Готово: {output}")
    for warning in info["backup"]["warnings"]:
        print("WARNING:", warning)


def resume_stage2_wizard() -> None:
    host = input("IP transition OpenWrt [192.168.1.1]: ").strip() or "192.168.1.1"
    manual = False
    manual_state = ""
    if _tcp_open(host, 22):
        manual, manual_state, board_name, probe_error = _manual_transition_probe(host, timeout=8)
        if probe_error:
            _write_session_only(f"[MANUAL-SSH] resume probe failed: {probe_error}")
            raise Error(tr(
                f"SSH 22 открыт, но режим transition определить не удалось: {probe_error[-500:]}",
                f"SSH 22 is open, but the transition mode could not be identified: {probe_error[-500:]}",
            ))
        elif manual and board_name and board_name != "nokia,xg-040g-md-ubi":
            _write_session_only(f"[MANUAL-SSH] resume marker accepted; board_name={board_name!r}")
    if manual:
        print(tr(f"[OK] Обнаружен ручной transition; состояние: {manual_state or 'unknown'}.", f"[OK] Manual transition detected; state: {manual_state or 'unknown'}."))
        if manual_state in ("STARTING", "CHECKING", "FORMATTING_AND_FLASHING", "WAITING_FOR_SYSTEM", "FAILED"):
            result = run_stage2(host, manual_mode=True)
        else:
            local_ip = input(tr("IP этого ПК для Nokia [auto]: ", "This PC IP for Nokia [auto]: ")).strip() or None
            port_text = input(tr("UDP-порт TFTP [1069]: ", "TFTP UDP port [1069]: ")).strip()
            result = run_custom_stage2(host, local_ip, int(port_text) if port_text else 1069, 4096)
    else:
        result = run_stage2(host)
    stage_header("9" if manual else "7", "Итог ожидания", "Monitoring result")
    print(tr(f"[OK] Финальный статус: {result}", f"[OK] Final status: {result}"))


def wizard() -> None:
    print(f"Nokia Router MedveFlasher — {APP_VERSION}")
    print(tr(
        "1 — установить OpenWrt (со снятием backup)",
        "1 — install OpenWrt (with a backup first)",
    ))
    print(tr("2 — снять backup", "2 — create a backup"))
    print(tr("3 — подготовить пакет из своего backup", "3 — prepare a package from your backup"))
    print(tr("4 — продолжить со 2 этапа", "4 — resume from stage 2"))
    print(tr("5 — откатить на сток (без UART)", "5 — restore stock (no UART)"))
    print(tr("6 — восстановить кирпич (нужен UART)", "6 — recover a brick (UART required)"))
    print(tr("7 — установить OpenWrt из готового backup", "7 — install OpenWrt from an existing backup"))
    print(tr("8 — выход", "8 — exit"))
    while True:
        choice = input(tr("Выберите 1/2/3/4/5/6/7/8: ", "Select 1/2/3/4/5/6/7/8: ")).strip()
        if choice == "1":
            full_wizard(); return
        if choice == "2":
            backup_only_wizard(); return
        if choice == "3":
            personalize_wizard(); return
        if choice == "4":
            resume_stage2_wizard(); return
        if choice == "5":
            stock_restore_running_wizard(); return
        if choice == "6":
            stock_recovery_wizard(); return
        if choice == "7":
            install_from_existing_backup_wizard(); return
        if choice == "8":
            return
        print(tr("Неверный выбор. Введите число от 1 до 8.", "Invalid selection. Enter a number from 1 to 8."))


def main(argv: list[str] | None = None) -> int:
    already_logging = SESSION_LOG_PATH is not None
    start_session_logging()
    if not already_logging:
        print(f"[LOG] work/logs/LATEST.log — build {BUILD_TAG}", flush=True)
    ensure_language()
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
    sub.add_parser("stock-restore-running")
    sub.add_parser("stock-restore")
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "wizard"):
            wizard()
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
        elif args.command == "stock-restore-running":
            stock_restore_running_wizard()
        elif args.command == "stock-restore":
            stock_restore_selector_wizard()
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
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
