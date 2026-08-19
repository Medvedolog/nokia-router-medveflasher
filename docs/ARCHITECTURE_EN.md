# Nokia Router MedveFlasher — Architecture

Technical deep-dive for developers and the curious: how the install works, what
carries each piece of data, and what makes the no-UART path tick. Users don't
need this — the [guide](INSTRUCTION_EN.md) is enough to install.

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

For the install path, the wizard keeps the fixed stock layout of the XG-040G-MD
(`FIXED_EXPECTED` in `master.py`). Key partitions:

```text
mtd0   bootloader   0x00080000   (BL2 + U-Boot + env)
mtd14  nsb_master   0x02880000   ← the transition image goes here
mtd16  all_flash    0x0EBA0000   stock restore span (backup/restore basis; not full physical NAND)
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

The XG-040G-MD (AN7581) and the closely related XG-040G-MF (AN7583) share the
same **coarse physical stock `all_flash` map**: bootloader/romfile, both NSB
regions, BOSA, RI, flags, config, data, oopsfs and log use the same physical
boundaries, and `mtd16` is `0x0EBA0000`. However, vendor `mtd2..mtd5`
(`kernel/rootfs` A/B) sizes are **not a byte-identical invariant**; they can vary
between MD and MF/stock releases. Therefore the install path does not infer the
model from `/proc/mtd`; the reliable gate remains the chipset reported by the
web UI's `device_status.cgi`: `AN7581` vs `AN7583`.

That is why in automatic mode (choice **1**) the wizard reads the model through
the web UI (`StockSetup.require_model`) **before the first write** and stops hard
on an MF, without falling back to manual entry — otherwise the check could be
bypassed. Installing the MD image on an MF remains blocked. rc9 supports **UART brick recovery** for MF from the operator's own complete stock backup plus a separate read-only BootROM backup; normal no-UART installation remains MD-only.

The guarantee is not the same for every access choice. The exact policy in code
(`ask_credentials`, field `AccessProfile.model_gate_policy`):

| Choice | What the wizard does about the model check |
|---|---|
| **1** — automatic setup | Strict gate via `device_status.cgi`. AN7583 → hard stop before any write |
| **2** — configure Telnet manually | `model_gate_policy = "best-effort"`: the web UI is unavailable, so a UID-0 Telnet probe is used instead. An explicit AN/EN7583 is rejected, AN/EN7581 is accepted, and **inconclusive output is allowed through after one warning** |
| **3** — use Telnet already enabled | Same as choice 2 |

In short: the strict Web chipset check exists on choice 1. Choices 2 and 3 use a weakened Telnet check. Selecting a custom sysupgrade no longer changes the model-gate policy and is handled separately before access-method selection.

---

## Brick recovery over UART

The last resort: U-Boot no longer boots and the BootROM repeats `C` over UART,
waiting for the next boot stage over XMODEM. Sequence:

```text
BootROM C → XMODEM SoC-specific preloader → RAM
          → XMODEM SoC-specific BL31+U-Boot FIP → RAM
U-Boot from RAM (AN7581> / AN7583> / U-Boot> / =>)
          → TFTP each 8-MiB IBU block from backup
          → PC SHA256 pin + RAM crc32
          → mtd write → mtd read → crc32 (per block)
          → BL2 from the selected backup last + CRC32 verify
          → reset → stock boot
```

The temporary components (preloader, FIP) run from RAM only and are never written
to NAND. MD uses the established AN7581/Nokia recovery artifacts. MF uses hardware-tested AN7583 RAM preloader/FIP stages bundled in the full rollup; they are verified locally before BootROM with no runtime download. Real MF hardware has confirmed BootROM → AN7583 preloader → BL31/U-Boot → `U-Boot>`, scripted `mtd list`, network `setenv`, and the first 8-MiB TFTP load. That U-Boot does not provide `hash sha256`, so rc9 verifies post-TFTP RAM and readback with `crc32` while source files on the PC remain SHA256-pinned. If RAM U-Boot is not captured or geometry does not match, NAND remains untouched.

U-Boot capture is strict: Ctrl-C is sent only after the U-Boot banner/menu appears, not periodically throughout initialization. After the first stable `AN7581>`, `AN7583>`, hardware-observed MF `U-Boot>`, or standard `=>` prompt, the wizard requires UART quiet so delayed break characters cannot corrupt the first command. Enter is never sent. The command and its `$?` status query are separate CR-terminated lines; a chained `; echo marker` line is not used. Before the first write, automatic `mtd list` must report `bl2=0x20000`, `ubi=0x0FFE0000`, and erase block `0x20000`. In rc8fix2 those values and the scripted command path were hardware-confirmed on MF; network `setenv` and the first 8-MiB TFTP load were confirmed as well.

---

## Read-only backup through BootROM/UART

RC9 reuses the same safe bootstrap but issues **no NAND write commands** after RAM U-Boot is captured. In rc9fix there is no operator `input()` after UART opens: monitoring begins immediately, `Press x`/`C` are detected automatically, and the first RX buffer is intentionally not flushed. Stale ACK/`C` cleanup is retained only before the following XMODEM stage. After an exact `mtd list` gate, a model-specific recovery FIT is loaded by TFTP into RAM and started with `bootm`. Recovery must confirm UID 0, the expected `board_name`, `all_flash=0x10000000`, and the presence of `dd`, `gzip`, `tftp`, and `sha256sum`.

```text
BootROM → XMODEM preloader/FIP → RAM U-Boot
        → mtd list (read-only gate)
        → TFTP recovery FIT → RAM Linux
        → dd /dev/mtd0 in chunks ≤ 8 MiB
        → gzip | TFTP PUT → PC
        → second dd | sha256sum → compare with PC
        → synthesize mtd16 and compatible mtd0..mtd16 set on PC
