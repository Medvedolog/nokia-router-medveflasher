# Nokia Router MedveFlasher changelog

## 1.0.0-rc7 — 10 August 2026

- Fixed a UART-confirmed manual-transition regression: `/lib/preinit/00_nokia_manual_installer` contained `exit 0` even though OpenWrt sources every `/lib/preinit/*` file into the shared `/etc/preinit` shell. This terminated normal preinit before `02_sysinfo`, netdev-label setup, and `82_config_generate`; `/tmp/sysinfo/board_name`, `/etc/board.json`, and `/etc/config/network` were missing and LAN stayed administratively DOWN despite physical carrier.
- Manual mode no longer exits the shared OpenWrt preinit. Normal sysinfo, DSA/netdev labels, board detection, and LAN configuration are allowed to complete.
- `/tmp/NOKIA_MANUAL_TRANSITION_READY` is now created only after the exact board name, `192.168.1.1/24` on `br-lan`, and a listening SSH/22 are verified. Failed LAN/SSH readiness sets `NETWORK_NOT_READY` instead of publishing a false ready marker.
- Fixed the expert custom-sysupgrade workflow stalling after the manual transition had booted: an open TCP/22 no longer triggers a hidden 30-second SSH probe whose exception is discarded.
- Added a short deterministic SSH probe for the manual transition: it first uses protocol-level passwordless login without local key/agent enumeration or interactive authentication methods, with one short ordinary `BatchMode` fallback when needed.
- Batch SSH probes no longer inherit console stdin, so the detector cannot silently wait for user input.
- Manual-transition readiness is identified by its own `/tmp/NOKIA_MANUAL_TRANSITION_READY` marker, state file, and `nokia-ubi-installer`; `board_name` is diagnostic only and is not treated as a model gate in expert mode.
- SSH probe failures are no longer swallowed: a short cause is shown when port 22 is open, while full diagnostics are kept in `LATEST.log`/the session log.
- The SSH mode proven by the readiness probe is reused for TFTP upload of the selected `.itb`, `nokia-ubi-installer check`, `fullflash` launch, and manual-install monitoring.
- `4 — resume from stage 2` uses the same fixed detector and can continue an already booted manual transition without rewriting NAND.
- Fixed the second half of the same regression: the manual transition inherited an empty `root` password while Dropbear was started without `-B`, so TCP/22 was open but OpenSSH exited with code 255 before the probe command could run. Dropbear now receives `-B` only in the manual transition; the standard transition is untouched.
- Standard transition, recovery, production payload, preloader, and FIP are unchanged from rc6. Only the manual transition and PC-side SSH detector changed. Known snapshot-initramfs kernel panics are outside this fix.

## 1.0.0-rc6 — 6 August 2026

- Fixed stage-2 monitoring: heartbeat lines no longer merge the current phase with the complete network-port list. Port state is emitted separately and only when it changes.
- When the transition system disconnects, the wizard explicitly reports final transition work, handoff to the OpenWrt installer, and the expected reboot.
- When network services return, the wizard reports production OpenWrt startup and performs final verification. SSH board/UBI verification is preferred over LuCI.
- Removed the stale `6/8 readback verification` heartbeat after SSH disappears; a brief transition disconnect no longer leaves an obsolete phase displayed until installation ends.
- Network status now uses the neutral label `Telnet 23` instead of `stock Telnet 23`, because port 23 may belong to stock, transition, or installed OpenWrt.
- Extended console coloring to `[NET]`, `[STEP]`, `[READY]`, `[IMPORTANT]`, `[INFO]`, and `[TECH]`. Colors remain active in normal and diagnostic output, while log files remain ANSI-free.
- Firmware payloads, standard/manual transition, recovery, preloader, and FIP are unchanged from rc5.

## 1.0.0-rc5 — 6 August 2026

- Fixed automatic Windows Samba password delivery. The wizard now uses the native `WNetAddConnection2W` API instead of `net use ... *` with a hidden password fed through stdin.
- The `useradmin` password is passed directly in process memory to the Windows API and is absent from process arguments, OS password dialogs, console output, and logs.
- If a stale guest session causes a credential conflict, only the Nokia share and its `IPC$` connection are removed before one retry.
- If the password previously entered for Telnet is genuinely different from the Samba password, the wizard asks once for the label password and retries.
- Firmware payloads, standard/manual transition, recovery, preloader, and FIP are unchanged from rc4.

## 1.0.0-rc4 — 6 August 2026

- Added an authenticated Windows connection to `\\<Nokia IP>\mnt` as `useradmin` before the first directory probe.
- The first attempt reused the device password read from the Web UI or entered from the label for Telnet.
- A rejected credential triggered one manual label-password retry.
- The `net use ... *` implementation was incompatible with some Windows builds because the hidden prompt could read from the console instead of stdin. rc5 replaces it with the native API.


