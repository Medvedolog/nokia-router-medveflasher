## 1.0.0-rc24 — return to menus without closing the script

RC24 changes the interactive PC wizard: after a successful task or an ordinary recoverable error, `master.py` no longer terminates the process automatically. The operator can return to the current section, go to the main menu, or exit. Invalid menu selections are re-prompted in place and never close the script.

Destructive-path safety is unchanged. `WRITE_STATE_UNKNOWN` sets a process-local `SAFETY-LATCH`: normal installation, no-UART restore, and destructive Stage 2 continuation are blocked until a successful full `RECOVERY_SAFE` BootROM/UART recovery. The menus remain available for read-only diagnostics/backup and UART recovery. `KeyboardInterrupt` is intentionally not swallowed by the interactive wrapper during possible NAND activity. Direct CLI subcommands keep their normal exit codes and are not converted into menu navigation. Firmware/transition/recovery payloads are unchanged from RC23.

## 1.0.0-rc23 — timestamps and backup MAC binding

RC23 adds an absolute local `[YYYY-MM-DD HH:MM:SS]` timestamp to operator-facing `master.py` lines and prompts so PC/UART events can be correlated unambiguously. Blank separator lines remain unprefixed; secrets are still excluded from session/LATEST logs.

Live-stock backup over direct TFTP and USB now creates `DEVICE_MAC.txt`. The primary MAC is taken from `eth0` when available, otherwise from the first non-loopback interface; the file also records discovered interface MACs and local/UTC capture time. `DEVICE_MAC.txt` is covered by the SHA256 manifest. Legacy backups without this file remain compatible and are not blocked.

The current MF hardware run confirmed the exact RC22 install path: transition `[1/8]..[8/8]`, UBI migration, and production `SSH + LuCI` verification PASS. This does not promote the RC22 UART bad-block restore to a full PASS: the restored stock booted the main image/kernel, but its `data` UBIFS reported recovery failure and entered a watchdog boot loop before a later boot.

## 1.0.0-rc22 — UART stock restore with bad blocks

RC22 fixes BootROM/UART restore on physical NAND containing bad eraseblocks. Before the destructive stage the wizard reads `mtd bad bl2` and `mtd bad ubi`. A known bad PEB inside the stock UBI-backed mutable physical region `0x052C0000..0x0EB60000` is skipped **physically**, without shifting adjacent bytes from canonical `mtd16`. Each 8-MiB source chunk is split into contiguous good spans and each span gets its own write/readback/CRC32 verification. The bad-block map is rebuilt after erase and must remain unchanged before BL2.

A bad block in BL2 or in raw-critical stock bootloader/kernel/rootfs/flags blocks automatic restore fail-closed because the OpenWrt RAM U-Boot does not prove stock BMT mapping for those addresses. BL2 is still written only LAST after the complete body readback passes. Firmware payloads are unchanged from RC21.

## 1.0.0-rc21 — Stage 6 telemetry / safe reboot / UX cleanup

- After `[6/8]`, the wizard temporarily polls transition every **350 ms** so the short `[7/8]` and `[8/8]` window is normally visible before networking disappears. If those lines are still lost during handoff, strict production `board + canonical UBI + release` verification reconciles them as **POST-BOOT VERIFIED** rather than inventing them from a timeout.
- If production sysupgrade does not reboot the router for more than 4 minutes, timeout alone **never authorizes** a power cycle. The wizard prints a conditional safe path: manual reboot is allowed only when the operator sees the exact UART line `sysupgrade successful`; without that marker, power must remain unchanged.
- Network telemetry is shortened to `[NET] TCP ports: ...`; the awkward `(not state identity)` text is removed. Port state remains telemetry only and never identifies the phase.
- TFTP remains **choice 1, the Enter default, and recommended** in every transport menu. USB routes now say explicitly that the drive is attached to the **Nokia**, while the PC reaches it over Samba or stock FTP.
- Existing-backup installation now immediately reports validation results: `mtd0..mtd16 17/17`, family/variant, canonical `mtd16` span, and SHA256-manifest status.
- Web credentials from successful startup auto-detection are retained only in current-process memory and reused for flashing; the same Web user/password is no longer requested twice.
- Startup uses vendored **Rich 15.0.0** without pip: brown Unicode bear, cyan product name, and green version/build tag.
- RC20 Stage 5 re-arm remains: after `CONFIRM FORMAT AND FLASH`, stock Telnet and the complete read-only preflight are checked again; a post-dispatch disconnect never triggers a destructive retry.
- All transition/recovery/production firmware payloads are byte-identical to RC20.