```

Only the stock range `0x00000000..0x0EBA0000` is captured even though physical NAND is 256 MiB. The result therefore feeds the existing restore pipeline directly. Every chunk has a `.raw.sha256` sidecar and previously verified chunks can be retained after an interrupted run. `mtd2..mtd5` are overlapping vendor views inside `mtd14/mtd15`; because a BootROM capture has no stock `/proc/mtd`, the wizard normalizes them to accepted layout A. The authoritative raw data remain `mtd14`, `mtd15`, and canonical `mtd16`.

The backup dispatcher contains no `erase/write/saveenv/sysupgrade`; recovery runs from RAM only. PC-side synthesis and `verify_stock_restore_backup()` were validated with the real MF `mtd16`; end-to-end hardware capture is a new rc9 path.

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

1. presence of `VERSION`, `data/VERSION`, `MANIFEST.json`, and all required payloads/scripts; both version files and MANIFEST `version/build_tag` must match the code;
2. presence of the MD recovery preloader/FIP/initramfs, `recovery/mf/OPENWRT_SNAPSHOT.json`, and the bundled MF stock-recovery FIT;
3. exact size and SHA256 of both transition bundles;
4. SHA256 of all three bundled MD recovery artifacts and the bundled MF stock-recovery FIT, plus exact size/SHA256 checks of both bundled AN7583 EVB RAM stages and an exact match between MF snapshot provenance metadata and the names/sizes/SHA256 pins compiled into the wizard;
5. **cross-check of the metadata inside `stock-launcher.sh.in` against the real
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
data/recovery/                       MD preloader, FIP, recovery FIT
data/recovery/mf/OPENWRT_SNAPSHOT.json pinned AN7583 snapshot provenance; the release-pinned EVB preloader/FIP are mandatory bundled payloads beside it; the recovery flow is hardware-confirmed while refreshed exact bytes are tracked separately and are verified locally by exact size/SHA256; runtime download/cache is forbidden
data/recovery/recovery-clients-source/    nokia-tftp / nokia-scp sources (C, aarch64)
data/recovery/manual-transition-source/   manual-transition bundle build

docs/                                README, CHANGELOG, IMAGE_STATUS, this document
```

Anything listed above and covered by `data/SHA256SUMS` requires the checksums to
be regenerated when changed. Line endings are pinned in `.gitattributes`: `.cmd`
is CRLF, everything else is LF.

---

# Appendix. Per-release contracts and invariants

Below is a traceability record: which release introduced which architectural contract, and why. This is not the user-facing change history — that lives in [CHANGELOG.md](CHANGELOG.md). Sections are grouped by release and do not form a strict chronological order.

## 1.0.0-rc31 — a rescue path is defined by where it puts you, not by whether it answers

**Answering is half the contract.** RC30 established that the board asking U-Boot's TFTP loop must be answered, and that was the hard half. It then answered with the stock rollback initramfs — an image that boots the same board correctly and cannot do the one thing the situation calls for. The board was alive, reachable, and in a system with no path forward. A recovery mechanism has to be judged by the state it leaves the operator in, not by whether the transfer succeeded.

**The situation already names the right image.** A board only reaches that loop with BL2 and the FIP in place, which means the migration ran and the only unfinished work is the production write. Exactly one image in the kit can do that work, and the kit already knew it: the same transition FIT is what the installer writes into the `fit` volume as the post-migration fallback, and the installer carries an explicit non-destructive branch for a device whose UBI headers already exist. The answer was in the codebase, in the failure path's own design, and the new code served something else — the same shape of mistake as the readiness loop in RC29, where a fact had already been reasoned about correctly in one place and not carried to its other reader.

**Offer the destructive alternative, never assume it.** Going back to stock and going forward to OpenWrt are opposite intents that share a transport. Making the forward path the default and the rollback an explicit flag matches which one an interrupted install actually needs, and keeps the operator from being quietly moved onto the wrong one.

## 1.0.0-rc30 — an operation that deletes its only fallback must be covered before it starts

**The dangerous window belongs to someone else's code.** The install's own steps are ordered so that BL2 goes last and every earlier failure is retryable. Then the production sysupgrade begins, `ubus call system sysupgrade` hands the work to procd, and OpenWrt's `nand_upgrade_prepare_ubi` removes the `fit` volume before recreating it. For the duration of that write the board holds no bootable image — and none of it is our code, our log, or our timing. Auditing our own sequence for a point of no return was not enough: the real one lived in the code we hand off to, and we neither instrumented it nor covered it.

**Cover the window instead of narrating it.** The installed U-Boot never abandons a board that cannot boot; `boot_tftp_forever` asks for a recovery image once a second, indefinitely. That is a complete recovery path that costs nothing to use and that this kit knew about — the filename constant, the image and a TFTP server were all already in the code — yet the wait stage answered none of it. Standing the server up for the whole watch converts the worst outcome of the install from a bricked-looking board into a self-healing one. It is started before the destructive phase can fail and released on every exit path, because the port it holds is needed later by the restore; and it never gates the install, because a net that can refuse to let you work is not a net.

**Observability has to end after the failure, not before it.** The session log went silent exactly one line before the only interesting part, so "hung" and "failed instantly" were indistinguishable, and the two plausible causes — memory exhaustion and a NAND-level write failure — could not be separated after the fact. Evidence is now taken while the device can still answer: a calm baseline, and a best-effort snapshot as the sysupgrade starts. Both are strictly read-only, both go to the session log rather than the console, and losing the race on the second one costs nothing.

**Advice must be actionable by the operator it is written for.** The old guidance permitted a power cycle only on proof of an exact UART line, in a tool whose entire premise is that there is no UART, and then offered that power cycle at four minutes — inside the half-written window. Guidance that cannot be followed is not caution; it is an invitation to guess. The wizard now states the expected duration early and proposes nothing, and later explains what is actually happening and answers according to whether the rescue net is up.

## 1.0.0-rc29 — a detector may not be the thing that blocks

**A gate and a readiness check are not the same question, and must not share an answer by accident.** RC27 established that the UBI partition size is evidence, not authorization: nothing in the no-UART restore depends on it, so `_all_in_ubi_shape()` checks exactly what the hardware and the boot contract fix — the 256 MiB `all_flash` chip, the `0x20000` `bl2` block, the `0x20000` erase size — and records the rest. That reasoning was applied to the restore gate and not to `wait_for_stable_openwrt`, which kept comparing whole `/proc/mtd` lines literally. The result was a system that passed the gate and then failed the readiness loop for the same reason the gate had stopped caring about. Both now call the one classifier. When a fact is demoted from authorization to evidence, every reader of that fact has to be found, not just the one that motivated the change.