## 1.0.0-rc3 — 6 August 2026

- Added visible overall progress for FTP and Samba backup downloads: percentage, a 20-cell bar, transferred size, average speed, file count, and current file.
- Added the same progress while uploading the personalized installation package to the Nokia USB drive through FTP or Samba.
- Progress is emitted as normal lines without carriage-return animation, keeping `LATEST.log` readable.
- If the FTP server does not support `SIZE`, the wizard still reports transferred bytes, speed, current file, and file count without inventing a percentage.
- Firmware payloads, standard/manual transition, recovery, preloader, and FIP are unchanged from rc2.


## 1.0.0-rc2 — 6 August 2026

- Cleaned the return-to-stock workflow: internal `BOARD`, `STATE`, MTD listings, `TOOL_*`, U-Boot environment values, and the complete `ARMED_BOOTCMD` are now kept in `work/logs/LATEST.log` instead of the operator console.
- Rewrote the introduction in user-facing language and removed legacy internal RC numbers from the current interface.
- The transition from installed OpenWrt now shows only meaningful stages: device verification, temporary boot preparation, TFTP request, recovery-system startup, and selected transport.
- A missing service state file is no longer shown as a warning when the exact recovery MTD layout is confirmed.
- The RI warning is reduced to one actionable instruction: verify that the selected backup belongs to this router.

## 1.0.0-rc1 — 6 August 2026

- Renamed the product to **Nokia Router MedveFlasher** and moved version/build
  identifiers to `1.0.0-rc1` / `medveflasher-1.0.0-rc1`.
- Removed the retired development label from archive names, directories,
  transition bundles, logs, temporary paths, manifest, README files, and source.
- Adopted the restructured parallel `docs` directory: localized README,
  IMAGE_STATUS, and CHANGELOG files only.
- Added `transition-manual-bundle.bin`, with no embedded production sysupgrade
  and no automatic stage 2.
- Expert mode selects a user `.itb` on the PC, uploads it to RAM over TFTP, and
  checks FIT magic, size, SHA256, `nokia-ubi-installer check`, and `sysupgrade -T`;
  formatting starts only after a second confirmation.
- Removed Telnet command/protocol noise while retaining transition phases, port
  state, and installer progress steps 1/8 through 8/8.
- TFTP backup reuses one healthy root session and reconnects only after failure.
  FTP resolves the stock USB chroot path correctly.
- Restore no longer requires live mutable partitions to match the later `mtd16`
  snapshot byte-for-byte; static partitions remain strict.
- The production sysupgrade, preloader, FIP, and recovery FIT are unchanged. The
  standard transition was rebuilt only for product/version text.

---

## RC34 — documentation reorganization

- The instruction and onboarding docs were rewritten and merged into a single
  `README_EN.md` / `README_RU.md`: structured text with a quick start up front
  and recovery technical detail in appendices. The English version was brought to
  full parity with Russian (previously it was a stub).
- Merged and removed: `FIRST_TIME_*` (now the README "Quick start"),
  `legacy full instruction files` (replaced by the README),
  `RECOVERY_CLIENTS_SOURCE.md` (now README "Appendix A").
- `LUCI_IMAGE_STATUS_RC34_*` renamed to `IMAGE_STATUS_*` and trimmed of the
  duplicated restore-transport tail (now in the README).
- `MANIFEST.json`: the `documentation` block was updated for the new layout.
- Final `docs/`: `README_EN/RU`, `IMAGE_STATUS_EN/RU`, `CHANGELOG(_RU)`.

## RC34 restore-validation and access-menu hotfix

- Package version remains `legacy RC34`; build tag: `rc34-hotfix-restore-live-slices-readable-access-menu-quiet-ui-tftp-reuse-s1-h6`.
- Fixed a false rejection of backups captured by the wizard: live stock partitions such as flags, configuration, data, oops, and logs may differ from the later `mtd16` snapshot. Their own manifest SHA256, gzip integrity, and exact sizes remain mandatory; canonical `mtd16` is used for restore.
- Replaced the access menu's developer-oriented model-gate descriptions with short user actions; technical warnings are shown only after the relevant choice.
- Choice 4 is now “Continue without checking the model (advanced users)” and uses a normal `y/N` confirmation. Direct TFTP remains mandatory in that mode.
- Firmware/recovery/transition binaries are unchanged.

## RC34 TFTP reuse / expert bypass hotfix