## 1.0.0-rc19 — restored TFTP client and fail-closed restore transport

- Restored the pinned minimal AArch64 `/usr/bin/nokia-tftp` and `/usr/bin/nokia-scp` clients used by the pre-Dark recovery lineage. This is a **router-side TFTP GET client, not a tftpd server**: the PC-side wizard still provides the TFTP server.
- Both clients are embedded in all six transient images: MD/MF auto transition, MD/MF manual transition, and MD/MF stock recovery. `/usr/bin/tftp -> nokia-tftp`, `/usr/bin/scp -> nokia-scp`.
- Recovery/transition Dropbear runs with `-B` for the intentionally blank transient root account; the wizard first uses deterministic SSH none-auth without `known_hosts`, key, or agent enumeration.
- Restore transport is now **nokia-tftp → TCP/nc → SCP**. Switching transport is allowed only before the `mtd write` command is issued. Any disconnect/error after NAND write starts becomes `WRITE_STATE_UNKNOWN`: automatic fallback is forbidden and only read-only device re-identification is attempted.
- The invariant remains `IBU -> readback SHA256 -> BL2 LAST -> readback -> full all_flash SHA256`. The known upstream MD initramfs panic/reboot issue does not trigger a Dark-kernel rollback; production/sysupgrade 6.18.41 remains unchanged.
- LAN1/2.5G remains forbidden for transition/recovery; use LAN2/LAN3/LAN4 only.

## 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- RC18 packaging correction: SAFE BL33 is now encoded in canonical Airoha LZMA-Alone form **known size + no EOPM** via `LZMA1EXT`. The first RC18 archive failed closed before COM/XMODEM under strict Windows liblzma with `Corrupt input data`; NAND was untouched. Runtime no longer decodes BL33 on the PC and instead pins exact FIP plus compressed BL31/BL33 SHA256.
- Fixed a critical BootROM recovery defect: the ordinary AN7581 RAM U-Boot used `bootdelay=0` and could reach first-boot `ubi_format -> mtd erase ubi` before an interactive prompt was proven. A U-Boot banner is no longer considered control of the bootloader.
- RC18 ships recovery-only SAFE FIP derivatives for AN7581 and AN7583. BL31 is preserved byte-for-byte; BL33 gets `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, and neutralized persistent UBI environment volume names so NAND `ubootenv/ubootenv2` cannot re-enable autoboot.
- After a stable prompt, `master.py` requires the exact SAFE marker, `bootdelay=-1`, inert bootcmd, and a fresh nonce. No NAND write/erase/saveenv capability exists before this gate; only UART/XMODEM and then read-only geometry are allowed.
- Ctrl-C after the banner remains only a secondary safety net: it is sent as a paced series until the prompt, not once. The primary safety boundary is inside the recovery BL33.
- Linux fallback after a missed BootROM-recovery U-Boot prompt is disabled fail-closed for both families.
- Full stock restore retains the existing invariant: body/IBU erase+write+readback first, exact stock BL2 LAST. U-Boot prints the `mtd erase ubi` range relative to the partition; physical BL2 is outside that erase.
- LAN1/2.5G remains prohibited for every transition/recovery process; use LAN2/LAN3/LAN4.
- Exact RC18 SAFE FIP bytes require the first hardware regression before promotion to HW CONFIRMED.

## 1.0.0-rc17fix5 — LAN1/2.5G excluded from transition/recovery

> **Network safety policy:** LAN1 / 2.5G is considered unstable and **must not be used for any transition or recovery process**. For stock→transition, manual/auto transition, live progress, RAM stock recovery, TFTP/SCP/SSH, and restore, connect the PC only to **LAN2, LAN3, or LAN4**. A link on LAN1 does not make it a supported transport path.

- The build-time patcher `data/recovery/transition-network-source/patch_transition_network.py` enforces this for MD/MF auto/manual transition and stock-recovery FITs. Production sysupgrade images are intentionally out of scope.
- Initramfs `/etc/board.d/02_network` exposes only `lan2 lan3 lan4` for Nokia; the exact fixed-slot script bytes contain no literal `lan1`.
- In transition/recovery DTs the single `2500base-x` MAC is `status = "disabled"`; its `openwrt,netdev-name` and NVMEM binding are removed. The primary/internal Ethernet path and switch remain active and use raw `ri-stock` MAC NVMEM.
- MD Dark and MF Uname production OpenWrt payloads remain byte-for-byte unchanged; the exclusion is transition/recovery-only.
- Evidence: exact fixed-size `02_network` (MD 767 bytes, MF 591 bytes) and byte-exact DTBs are verified by release QA; see the rc17fix5 section in ARCHITECTURE for the summary.

## 1.0.0-rc17fix4 — recovery DT hardening / pre-SSH diagnostics

- Fixed the MF stock-recovery release blocker: the recovery FIT no longer carries the production DT. `all_flash` remains read-only, `bl2` is writable only in RAM recovery, `mtd2=ibu`, and there is no pre-restore `linux,ubi` auto-attach.
- MD and MF stock-recovery now use the same fail-closed pre-restore NVMEM topology: read-only raw `ri-stock` at `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 bytes), with Ethernet MAC consumers bound to that raw RI provider. Recovery Ethernet no longer depends on the future UBI `ri` volume.
- `docs/dtb-evidence/` carries byte-exact DTBs for MD/MF recovery/transition/production. QA now proves for both families that recovery != production, recovery BL2 is writable, `ibu` has no `linux,ubi`, Ethernet uses raw-RI MAC NVMEM, and Ethernet/switch and active DSA LAN2/LAN3/LAN4 are present.
- Manual READY no longer uses the approximate `/proc/net/route` fallback. The exact address is parsed from `/proc/net/fib_trie`, with exact `ip -4 addr` output as fallback.
- Both manual initramfs images contain `uhttpd` and its init script. The PC master can now consume `/www/medveflasher-manual.status` as content-based pre-SSH diagnostics; READY and custom image transfer still require SSH content identity.