**Determinism is a property of the detector, not of the program.** A probe must succeed or fail; it may not wait invisibly for a human. That is why both probe modes run under `BatchMode=yes` with `/dev/null` on stdin, and it stays true. But "never interactive" was applied one step too far: the first contact with an installed OpenWrt is not a poll, it is a conversation with an operator who is sitting there, and a production system may legitimately have a root password. Refusing to ask converted a solvable situation into a timeout — and worse, into a timeout whose message described the network. The rule is therefore stated by position rather than by mechanism: exactly one call site, the operator-facing detection, may fall back to a single interactive attempt; it may do so only when the probe reached SSH and only authentication was refused, and only when a real console is attached. Every polling loop remains what it was.

**One authentication, then determinism again.** ssh reads a password from the terminal and cannot be told to remember it, so making a polling loop interactive does not cost one prompt — it costs one prompt per iteration. Rather than spread the interaction, the single login carries its own solution: it installs a throwaway key into `/etc/dropbear/authorized_keys` in the same connection, and every later probe and transfer is an ordinary batch call. The key is per-run, temporary on the PC, absent from the session log, and destroyed on the device by the restore itself. Registering it is a claim; a batch probe through it is the proof, and a key that does not verify is dropped rather than assumed. Recognition is still not authorization — the restore's authority continues to rest on the verified environment write, the content-revalidated backup, and the geometry the recovery system pins for itself.

## 1.0.0-rc28 — RAM worker autonomy, including its voice

**The invariant, stated plainly.** `mtd3` is a view inside `mtd14`, so erasing the transition target takes the stock rootfs with it. After that first destructive operation, no executable, library, shell helper *or logging primitive* the worker still needs may come from stock NAND. The command closure already honoured this — everything went through the staged BusyBox and `mtd_debug` — but the reporting channel did not, in two ways at once.

The worker was launched with its output redirected to `/dev/null`, and the `ramlog`/`usb_log` paths it was handed were assigned and never referenced. Every stage line and every `CRITICAL FAILURE` message went nowhere. A worker that erased `mtd14` and stopped left no record of why, which is precisely the observed incident: the erase completed, nothing was written, and there was nothing to read afterwards.

Worse, the staged script started `nokia_begin_output_mirror` for `--ram-flash`. That mirror needs `tee` and `mkfifo`, both resolved through `PATH` from the rootfs about to be erased. The channel meant to report the erase was itself a casualty of it.

**The fix is removal, not repair.** A tee and a FIFO are two more things that can die between the erase and the message explaining why the erase was the last thing that happened. The worker now starts no mirror at all: its stdout and stderr are a plain open file in tmpfs, so `rlog` is a shell `printf` into an already-open descriptor — no pipeline, no helper process, no external `nohup`, and `trap '' HUP` before `exec` already survives a dropped Telnet. Anything `mtd_debug` writes to stderr is captured for free. The bundle-directory log on stock NAND is gone along with the argument that carried it, so the launch, the dispatcher and the worker agree on a nine-argument contract.

## 1.0.0-rc27 — identity, state and authorization in the restore path

**Three questions that were one.** The no-UART restore asked a single one — does `board_name` equal the exact `-ubi` string this kit installs, and does `/proc/mtd` match three lines of text — and answered "does not match" to a stage-1 transition system, an all-in-UBI system built by another tool, a third-party image, and an unreadable probe alike. They are now separate:

- *What the board is* comes from `/proc/device-tree/compatible`, primary evidence carrying both board and SoC, so MD is recognised from `airoha,an7581` even without a usable `board_name`. The `-ubi` suffix keeps a narrower meaning of its own — provenance, not hardware.
- *What it is running* is classified from the MTD shape: `recovery`, `production`, `stock-layout`, `foreign-ubi`.
- *What may proceed* is unchanged: only `recovery` and `production` built by this kit.

**Geometry that describes the operation, and geometry that does not.** A field device published `mtd2=0x0FF00000` where this kit's build publishes `0x0FFE0000` — seven eraseblocks another build leaves unused — and was refused. But restoring from a running system rewrites the U-Boot environment, verifies it by read-back, reboots and TFTPs the recovery image into RAM; the `ubi` partition is never read, erased or written, and the recovery system pins the physical target itself before flashing. The size was an identity fingerprint wearing the clothes of a safety check. `/proc/mtd` is now parsed structurally: the 256 MiB `all_flash`, the `0x20000` `bl2`, the `0x20000` erase size and the `ubi`/`ibu` name stay exact, because those are fixed by the hardware and the boot contract; the partition size becomes `[RESTORE-SHAPE]` evidence in the session log. This is the RC25 rule applied one path further — authorize on the facts that describe the operation, and record the rest.

**A fail-closed gate owes an explanation.** The probe had already collected the board name and `/proc/mtd`; the refusal reported neither, leaving an operator mid-incident to guess which half was wrong. Refusals now print what was observed against what was wanted, name the failing half, list the missing markers, and point at the path that does apply.

## 1.0.0-rc26 — console/log split

**Console contract, restated.** RC23 put an absolute timestamp on operator lines so PC output could be correlated with UART events; RC25 scoped that away from menus. RC26 finishes the thought by asking where the correlation actually happens. It happens in a file, read after the fact — not on the screen the operator is working on, where a 21-character prefix competed with the message on every single line. So the console now shows exactly what the code printed, and `_ConsoleTee` stamps the copy going to `work/logs/`. Every log line carries the clock, menu options and input prompts included, which makes the log a better record than it was before.

The consequence is that the console-side suppression machinery has nothing left to suppress: `menu_ui()`, `_MENU_RENDERING`, `_stamp_stream()` and `_timestamp_text()` are gone, along with all twenty `with menu_ui():` blocks. Their removal was verified by comparing the module's AST before and after, so only the wrappers disappeared. One invariant now replaces a rule that had to be re-applied at every new selector: the console is never stamped, the log always is — and neither can drift without a selftest failing.

Two details keep the log honest. `_write_session_only()` writes past the tee and therefore stamps itself, and `_log_prompt_newline()` resets the log column, so the line following a prompt begins a line rather than continuing one. The stamp is still a line prefix: a chunk that continues a line passes through untouched, which is what keeps a live UART mirror readable and stops a `\r` progress counter from collecting a stamp per redraw.

## 1.0.0-rc25 — symmetric write authorization / console and identity contracts