- Package version remains `legacy RC34`; build tag: `rc34-hotfix-tftp-reuse-expert-bypass-s1-h6`.
- Direct-TFTP backup reuses one UID-0 Telnet session for every successful partition. A new session is opened only after a timeout, socket/Telnet error, or missing completion marker; only the current MTD is retried and validated files remain untouched.
- Manual access choices 2/3 now use a best-effort model gate: an explicit `AN/EN7583` is blocked, an explicit `AN/EN7581` is accepted, and an inconclusive result may continue after one warning.
- Added access-menu choice 4: expert installation through direct TFTP only, without running any model probe. Exact `EXPERT` confirmation is required; USB/Samba and FTP are unavailable in this mode.
- FTP chroot mapping, Windows `SIO_UDP_CONNRESET`, S1, and H6 fixes are retained; firmware/recovery/transition binaries are unchanged.

## RC34 net/manual hotfix — TFTP retry, FTP path mapping, and Telnet model gate

- Package version remains `legacy RC34`; build tag: `rc34-hotfix-net-manual-gate-s1-h6`.
- Direct-TFTP backup was initially changed to use a separate UID-0 Telnet session for every partition attempt; the next hotfix optimised this to reconnect only after an actual failure.
- Fixed stock-FTP path mapping: router path `/mnt/USB_disc1/...` is probed as `/mnt/USB_disc1/...`, `/USB_disc1/...`, and `/...` according to the ProFTPD chroot. The backup is downloaded from the actual USB directory and the package is uploaded back to that same USB directory instead of `/mnt`.
- Manual access choices 2/3 are available for installation again; the model-gate policy is refined in the next hotfix.
- Previous S1 and H6 fixes are retained; firmware/recovery/transition binaries are unchanged.

## RC34 hotfix — secret filtering, XMODEM CAN, and exact restore wording

- Package version remains `legacy RC34`; build tag: `rc34-hotfix-s1-h6-doc-truth`.
- `_ConsoleTee` now removes every registered password of at least four characters from session/LATEST logs while leaving console output unchanged. Web UI, Telnet, UID-0, FTP, and Samba passwords are registered automatically.
- On every local XMODEM failure the wizard sends `CAN` three times before raising, so BootROM is not left in a pending receiver state.
- Documentation now distinguishes the verification paths precisely: RAM U-Boot verifies every IBU chunk and BL2 with separate readback SHA256 checks; RAM recovery/SSH additionally computes one monolithic SHA256 for the complete `all_flash`.
- Transition bundle, production OpenWrt, recovery FIT, preloader/FIP, backup agent, and stock launcher are unchanged.

## RC34 — model gate enforced on every installation path

- Version bumped to `legacy RC34`; build tag: `rc34-model-gate-all-access-paths`.
- Installation menu items 1 and 7 call `ask_credentials(require_model_gate=True)`.
- Manual access choices 2/3 can no longer bypass model verification: installation stops before manual Telnet input and before any NAND operation.
- Any automatic Web UI failure that leaves the model unconfirmed is also a hard stop for installation; manual fallback remains only in backup-only mode.
- Even when TCP/23 is open, installation defaults to automatic Web UI instead of blocked choice 3.
- Transition bundle, production OpenWrt, recovery FIT, preloader/FIP, backup agent, and stock launcher are unchanged.

## RC33 hotfix — model gate enforced in code

- **Critical fix.** Dropping XG-040G-MF support (see "RC33 — MD-only build" below) was declarative: the code that enables Telnet and proceeds with installation never checked the device model. The `/proc/mtd` check does not protect against this — stock NAND layout can match byte-for-byte across models in this lineup, confirmed against XG-040G-MF dumps.
- Added `StockSetup.read_device_info()` / `require_model()` to `stock_web.py`: before the first change to the device (before `enable_telnet`), the wizard reads `ModelName`/`X_ASB_COM_Chipset` from `device_status.cgi` and stops if the model is not in `SUPPORTED_INSTALL_MODELS = ("XG-040G-MD",)`.
- A new `UnsupportedModel` exception type is kept separate from `UnsupportedFirmware`: a model mismatch is a hard stop with no fallback to manual entry — otherwise menu item 2/3 could be used to bypass the check.
- The gate is covered by `stock_web.py --selftest`; a build without it fails the automated tests.
- Also shortened and re-synced the main menu and access menu text (RU/EN) with the instruction's quoted copies; fixed two case errors and one untranslated word in `INSTRUCTION_..._RU.md`.
- Version kept at `legacy RC33`; firmware/recovery/transition binaries unchanged.

## RC33 — MD-only build with the XG-040G-MF branch removed

- Removed the model selector, MF master, MF installer, MF image fetcher, and MF documentation. The kit is again exclusively for Nokia XG-040G-MD (AN7581).
- Retained automatic stock-web integration: encrypted-first login, retrieval of Telnet/FTP credentials and actual ports, and automatic Telnet, Samba, and FTP enablement with live port verification.
- FTP is enabled through the absolute `ftp_en=true` setting only after USB/FTP is selected; Samba is enabled only after USB/Samba is selected.
- Retained USB/Samba, USB/FTP, and direct-TFTP backup, installation from an existing backup, transition, LuCI production OpenWrt, and both MD recovery paths.
- MD Telnet uses independent reconnect attempts; UID 0 is accepted only after `id -u = 0` verification.
- Version remains `legacy RC33`; firmware/recovery/transition binaries are unchanged.