## 1.0.0-rc17fix3 — persistent manual READY / reviewable DT evidence

- Manual transition no longer freezes at `NETWORK_NOT_READY` after 60 seconds. The family/LAN/SSH readiness monitor runs in the background until READY, so the PC-side 600 s retry now observes state that can actually change.
- The READY gate no longer depends on `netstat`: SSH LISTEN is parsed from `/proc/net/tcp{,6}`, LAN 192.168.1.1 from `/proc/net/fib_trie` / `/proc/net/route`; `ip` is fallback only. Preflight confirms `sbin/ip`, `bin/netstat`, and `bin/cat` exist in both manual initramfs images.
- `/tmp/NOKIA_MANUAL_STATE` and `/www/medveflasher-manual.status` now expose ASCII key/value diagnostics: `STATE`, `REASON`, board, br-lan/IP/SSH flags, and `DEFERRED`.
- Auto transition still performs destructive work autonomously, while Ethernet is required for PC-side live progress/control-plane telemetry. MF/MD transition DTs retain the raw `ri-stock` pre-format NVMEM policy.
- `fullflash` rc=0 without reboot is no longer classified as FAILED; it becomes verification-pending and requires production verification.
- `docs/dtb-evidence/` contains byte-exact DTBs extracted from MD/MF auto/manual transition, stock-recovery, and production sysupgrade images, allowing REVIEW_ONLY to independently inspect NVMEM/MTD/network topology without runtime ITBs.

## 1.0.0-rc17fix2 — transition network / Dark MD audit

- Fixed the root cause of missing Ethernet in MF transition before formatting: MAC NVMEM now comes from read-only raw stock RI at `0x05200000+0x3e`, not from the future UBI `ri` volume. This applies to auto and manual transitions.
- Auto mode needs Ethernet for PC-side live progress/control-plane, not for the autonomous destructive installer itself. RC17fix2 restores that channel.
- MF target `mtd2` keeps label `ubi` for compatibility with the hardware-confirmed installer, while pre-format `linux,ubi` auto-attach is disabled.
- All MD ITBs were audited. Production sysupgrade and stock recovery were already Dark 6.18.41; auto/manual transition were still old 6.18.39 r35573. RC17fix2 rebases both transitions onto the selected Dark 6.18.41 / r0-486b4a4 kernel and a minimized initramfs while retaining the fail-closed installer gates.
- Manual readiness is family-specific; the MF path no longer contains an MD board-name hardcode.