**Write-authorization contract.** The stock slot map `mtd2..mtd5` is a *classifier*, not an allowlist. It answers "which family and which vendor slot revision is this", and that answer feeds backup selection and evidence only. Permanent-write authorization is assembled from facts that describe the actual write target: a live family match, `/proc/mtd == sysfs`, exact fixed stock partitions, byte-exact stock handoff targets `mtd0/mtd14/mtd15/mtd16`, erase size `0x20000`, a complete `mtd0..mtd16` backup revalidated from content, device-specific environment, and the pinned transition bundle. After the handoff into RAM, the board-specific installer independently re-derives the physical target — `all_flash=0x10000000`, `BL2=0x20000`, `UBI/IBU=0x0FFE0000`, erase `0x20000`, write `0x800` — before `ubiformat` is reachable at all.

The consequence is symmetry: MD and MF now differ in profile, geometry, and payload bytes, not in policy. `MD_PERMANENT_WRITE_LAYOUTS`, `InstallProfile.allowed_stock_variant`, and the MF-only exact `MF-A` gate are gone, because a vendor slot revision was never evidence about the physical target it authorized. `BACKUP_HW_VALIDATED` is demoted to an evidence marker for the same reason: the installer re-reads and re-validates every selected backup instead of trusting a token.

Recognition stays fail-closed where it belongs. The canonical pair `00480000/02400000` must match byte-exact; the opposite slot is matched inside a window far narrower than half the distance between the MD and MF reference points, so a pair that lands in both families resolves to `unknown` rather than to a guess.

**Console contract.** RC23 established that operator lines carry an absolute timestamp so PC output can be correlated with UART events. RC25 scopes that to what it was for: an event. Selector text — the startup-mode menu, the main menu, all four submenus, the manual model fallback, and the post-action navigation prompt — renders inside `menu_ui()`, a context manager that suspends the prefix and always restores it, including on an exception. Everything that reports an event keeps its timestamp: operational output, `[BLOCKED]`/`[SAFETY-LATCH]` decisions, and the `[NAV]` completion lines that state when an action finished. The invariant is enforced structurally: a `selftest-safety` case parses the module and fails if any of those functions prompts for a choice or prints a numbered option outside a `menu_ui()` block.

**Advisory contract.** The LAN1 check is the codebase's first deliberately non-authoritative signal, and it is worth stating why it is not a gate. LAN1 is the only 2.5G port on either board, so a link negotiated at 2500 Mbit/s or above identifies it positively; but a gigabit PC NIC plugged into LAN1 negotiates 1000 and is indistinguishable from LAN2..LAN4. A detector with a false-negative rate that high cannot carry a block: it would refuse correct setups while still missing the mistake it exists to catch. So it warns, defaults to continuing, degrades to the existing policy reminder when the speed is unreadable, and never raises on its own — the single failure path is the operator answering "no". A selftest pins that shape so the advisory cannot quietly become a gate.

**Read-by-fact contract.** Classifying `mtd2..mtd5` is a precondition for *writing*, never for *reading*. Installation needs the family because that choice selects the firmware payload; a backup does not. A read-only capture is authorised by the fixed stock partitions, `/proc/mtd == sysfs`, the `0x20000` erase size, and the MAC recorded in `DEVICE_MAC.txt` — none of which depend on a vendor slot revision. So `_stock_live_geometry_preflight()` takes `require_slot_family`: capture and diagnostics pass `False` and proceed on whatever is there, reporting the unrecognised layout as evidence; `_install_live_gate()` keeps `True`. Refusing to copy a NAND because a slot revision drifted would deny a rollback image to precisely the operator who needs one, and the drift is expected — the field has already produced `mtd4=0x003AF742` and `0x003AF61F` against a `0x01CC0000` reference sitting exactly one eraseblock away from the tolerance edge. Widening the reference table would chase each new revision forever; the fix is to stop gating reads on it at all.

The same correction removes two leftovers from an older release, where an exact-MD table was the only thing consulted: every MF backup, including the hardware-confirmed exact MF-A, fell through to a rejection that claimed MF installation was pending a hardware gate. That blocked the no-UART stock restore for MF. `verify_backup()` now pins the observed slot sizes for either family, so the dump/`proc` cross-check stays exact while the family table stops being a gate.

**Reset paths.** On MD the Reset button reaches two distinct recovery entry points, decided by press timing relative to power-up. Pressing Reset *after* power lands in tcboot's own Web recovery — the bootloader has already initialised DDR, probed the 256 MiB SPI-NAND and raised `eth0`/`httpd`, so no UART is needed. Holding Reset *before* power arrives preempts tcboot and lands in the BootROM `Press x` prompt, which is the XMODEM path this wizard drives. The two are not variants of one procedure and must not be documented as such. On MF the tcboot network layer is unproven — AN7583 needs its own PCS, MDIO, pinctrl and switch glue — so only the BootROM path can be assumed there.

**Identity contract.** The release version is declared in eight places across code, JSON metadata, plain-text `VERSION` files, and the launcher template, because different consumers read different ones. Duplication of a value that must never disagree is only safe if disagreement is detectable, so `selftest-safety` compares all eight and fails on any mismatch. It also rejects a `fix` suffix: repository releases are whole versions, and interim `fix` iterations are folded into the release they belong to. `verify_kit()` covers the runtime half of the same idea, checking `MANIFEST.release.version/build_tag/archive_root` against the code and the six pinned payloads against their recorded sizes and SHA256 values.

## 1.0.0-rc24 — interactive navigation / safety-latch contract

The interactive `wizard` is now a persistent state machine rather than a one-shot dispatcher. After each action, an ordinary success/error resolves to a navigation state `section | main | exit`; the exception does not terminate the Python process by itself. Direct CLI subcommands stay outside this wrapper and retain machine-checkable exit codes.

Safety invariant: menu navigation is not authorization for a destructive retry. `WriteStateUnknownError` sets a process-local `SAFETY-LATCH`; while active, normal installation, no-UART restore, and destructive Stage 2 are unavailable. Read-only diagnostics/backup and full BootROM/UART recovery remain available. Only successful completion of full UART recovery clears the latch. `KeyboardInterrupt` is not caught by the interactive action wrapper.

## 1.0.0-rc23 — timestamp/backup identity contract

Operator console contract: every non-empty line and prompt passing through the shared `master.py` print/input layer receives an absolute local `[YYYY-MM-DD HH:MM:SS]` prefix. The timestamp is presentation-only and does not alter protocol markers, hashes, UART commands, or the NAND state machine. Prompts receive a log-only terminating newline so the next timestamp does not concatenate with the prompt; no extra blank line is emitted to the console.