## RC30 same-version localization and checksum-instruction correction

- Added explicit RU/EN pairs for every remaining user-facing `Error`/`TransportError` message that still produced Cyrillic or hybrid text in English mode, including transition-bundle validation, UART recovery, SCP, readback SHA256, and transport exhaustion failures.
- Fixed the remaining untranslated recovery-FIT success line and invalid 1/2 selection prompt.
- Documented that `sha256sum -c data/SHA256SUMS` must be run from the extracted kit root.
- Package version and all firmware/recovery/transition binaries remain unchanged.

## RC30 — stock-web and recovery UX maintenance

- English stock-web failures now preserve both the exception class and full diagnostic text; `ftp_cfg`, `csrf_token`, and HTTP status details are no longer hidden.
- Fixed the hybrid stock-web module-load error by using an explicit RU/EN pair instead of substring translation that changed “load” into “upload”.
- Invalid 1/2/3 stock-access input now re-prompts without restarting the wizard or asking for the Nokia IP again.
- The Telnet toggle safety error reports the configured Telnet port rather than hard-coding port 23.
- Removed an unreachable encrypted-login branch and documented TCP/23 as a deliberate default-selection heuristic used before Web UI configuration is available.
- Critical IBU/BL2/all_flash SSH-restore messages now have explicit RU/EN variants.
- The transition bundle, LuCI production OpenWrt, recovery FIT, stock launcher, and backup agent are byte-identical to RC29.

## RC29 — stock Web UI automation with manual fallback

- Added `data/stock_web.py`, using only the Python standard library.
- Encrypted-first login reproduces the stock AES-128-CBC + RSA-1024 form; plain login is available only through `NOKIA_ALLOW_PLAIN_WEB_LOGIN=1`.
- Telnet/FTP users, passwords, and actual ports are read from JavaScript; web flags use strict normalization and do not suffer from `bool("0")`.
- Telnet can be enabled automatically and is confirmed by its TCP port. Samba is enabled only after Samba transport is selected and checked on 445/139. FTP enabling remains manual and explicit when its port is closed.
- If TCP/23 is already open, “Telnet already configured” is the default, avoiding an unnecessary stock-web session.
- Unsupported firmware, login failure, unavailable HTTP, and failed setting changes close the web session and fall back to manual Telnet input instead of terminating the wizard.
- Web/Telnet/FTP secrets are not printed, written to session/state files, or passed through argv.
- Production OpenWrt, transition bundle, recovery FIT, preloader, and FIP are unchanged from RC28.

## RC28 — fix false Fudan detection after completed UBI migration

- RC27 could identify SkyHigh correctly before formatting, complete and verify the UBI migration, then fail before production sysupgrade. The cause was self-poisoning: the installer wrote its own Fudan policy text to kernel log and a later `dmesg` scan treated that text as hardware evidence.
- NAND identity is now established once before destructive work and cached for the current transition boot. Installer/autoflash `NOKIA-*` log lines are excluded from hardware evidence.
- Post-migration `status` validates board, MTD geometry, required tools and canonical UBI volume IDs without re-identifying NAND from mutable logs.
- Menu item 4 can recover the exact RC27 failure only after strict checks of the earlier SkyHigh result, completion marker, authorization marker, six canonical UBI volumes, embedded production size and SHA256. It then runs only production sysupgrade; it does not format NAND again.
- Transition FIT: `0b89420b81e933fbda323488a67a5e9a97532d4c38e8f2d3e50f062ef508a6eb`; complete bundle: `091dd9f5bbfa5bd6a874df96bac3f8f763f4f9dceecf760bec5ce537a2d59bc8`.
- Production OpenWrt with LuCI remains byte-identical: `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`.


## RC27 — reliable RAM-worker detection and clean transition UART diagnostics

- Fixed a false stage-1 failure in Russian mode: the PC master no longer waits for the English sentence `RAM worker started`.
- The stock launcher now emits the stable marker `__NOKIA_RAM_WORKER_STARTED__PID__` immediately after `kill -0` confirms the detached RAM worker.
- Rebuilt the transition FIT so BusyBox `ash` never writes directly to `/dev/kmsg`; complete diagnostic lines are buffered through `dd` and become single kernel/UART records.
- This removes the repeated one-character `N`, `O`, `K`, ... messages and associated printk rate limiting.
- The embedded production OpenWrt with LuCI is unchanged: SHA256 `95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6`.
- Transition FIT SHA256: `32994c4e5f813f89865aecf60027971d576f09e98231ef4d58e96d124c8862d6`; complete bundle SHA256: `c84e9bf67469e7483ddb9365756603dde66893d678c9b355858b87dc975b3df7`.

