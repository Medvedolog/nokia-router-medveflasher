# Nokia Router MedveFlasher

**Version:** 1.0.0-rc31 · **Date:** 18 August 2026

**OpenWrt installation:** Nokia XG-040G-MD (AN7581) and Nokia XG-040G-MF (AN7583) — both models run the full cycle.
**Brick recovery:** XG-040G-MD/AN7581 and XG-040G-MF/AN7583.

**Default transport:** TFTP — always choice 1 in every transport menu. LAN1/2.5G is prohibited for transition/recovery: use LAN2, LAN3, or LAN4.

**Where else to look:** technical architecture — [ARCHITECTURE_EN.md](ARCHITECTURE_EN.md); hardware-confirmed status — [IMAGE_STATUS_EN.md](IMAGE_STATUS_EN.md); change history — [CHANGELOG.md](CHANGELOG.md).

> [!WARNING]
> This is a release candidate. Before flashing, take a full verified backup and keep
> it on your computer — without it there is no way back. Never cut power while
> NAND is being written.

---

## What this does

Nokia Router MedveFlasher installs OpenWrt on the Nokia XG-040G-MD and XG-040G-MF without
opening the case or requiring UART for the normal install path. MD and MF use one profile-driven installer engine; only the profile, geometry, and ready transition payloads differ. It can also take
a full image of the stock firmware, roll back to stock, and revive a bricked
device — the last one does require a USB-UART adapter.

Inside is a single Python wizard (`master.py`) that needs no third-party
libraries: an installed Python 3 is enough. No pip packages, no drivers beyond
the stock ones.

**The install has three stages:**

1. **Backup.** The wizard captures the stock restore span (`mtd16`, normally `0x0EBA0000`) plus the related vendor views and verifies them. Physical SPI-NAND capacity is a separate quantity; `mtd16` is not the entire physical NAND.
   It will not proceed without a successful backup.
2. **Transition (stage 1).** A temporary OpenWrt image is written to stock NAND
   and one bootloader variable is changed so the device boots into it.
3. **Install (stage 2).** In the normal path, temporary OpenWrt formats NAND as
   UBI and deploys the permanent system. In expert mode, the wizard first uploads
   and validates the user-selected sysupgrade.

In the normal path, `CONFIRM FORMAT AND FLASH` authorizes the destructive cycle.
In expert mode, formatting starts only after a separate second confirmation of
the already validated file.

---

## Quick start

If this is your first time, here is the short version; each step is detailed
below.

**You need:** a router on stock firmware, an Ethernet cable, a computer with
Python 3, about 1 GB of free space and around 90 minutes. USB-UART is only for
brick recovery — a normal install does not use it.

**Steps:**