Backup identity contract: live-stock TFTP/USB backup creates `DEVICE_MAC.txt` before the final `SHA256SUMS`. The preferred source is `/sys/class/net/eth0/address`; the fallback is the first non-loopback sysfs interface. The file contains model/family, local+UTC capture time, primary interface/MAC, and all discovered interface MACs. If a resumed TFTP directory is already bound to a different known MAC, backup fails closed to prevent cross-device mixing. Missing metadata in a legacy backup is not a compatibility failure.

## 1.0.0-rc22 — bad-block-aware physical restore contract

UART stock restore now follows the physical canonical-`mtd16` model rather than allowing U-Boot `mtd write` to compact a logical stream across bad blocks. Contract:

`RECOVERY_SAFE prompt -> exact geometry -> mtd bad bl2/ubi -> TFTP first chunk while NAND untouched -> explicit confirmation -> erase ubi -> rescan bad map -> physical good-span write/readback/CRC32 -> stable bad map -> BL2 LAST`.

Automatic skipping inside the canonical stock span is limited to physical `0x052C0000..0x0EB60000`, where the stock layout uses UBI-backed config/data/oopsfs/log_truncated. BMT semantics are not proven for raw-critical regions, so a bad block there is a capability-gate failure. No `mtd write` good span may cross a known bad eraseblock; the RAM source offset always equals the physical NAND offset within the chunk so skipping never shifts following data.

**HW qualification (RC22/RC24):** the exact bad-block restore is not validated as a complete stock restore. On real MF hardware the write/readback completed and the stock main image/kernel booted, but the `data` UBIFS failed recovery (`ubifs_recover_master_node`) and stock entered a watchdog reboot. This mapper therefore is not HW PASS; until a dedicated fix/validation it is classified as a partial hardware failure / recovery not validated.

## 1.0.0-rc21 — Stage 5 handoff contract

## RC21 Stage 6 postcondition reconciliation

The PC-side monitor never emits `[7/8]`/`[8/8]` merely because networking disappeared. After `[6/8]` the cadence temporarily increases to 350 ms. If handoff still hides the final lines, events may be reconciled only after the strict production postcondition: expected `board_name`, canonical UBI volumes, and a release marker. That postcondition means transition passed BL2-last/readback and its completion gate before production sysupgrade. Timeout without content proof never authorizes a power cycle. For a post-sysupgrade hang, manual reboot is allowed only with external UART proof of the exact `sysupgrade successful` line.

Startup Web credentials from successful auto-detection remain only in Python process RAM, are never serialized into `work/`, and remain covered by log redaction. Rich 15.0.0 is vendored under `data/vendor/rich` only for the startup banner.

## 1.0.0-rc19 — restore transport contract

RC19 separates a **pre-write transport failure** from **unknown NAND state after a write starts**. Before `mtd write`, the wizard may fail over `nokia-tftp -> TCP/nc -> SCP`. Once `mtd write` has been issued, any SSH/TCP disconnect becomes `WRITE_STATE_UNKNOWN`; a second write transport is forbidden until separate read-only re-identification.

`nokia-tftp` is a minimal AArch64 TFTP GET client inside the transient initramfs, not a server. The Python TFTP server runs on the PC. Exact pinned clients: `nokia-tftp` 7792 bytes / `2b6bbc51…`, `nokia-scp` 6072 bytes / `232a4ba7…`. They are embedded in all MD/MF auto/manual transition and stock-recovery FITs. Transient Dropbear runs with `-B`.

The stock-restore invariant remains: `IBU write -> readback SHA256 -> BL2 write LAST -> BL2 readback -> full all_flash SHA256 -> reboot`.

## 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

A U-Boot banner is not proof of control: the ordinary AN7581 RAM U-Boot uses `bootdelay=0` and can reach first-boot `ubi_format -> mtd erase ubi` before an interactive prompt is proven. RC18 ships recovery-only SAFE FIP derivatives for AN7581/AN7583, preserving BL31 byte-for-byte while patching BL33 to `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, and neutralized persistent UBI environment volume names, so NAND `ubootenv`/`ubootenv2` cannot re-enable autoboot. After a stable prompt, `master.py` requires the exact SAFE marker, `bootdelay=-1`, inert bootcmd, and a fresh nonce before any NAND write/erase/saveenv capability exists; Ctrl-C after the banner is only a secondary safety net, sent as a paced series rather than once. Linux fallback after a missed prompt is disabled fail-closed for both families, LAN1/2.5G remains prohibited for every transition/recovery process, and full stock restore keeps the existing body/IBU erase+write+readback-first, BL2-LAST invariant.

SAFE BL33 is encoded with `LZMA_FILTER_LZMA1EXT` (known uncompressed size, no EOPM) to match the source Airoha payload representation: the first published RC18 archive failed closed before COM/XMODEM under strict Windows liblzma with `Corrupt input data`, with NAND untouched. Runtime preflight no longer decodes BL33 on the PC and instead pins exact whole-FIP and compressed BL31/BL33 SHA256.

## 1.0.0-rc17fix5 — LAN1/2.5G excluded from transition/recovery

> **Network safety policy:** LAN1 / 2.5G is considered unstable and **must not be used for any transition or recovery process**. For stock→transition, manual/auto transition, live progress, RAM stock recovery, TFTP/SCP/SSH, and restore, connect the PC only to **LAN2, LAN3, or LAN4**. A link on LAN1 does not make it a supported transport path.

The build-time patcher `data/recovery/transition-network-source/patch_transition_network.py` enforces this for MD/MF auto/manual transition and stock-recovery FITs (production sysupgrade images are intentionally out of scope): initramfs `/etc/board.d/02_network` exposes only `lan2 lan3 lan4` for Nokia as an exact fixed-size, ASCII-only script (MD 767 bytes / SHA256 `10244ac2…`, MF 591 bytes / SHA256 `af0757d1…`) containing no literal `lan1`. In transition/recovery DTs the single `2500base-x` MAC is `status = "disabled"` with its `openwrt,netdev-name` and NVMEM binding removed; the primary/internal Ethernet path and switch stay active on raw `ri-stock` MAC NVMEM. MD Dark and MF Uname production OpenWrt payloads remain byte-for-byte unchanged — the exclusion is transition/recovery-only. Release QA statically confirms this for all six affected images (MD/MF auto/manual transition, MD/MF stock recovery): no OpenWrt `lan1` name/NVMEM binding, LAN2/LAN3/LAN4 present, and — for stock recovery — writable recovery BL2 with no pre-restore `linux,ubi` auto-attach.

## 1.0.0-rc17fix4 — recovery DT hardening / pre-SSH diagnostics

MF stock-recovery uses its own DT rather than the production one: `all_flash` stays read-only, `bl2` is writable only in RAM recovery, `mtd2=ibu`, and there is no pre-restore `linux,ubi` auto-attach. MD and MF stock-recovery share the same fail-closed pre-restore NVMEM topology — read-only raw `ri-stock` at `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 bytes) — with Ethernet MAC consumers bound to that raw RI provider instead of the future UBI `ri` volume. Release QA compares byte-exact DTBs across MD/MF recovery/transition/production to prove recovery != production, writable recovery BL2, no `linux,ubi` in `ibu`, raw-RI MAC NVMEM, and active Ethernet/switch DSA ports LAN2/LAN3/LAN4 for both families.

