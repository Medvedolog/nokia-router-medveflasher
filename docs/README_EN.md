# Nokia Router MedveFlasher

**Version:** 1.0.0-rc7

During stage 2, installation phase and network ports are reported separately. Ports are printed only when they change, while the wizard explicitly marks transition boot, installer handoff, reboot, and production OpenWrt verification.
**Date:** 6 August 2026
**Device:** Nokia XG-040G-MD only (Airoha AN7581) with the stock NAND layout

> [!WARNING]
> This is a release candidate. Before flashing, take a full verified backup and keep
> it on your computer — without it there is no way back. Never cut power while
> NAND is being written.

---

## What this does

Nokia Router MedveFlasher installs OpenWrt on the Nokia XG-040G-MD without
opening the case or attaching UART. Everything runs over a normal Ethernet cable. It can also take
a full image of the stock firmware, roll back to stock, and revive a bricked
device — the last one does require a USB-UART adapter.

Inside is a single Python wizard (`master.py`) that needs no third-party
libraries: an installed Python 3 is enough. No pip packages, no drivers beyond
the stock ones.

**The install has three stages:**

1. **Backup.** The wizard takes a full NAND image (~250 MB) and verifies it.
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
3. Run `START.cmd` (Windows) or `./START.sh` (Linux), pick a language.
4. Menu item `1 — install OpenWrt`.
5. Wait for the backup — 250 MB, 20–40 minutes. **Copy it somewhere else too.**
6. Type `CONFIRM FORMAT AND FLASH` and leave power alone until it finishes.

As long as the backup is intact, the device is recoverable. If something goes
wrong, see [If an error occurs](#if-an-error-occurs).

### Verifying the archive

A `…zip.sha256` file ships next to the archive. Check it before unpacking:

```powershell
# Windows
(Get-FileHash .\Nokia-Router-MedveFlasher-1.0.0-rc7.zip -Algorithm SHA256).Hash
```

```bash
# Linux — from the folder holding the archive
sha256sum -c Nokia-Router-MedveFlasher-1.0.0-rc7.zip.sha256
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

1. Connect the computer to the Nokia LAN port by cable.
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
1 — install OpenWrt (with a backup first)
2 — create a backup
3 — prepare a package from your backup
4 — resume from stage 2
5 — restore stock (no UART)
6 — recover a brick (UART required)
7 — install OpenWrt from an existing backup
8 — exit
```

When to use which:

- **1** — the normal path. Router on stock, you want OpenWrt.
- **2** — only save the stock image, no install.
- **5** — return to stock from a working OpenWrt, no UART.
- **6** — the router does not boot at all; needs USB-UART.
- **7** — install OpenWrt when a backup was taken earlier.

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

Why the model check matters: the XG-040G-MD and the closely related XG-040G-MF
have **byte-identical NAND layouts**, so an ordinary partition check cannot tell
them apart. They differ only by the chip reported in the web UI — `AN7581` (MD,
supported) versus `AN7583` (MF, not supported). Installing the MD image on an MF
would brick it, so the wizard blocks it.

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

`mtd16` is the full NAND image, the basis for rollback. The file existing proves
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

## Rolling back to stock from a running OpenWrt

If OpenWrt is already installed and running, you can return to stock without
UART.

1. Leave the router on, connect Ethernet, set the computer to `192.168.1.254/24`.
2. Run `RESTORE_STOCK.cmd` (Windows) or `./RESTORE_STOCK.sh` (Linux), pick a
   language.
3. Choose the running-OpenWrt option and point it at the full `mtd0..mtd16`
   backup.
4. **Do not press Reset.**

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

## Recovering a brick over UART

This mode is for when the router boots neither stock nor OpenWrt but repeats the
character `C` over UART. That means the BootROM is alive and waiting for the next
boot stage over the XMODEM protocol.

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
U-Boot runs from RAM, the wizard captures the AN7581> prompt
      ↓  mtd list check: erase=0x20000, bl2=0x20000, ubi=0x0FFE0000
      ↓  TFTP each 8-MiB IBU block into RAM U-Boot
      ↓  mtd write → clear RAM → mtd read → hash sha256 per block
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
