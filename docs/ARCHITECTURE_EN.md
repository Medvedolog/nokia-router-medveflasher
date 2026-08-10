# Nokia Router MedveFlasher — Architecture

Technical deep-dive for developers and the curious: how the install works, what
carries each piece of data, and what makes the no-UART path tick. Users don't
need this — the [guide](README_EN.md) is enough to install.

---

## Principles

**Zero external dependencies.** The entire PC wizard runs on the Python 3
standard library. No `requests`, no `pyserial`, no `cryptography`, no browser.
The reason is not asceticism: the target user is not a developer, and every
external library is a command that can be mistyped and requires internet access at
the exact moment when the computer is already cabled to the router. So everything
is implemented from scratch where a package would normally be used:

- **AES-128-CBC + RSA-1024** for web-UI login — pure Python, verified against
  FIPS-197 and NIST SP 800-38A vectors (`stock_web.py --selftest`);
- **Win32 COM-port backend** via `ctypes` and `kernel32` — instead of `pyserial`,
  including correct `COMMTIMEOUTS` for XMODEM;
- **TFTP server and client**, **XMODEM**, **FIT/DTB parsing** — also custom.

**Fail closed.** On the only device holding the stock firmware, any ambiguity
means a stop, not "let's try and see". This applies especially before NAND erase
and BL2 write.

---

## Stock NAND layout

The wizard works against the fixed stock layout of the XG-040G-MD
(`FIXED_EXPECTED` in `master.py`). Key partitions:

```text
mtd0   bootloader   0x00080000   (BL2 + U-Boot + env)
mtd14  nsb_master   0x02880000   ← the transition image goes here
mtd16  all_flash    0x0EBA0000   full NAND image (backup/restore basis)
```

Inside `mtd0`: BL2 in the first `0x20000`, U-Boot environment at offset
`0x1C000` within erase-block `0x60000`, payload size `0x4000`.

**Two accepted slot layouts.** Stock partitions `mtd2`..`mtd5` exist in two
mirrored arrangements (A/B); which one is active depends on the slot the device
last booted from. `SLOT_LAYOUTS` in `master.py` holds both, and the layout check
accepts either:

```text
layout A   mtd2=0x003AF6DA  mtd3=0x01CC0000  mtd4=0x00480000  mtd5=0x02400000
layout B   mtd2=0x00480000  mtd3=0x02400000  mtd4=0x003AF6DA  mtd5=0x01CC0000
```

The sizes of all other partitions (`FIXED_EXPECTED`) are fixed and matched
exactly: any mismatch stops the run.

---

## Full install cycle

```text
┌─────────────┐   Telnet    ┌──────────────┐
│     PC      │────────────▶│ stock Nokia  │
│  master.py  │   backup    │ (stock FW)   │
└─────────────┘◀────────────└──────────────┘
      │ 1. backup mtd0..mtd16 → verify
      │ 2. env_patcher: patch bootcmd in mtd0 env
      │ 3. write transition to mtd14 + patched env to mtd0
      ▼
┌──────────────────────────────────────────┐
│ reboot → stock U-Boot reads mtd14,        │
│ loads transition OpenWrt initramfs to RAM │
└──────────────────────────────────────────┘
      │ 4. initramfs formats NAND as UBI
      │    and installs permanent OpenWrt (sysupgrade)
      ▼
┌──────────────────────────────────────────┐
│ permanent all-in-UBI OpenWrt with LuCI    │
└──────────────────────────────────────────┘
```

---

## Key insight: patching bootcmd instead of replacing the bootloader

This is the core of the no-UART path. A normal OpenWrt install on this hardware
requires serial-port access to U-Boot. We avoid it like this:

**Step 1 — extract env from the backup.** After taking a backup, `env_patcher.py`
pulls the stock U-Boot environment out of the `mtd0` dump (erase-block `0x60000`,
payload at `0x1C000`, size `0x4000`). It **preserves every byte** outside the
payload and **every variable**, changing exactly one — `bootcmd`:

```text
flash read 0xc0000 0x800000 0x92000000; bootm 0x92000000
```

This command tells the stock U-Boot to read the transition image from NAND (at
the physical offset where it will land after being written to `mtd14`) into RAM
at `0x92000000` and boot it as a FIT. `env_patcher` then recomputes the **CRC32**
of the environment (otherwise U-Boot rejects it) and emits a clean `0x20000`-byte
image.

**Step 2 — write.** The wizard writes the transition image to `mtd14` and the
patched env to `mtd0` **last**, with a read-back verify. The U-Boot binary itself
is untouched — only its autoboot command changes.