Manual READY no longer uses the approximate `/proc/net/route` fallback: the exact address comes from `/proc/net/fib_trie`, with `ip -4 addr` as fallback. Both manual initramfs images ship `uhttpd` and its init script, so the PC master can read `/www/medveflasher-manual.status` as content-based pre-SSH diagnostics — READY and custom image transfer still require SSH content identity.

## 1.0.0-rc17fix3 — persistent manual READY / reviewable DT evidence

Manual transition no longer freezes at `NETWORK_NOT_READY` after 60 seconds: a background family/LAN/SSH readiness monitor runs until READY, so the PC-side 600 s retry observes state that can actually change. The READY gate no longer depends on `netstat` — SSH LISTEN comes from `/proc/net/tcp{,6}`, LAN `192.168.1.1` from `/proc/net/fib_trie`/`/proc/net/route`, with `ip` as fallback only — and both manual initramfs images preflight-confirm `sbin/ip`, `bin/netstat`, and `bin/cat`. `/tmp/NOKIA_MANUAL_STATE` and `/www/medveflasher-manual.status` expose ASCII key/value diagnostics (`STATE`, `REASON`, board, br-lan/IP/SSH flags, `DEFERRED`). Auto transition still performs destructive work autonomously — Ethernet is required only for PC-side live progress/control-plane telemetry — and MF/MD transition DTs keep the raw `ri-stock` pre-format NVMEM policy. `fullflash` returning `rc=0` without a reboot is no longer classified as FAILED; it becomes verification-pending and awaits production verification.

## 1.0.0-rc17fix2 — transition network / Dark MD audit

MF transition Ethernet MAC NVMEM comes from read-only raw stock RI at `0x05200000+0x3e`, not the future UBI `ri` volume, for both auto and manual transitions — Ethernet during auto mode exists for PC-side live progress/control-plane telemetry, not for the autonomous destructive installer itself. The MF target `mtd2` keeps label `ubi` for compatibility with the hardware-confirmed installer while pre-format `linux,ubi` auto-attach is disabled. All MD ITBs were audited: production sysupgrade and stock recovery were already Dark 6.18.41, while auto/manual transition were rebased from the older 6.18.39 r35573 onto the same Dark 6.18.41 / r0-486b4a4 kernel and a minimized initramfs, retaining the fail-closed installer gates. Manual readiness is family-specific — the MF path carries no MD board-name hardcode.

## RC16: payload provenance and build-time recovery transform

RC16 deliberately does not force MD and MF onto one firmware build-set. MD production uses the selected Dark patched 2026-08-09 snapshot; MF production keeps the Uname UBI set. BootROM recovery stages are a third, separate payload class and are never substituted with production bootloader artifacts.

The Dark MD source initramfs cannot be used as stock recovery unchanged: its production DT marks `bl2` read-only and describes `ubi`. RC16 preserves the source kernel/rootfs byte-for-byte while rebuilding only the recovery DT: `all_flash` read-only, `bl2` writable only in RAM recovery, and `ibu` spanning `0x20000..0x10000000`. This is a build-time transform; there is no runtime repack. It retains the Dark PHY/NPU/kernel changes while preserving the proven stock-restore sequence `IBU -> readback -> BL2 LAST -> readback`.

Release integrity now binds MANIFEST not only to bundle SHA, but also to actual FIT totalsize/FIT SHA and production size/SHA for MD auto/manual and MF auto/manual. Any metadata drift causes `verify_kit()` to fail closed.

## rc10: menu and credential inventory

The main wizard now routes four areas only: flashing/recovery, backup, credentials/users, and preparation/continuation. The credential path is separate from the install model gate: it can read identity and device-specific Telnet/FTP data through the stock Web UI on MD/MF, then build an inventory from `/etc/passwd` and `/etc/group` when Telnet is available. Secrets are registered for redaction, but explicit display writes directly to the underlying console and bypasses `_ConsoleTee`, keeping them out of persistent logs. UID-0 verification uses only credential candidates already returned by the device; there is no dictionary guessing.

BootROM backup retains its read-only NAND policy. TCP/22 readiness alone is no longer treated as sufficient: the SSH command path has bounded full handshake/probe retries because Dropbear can accept TCP before its protocol/authentication layer is fully ready.


## rc10fix: resilient credential Web transport

The credential audit uses the same stdlib `StockWeb`, but the transport now tolerates embedded HTTP servers that close a connection without an HTTP response. GET/POST requests receive bounded retries, the opener is rebuilt around the same cookie jar, and `Connection: close` avoids dependence on a broken keep-alive socket. When plain compatibility is explicitly enabled, an encrypted-POST transport close no longer suppresses the separate plain-login attempt. A final Web failure is treated as an unavailable data source rather than a fatal master error: Web-derived secrets are never invented, and only an optional read-only Telnet inventory is offered when Telnet is already open.


### RC10fix2: SSH-free BootROM backup

For MD/MF read-only BootROM backup the recovery FIT is booted with `rdinit=/bin/sh`. Control uses UART and payload data uses gzip/TFTP. The wizard verifies the model, `all_flash`, BusyBox applets, and a RAM-only TFTP probe before the first NAND read. Each chunk is confirmed by a second NAND SHA256 read. UBI, Dropbear, and SSH are not started in this path.

## RC11: MF stock audit and physical-NAND/restore-span separation