1. Enable Telnet in the Nokia web UI (see [Preparing stock firmware](#preparing-the-stock-firmware)).
2. Connect the router by cable, confirm `ping 192.168.1.1`.
3. Run `START.cmd` (Windows) or `./START.sh` (Linux), pick a language. The wizard then tries to auto-detect MD/MF through the stock Web UI; manual selection is offered only on failure and is marked `UNVERIFIED`.
4. Use the install path for whichever model VERIFIED stock-Web detection confirmed. Manual/custom sysupgrade must not continue until the family/LAN/SSH READY gate passes.
5. Wait for the backup — 250 MB, 20–40 minutes. **Copy it somewhere else too.**
6. Type `CONFIRM FORMAT AND FLASH` and leave power alone until it finishes.

As long as the backup is intact, the device is recoverable. If something goes
wrong, see [If an error occurs](#if-an-error-occurs).


### Firmware capabilities

Item `6 — probe firmware capabilities (read-only)` re-proves stock Web access, Telnet, `UID 0`, family/variant, and `/proc/mtd == sysfs`, then intersects those live facts with release hardware status. The report **does not authorize NAND writes** and does not replace the pre-write gates of any operation.

Release profile for 1.0.0-rc31:

```text
                          MD / AN7581            MF / AN7583
CAP_FULL_BACKUP           YES                    YES
CAP_RAM_OPENWRT           YES                    YES
CAP_UBI_FORMAT            YES                    YES
CAP_UBI_VOLUME_WRITE      YES                    YES
CAP_BOOTLOADER_REPLACE    EXPERIMENTAL_DISABLED  YES
CAP_PERMANENT_INSTALL     YES                    YES
CAP_UART_RECOVERY         RC18_SAFE_PENDING_HW   RC18_SAFE_PENDING_HW
```

From RC25 the slot variant no longer changes capability within a family, so the table carries no `(MF-A)` qualifiers: `MF-A-MIRROR`, `MF-B`, `MF-B-MIRROR`, and recognized MD revisions follow the same install policy as the exact variant. `YES` means the family path exists under current live gates, not that a write is already authorized: a full backup, exact stock handoff targets `mtd0/mtd14/mtd15/mtd16`, and the physical NAND/UBI geometry check in the RAM transition all remain mandatory. `RC18_SAFE_PENDING_HW` means the restore path itself is hardware-confirmed while the exact RC18 SAFE FIP bytes await their first regression run.

After the startup Web fingerprint, the installation menu selects the MD or MF profile, but that never authorizes writes: live Web/root/MTD/backup gates are repeated inside the shared installer engine. MD and MF expose the same installation actions; board-specific differences live in the profile. Machine-readable release matrix: `data/FIRMWARE_CAPABILITIES.json`.

### Verifying the archive

A `…zip.sha256` file ships next to the archive. Check it before unpacking:

```powershell
# Windows
(Get-FileHash .\Nokia-Router-MedveFlasher-1.0.0-rc31.zip -Algorithm SHA256).Hash
```

```bash
# Linux — from the folder holding the archive
sha256sum -c Nokia-Router-MedveFlasher-1.0.0-rc31.zip.sha256
```

After unpacking, the checksums of every kit file can be verified from the root
of the extracted folder:

```bash
sha256sum -c data/SHA256SUMS
```

---

## Preparing the stock firmware

Before the first run you must enable Telnet on the router itself — the wizard
reaches the device through it. For the common China Mobile firmware the web UI
login is:

```text
Login:    CMCCAdmin
Password: aDm8H%MdA
```

> [!NOTE]
> This is the typical factory pair for this firmware. Carrier-modified firmware
> may use different credentials — log in with your own then. Do not factory-reset
> just to check the password: you would lose your ISP connection settings.

1. Connect the computer to the Nokia LAN port by cable.
2. Open `http://192.168.1.1/` and log in as `CMCCAdmin`.
3. Enable Telnet by opening `http://192.168.1.1/system.cgi?telnet`, then save.
4. For a USB backup, enable Samba and/or FTP in the storage section (usually
   **Home Storage**).
5. Insert a USB drive and confirm the firmware sees it.

The current version can perform these steps itself — see
[Automatic device access](#automatic-device-access). Manual enabling stays as a
fallback.

### Preparing the USB drive (for USB backup)

A USB drive is only needed for the Samba or FTP backup modes. Requirements:

- **FAT32** format (stock firmware may not mount exFAT or NTFS);
- at least 2 GB;
- no important data on it.

Once inserted it usually appears as `/mnt/USB_disc1`. Check over Telnet:

```sh
mount | grep /mnt/USB_disc1
df -h /mnt/USB_disc1
touch /mnt/USB_disc1/write-test && rm /mnt/USB_disc1/write-test
```

If the directory is missing, the write fails, or there is less than 2 GB free,
do not start the backup.

---

## Logins and passwords

Two independent credential sets are involved. They are easy to confuse, so here
they are side by side:

| What the wizard asks | What to enter |
|---|---|
| Web UI login | `CMCCAdmin` / `aDm8H%MdA` (or yours) |
| `Nokia IP [192.168.1.1]` | usually Enter |
| `Telnet user [useradmin]` | login **from the router label**; usually `useradmin` |
| Telnet password | password **from the router label** |
| `UID 0 account [auto]` | Enter — the wizard finds the root account itself |
| `UID 0 password [same]` | usually Enter — the same label password |
| Samba | `useradmin`; the wizard reuses the password obtained from the Web UI or label and connects through the native Windows WNet API without an OS password prompt |
| FTP | credentials are read from the Web UI; manual mode asks separately |
| Transition OpenWrt SSH | `root`, no password |

The key distinction: **`CMCCAdmin` / `aDm8H%MdA` is only the web UI login**, used
to enable Telnet and Samba/FTP. It is public and identical across the fleet.
**Telnet needs a separate password from the label** — that one is unique to the
device.

After the Telnet login the wizard looks for the root account (UID 0) itself. On
known firmwares it is `user_ftp` or `useradmin_ftp`, and the password usually
matches the label — so try Enter first at both UID 0 prompts.

---

## Connecting the router

1. Connect the computer to the Nokia LAN port by cable. Use **LAN2, LAN3, or
   LAN4**. LAN1 is the 2.5G port and is excluded from transition/recovery
   because the link is unstable there.
2. The router should be reachable at `192.168.1.1`, the computer on the same
   subnet (e.g. `192.168.1.2`).
3. Check connectivity:

```powershell
ping 192.168.1.1          # Windows
```

```bash
ping -c 4 192.168.1.1     # Linux
```

If the router uses a different address, give it to the wizard instead of
`192.168.1.1`.

### Port check before an operation

Before installation, backup, stock restore, UART recovery, and Stage 2
continuation, the wizard looks at the computer's link speed. A link at
2500 Mbit/s or faster can only be LAN1, because LAN2..LAN4 are gigabit ports, and
it produces a warning and a prompt:

```text
[NETWORK POLICY] WARNING: eth0 negotiated 2500 Mbit/s, which only LAN1 / 2.5G can do,
and that port is excluded from transition/recovery because the link is unstable.
[NETWORK POLICY] Move the cable to LAN2, LAN3, or LAN4 before the 'OpenWrt installation' operation.
Continue anyway? [Y/n]:
```

This is an advisory, not a block: Enter continues. The trade-off is that a
gigabit NIC in LAN1 negotiates 1000 Mbit/s and is indistinguishable from
LAN2..LAN4, so that case is not caught — check the port yourself as well. When
the speed cannot be read, the wizard just repeats the policy reminder and
continues.

---

## Running the wizard

### Windows

1. **Python.** Check `py -3 --version`. If missing, install from python.org with
   “Add Python to PATH” ticked.
2. **OpenSSH.** The system OpenSSH client is needed (to talk to the transition
   OpenWrt). The wizard checks for it and shows the install command if absent.
   `pyserial` and pip are not needed — COM handling is built in.
3. **Unpack** into a simple path without spaces, e.g. `C:\nokia\`.
4. **Run** from the kit folder: `py -3 data\master.py wizard`, or just
   `START.cmd`.

### Linux

```bash
python3 --version        # Python 3 required
./START.sh
```

Brick recovery needs UDP port 69 (TFTP from the bootloader). If a normal user
cannot open it, run `sudo ./START.sh`.

---

## Main menu

```text
=== Main menu ===
1 — flashing / installation / recovery
2 — backup
3 — credentials / users / stock audit
4 — preparation / continue installation
5 — exit
Select 1/2/3/4/5:
```

From RC26 **the screen carries no timestamps at all** — not in menus, not on
operational lines. The `[YYYY-MM-DD HH:MM:SS]` prefix is now written only into
`work/logs/`, to both `LATEST.log` and the session file. Its purpose was to line
PC output up against UART events afterwards, and that is work you do on a file,
not on the live console where the prefix took space from the message on every
single line.

To reconstruct the chronology, open `work/logs/LATEST.log`: every line is
timestamped there, menu options and input prompts included.

Submenu **1** contains stock-MD OpenWrt installation, installation from an existing backup, stock restore without UART, and BootROM/UART brick recovery for MD/MF.

Submenu **2** contains normal stock backup through a running Telnet session (USB/TFTP) and read-only BootROM backup through RAM recovery for MD/MF.

Item **3** shows the hardcoded Web default shipped by the kit, device-specific Telnet/FTP/Samba credentials read from the router, then enumerates `/etc/passwd` and `/etc/group` over Telnet with UID/GID, groups, home, shell and privilege classification. Secrets are console-only and excluded from logs.

Submenu **4** contains device-specific package preparation and an explicit continuation action: **transition OpenWrt is already running in RAM; stage 2 = verify transition → format UBI → flash sysupgrade → monitor first boot**.

---

## Automatic device access

After you enter the IP, the install flows offer:

```text
1 — Automatic setup (recommended)
2 — Configure Telnet manually
3 — Use Telnet that is already on
4 — Continue without a model check (experts only)
```

**Item 1** is preferred. The wizard logs into the web UI, **confirms the model**
via `device_status.cgi`, reads the Telnet credentials and enables Telnet (and,
if you pick Samba/FTP, that service too). The model check here is the most
reliable, so item 1 is the default.

Why the model check matters: the XG-040G-MD and XG-040G-MF share the physical
map of the major stock partitions and `all_flash`, but the vendor `kernel/rootfs`
subpartitions (`mtd2..mtd5`) can have different sizes. For **installation**, the
MD image is still allowed only on `AN7581`; `AN7583` is blocked. Starting with
rc8, MF is supported separately only by menu item 6 — **brick recovery from that
device's own stock backup**, using AN7583-specific RAM stages.

**Items 2 and 3** use a lighter Telnet-based model check before the backup
starts: an explicit `AN7583` is blocked, an explicit `AN7581` is accepted, and an
undetermined result can be accepted after a warning.

**Item 4** installs a user-selected sysupgrade in expert mode. It skips the
model check and uses direct TFTP only. A separate `transition-manual-bundle.bin`
is written; after reboot it brings up SSH and waits for the wizard to select an
`.itb` file from the PC.

The selected file is checked locally and on the router: FIT magic, size, SHA256,
`nokia-ubi-installer check`, and `sysupgrade -T`. NAND formatting starts only
after the second `Flash the selected image? [y/N]` confirmation. Model choice
and image compatibility remain the operator's responsibility; `sysupgrade -F`
is never used.

The web UI login uses an encrypted form (AES/RSA). The plaintext form is enabled
only by `NOKIA_ALLOW_PLAIN_WEB_LOGIN=1` and comes with a warning: the RSA key is
fetched over plain HTTP, which protects against passive sniffing but not against
an active MITM on the local network.

The web UI password is entered hidden, never printed, and never written to
`LATEST.log`, `state.json`, or the command line. It can be passed once via
`NOKIA_WEB_PASSWORD` — the wizard removes the variable from its own environment
after reading it. The Telnet/FTP passwords it reads stay in process memory only.

If the web UI is unreachable, the page lacks the expected fields, the login is
rejected, or a result is not confirmed, the wizard closes the web session and
offers manual Telnet with a strict check (an explicit `AN7581` is required). When
HTTP is closed entirely, the wizard asks you to check whether the router is already
in a temporary recovery/transition system and, when appropriate, continue from stage 2.

---

## Taking a backup

The backup is mandatory: it is the only way back to the original state. The
wizard offers one of several transfer methods.

### Methods

- **USB drive only.** The image is written to the drive in the router; the
  computer barely participates. Needs a prepared drive (see above).
- **USB + Samba.** The drive is mounted, the wizard connects Windows to `\\<Nokia IP>\mnt` as `useradmin` through the native WNet API, and pulls the image over Samba. The password is not placed in process arguments or an OS dialog. If the Telnet and Samba passwords differ, it asks once for the label password.
- **USB + FTP.** The same, over FTP.
- **Direct TFTP.** No drive needed: the image goes straight to the computer over
  TFTP. The simplest option if the drive is troublesome.

For **XG-040G-MF in rc12fix**, direct TFTP is the recommended hardware path. Before any read, the wizard re-proves Web/Telnet/root access, cross-checks `/proc/mtd` against sysfs, and accepts only a known MF-A/MF-B layout. Reads use `/dev/mtd*ro`. For canonical `mtd16`, the exact same gzip stream is fed to TFTP and to `sha256sum` on the Nokia through `tee`/FIFO; that SHA256 must match the received `.gz` file on the PC. Gzip integrity, exact raw size, and the complete stock-restore validator follow. A second full read of live `mtd16` is no longer a fatal gate. `BACKUP_HW_VALIDATED` is created only after transport+validator PASS.

When a backup or installation package is copied through FTP or Samba, the wizard
shows overall percentage, a `#` bar, transferred size, average speed, file count,
and the current file. Progress remains line-oriented so the session log stays clean.

### Verifying the backup

Afterwards the wizard shows the backup path. It must contain:

```text
mtd0*.bin.gz … mtd16*.bin.gz
proc_mtd.txt   dmesg_full.txt   cmdline.txt
SHA256SUMS.txt   BACKUP_COMPLETE
```

Do not proceed if the backup is not on the computer, `mtd16` or
`BACKUP_COMPLETE` is missing, there is a gzip error, partition sizes mismatch, or
the wizard reported an incomplete transfer. **Copy the backup to a second safe
place.**

`mtd16` is the canonical stock restore span used for rollback; it is not the full physical SPI-NAND capacity. The file existing proves
nothing on its own: for the stock layout the uncompressed size must be exactly
`247070720` bytes, but the source of truth is the `mtd16` line in `proc_mtd.txt`.

Verify the whole folder with the kit’s validator:

```bat
py -3 data\master.py verify-backup "D:\path\to\backup"     :: Windows
```

```bash
python3 data/master.py verify-backup /path/to/backup       # Linux
```

The validator unpacks all `mtd0–mtd16`, checks gzip, exact sizes and agreement
with `proc_mtd.txt`. Until it passes without errors, do not move on to
`CONFIRM FORMAT AND FLASH`.

---

## Personalization and writing

### What gets personalized

The wizard extracts your router’s own U-Boot environment from the backup and
changes one variable in it — `bootcmd`: the new command tells the stock
bootloader to load the transition OpenWrt straight from NAND. The bootloader
itself is not replaced at this stage.

> [!IMPORTANT]
> The personal package is tied to one device. Do not use it on another router or
> publish it together with the personal environment — it holds unique MAC
> addresses and serial data.

### The pre-flight check

Before the first write the wizard automatically verifies: the board model, the
stock `mtd0–mtd16` layout and partition sizes, the transition bundle checksums,
that the personal environment matches the current device, the presence of the
writing tools, and the NAND geometry and type.

NAND policy: a clearly identified FudanMicro FM25G02B is blocked, SkyHigh is
allowed, and a chip without an exact name is accepted if the board, MTD sizes and
geometry match — with user confirmation. NAND is not formatted until this check
passes.

### The point of no return

In the normal path one phrase authorizes the complete automatic cycle. The
wizard first reminds you that the backup is on the PC, power is stable, and the
device and NAND are compatible. Then type exactly:

```text
CONFIRM FORMAT AND FLASH
```

In expert mode the first yes/no confirmation authorizes only the manual
transition write and reboot. The selected sysupgrade is then uploaded into RAM
and validated. A separate `Flash the selected image? [y/N]` prompt starts UBI
formatting and installation of that exact file. NAND is not formatted before the
second confirmation. Once autonomous flashing starts, do not cut power.

### How writing proceeds

**Stage 1 — transition.** The wizard writes the selected transition to `mtd14`,
verifies it by read-back SHA256, writes the personal environment last, and
reboots into temporary OpenWrt in RAM.

**Normal stage 2.** `transition-bundle.bin` contains the verified production
sysupgrade. Temporary OpenWrt checks the board, NAND, BL2/FIP, and image, formats
NAND as UBI, creates and verifies the volumes, writes full BL2 **last**, and runs
`sysupgrade -v -n`.

**Expert stage 2.** `transition-manual-bundle.bin` contains no production
sysupgrade and performs no automatic formatting. The wizard waits for SSH,
selects a PC `.itb`, uploads it by TFTP into `/tmp`, verifies SHA256, runs
`nokia-ubi-installer check` and `sysupgrade -T`, and only after a second
confirmation starts autonomous `fullflash` of the selected image. A restarted
wizard can resume monitoring an already-running autonomous flash.

### Successful completion

The router boots into the permanent OpenWrt, again reachable at `192.168.1.1`,
with a clean config. Connect and set a password right away:

```bash
ssh root@192.168.1.1
passwd
```

> Do not connect the device to an untrusted network before setting the password.

---

## If an error occurs

**Before `CONFIRM FORMAT AND FLASH`.** No destructive change has happened. Fix
the cause and restart the wizard.

**After the temporary OpenWrt has booted.** Do not cut power or reboot manually —
the temporary system stays reachable over SSH. Connect (`ssh root@192.168.1.1`,
no password) and inspect the state:

```sh
cat /tmp/NOKIA_AUTOFLASH_STATE      # current state
cat /tmp/NOKIA_AUTOFLASH_FAILED     # stop reason
tail -n 100 /tmp/nokia-autoflash.log
tail -n 100 /tmp/nokia-ubi-installer.log
cat /tmp/NOKIA_MANUAL_STATE 2>/dev/null
cat /tmp/NOKIA_MANUAL_FLASH_FAILED 2>/dev/null
```

Do not blindly rerun `fullflash`, `ubiformat`, or a BL2 write.

---

## If the installation stops at "starting production OpenWrt"

From 1.0.0-rc31 the wizard keeps a rescue TFTP server up for the whole wait, so
an interruption here normally repairs itself: unable to boot, U-Boot asks for
the recovery image once a second, the wizard serves it, and the board comes up.
A `[RESCUE]` line in the wizard window reports this.

If the wizard was already closed, or the server could not start (UDP/69 taken,
insufficient rights):

1. Set the PC to a static **192.168.1.254/24**; turn Wi-Fi and VPN off.
2. Cable into **LAN2/LAN3/LAN4** — U-Boot brings up only the switch port, not LAN1/2.5G.
3. Power the router off.
4. As Administrator: `python data\tftp-rescue.py`
5. Power the router on.

The script waits for the request, serves the image and reports `[OK] delivered`.
About a minute later the board answers SSH at 192.168.1.1.

By default it serves the **transition system** — the only image in the kit that
can finish an install. Once it is up, pick the wizard's installation-continuation
entry: the installer sees the existing UBI, refuses to format again and writes
only the production image. The migration is not repeated.

`--stock-recovery` serves the rollback image instead, for going back to stock
rather than completing OpenWrt.

> [!IMPORTANT]
> While production OpenWrt is being written, the `fit` volume has been deleted
> and is being rewritten — there is no bootable image on the board at that
> moment. Do not cut power without the rescue TFTP server running: a timeout on
> its own fixes nothing, and an interruption inside that write has to be
> repaired over the same TFTP path anyway.

---

## Rolling back to stock from a running OpenWrt

If OpenWrt is already installed and running, you can return to stock without
UART.

1. Leave the router on, connect Ethernet, set the computer to `192.168.1.254/24`.
2. Run `RESTORE_STOCK.cmd` (Windows) or `./RESTORE_STOCK.sh` (Linux), pick a
   language.
3. Choose the running-OpenWrt option and point it at the full `mtd0..mtd16`
   backup.
4. **Do not press Reset.**

If root has a password on the installed OpenWrt, the wizard asks for it once, on
first contact with the device. After that login it leaves a one-off key in
`/etc/dropbear/authorized_keys` so the remaining checks run without questions;
the stock restore overwrites that key along with the whole flash. When there is
no console — the wizard was started from a script, or over a channel without a
terminal — there is nowhere to ask: clear the password on the device with
`passwd -d root`, add your own key to `/etc/dropbear/authorized_keys`, or restore
through BootROM/UART.

What happens next: the wizard checks the layout, brings up a TFTP server on the
computer in advance, and writes a one-shot next-boot command into the bootloader.
On the next reboot the bootloader first restores the stock `bootcmd`, then pulls
a safe recovery image into RAM over TFTP (automatic UBI migration is disabled in
it). Recovery continues over SSH. If TFTP does not happen, the bootloader returns
to normal boot and the wizard offers up to three attempts.

The recovery image transfers data in the order TFTP → SCP → TCP/nc, and every
written partition is verified by read-back SHA256.

The write order is always the same: `IBU` first (`0x00020000..0x0EBA0000`),
SHA256 check, and only then `BL2` (`0x00000000..0x00020000`). In recovery/SSH a
monolithic SHA256 of the whole `all_flash` is then computed against the original
`mtd16`. Before writing, the wizard requires the exact phrase
`RESTORE STOCK BACKUP`.

---

## Read-only backup through BootROM/UART — MD and MF

New menu item **8** captures a complete stock image without needing stock Linux, including from a partially broken router. In this mode the wizard does **not** execute `mtd erase`, `mtd write`, `saveenv`, `sysupgrade`, or UBI mutations. Reset is used only to enter BootROM.

```text
Reset + power → BootROM C
      ↓ XMODEM: SoC-specific preloader → RAM
      ↓ XMODEM: BL31 + U-Boot → RAM
      ↓ mtd list + exact geometry gate
      ↓ TFTP: recovery FIT → RAM, bootm
      ↓ SSH UID 0; all_flash=256 MiB
      ↓ 30 read-only chunks through stock length 0x0EBA0000
      ↓ gzip + TFTP PUT → PC
      ↓ second independent dd | sha256sum on router
      ↓ synthesize conventional mtd0..mtd16 backup on PC
```

**rc9fix:** after selecting UART/IP/TFTP/destination there is no extra Enter-to-start step. The wizard opens UART immediately, mirrors incoming serial output live, detects `Press x`, sends `x` itself, and catches `C` automatically. The first BootROM wait does not flush RX, so an already-visible BootROM readiness sequence is preserved.

Every 8-MiB chunk is retained with a `.raw.sha256` sidecar. A restarted run reuses already verified chunks, providing resume behavior. From canonical `mtd16/all_flash`, the wizard creates the normal MedveFlasher files plus `bosa.bin`, `ri.bin`, `proc_mtd.txt`, `SHA256SUMS.txt`, and `BOOTROM_BACKUP.json`. Overlapping vendor views `mtd2..mtd5` are normalized to accepted layout A because BootROM capture has no stock `/proc/mtd` and raw NSB data contain overlapping views; `mtd14`, `mtd15`, and `mtd16` remain the authoritative raw stock data.

The rc9 PC-side splitter and final backup validator were tested against the real MF backup; the end-to-end menu-item-8 capture path is new and still needs its first hardware run.

## Recovering a brick over UART

This mode is for when the router boots neither stock nor OpenWrt but repeats the
character `C` over UART. That means the BootROM is alive and waiting for the next
boot stage over the XMODEM protocol.

### Two different Reset paths — do not mix them up

On an MD with a live tcboot, the Reset button leads to **two different** places,
and what decides which one is when you press it relative to powering up.

**Path A — tcboot Web recovery, no UART needed:**

```
Reset released
   ↓
apply power
   ↓
press Reset immediately and hold 5–10 seconds
   ↓
on UART: "Reset button is pressed for: 5"
   ↓
httpd at 192.168.1.1
```

Here the bootloader has already started and brought up Ethernet and HTTP itself.
An Ethernet cable and a browser are enough.

**Path B — BootROM, UART required:**

```
Reset already held
   ↓
apply power
   ↓
on UART: "Press x"
```

Power arrives with the button already held, so tcboot is never reached — you land
in the BootROM. That is the entry point for the XMODEM procedure described below.

> [!NOTE]
> Path A is confirmed on live XG-040G-MD / AN7581 hardware: tcboot boots from
> NAND, initialises DDR, probes the 256 MiB SPI-NAND, and brings up `eth0` and
> `httpd`. For XG-040G-MF / AN7583 the tcboot network is **not confirmed** — it
> needs its own PCS, MDIO, pinctrl and switch glue, and that layer is still under
> research. On MF, assume only path B is available.

The MedveFlasher wizard drives path B: it runs the UART procedure and does not
operate the tcboot web interface.


### MD and MF support

UART restore classifies the backup by stock geometry and selects a SoC-specific profile. The preloader remains release-pinned, while the RC18 FIP is a **RECOVERY_SAFE derivative** of the ordinary RAM U-Boot.

- **MD / AN7581**: preloader `113447` bytes / `6c3b2339…`; RC18 SAFE FIP `308154` bytes / `2ebcbf3981e3e56b6389521fc2caa3320cf259c08f173b660b29366b9290bcc1`. The unsafe source FIP SHA256 was `9c29cdbc…`.
- **MF / AN7583**: hardware-proven EVB preloader `118322` bytes / `c2ac1c18…`; RC18 SAFE FIP `339010` bytes / `8bfe8870e44923a463a3ed66c8b1906214f5c820fd8c15865c63430185de8bb2`. The source EVB FIP `339224` / `b2f5f93f…` is retained only as provenance.

Both SAFE BL33 images use `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, and neutralized persistent environment volume names. After XMODEM, the master does not trust a banner or visual prompt alone: marker + `bootdelay=-1` + inert bootcmd + a fresh nonce are required. NAND erase/write/saveenv remain blocked before that gate.

Ctrl-C after the U-Boot banner is only a secondary safety net. Linux fallback after a missed SAFE prompt is disabled for both families. Exact RC18 SAFE FIP bytes are hardware-regression pending.

### What you need

- a previously taken full backup **of this same router** (`mtd0`–`mtd16`), with a
  valid `mtd16.bin.gz` of `247070720` bytes uncompressed;
- a **3.3 V** USB-UART adapter;
- Ethernet between the computer and the router;
- Python 3 (on Windows COM handling is built in, nothing to install);
- stable power.

### Wiring the UART

```text
Nokia GND ↔ USB-UART GND
Nokia TX  ↔ USB-UART RX
Nokia RX  ↔ USB-UART TX
```

> [!WARNING]
> Do **not** connect the power line (VCC/3.3V/5V) from the adapter to the router.
> The router is powered only by its own PSU.

Set the computer to a static address `192.168.1.254`, mask `255.255.255.0`, empty
gateway.

### Running it

1. `START.cmd` / `./START.sh`, item `6 — recover a brick`.
2. The wizard checks dependencies and lists the UART ports that actually exist —
   pick yours (`COM10`, `/dev/ttyUSB0`). The port opens at `115200 8N1`
   immediately, so a driver error surfaces before the long backup processing.
3. Keep the default addresses (PC `192.168.1.254`, router `192.168.1.1`) and
   point it at the backup folder. The wizard checks every partition and matches
   regions inside `mtd16` against the separate dumps byte-for-byte — an
   inconsistent backup will not do.
4. If UART already shows `Press x` or repeated `C`, leave power and Reset alone.
   If there is no prompt, power the router off, hold Reset, power on, and wait for
   `Press x`.
5. Release the port from any terminal (close PuTTY/Tera Term) and press Enter.

### What the wizard does itself

```text
BootROM emits C
      ↓  XMODEM: preloader → RAM
      ↓  XMODEM: BL31 + U-Boot FIP → RAM
U-Boot runs from RAM, the wizard captures AN7581>/AN7583>/=>
      ↓  mtd list check: erase=0x20000, bl2=0x20000, ubi=0x0FFE0000
      ↓  TFTP each 8-MiB IBU block into RAM U-Boot
      ↓  mtd write → clear RAM → mtd read → crc32 per block
      ↓  the exact stock BL2 (0x0..0x20000) written last + verify
      ↓  reset → normal Press x window → stock boots
```

The temporary OpenWrt components (preloader, FIP) run from RAM only and are **not
written to NAND**. Before any real write the wizard requires the exact phrase
`RESTORE STOCK BACKUP`.

### Why BL2 is written last

The `ibu` region (from `0x20000`) is restored and verified first. While it is
being written the current BL2 is untouched, so a network glitch lets you retry.
Only once the SHA256 of every IBU block matches is `bl2` (`0x20000`) written, with
its own read-back check. These checks cover the entire written range, even though
the direct RAM path does not compute one combined SHA256 of the whole image. The
router reboots only after every block matches.

### On error

Do not cut power. Do not run `ubiformat`, `fullflash`, or a manual BL2 write.
Leave the recovery image running from RAM. Save for diagnosis:

```text
work/stock-recovery/<id>/uart-recovery.log
work/stock-recovery/<id>/restore-manifest.json
```

If the failure was before the BL2 write, the main stage can be retried after
fixing the network. If any IBU block or the BL2 SHA256 mismatches, the automatic
reboot is blocked.

> [!WARNING]
> This mode restores a backup only to the same router it came from. Someone
> else’s backup would carry over foreign MAC addresses, serial data, RI/BOSA, and
> environment.

---

## Appendix A. Recovery technical notes

**Strict transition into U-Boot.** The wizard does not treat the U-Boot banner as
success. After the XMODEM FIP is confirmed, the wizard sends `Ctrl-C` at once,
recognizes the banner and bootmenu, exits the menu via `ESC`, and requires a
stable `AN7581>` prompt. Enter is not sent here — it would pick “run default
boot”. Each `setenv` is confirmed by its own marker; TFTP counts only at the full
size on the server; in the recovery path `iminfo` must confirm the FIT before
`bootm`, and the layout after `bootm` must show `mtd2=ibu` (`mtd2=ubi` blocks
writing). If the permanent kernel does start anyway, the wizard does not quit: it
waits for SSH and applies a one-shot recovery boot without another XMODEM.

**If UART stopped at `Press x`.** That is BootROM emergency mode, not bootloader
TFTP — the router is recoverable. Leave power alone, close the terminal, run
`RESTORE_STOCK` and choose the UART/BootROM option: the wizard sees `Press x`,
sends `x` itself, waits for `C`, and continues the XMODEM.

**Transfer clients in the recovery image.** The recovery image contains two minimal tools in the
RAM image: `tftp` (IPv4 GET with `blksize` negotiation) and a restricted `scp`
(receive into `/tmp` only, `scp -t` only). The transport order during restore is
TFTP → SCP → TCP/nc, each followed by a NAND read-back SHA256.

---

## Appendix B. OpenWrt image status

The kit installs a permanent OpenWrt with the LuCI web interface in an all-in-UBI
layout. After install the system is reachable at `192.168.1.1`; the root password
is unset — set it immediately. The current branch status and known build
limitations are published in a separate image-status file in the release.

---

## Install cheat sheet

```text
Connect the router by cable
      ↓  Run START.cmd / START.sh, pick a language
      ↓  Item 1 — install OpenWrt
      ↓  Telnet user: useradmin, password from the label
      ↓  UID 0 account: Enter, password: Enter
      ↓  Pick a backup method (Samba / FTP / TFTP)
      ↓  Wait for the full backup, copy it again
      ↓  Type CONFIRM FORMAT AND FLASH
      ↓  Do not cut power
      ↓  Wait for the installed OpenWrt
      ↓  Set the root password with passwd
```

A full log of each run is in `work/logs/LATEST.log`.