## RC26 — non-blocking existing-backup handling and console-prefix colors

- Fixed the USB incomplete-backup scanner returning failure when the only matching directory was a valid completed backup.
- Completed backup directories from this or another Nokia are ignored and never modified.
- A scan failure or optional deletion failure is now a warning, not a blocker; the backup agent creates a new unique directory.
- Removed the duplicate Windows/Samba-side incomplete-backup prompt; the router-side mount is the authoritative scan location.
- Added bright-magenta `[INPUT]` and bright-cyan `[PATH]` coloring while retaining prefix-only coloring for wizard-owned messages.
- Firmware, recovery FIT, transition bundle, and production OpenWrt are unchanged from RC25.

## RC25 — pragmatic USB preflight

- Removed raw MBR/GPT, partition-count, partition-type, and FAT32 boot-sector inspection.
- USB is accepted when stock Nokia has mounted it as FAT/FAT32, the mount is writable, a real create/sync/delete test succeeds, and at least 2 GiB is free.
- This avoids false failures on valid drives whose block-device layout is hidden or reported unusually by the stock kernel.
- Firmware, recovery FIT, transition bundle, and production OpenWrt are unchanged from RC24.

## RC24 — mandatory USB preflight and clean Telnet console

- Menu item 1 now says “full OpenWrt installation with mandatory backup” and prints the exact route after transport selection.
- USB/Samba and USB/FTP display mandatory requirements before work: drive in the Nokia USB port, MBR, one FAT32 partition, at least 2 GiB free.
- UID 0 Telnet preflight strictly validates mount, write test, FAT32 boot sector, non-GPT MBR, exactly one partition entry, and free space.
- Telnet command echo, here-documents, and uploaded backup-agent source are hidden; only stages and runtime results remain visible.
- Incomplete USB backup directories (`*.incomplete` or missing `BACKUP_COMPLETE`) are detected over Telnet and removed only after explicit confirmation.
- Telnet decoding now uses a streaming UTF-8 decoder, preventing broken multibyte characters across `recv()` boundaries.


This file consolidates release notes and validation history.

Current package version: `legacy RC30`  
Release date: 2026-08-05  
Classification: **Public Preview**

## RC24

### USB backup marker, transactional directories, and password input

- Fixed a Telnet command-echo collision that could return the literal `%s` instead of `/mnt/USB_disc1` and pass `%s` to the device-side backup agent. Runtime markers are now split across output calls and validated against the candidate path set.
- USB backups are created as `nokia-xg040gmd-backup-*.incomplete` and renamed to the final directory only after all dumps, hashes, and `BACKUP_COMPLETE` are written.
- Existing completed backups are never deleted. Incomplete legacy/staging directories are listed and may be removed explicitly before a new Samba backup.
- The label password is mandatory and accepts printable ASCII without spaces only; empty input, Cyrillic, and other keyboard layouts are rejected and re-prompted.
- Firmware, transition, production, recovery, preloader, and FIP binaries are byte-identical to RC22.

## RC22 archive layout cleanup (same version)

- Moved all Markdown documentation to `docs/`.
- Merged `README_FIRST.txt` into the localized `FIRST_TIME_RU.md` and `FIRST_TIME_EN.md`, then removed the redundant README file.
- Moved `VERSION` and the internal checksum manifest to `data/`, leaving only `START.*` and `RESTORE_STOCK.*` as files in the archive root.
- Firmware, recovery, transition, and orchestration binaries are unchanged.

## RC22

### Stock Samba path detection

- Fixed the case-sensitive stock mount mismatch: physical Nokia exposes `/mnt/USB_disc1`; older wizards verified `/mnt/USB_Disc1`.
- The Windows default is now `\\<router>\mnt\USB_disc1\nokia-openwrt-install`.
- The prompt accepts the USB root or the complete `nokia-openwrt-install` directory.
- The UNC path is mapped to the router path and both lowercase and legacy uppercase variants are probed.
- Before stage 1, the router-visible `SHA256SUMS` file must have the exact SHA256 of the newly generated package.
- Firmware, transition, production, recovery, preloader, and FIP binaries are byte-identical to RC21.

## RC21

### Embedded recovery TFTP, SCP fallback, and restore progress