`STOCK_ALL_FLASH_SIZE` is renamed to `STOCK_RESTORE_SPAN = 0x0EBA0000`. This is behavior-preserving: existing backup/restore operations still use the same byte range. A separate `PHYSICAL_NAND_SIZE = 0x10000000` is only a reference for known AN7581/AN7583 hardware; the stock audit never derives chip capacity from `mtd0`, because stock `mtd0` is the `0x00080000` bootloader partition. Actual physical capacity comes from NAND-driver/dmesg evidence, while the restore span comes from `mtd16/all_flash` and is cross-checked against `/sys/class/mtd`.

Two field-observed MF profiles and their mirrored variants are accepted:

```text
MF-A: mtd2=0x003B6CC0 mtd3=0x01D00000 mtd4=0x00480000 mtd5=0x02400000
MF-B: mtd2=0x003B6D40 mtd3=0x01D10000 mtd4=0x00480000 mtd5=0x02400000
```

The `credentials / stock audit` menu can run a diagnostic-only path: Web reads device-specific credentials, the PC drives interactive `su`, and `CAP_STOCK_ROOT=YES` is emitted only after a real `id -u = 0`. It then captures IDENTITY/USERS/SU/MTD/NAND-UBI/read-primitives/stock-upgrade inventory. Discovered upgrade files are never executed; write verbs are parsed only from explicit `AUDIT_HIT` result markers, so the audit scanner's own grep regex cannot create a false hit.

Normal/permanent MF installation remains disabled in RC11. `CAP_FULL_BACKUP=READY FOR HW ENABLEMENT` means only that root, geometry and read primitives are consistent enough for the next hardware gate.

BootROM backup also gains a runtime command firewall: each RAM-shell command actually sent over UART is checked before TX for `mtd/nand write|erase`, `saveenv`, destructive UBI verbs, `sysupgrade`, and `dd ... of=/dev/mtd*`.

For the known physical capacity `0x10000000`, the difference to restore span `0x0EBA0000` is `0x01460000` = **20.375 MiB**. RC11 does not automatically label this tail as BMT; its purpose must be established from `dmesg`/vendor behavior.


## RC12/RC12fix: startup fingerprint and normal MF backup

After language selection the wizard performs a best-effort read-only fingerprint through the stock Web UI (`ModelName`/chipset). A successful result is marked `VERIFIED`; manual MD/MF fallback is only an `UNVERIFIED` UI profile. No backup/write backend trusts that selection: the model is re-proven from Web evidence and live MTD geometry.

Normal MF backup is an additive backend and does not refactor the hardware-confirmed MD install path. Gate: Web family MF -> Telnet -> `id -u == 0` -> known MF-A/MF-B slot layout -> exact fixed partitions -> `/proc/mtd == sysfs` -> readable `/dev/mtd0ro..mtd16ro`. Data is read only from `*ro` nodes and sent by gzip/TFTP PUT. In rc12fix, canonical `mtd16` uses one gzip stream split by `tee`: one branch goes to TFTP and the other through a FIFO to `sha256sum`; the router stream SHA256 must equal the received PC `.gz` SHA256. A second full live-NAND read is not a gate because mutable stock partitions can change between reads. Resume trusts only a locally valid gzip with exact raw size and retained transport-stream SHA256. The final directory is accepted only by `verify_stock_restore_backup()`.

MF `CAP_PERMANENT_INSTALL` remains closed. RC12 extends the read-only upgrade inventory with metadata/strings/text capture to reconstruct vendor upgrade semantics without executing discovered utilities.


## RC13: firmware capability gates

The live rc12fix MF-A capture is now closed end-to-end: Web -> Telnet -> `UID 0` -> MF-A `/proc/sysfs` -> `/dev/mtd*ro` -> TFTP for all 17 MTD devices -> SHA256 of the **same gzip stream** on the Nokia and PC -> `verify_stock_restore_backup()` -> `BACKUP_HW_VALIDATED`. The release-level normal MF-A backup status is therefore promoted to `CAP_FULL_BACKUP=YES - HW CONFIRMED`. MF-B/mirror variants remain live-gated and still need their own end-to-end capture before receiving HW-CONFIRMED status.

rc13 introduces two capability layers. `data/FIRMWARE_CAPABILITIES.json` stores release-level hardware evidence, while `firmware_capabilities_wizard()` intersects it with current read-only device facts: Web family, Telnet, `id -u == 0`, known slot variant, and `/proc/mtd == sysfs`. A capability report is not write authorization: destructive functions retain their own fail-closed preflight and explicit confirmations.

MF write capabilities are deliberately separated:

```text
CAP_RAM_OPENWRT          PARTIAL
CAP_UBI_FORMAT           BLOCKED
CAP_UBI_VOLUME_WRITE     BLOCKED
CAP_BOOTLOADER_REPLACE   BLOCKED
CAP_PERMANENT_INSTALL    BLOCKED
CAP_UART_RECOVERY        YES - HW CONFIRMED
```

`PARTIAL` for `CAP_RAM_OPENWRT` means BootROM/RAM recovery is proven, while the normal-install transition as part of permanent MF installation is not yet a confirmed write-path gate. rc13 adds no MF `ubiformat`, `ubi write`, or bootloader-replacement path. If startup Web has already verified an MF, MD-only install entries are blocked in the UI before entering the old MD wizard; this is an additional guard, not a replacement for internal MD model/backup checks.


## rc14: separate MF-A transition-to-RAM write gate

rc14 does not repurpose the MD installer as a universal backend. MF gets dedicated `MF_TRANSITION_BUNDLE`, `MF_TRANSITION_LAUNCHER_TEMPLATE`, `personalize_mf_transition()`, and `mf_transition_to_ram_wizard()` paths, leaving the proven MD flow unchanged.

The MF-A gate requires all of: startup `VERIFIED MF`, a repeated live Web MF fingerprint, Telnet → proven UID 0, `/proc/mtd == sysfs`, variant `MF-A`, a full `verify_stock_restore_backup()`, and a `BACKUP_HW_VALIDATED` marker carrying `family=mf/variant=MF-A`. MF-B and mirror variants are recognized but fail closed for writes.

The package is bound to the current source U-Boot environment erase block. The launcher rechecks the live `mtd0+0x60000` source SHA before erase. Write order is: erase/write `mtd14/nsb_master` → full readback SHA256 → recheck source env SHA → erase `mtd0` `0x60000/0x20000` → write personalized erase block → readback SHA256 → reboot. `bootflag`, `bosa`, `ri`, `data`, UBI metadata, and the bootloader body are not changed.