**Step 3 — reboot.** The stock U-Boot executes the new `bootcmd`, loads the
transition OpenWrt from NAND into RAM. No UART is involved — all the logic is
already in the env.

Why this is safe: the env is device-specific (unique MACs, serial data), so the
personal package cannot be moved to another router. Since the bootloader is not
replaced, a failure leaves the device normally bootable right up to the NAND
format step.

---

## Key insight: transition image with an embedded snapshot

`transition-bundle.bin` is not just an initramfs. It is a FIT image of an OpenWrt
initramfs with a **full production sysupgrade** (OpenWrt SNAPSHOT with LuCI)
**embedded inside**. The point: once the transition system is up in RAM, it needs
nothing from the network — the permanent-system image is already there.

What the transition initramfs does automatically (stage 2), with no manual
commands:

1. brings up networking and SSH;
2. checks the board, MTD layout, NAND geometry and type;
3. verifies the embedded BL2, FIP, and sysupgrade by SHA256;
4. **formats NAND from `0x20000` to the end as UBI**;
5. creates UBI volumes: `ubootenv`, `ubootenv2`, `bosa`, `ri`, `fip`, `fit`;
6. writes `bosa` and `ri` (from backup), Ethernet-fixed FIP, return FIT;
7. verifies everything by read-back;
8. writes the full **BL2 last** (with preloader, offset `0x800`);
9. runs `sysupgrade -v -n` on the embedded image (`-n` keeps the temporary
   config out of the permanent one).

BL2 is written last on purpose: up to that point the device is recoverable by
retrying, because the old bootloader is still intact.

Exact versions of the embedded image (profile, target, SNAPSHOT revision, kernel,
SHA256, offset in the bundle) are in [IMAGE_STATUS_EN.md](IMAGE_STATUS_EN.md).

---

## Key insight: manual mode for experts

Alongside `transition-bundle.bin` there is `transition-manual-bundle.bin` — the
same transition initramfs but **without an embedded sysupgrade** and without an
automatic stage 2. It is for users who want to install **their own** image rather
than the SNAPSHOT that is baked into the main bundle.

Expert flow:

1. the wizard writes the manual transition to `mtd14`; the router boots into it;
2. instead of auto-installing, the wizard asks for **your own `.itb`** on the PC;
3. the file is sent to RAM over TFTP;
4. before any write: FIT magic, size, SHA256, `nokia-ubi-installer check`, and
   `sysupgrade -T` are all checked;
5. NAND formatting starts **only after a second confirmation**.

This gives the expert full control over which system is installed while keeping
the same safety checks as the automatic path.

---

## Transfer transports

### Backup (router → PC)

The NAND image (~250 MB) is dumped on the device via `dd | gzip` and sent by one
of the following methods, which the user picks based on what services are
available:

| Transport | How it works |
|---|---|
| **USB drive only** | the backup agent writes dumps directly to the mounted drive on the router; the PC barely participates |
| **USB + Samba** | the drive is mounted and the PC pulls the finished dumps over SMB |
| **USB + FTP** | the same over FTP (USB chroot path is accounted for) |
| **Direct TFTP** | no drive needed: `dd | gzip` streams straight to the PC over TFTP (UDP/1069 by default; the port is prompted) |

The TFTP path reuses one healthy root Telnet session and reconnects only after a
failure.

### Install package (PC → router)

The wizard assembles a package (transition image, patched env, `INSTALL.sh`,
agent, `SHA256SUMS`) and delivers it to the device:

- **Samba/FTP** — by uploading files to a share visible to the router;
- **direct** — `send_file_to_router` over TFTP/nc into `/tmp`.

On the device, `INSTALL.sh` checks `SHA256SUMS` and runs preflight, then flash.

### Stock restore (PC → router)

During rollback, image blocks are sent in the order **TFTP → SCP → TCP/nc** (the
next transport is tried if the previous one is unavailable). After every written
partition, a SHA256 read-back check is performed. The SCP receiver in the recovery
image is restricted: it accepts only `scp -t` and only into `/tmp`.

---

## RAM worker: surviving the erasure of your own rootfs

The stage-2 problem: NAND formatting erases the partition the installer is running
from. The solution is the RAM worker: the critical part of the installer is copied
to tmpfs and launched from there, so it keeps running after the original rootfs is
gone. The wizard tracks it by the `__NOKIA_RAM_WORKER_STARTED__` marker in the
output.

---

## Model detection and brick guard