- Rebuilt the stock-recovery FIT with a minimal AArch64/musl TFTP GET client exposed as `/usr/bin/tftp`.
- Added automatic restore transport order: embedded TFTP, legacy SCP over Dropbear SSH, then TCP/nc.
- SCP stages the compressed payload in recovery RAM, verifies its SHA256, writes NAND, removes the temporary file, and then performs the standard raw NAND readback SHA256.
- Streaming transports show transferred MiB, percentage, and elapsed time. NAND writes and SHA256 readback checks show periodic heartbeats.
- Added colored `STAGE_R1` through `STAGE_R5` headings for preflight, IBU, BL2-last, full `all_flash`, and reboot.
- Expanded the recovery console with the required power, Ethernet, PC IPv4, UART, firewall, and no-Reset instructions.
- When the state file is not yet visible, the recovery console derives `RECOVERY_READY` from `root=tmpfs` and the `ibu` MTD layout instead of displaying `UNKNOWN`.
- The transition bundle and embedded LuCI production sysupgrade remain byte-identical to RC20.

### Validation status

- FIT CRC32/SHA1: PASS.
- Embedded CPIO extraction and `/usr/bin/tftp` presence: PASS.
- Native build of the same TFTP client source against the actual PC TFTP server: PASS at 20,000, 2,000,000, and 8,388,731 bytes with exact SHA256.
- Restricted SCP sink protocol test: PASS at 2,500,123 bytes with exact SHA256.
- Python and shell syntax, RU/EN menu smoke tests, internal hashes, and clean ZIP extraction: PASS.
- Hardware validation of embedded ARM64 TFTP and SCP fallback remains required; RC22 stays Public Preview.

## RC20

### RAM recovery rollback fix

**Hardware observation**

The production rollback reached the intended RAM recovery state successfully:

```text
production OpenWrt
→ self-reverting U-Boot one-shot command
→ TFTP/69 recovery FIT
→ RAM recovery
```

The observed recovery layout was:

```text
root=tmpfs
mtd2="ibu"
mtd3="ri-stock"
```

No stock NAND write had started at the time of the reported loop.

**Root cause**

RC19 required `command -v tftp`. The shipped recovery image had no standalone `tftp` command. An earlier static inspection incorrectly inferred a usable BusyBox applet; the physical recovery later proved that `/bin/busybox tftp --help` returns `127`, so the applet is not registered in that build. The dependency preflight therefore correctly reported no Linux TFTP client, but RC19 had no usable payload fallback and repeated the recovery diagnostic.

**RC20 maintenance correction (same version)**

The first RC20 packaging revision used `/bin/busybox --list | grep -x tftp`, which was not a reliable capability test. RC20 then switched to the executable probe `/bin/busybox tftp --help`. Hardware returned `127`, conclusively identifying the applet as unavailable. RC20 therefore selected the recovery image's existing `nc` applet and reached the final `RESTORE STOCK BACKUP` confirmation over TCP without starting a NAND write. The NAND readback SHA256 gates and BL2-last order remained unchanged.

**Corrections**

- Detect a standalone `tftp` command and probe a possible BusyBox applet by execution.
- Treat BusyBox status `127` as applet unavailable and choose TCP/nc instead of looping.
- Require two quiet, stable recovery probes and validate dependencies once.
- Report a permanent missing dependency once instead of repeating the full `/proc/mtd` diagnostic.
- Suppress repeated OpenSSH known-host notices with `LogLevel=ERROR`.
- Keep all firmware payloads byte-identical to RC19.

**Validation**

- Python compilation: PASS.
- POSIX shell syntax: PASS.
- Recovery FIT inspection plus hardware execution probe confirmed that the older image has no usable Linux TFTP client.
- TCP/nc fallback selection reached the destructive confirmation safely on hardware; no NAND write had begun.
- RU/EN menu smoke tests: PASS.
- Internal `SHA256SUMS` after clean extraction: PASS.
- Windows launchers are ASCII, CRLF, and without BOM: PASS.

**Hardware validation still required**

Continue menu item 5 from RAM recovery and complete:

```text
IBU write and readback
→ stock BL2 written last
→ final all_flash verification
→ stock boot
```

### Persistent PC logs, console presentation, and final-system monitoring

RC20 retains the RC18 transition and production payloads byte-for-byte and changes PC orchestration and presentation:

- `START.cmd` and `RESTORE_STOCK.cmd` wait for a key after both success and failure; the window does not close automatically.
- POSIX launchers wait for Enter when attached to a terminal.
- Every session is stored in `work/logs/LATEST.log` and in a timestamped `session-YYYYMMDD-HHMMSS-PID.log`.
- ANSI color codes are removed from saved logs.
- `[OK]` is green, errors are red, warnings are yellow, waits are blue, and `STAGE_X` headers are cyan.
- Installation paths use blank-line-separated `---------- STAGE_X ----------` headers.
- Password input is visible by default. Set `NOKIA_HIDE_PASSWORDS=1` to restore hidden input. Password characters typed by the terminal are not copied by the Python session logger.
- Final installation monitoring no longer requires SSH/22. After stock Telnet/23 disappears, either strict SSH board/UBI verification or an HTTP/HTTPS response containing `/cgi-bin/luci` is accepted.
- LuCI is checked before SSH, so delayed or disabled Dropbear does not block successful completion.
- Stage-2 SSH probes use batch mode and cannot stop on an interactive password prompt.
- There is no silent final timeout. Every 30 minutes the operator can continue waiting or finish as `post-install-unverified`.
- `state.json` records the final result and the PC session-log path.