After reboot, the PC waits for stock services to disappear and proves RAM OpenWrt through LuCI response or an SSH identity containing `xg-040g-mf`/`AN7583`. On success it records `MF_TRANSITION_HW_VALIDATED.json`. If the network identity cannot be proven, the workflow stops and asks for a UART log; stage2 is never launched automatically. `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, and `CAP_PERMANENT_INSTALL` remain separate closed gates.

## rc14fix: permanent MF-A all-in-UBI path

MF-A uses the same two-phase model as MD. The stock-side launcher does not format UBI: it re-proves MF-A, bundle/environment SHA256, and the stock boot path, stages a minimal worker in RAM, writes the selected auto/manual bundle to `mtd14` and verifies its full readback, then rechecks the untouched source environment and writes only the `mtd0` erase block `0x60000..0x7ffff` last.

After reboot, the transition initramfs identifies `nokia,xg-040g-mf-ubi`, validates physical NAND geometry `all_flash=0x10000000`, `bl2=0x20000`, `ubi=0x0ffe0000`, and the pinned preloader/FIP/sysupgrade. Before `ubiformat`, it preserves stock `bosa` (`0x51c0000+0x40000`), `ri` (`0x5200000+0x40000`), and the current transition FIT (`0x0c0000`) from the physical view. It then creates fixed UBI volume IDs: 0 `ubootenv`, 1 `ubootenv2`, 2 `bosa`, 3 `ri`, 4 `fip` static 1 MiB, 5 `fit`. bosa/ri/FIP/fallback FIT are read back and SHA256-verified. The complete 128-KiB BL2 container (FF prefix `0x800`, preloader at offset `0x800`) is written **last** and read back. Auto mode then starts the bundled `sysupgrade`; manual mode accepts the PC-selected image only after `sysupgrade -T` and SHA256 gates.

This permanent path is enabled only for MF-A in rc14fix and remains labeled experimental until its first successful end-to-end run. Hardware-confirmed UART/BootROM full-stock restore is the rollback path.


## rc14fix2: RAM worker and operator-clean UI

MF stage 1 keeps the existing architecture and destructive gates. Only runtime bootstrap changes: the staged BusyBox executes `flash.sh` through the `sh` applet because the live MF stock BusyBox does not expose a separate `ash` applet. Verbose preflight is hidden from the operator; raw transcript is retained in the timestamped session log while `LATEST.log` mirrors only the user-facing flow.

## rc14fix3: shared MD/MF installer engine

Installation no longer has a separate MF orchestration branch. `InstallProfile` supplies family/model, auto/manual bundle, runtime names, expected UBI board, and variant/backup policy. Shared `install_openwrt_wizard(profile, from_existing_backup)` performs backup/deploy/stage1/stage2 while `personalize_transition(profile, ...)` uses one `stock-launcher.sh.in`. MF-A keeps its additional fail-closed gates. Ready transition bundles are not rebuilt at runtime. Standalone MF transition FIT/sysupgrade and production preloader/FIP files are omitted from the runtime kit because those bytes already live in the corresponding bundles/initramfs payloads.


## rc14fix4: failure-isolated UART mirroring

On stock MF, `/dev/console` is not a reliable diagnostic sink: a character device with write permission can still fail an actual write. In rc14fix3 UART was a direct output of `tee`, so `/dev/console` `EIO` could tear down the shared FIFO/log pipeline before the RAM worker started.

In rc14fix4 the primary `tee` owns only caller/session/USB logging. Optional UART receives a copy through a separate FIFO that is continuously drained by a relay process. After the first UART error the relay stops serial writes but keeps draining the FIFO, so the primary `tee`, RAM worker, and destructive state machine do not depend on the serial device. `/dev/ttyS0` is preferred over `/dev/console`. Safety gates and NAND write ordering are unchanged.


## rc14fix6: direct RAM BusyBox applet probe

The pre-write self-test no longer treats no-argument `busybox` output as a portable applet registry. Vendor BusyBox may omit the `Currently defined functions` section, so parsing that text produced a false `missing` result for the first requested name. The shared MD/MF launcher now proves `echo` and `sh` first, then invokes `busybox <applet> --help` with stdin=`/dev/null` for each applet actually needed by the detached RAM worker and treats only explicit `applet not found` as absence. This block still runs before erase/write; destructive state-machine and BL2-last ordering are unchanged.


## rc15: transition-only writable BL2 and live stage2 monitor

The MF production DT keeps `bl2` read-only as a software safety barrier. Only the auto/manual transition FIT carries a DT without `read-only` on the `bl2` partition plus the `medveflasher,transition-writable-bl2` marker. Before UBI format the installer requires both that marker and MTD_WRITEABLE; after UBI readback and immediately before BL2-last it re-proves pinned preloader/FIP/complete-BL2 provenance. Shared MD/MF `run_stage2` reads state/log through deterministic BatchMode SSH and falls back to read-only Telnet when SSH is unavailable. The monitoring channel never authorizes destructive operations.


## RC17 control-plane invariant

Transition identity is content-based (`MEDVEFLASHER_TRANSITION_PROTOCOL=1`), never inferred from an open TCP port. On-device shell protocol/log files are ASCII-only. A power-cycle may only be suggested in a previously observed pre-destructive state carrying `SAFE_TO_POWER_CYCLE=1`; after `[1/8]` or `FORMATTING_AND_FLASHING`, power removal is never recommended. Restore Stock gates are bound to the validated backup family (MD/MF).
## RC17fix: post-restore boot proof

NAND-write success and subsequent boot success are separate states. UART restore completes all readback checks first, then independently confirms execution of the U-Boot `reset`. Stock boot succeeds only after a content fingerprint of the Nokia stock login page; a TCP connect alone is transport telemetry. If reset cannot be confirmed, one manual power-cycle is permitted only after BL2 readback has completed.


### RC20: pre-destructive Telnet re-arm

After operator confirmation, the pre-existing stock Telnet session is not assumed to remain alive. The wizard performs a nonce probe, reconnects when needed, repeats the read-only preflight, and only then dispatches `--flash` once. Any channel loss after dispatch attempt becomes `STAGE1_HANDOFF_UNKNOWN`; destructive retry is forbidden. TFTP is the first recommended transport path in every operator transport menu.