The XG-040G-MD (AN7581) and the closely related XG-040G-MF (AN7583) have
**byte-identical stock NAND layouts** and the same `/proc/cpuinfo` (Cortex-A53).
A `/proc/mtd` check cannot tell them apart. The only reliable signal is the chip
from the web UI's `device_status.cgi`: `AN7581` vs `AN7583`.

That is why in automatic mode (choice **1**) the wizard reads the model through
the web UI (`StockSetup.require_model`) **before the first write** and stops hard
on an MF, without falling back to manual entry — otherwise the check could be
bypassed. Installing the MD image on an MF would produce a brick recoverable only
via UART. The MF cannot be handled without UART at all — network root is closed
there; details are in the project history.

The guarantee is not the same for every access choice. The exact policy in code
(`ask_credentials`, field `AccessProfile.model_gate_policy`):

| Choice | What the wizard does about the model check |
|---|---|
| **1** — automatic setup | Strict gate via `device_status.cgi`. AN7583 → hard stop before any write |
| **2** — configure Telnet manually | `model_gate_policy = "best-effort"`: the web UI is unavailable, so a UID-0 Telnet probe is used instead. An explicit AN/EN7583 is rejected, AN/EN7581 is accepted, and **inconclusive output is allowed through after one warning** |
| **3** — use Telnet already enabled | Same as choice 2 |
| **4** — custom OpenWrt image (expert) | The model is **not checked at all**. A `[DANGER]` notice is printed and an explicit `y/N` is required. The only remaining guard is that NAND is not formatted until the selected sysupgrade has been validated |

In short: the strict chipset check exists only on choice 1. Choices 2 and 3 give
a weakened check, and choice 4 gives none — it relies on informed operator
confirmation.

---

## Brick recovery over UART

The last resort: U-Boot no longer boots and the BootROM repeats `C` over UART,
waiting for the next boot stage over XMODEM. Sequence:

```text
BootROM C → XMODEM preloader → RAM
          → XMODEM BL31+U-Boot FIP → RAM
U-Boot from RAM (wizard captures the AN7581> prompt)
          → TFTP each 8-MiB IBU block from backup
          → mtd write → mtd read → hash sha256 (per block)
          → BL2 last + verify
          → reset → stock boot
```

The temporary components (preloader, FIP) run from RAM only and are never written
to NAND. U-Boot capture is strict: after XMODEM FIP confirmation the wizard sends
`Ctrl-C`, exits the bootmenu via `ESC`, and waits for a stable `AN7581>` prompt —
Enter is not sent because it would select "run default boot".

---

## Secrets handling

The web-UI password is never written to `LATEST.log`, `state.json`, or the
command line. It can be passed once via `NOKIA_WEB_PASSWORD` (the wizard removes
the variable from its environment after reading). Telnet/FTP passwords read from
the web UI stay in process memory only. Login uses AES/RSA encryption; the
plaintext form requires `NOKIA_ALLOW_PLAIN_WEB_LOGIN=1` with a warning (the RSA
key is fetched over plain HTTP, which does not protect against an active MITM).

**Echo during entry is on by design.** Contrary to the usual convention, the
password is **visible on screen** by default: `_localized_getpass` calls plain
`input()` rather than `getpass`. This is a deliberate trade-off for
non-technical users, who otherwise assume the program has frozen because typing
shows nothing. Hidden entry is enabled with `NOKIA_HIDE_PASSWORDS=1`. Terminal
echo is not produced by Python, so it is never copied into session logs.

**Log filtering and its boundary.** Known secrets are registered through
`_register_log_secret()` and replaced with `[REDACTED]` in `_ConsoleTee`. A
by-design limit: values **shorter than 4 characters are not filtered**, because
a global substitution of such a value would destroy ordinary diagnostics. Nokia
label passwords are materially longer, so the filter is effective in practice,
but a short user-chosen password will not be masked in the log.

---

## Kit integrity: `verify_kit()`

Before doing anything the wizard validates its own kit and **refuses to start**
on any mismatch. This is not a formality: the check couples Python and shell.

1. presence of every required file (`transition-bundle.bin`,
   `transition-manual-bundle.bin`, launcher template, backup agent,
   `stock_web.py`, `env_patcher.py`, recovery preloader/FIP/initramfs);
2. exact size and SHA256 of both transition bundles;
3. SHA256 of all three recovery artifacts;
4. **cross-check of the metadata inside `stock-launcher.sh.in` against the real
   bundle** — `BUNDLE_SIZE`, `BUNDLE_SHA`, `TRANSITION_TOTALSIZE`,
   `TRANSITION_FIT_SHA`, `TRANSITION_WINDOW_SHA`, `SYSUPGRADE_SIZE`,
   `SYSUPGRADE_SHA`.