> **rc17 / monitor+restore hardening:** the MF RC16 hardware run confirmed refreshed EVB recovery, BL2-last, and permanent installation end-to-end. RC17 keeps production payloads unchanged, adds content-identified HTTP transition monitoring, treats raw TCP ports as debug telemetry only, family-binds Restore Stock to the validated MD/MF backup, exposes brick UART recovery before stock autodetect, and enforces ASCII-only on-device shell payloads.

# Nokia Router MedveFlasher
> **rc16 / payload refresh + release hardening:** MD/AN7581 production now uses the selected Dark patched 2026-08-09 snapshot (`r0-486b4a4`, kernel 6.18.41): bundled LuCI sysupgrade `13226255` bytes / `c6f06fcf…`. MD RAM stock recovery keeps the exact kernel/rootfs from the selected Dark initramfs `a8e24301…`, while rebuilding only the recovery DT: `all_flash` remains read-only, `bl2` is writable only in recovery, and production `ubi` is exposed as `ibu`. MF/AN7583 keeps the Uname production UBI build-set unchanged. The EVB BootROM/XMODEM pair remains offline-bundled (`c2ac1c18…` / `b2f5f93f…`) and the refreshed exact-byte pair was hardware-confirmed on Nokia XG-040G-MF in the RC16 recovery run on 2026-08-12. Stale MF `transition_fit_totalsize` metadata is fixed; `verify_kit()` now fail-closes if MANIFEST size/SHA/FIT totalsize/FIT SHA/production metadata differs from any of the four shipped transition bundles. Both production sysupgrades passed build-time LuCI filesystem validation.

> **rc15 / MF permanent HW continuation:** rc14fix6 hardware-confirmed stock→transition, UBI format, canonical volumes, and bosa/ri/FIP/FIT readback. BL2-last failed because the transition DT marked `bl2` read-only. rc15 makes `bl2` writable only in the transition DT, checks MTD_WRITEABLE before format, rechecks the pinned BL2/preloader/FIP immediately before BL2-last, and restores live progress through the shared SSH/Telnet monitor. Production DT/sysupgrade remain protected and unchanged.


**Version:** 1.0.0-rc24

**Default transport:** TFTP (recommended). It is always item 1 in transport menus; LAN1/2.5G is prohibited for transition/recovery.

> **rc14fix6 / RAM-worker hotfix:** applet detection itself is fixed: vendor BusyBox on MF is not required to print a `Currently defined functions` inventory when invoked without arguments. Required applets are now probed directly through the staged BusyBox before any NAND write. Destructive ordering and UART FIFO isolation are unchanged.

> **rc14fix5 / RAM-worker hotfix:** removed the RAM worker dependency on `awk` for SHA256 token parsing. rc14fix6 later showed that the observed `applet missing` failures came from unreliable parsing of no-argument BusyBox output, not proven absence of a particular applet.

During stage 2, installation phase and network ports are reported separately. Ports are printed only when they change, while the wizard explicitly marks transition boot, installer handoff, reboot, and production OpenWrt verification.
**Date:** 13 August 2026
**OpenWrt installation:** Nokia XG-040G-MD (AN7581) and experimental XG-040G-MF/MF-A (AN7583). **Brick recovery:** XG-040G-MD/AN7581 and XG-040G-MF/AN7583.