### U-Boot environment parser correction

RC12 could incorrectly parse consecutive lines such as:

```text
SERVERIP=192.168.1.254
IPADDR=192.168.1.1
```

as one `SERVERIP` value. RC20 accepts only complete `BOOTFILE=`, `SERVERIP=`, `IPADDR=`, and `BOOTCMD=` lines and ignores SSH diagnostics and CRLF/LF differences. The original RC12 failure happened before reboot or NAND modification.

### Windows input and launcher correction

RC11 used the batch `choice` command for language selection. Typing `1` followed by Enter could leave Enter in the console buffer, causing the next Python prompt to receive an empty answer and exit with `invalid selection`.

RC20:

- performs language selection inside the Python master;
- repeats invalid or empty menu prompts;
- no longer prints a literal `\n` sequence;
- keeps one direct stock-restore launcher: `RESTORE_STOCK.cmd` / `RESTORE_STOCK.sh`;
- removes the duplicate `RECOVER_STOCK` alias.

### Running OpenWrt transition and production rollback

- An open TCP port 22 is no longer treated as proof that OpenWrt finished booting.
- Two successful SSH probes with the expected MTD layout are required.
- The one-boot U-Boot command restores the normal `bootcmd` before TFTP.
- Temporary network settings are applied only in RAM.
- Recovery TFTP is retried up to twenty times.
- If recovery TFTP fails, U-Boot returns to installed OpenWrt and the master waits for stable SSH before another attempt.
- The production rollback path does not hold Reset. Early Reset can be intercepted by BootROM and show `Press x` before U-Boot starts.
- The initial TFTP RRQ/WRQ wait now honors the complete configured timeout. RC13 stopped after the first five-second socket timeout.
- The self-reverting one-shot boot command is verified by reading it back before reboot.

### Strict UART state machine after XMODEM FIP

The U-Boot banner alone is not considered successful control acquisition.

The flow requires:

1. FIP XMODEM ACK.
2. Immediate `Ctrl-C`.
3. Boot-menu detection and `ESC` when required.
4. A stable `AN7581>` prompt.
5. An individual completion marker and returned prompt for every U-Boot command.
6. Complete TFTP transfer and U-Boot confirmation.
7. FIT validation before `bootm` where the recovery-FIT path is used.
8. Recovery layout `mtd2=ibu`; production layout `mtd2=ubi` blocks stock writes.

Enter is not sent during boot-menu acquisition because it selects `Run default boot command`.

### Direct brick restore from RAM U-Boot

Menu item 6 uses:

```text
BootROM C
→ XMODEM preloader in RAM
→ XMODEM BL31 + U-Boot in RAM
→ mandatory AN7581> prompt
→ TFTP test before NAND changes
→ complete ubi erase
→ stock IBU writes in 8 MiB chunks
→ per-chunk readback SHA256
→ exact stock BL2 last, without a 0x800 offset
→ BL2 readback SHA256
→ reset
```

The `0x800` prefix applies only to the OpenWrt all-in-UBI BL2 container. It is never applied to the original stock BL2. Backups containing either known OpenWrt-preloader layout are rejected.

### Installation from an existing backup

Menu item 7 installs OpenWrt from an already saved complete stock backup without taking the backup again and without UART. It is intended for a Nokia still running stock firmware when a previous run stopped during stage-1 preflight.

```text
7 — install OpenWrt from an existing backup without another backup or UART
8 — exit
```

### Transition FIT preflight correction

RC17 contained a malformed `TRANSITION_FIT_SHA` in the launcher template. The preflight correctly stopped before any NAND write with `transition FIT SHA256 mismatch`.

Correct transition FIT SHA256:

```text
7eaecd7d3f82edc69c0bf92cdf668e90295cf2f30ac68bc9ec092449ae5ab55c
```

The PC master now derives bundle metadata directly from `transition-bundle.bin`, injects it into every personalized `INSTALL.sh`, and verifies the launcher template against the binary before deployment.

### LuCI production image

RC20 embeds custom OpenWrt SNAPSHOT `r35679-e9a6e45556`, Linux `6.18.41`, profile `nokia_xg-040g-md-ubi`, with verified LuCI, `uhttpd`, `rpcd-mod-luci`, Dropbear, and `/www/index.html`.

Production image:

```text
size:   9531670 bytes
SHA256: 95fe315cedca64b5f5db39a5e03e75eb773b7c43e970d06fc3be6d0d8e1cbdc6
```