Item 4 matters to anyone editing the code: the values are located with the regex
`^KEY=(.+)$` and compared as strings, **including the single quotes**. Any
reformatting of the launcher, quote normalisation by an auto-formatter, or line
reordering breaks wizard startup entirely. A separate trap: the comparison calls
`.strip()`, so a trailing `\r` from CRLF is **not caught by this check** — line
endings are the job of `.gitattributes`, not `verify_kit()`.

In parallel, `data/SHA256SUMS` covers the whole shipped kit and must be
regenerated whenever any covered file changes.

---

## Telnet sessions and the root gate

Telnet is implemented in-tree (`class Telnet` in `master.py`) rather than via
`telnetlib`, which has been removed from the Python standard library. Connection
policy:

- up to **3 independent root sessions**, each with up to **3 fresh TCP login
  attempts**;
- a mandatory gate: `id -u` must return `0`, otherwise the session is rejected;
- root escalation through `su` with UID-0 account discovery
  (`_read_uid0_accounts`, `_ordered_uid0_candidates`);
- every command sent to the device is escaped with `shlex.quote()`; `subprocess`
  is always invoked with an argument list, and `shell=True` appears nowhere.

On the TFTP path a single healthy session is reused across partitions;
reconnection happens only after a timeout, a socket/Telnet error, or a missing
completion marker.

---

## Output, localisation and logging

A non-obvious architectural decision worth understanding before editing the
code: `master.py` **rebinds `print`, `input` and `getpass.getpass` at module
level**:

```python
print = _localized_print
input = _localized_input
getpass.getpass = _localized_getpass
```

This is deliberate and fail-closed: localisation and colouring **cannot be
forgotten**, because all output passes through them. Replacing this with
explicit wrappers would make the mechanism bypassable — a forgotten `print()`
would silently escape localisation.

Consequences that are easy to trip over:

- the rebind applies **only to `master.py` globals**. Moving code into a separate
  package module restores the builtin `print` there, and localisation breaks
  silently, with no error;
- `tr()` calls `ensure_language()`, which **prompts the user on stdin** when no
  language is set. So `tr()` is not a pure function. Evaluating it in
  module-level constants or from a worker thread produces an interactive prompt
  at import time or a race for stdin;
- for the same reason non-interactive runs need `NOKIA_LANG`:
  `python3 data/master.py --help` without it asks for a language before argparse
  and dies on EOF;
- English text comes from two sources: explicit `tr(ru, en)` calls and the
  `_RU_EN` substitution catalogue applied to exception messages via
  `Error.__str__`. At the time of writing roughly **82 of 205** `raise` sites
  rely on the catalogue. It can only be removed once all of them are translated
  explicitly — otherwise English disappears precisely on failure paths, silently.

All console output is mirrored into `work/logs/LATEST.log` through
`_ConsoleTee`, with ANSI sequences stripped and registered secrets replaced by
`[REDACTED]`.

---

## Module map

```text
START.cmd / START.sh                 entry point: install (CRLF / LF)
RESTORE_STOCK.cmd / RESTORE_STOCK.sh entry point: roll back to stock
VERSION                              kit version (must match data/VERSION)

data/master.py                       full wizard, state machine, transports (~6.5k lines)
data/stock_web.py                    web-UI client: AES/RSA login, services, model gate
data/env_patcher.py                  bootcmd patch in U-Boot env with CRC32 recompute
data/backup-agent.sh                 on-device backup agent
data/nokia-stock-tftp-backup-safe.sh stock backup over TFTP (safe variant)
data/stock-launcher.sh.in            on-device stage 1/2 (INSTALL.sh template)
data/MANIFEST.json                   release description: sizes, SHA256, bootcmd, policies
data/SHA256SUMS                      checksums for the entire shipped kit
data/VERSION                         version behind APP_VERSION and BUILD_TAG

data/transition-bundle.bin           transition initramfs + embedded SNAPSHOT
data/transition-manual-bundle.bin    transition without sysupgrade (expert mode)
data/recovery/                       preloader, FIP, recovery FIT
data/recovery/recovery-clients-source/    nokia-tftp / nokia-scp sources (C, aarch64)
data/recovery/manual-transition-source/   manual-transition bundle build
data/recovery/alternate-cbacd7ae4231/     alternate preloader/FIP revision

docs/                                README, CHANGELOG, IMAGE_STATUS, this document
```

Anything listed above and covered by `data/SHA256SUMS` requires the checksums to
be regenerated when changed. Line endings are pinned in `.gitattributes`: `.cmd`
is CRLF, everything else is LF.