> **rc9fix / MF:** rc8fix2 hardware-confirmed the scripted `mtd list`, network setup, and first 8-MiB TFTP load through RAM U-Boot. The next blocker was narrow: AN7583 U-Boot has no `hash` command. rc9 uses U-Boot `crc32` for RAM/readback verification while the PC source remains SHA256-pinned. It also adds menu item 8: a fully read-only MD/MF backup through BootROM/UART and a temporary recovery Linux running only in RAM.
> **rc11 / MF diagnostics:** a second real MF layout is accepted (`MF-B`: `mtd2=0x003B6D40`, `mtd3=0x01D10000`), the wizard gains a full stock audit through Web → Telnet → proven `UID 0`, and the PC parser derives geometry from real `/proc/mtd`/sysfs/dmesg evidence. `STOCK_ALL_FLASH_SIZE` is renamed to `STOCK_RESTORE_SPAN`; normal/permanent MF installation intentionally remains blocked in rc11 pending a separate hardware gate.
> **rc12fix / MF normal backup:** the live rc12 run hardware-confirmed Web/Telnet/root, MF-A, read-only `/dev/mtd*ro`, and TFTP PUT for all `mtd0..mtd16`. The old fatal rule requiring a second full `mtd16` read to be byte-identical is removed because live stock mutates config/data/log during backup. rc12fix hashes the exact gzip stream on the Nokia (`tee` + FIFO + `sha256sum`) and requires it to match the PC file SHA256, then checks gzip/raw size and the full stock-restore validator. Permanent MF installation remains disabled.
> **rc13 / firmware capabilities:** the repeat live MF-A backup on rc12fix completed through `MF mtd16 transport SHA256 PASS`, `verify_stock_restore_backup()`, and `BACKUP_HW_VALIDATED`. Therefore `CAP_FULL_BACKUP=YES` for a live MF-A after root/geometry gates. The flashing menu now exposes a read-only capability report; MF `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, and `CAP_PERMANENT_INSTALL` remain `BLOCKED`. rc13 adds no new destructive MF commands.
> **rc14 / MF transition HW gate:** hardware-confirmed MF-A now has a separate experimental path: `stock -> HW-validated backup -> mtd14/nsb_master transition FIT -> readback -> personalized U-Boot env last -> reboot -> pinned MF initramfs/RAM OpenWrt`. The workflow stops immediately after proving RAM OpenWrt: `ubiformat`, `ubi write`, `sysupgrade`, and persistent bootloader replacement are unreachable. `CAP_MF_TRANSITION_BOOT=EXPERIMENTAL` and `CAP_RAM_OPENWRT=PARTIAL` until the live run; `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, and `CAP_PERMANENT_INSTALL` remain `BLOCKED`.

> **rc14fix / MF permanent install:** MF-A now mirrors the proven MD architecture: mandatory `BACKUP_HW_VALIDATED` → live Web/Telnet/UID0 + MF-A `/proc==sysfs` → device-specific transition written to `mtd14` with readback → `mtd0` environment last → MF UBI initramfs. After `CONFIRM FORMAT AND FLASH`, the transition preserves stock `bosa/ri`, formats `0x20000..0xffffffff` as UBI, creates `ubootenv/ubootenv2/bosa/ri/fip/fit`, verifies payload readback, writes the complete BL2 **last**, then installs the bundled MF sysupgrade. A separate manual mode accepts a user-selected compatible `nokia,xg-040g-mf-ubi` sysupgrade after `sysupgrade -T`. Hardware-confirmed UART/BootROM full stock restore remains the fallback.
> **rc14fix2 / MF hotfix:** fixes the live `RAM BusyBox applet missing: ash` blocker: the autonomous RAM worker uses the available BusyBox `sh` instead of requiring a separate `ash` applet. The MF menu is device-specific; verbose preflight and Telnet protocol markers are removed from the operator console/LATEST while timestamped session diagnostics retain them. Destructive gates and write ordering are unchanged.
> **rc14fix3 / shared installer:** MD and MF now use one profile-driven installer engine and one `stock-launcher.sh.in`. Installation menus are synchronized. The MF auto/manual bundles are the ready runtime images; duplicate standalone MF transition FITs, the standalone MF sysupgrade, and standalone production preloader/FIP are removed, with no runtime repacking. MF-A safety gates and BL2-last ordering are unchanged.
> **rc14fix4 / UART-log hotfix:** on stock MF, `/dev/console` may exist and look writable while returning `EIO` on an actual write. UART is no longer a direct sink of the primary `tee`; serial mirroring is isolated behind a draining FIFO, so UART failure cannot stop the RAM worker. NAND write ordering and safety gates are unchanged.



> [!WARNING]
> This is a release candidate. Before flashing, take a full verified backup and keep
> it on your computer — without it there is no way back. Never cut power while
> NAND is being written.

---

Technical architecture: [ARCHITECTURE_EN.md](ARCHITECTURE_EN.md). Image and hardware-evidence status: [IMAGE_STATUS_EN.md](IMAGE_STATUS_EN.md).

## What this does

Nokia Router MedveFlasher installs OpenWrt on the Nokia XG-040G-MD and hardware-gated MF-A without
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
4. Use the family-specific install path selected by VERIFIED stock-Web detection. MF-A permanent install is hardware-confirmed end-to-end from RC16; RC17fix2 changes transition network/bootstrap bytes, so the exact RC17fix2 transition still requires a hardware regression. Manual/custom sysupgrade must not continue until the family/LAN/SSH READY gate passes.
5. Wait for the backup — 250 MB, 20–40 minutes. **Copy it somewhere else too.**
6. Type `CONFIRM FORMAT AND FLASH` and leave power alone until it finishes.