Embedding layout:

```text
production bundle offset:      0x800000
physical NAND offset:          0x8c0000
complete bundle size:          17956864 (0x1120000)
erase-block alignment:         0x20000
bundle SHA256:                 dd2647be19d4e890fdee6e0b01e850cc8381d4a2f9015228bc36e911d3715c56
transition FIT SHA256:         7eaecd7d3f82edc69c0bf92cdf668e90295cf2f30ac68bc9ec092449ae5ab55c
```

The stock → transition → embedded sysupgrade → LuCI production path was completed successfully on hardware through RC18 menu item 7.

## Hardware-confirmed results carried into RC20

1. Full brick caused by invalid BL2 placement:
   `BootROM C → XMODEM preloader → XMODEM FIP → RAM U-Boot`.
2. Direct stock restore from RAM U-Boot:
   - complete `ubi` erase;
   - 30 IBU chunks, each TFTP-loaded, RAM-hashed, written, RAM-cleared, read back, and SHA256-verified;
   - exact `0x20000` stock BL2 written last and SHA256-verified;
   - reset followed by reachable stock Web UI.
3. No-UART installation using an existing backup through RC18 menu item 7:
   `stock → stage-1 RAM worker → transition initramfs → embedded sysupgrade → production OpenWrt with reachable LuCI`.
4. Production OpenWrt → self-reverting one-shot → TFTP recovery FIT → RAM recovery was hardware-confirmed in RC19/RC20 testing. The reported RC19 loop happened after recovery boot and before stock NAND writes.

## Safety gates retained

- Complete `mtd0..mtd16` backup validation.
- Exact raw `mtd16` size `0x0EBA0000`.
- Stock physical-slice cross-checks.
- Explicit FudanMicro FM25G02B block.
- Stage-1 transition FIT, bundle, environment, and NAND-geometry preflight.
- Exact direct-U-Boot `bl2`/`ubi` geometry gate.
- IBU verification before BL2.
- BL2 written last.
- No reboot after a write/readback SHA256 mismatch.

## Static and regression validation

- Python bytecode compilation: PASS.
- POSIX shell syntax for shipped `.sh` and `.sh.in` files: PASS.
- RU and EN main-menu smoke tests: PASS.
- Session-log creation and `LATEST.log` mirroring: PASS.
- HTTP-only final-system detection with SSH closed: PASS.
- Internal `SHA256SUMS` after clean archive extraction: PASS.
- Windows launchers: 7-bit ASCII, CRLF, no BOM, no lone LF: PASS.
- No `work/`, logs, `__pycache__`, or temporary payloads shipped: PASS.
- Transition and production binaries match RC18: PASS.

## Not yet hardware-confirmed

- RC22 embedded TFTP client on physical recovery hardware.
- RC22 legacy-SCP fallback and automatic TFTP → SCP → TCP/nc failover on hardware.
- Restore behavior with a non-zero NAND bad-block count.
- Native-Windows validation of all new progress and color paths.

## Earlier fixes retained

### RC13

- Reset-based production rollback was removed because early Reset can enter BootROM before U-Boot.
- Initial TFTP request waiting was later corrected so one five-second socket timeout does not terminate the configured wait window.

### RC12

- Fixed exact parsing of `SERVERIP`, `IPADDR`, `BOOTFILE`, and `BOOTCMD` output.

### RC11

- Removed Windows `choice` from the interactive path to prevent a trailing Enter from becoming the next empty Python answer.
- Removed the duplicate `RECOVER_STOCK` launcher alias.

### RC9

- Running recovery could expose SSH before the late readiness marker appeared. Later releases accept the exact recovery-only `all_flash` / `bl2` / `ibu` layout while waiting for late initialization.

### RC7

- Windows launchers were standardized as ASCII command text with CRLF line endings to prevent `cmd.exe` from interpreting broken localized text as commands.

### RC6

- `/mnt/USB_disc1` became the default USB mount path suggested by the master.

## Release classification

**Public Preview.** Installation to LuCI production, direct full-brick RAM-U-Boot recovery to stock, and production one-shot entry into RAM recovery are hardware-confirmed. Remaining uncertainty is RC22 payload transport/failover on hardware, non-zero bad-block handling, and native-Windows presentation validation.
### RC34 hotfix: concise flash UX

- Removed the second interactive `CONFIRM FORMAT AND FLASH` prompt inside `INSTALL.sh` when the PC wizard has already obtained confirmation. Direct launcher use still prompts.
- The RAM-worker protocol marker and verbose launcher transcript are hidden from the operator console on successful startup.
- The pre-write warning now contains only the critical actions: disconnect fiber, keep power stable, and retain the complete backup on the PC.
- Production OpenWrt monitoring now prints one concise status every 30 seconds without a TCP-port dump.