As long as the backup is intact, the device is recoverable. If something goes
wrong, see [If an error occurs](#if-an-error-occurs).


### rc14 firmware capabilities

`1 — flashing / installation / recovery` now uses item `5` for the MF-A transition HW test; the read-only report is item `6 — probe firmware capabilities (read-only)`. It re-proves stock Web access, Telnet, `UID 0`, family/variant, and `/proc/mtd == sysfs`, then intersects those live facts with release hardware status. The report **does not authorize NAND writes** and does not replace the pre-write gates of any operation.

For the hardware-confirmed MF-A profile before the first transition hardware run, rc14 reports:

```text
CAP_FULL_BACKUP          YES - HW CONFIRMED MF-A normal TFTP backup
CAP_MF_TRANSITION_BOOT   EXPERIMENTAL - rc14 MF-A HW gate available; requires BACKUP_HW_VALIDATED
CAP_RAM_OPENWRT          PARTIAL - stock transition path needs this hardware run
CAP_UBI_FORMAT           BLOCKED
CAP_UBI_VOLUME_WRITE     BLOCKED
CAP_BOOTLOADER_REPLACE   BLOCKED
CAP_PERMANENT_INSTALL    BLOCKED
CAP_UART_RECOVERY        YES - HW CONFIRMED full stock restore
```

After the startup Web fingerprint, the installation menu selects the MD or MF profile, but that never authorizes writes: live Web/root/MTD/backup gates are repeated inside the shared installer engine. MD and MF expose the same installation actions; board-specific differences live in the profile. Machine-readable release matrix: `data/FIRMWARE_CAPABILITIES.json`.

### Verifying the archive

A `…zip.sha256` file ships next to the archive. Check it before unpacking:

```powershell
# Windows
(Get-FileHash .\Nokia-Router-MedveFlasher-1.0.0-rc24.zip -Algorithm SHA256).Hash
```

```bash
# Linux — from the folder holding the archive
sha256sum -c Nokia-Router-MedveFlasher-1.0.0-rc24.zip.sha256
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
1 — flashing / installation / recovery
2 — backup
3 — show credentials, all device users, and privileges
4 — preparation / continue installation
5 — exit
```

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


### MD and MF support in RC18

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


## rc10 changes

- The main menu is grouped into flashing/recovery, backup, and preparation/continuation submenus; credentials are a dedicated top-level item.
- “Resume from stage 2” is explicit: transition OpenWrt is already running from RAM, then the wizard verifies transition, formats UBI, flashes sysupgrade, and monitors first boot.
- The credential audit shows the hardcoded Web default, device-specific Telnet/FTP/Samba credentials, and every local `/etc/passwd` user with UID/GID/groups/home/shell and privilege classification. UID-0 `su` is tested only against Telnet/FTP passwords returned by the device; there is no dictionary guessing.
- Secrets are rendered only to the physical console and are excluded from `LATEST.log`/session logs. `telecomadmin` is shown as a credential only when that account actually exists on the device; no unverified password is invented.
- BootROM backup retries a full SSH handshake after TCP/22 appears to tolerate early Dropbear startup instead of failing immediately with SSH code 255.

### rc10fix: resilient credential audit

If the Nokia stock HTTP server closes a connection without a response, the credential audit performs bounded transport retries and avoids reusing a broken keep-alive socket. When plain compatibility is explicitly allowed, failure of the encrypted POST no longer blocks a separate plain-login attempt. If the Web UI remains unavailable, the credentials menu no longer terminates MedveFlasher: hardcoded/default values have already been shown and, when Telnet is already open, only a read-only `/etc/passwd` and `/etc/group` inventory is offered with manually entered device credentials.


### RC10fix2: SSH-free BootROM backup

For MD/MF read-only BootROM backup the recovery FIT is booted with `rdinit=/bin/sh`. Control uses UART and payload data uses gzip/TFTP. The wizard verifies the model, `all_flash`, BusyBox applets, and a RAM-only TFTP probe before the first NAND read. Each chunk is confirmed by a second NAND SHA256 read. UBI, Dropbear, and SSH are not started in this path.
