# 1.0.0-rc27 — the restore gate stops guarding a partition it never touches

Found on hardware: a device reporting the correct board name, a 256 MiB
`all_flash`, a `0x20000` `bl2` and a `ubi` partition of `0x0FF00000` was refused
by the no-UART stock restore. Payload bytes are unchanged from RC24.

## 1.0.0-rc27 — 18 August 2026

- **`/proc/mtd` is parsed structurally instead of matched as text.** The gate
  compared whole lines, so `mtd2: 0ff00000` failed against the `0x0FFE0000` this
  kit's own build publishes — seven eraseblocks another build of the same board
  leaves unused at the end of the chip. Nothing in the operation depends on that
  number: restoring from a running system rewrites the U-Boot environment,
  verifies it by read-back, reboots and TFTPs the recovery image into RAM, while
  the `ubi` partition is never read, erased or written, and the recovery system
  pins the physical geometry itself before anything is flashed. The size was an
  identity fingerprint dressed as a safety check — the same confusion between
  recognition and authorization that RC25 removed from the install path.
- What the hardware and the boot contract fix stays exact: the full 256 MiB
  published as `all_flash`, one `0x20000` block named `bl2`, the `0x20000` erase
  size, and `mtd2` named `ubi` or `ibu`. The observed partition size is written to
  the session log as `[RESTORE-SHAPE]` evidence.
- **Board identity is read apart from the running system.** The probe now also
  reports `/proc/device-tree/compatible`, which is primary evidence and carries
  the SoC, so the MD family is recognised from `airoha,an7581` even when
  `board_name` is empty or lacks the `-ubi` suffix. That suffix keeps its own
  narrower meaning: a system this kit built. The running system is classified
  separately as `recovery`, `production`, `stock-layout` (a stage-1 transition) or
  `foreign-ubi`.
- **A refusal now says what it saw.** The gate used to answer "does not match" to
  four unrelated situations while the observed board name and `/proc/mtd` sat
  unused in the probe output. It now prints them, names which half failed, lists
  the missing markers, and points at the path that does apply — stage 2 for a
  transition system, BootROM/UART for anything this kit did not build. A layout
  matching all-in-UBI under a board name without the suffix is stated as a
  deliberate decision rather than implied to be a detection failure.
- Selftests cover the field size, the kit's own size, the recovery partition,
  upstream-named MD, SoC-only identification, a stage-1 layout, and four shapes
  that must still be refused. Every one was verified against a deliberate
  regression.

# 1.0.0-rc26 — the console loses the clock, the log keeps it

RC25 was published and then rebuilt three times under the same tag. This release
exists so that stops: content that changes behaviour gets its own version, and
`v1.0.0-rc25` stays where it is. Firmware, transition and recovery payload bytes
are unchanged from RC24.

## 1.0.0-rc26 — 18 August 2026

- **The console carries no timestamps at all.** RC23 added the absolute
  `[YYYY-MM-DD HH:MM:SS]` prefix so PC output could be correlated with UART
  events. That is a job for the file you read afterwards, not for the screen the
  operator is working on, where the prefix competed with the message on every
  line. Stamping moved into `_ConsoleTee`, so `work/logs/LATEST.log` and the
  session log carry the clock on every line — menu options and input prompts
  included — while the console shows exactly what the code printed.
- `_write_session_only()` bypasses the tee and therefore stamps its own
  diagnostics; `_log_prompt_newline()` also resets the log column, so the line
  after a prompt is not mistaken for a continuation and does not lose its stamp.
- The RC25 console-side machinery is gone: `menu_ui()`, `_MENU_RENDERING`,
  `_stamp_stream()` and `_timestamp_text()` are removed along with all twenty
  `with menu_ui():` blocks. The removal was verified by comparing the module's
  AST before and after, so only the wrappers disappeared. The invariant that
  replaces them is simpler and wider: the console is never stamped, the log
  always is.
- The stamp remains a line prefix. Live mirrors — the UART character feed, the
  Telnet echo, the XMODEM counter — write partial chunks, and a chunk continuing
  a line passes through untouched; a `\r` progress redraw does not collect one
  stamp per refresh.
- A `selftest-safety` case pins both halves of the split and was verified against
  four deliberate regressions: the console stamping again, the log no longer
  stamping, the suppression machinery returning, and per-chunk stamping of a live
  mirror.

# 1.0.0-rc25 — symmetric MD/MF install policy, clean menus, LAN1 advisory

Released to this repository as a single `1.0.0-rc25`. The interim `rc25fix` and
`rc25fix2` iterations are folded into this entry, which describes the shipped
state rather than the path taken to it. Firmware payloads are byte-identical to
RC24; RC25 changes PC-side orchestration, the stock launcher template, and
documentation.

## 1.0.0-rc25 — 17 August 2026

### Install authorization

- `mtd2..mtd5` now classify the stock family and vendor slot revision only. They are no longer a permanent-write allowlist. `MD_PERMANENT_WRITE_LAYOUTS`, `InstallProfile.allowed_stock_variant`, and the MF-only exact `MF-A` write gate are removed, so MD and MF follow one symmetric destructive policy.
- MD slot matching is revision-tolerant: the slot carrying the canonical pair `00480000/02400000` must still match byte-exact, while the opposite slot is matched against the MD reference within `±0x2000` (kernel image size) and `±0x10000` (rootfs slot size, `0x10000` alignment required). The field cases `mtd4=0x003AF742` and `mtd4=0x003AF61F` are recognized. Family windows stay far inside half the distance between the family reference points; a pair falling into both families is reported `unknown` and fails closed.
- `_install_live_gate()` byte-exact checks the stock handoff targets `mtd0/mtd14/mtd15/mtd16` and erase geometry. Stage 2 payloads independently pin physical 256 MiB NAND, `BL2=0x20000`, `UBI/IBU=0x0FFE0000`, erase `0x20000`, and write `0x800` before `ubiformat` is reachable.
- `stock-launcher.sh.in` no longer dies on a recognized slot revision. It keeps exact fixed partitions and target identity, and reports the vendor slot label as diagnostic evidence.
- Install backup policy is unified: both MD and MF use `verify_stock_restore_backup()`. `BACKUP_HW_VALIDATED` is evidence, not an authorization token, and every selected backup is re-read and validated from content.
- Capability reporting follows the same model: `READY` means the family path exists under current live gates while backup and physical-target gates remain mandatory. Variant no longer changes permanent-install capability within a family.
- `verify_kit()` also checks `MANIFEST.release.version/build_tag/archive_root` against the code, closing the one version-identity site that was not enforced at runtime.

### Stock Web sessions and UID-0 acquisition

- Backup and MF install use `_stock_operational_web_access()` and retain the authenticated `web_client/web_setup` until the operation finishes, so opt-in UID-0 provisioning can actually enable FTP/Samba and re-read credentials.
- `stock_audit_wizard()` and `firmware_capabilities_wizard()` stay read-only and use `_stock_audit_web_access()`, which logs out before returning. A selftest blocks accidental use of the operational wrapper from a read-only flow.
- Stock service provisioning is opt-in through `allow_service_provisioning`, default `False`, and `provision_next()` performs exactly one service attempt per failed root-discovery cycle — FTP first, Samba only on the next cycle. An FTP error or timeout can no longer fall through to Samba within the same cycle.
- Provisioning is described as "no raw MTD, flash, or firmware write" rather than as leaving NAND untouched: it saves a stock Web-UI settings form, and where the firmware persists those settings is not observable from the wizard.
- `_slot_layout_diagnostic()` no longer reports `outside every family window` for a recognized fuzzy MD/MF pair, so permanent-write rejection diagnostics are internally consistent.
- The audit parser uses the same revision-tolerant MD/MF classifier and no longer blocks MF variants on exact `MF-A`.

### Operator console

- Menus render without timestamps. The startup-mode selector, main menu, all four submenus, the manual model fallback, and the post-action navigation selector are drawn inside `menu_ui()`, which suspends the RC23 timestamp prefix for selector text only. Operational output, `[BLOCKED]`/`[SAFETY-LATCH]` decisions and the `[NAV]` completion lines keep their timestamps, so PC output still correlates with UART events.
- A `selftest-safety` case parses the module and fails the build if any of those functions prompts for a choice or prints a numbered option outside `menu_ui()`.

### LAN1 advisory

- Installation, backup, no-UART stock restore, BootROM/UART recovery, read-only BootROM/UART backup, and Stage 2 continuation now check the PC's link before the operation starts. A link negotiated at 2500 Mbit/s or faster can only be LAN1, because LAN2..LAN4 are gigabit ports, and it produces a warning naming the operation, a reminder to move the cable to LAN2/LAN3/LAN4, and a prompt that defaults to continuing.
- The check is an advisory, not a gate. A gigabit PC NIC in LAN1 is indistinguishable from LAN2..LAN4, so a hard block would refuse correct setups while still missing the common mistake. Detection failures degrade to the existing policy reminder, a non-interactive run continues silently, and write authorization still comes only from the live family, MTD, handoff-target and backup gates. A selftest asserts the advisory keeps exactly one failure path: the operator answering "no".

### Recovery, labels and the console

- **The no-UART recovery no longer kills its own TFTP server.** `ssh_run()`'s `allow_disconnect` tolerates a non-zero exit status but never covered a command that does not return at all, and `reboot -f` leaves the SSH channel hanging rather than closing it. The timeout therefore raised straight through `boot_recovery_from_production_openwrt()`, unwinding it together with the TFTP thread it had started — exactly while U-Boot was requesting the image. A new `allow_timeout` makes the fire-and-forget reboot explicit; the R5 stock-reboot path already guarded the same class with `try/except`.
- **A tolerated slot label names the profile it resembles.** The `-REV` label was built from slot orientation, so every tolerated MF unit was reported `MF-A-REV`, including revisions sitting beside the MF-B reference. The reference table now carries the vendor profile letter, and labels read `MF-B-REV` / `MF-B-MIRROR-REV`. Exact labels and the observed `MD-A-MIRROR-REV` are unchanged. Under the symmetric write policy this label is all the slot revision still produces, and operators and evidence files read it.
- **The launcher proves the partition it is about to erase.** `verify_slot_alias` (was `verify_active_slot_alias`) ran only for the active slot, so at `bootflag=1` the transition target `mtd14/nsb_master` was never shown to back its `mtd2` view — while "mtd2..mtd5 are views inside byte-exact aggregates" is the entire basis of the symmetric policy. The write target is now verified in addition to the active slot.
- **Timestamps are line prefixes again.** Live mirrors write partial chunks with `end=""`, and stamping each chunk cut the device's own output apart: `Press x` arrived as `P[12:24:31] ress x`, and the XMODEM counter collected a stamp per redraw. Stamping now happens only where a line actually begins, tracked across writes; a `\r` progress refresh continues its line. The stock-restore method selector also renders inside `menu_ui()`.
- **The LAN1 advisory no longer trusts a tunnel.** An observed `throne-tun` reported 100000 Mbit/s and was announced as LAN1. A router-facing link cannot outrun the port at the other end, so a speed above 5G is now reported as a virtual route — together with the warning that such a route makes every network observation unreliable, because a tunnel can answer for addresses that are not there. Interfaces without a backing device are excluded outright.
- The menu selftest's option pattern demanded a literal backslash, so `"1 — ..."` options were never actually tested and only `\n===` headers were. Fixed, and every check above is pinned by a selftest verified against a deliberate regression.

### Reading by fact

- Classifying `mtd2..mtd5` is a precondition for writing, not for reading. `_stock_live_geometry_preflight()` gained `require_slot_family`: the TFTP capture, the USB capture and the capability probe pass `False` and proceed on whatever the device reports, printing the unrecognised layout as evidence; `_install_live_gate()` keeps `True` because the family choice selects the firmware payload. A read-only capture is still authorised by the fixed stock partitions, `/proc/mtd == sysfs`, the `0x20000` erase size and the MAC recorded in `DEVICE_MAC.txt`.
- The reason is field drift, not convenience: observed MD revisions `mtd4=0x003AF742` and `0x003AF61F` sit against a rootfs reference exactly one eraseblock from the tolerance edge. Widening the reference table would chase every future revision; refusing to copy a NAND over a slot revision would deny a rollback image to the operator who needs one.
- Removed two leftovers from an older release that consulted an exact-MD table only. Every MF backup, including the hardware-confirmed exact MF-A, fell through to a rejection claiming MF installation awaited a hardware gate — which blocked the no-UART stock restore for MF. `verify_backup()` now pins the observed slot sizes for either family, keeping the dump/`proc` cross-check exact. The dead `backup_direct()` helper, unreachable and carrying the same stale gate, is deleted.
- A `selftest-safety` case pins the split: capture and diagnostics must read by fact, `_install_live_gate()` must not, the capture must still record `DEVICE_MAC.txt`, and the stale release gate must not return.

### Documentation

- The two MD Reset paths are documented as the distinct entry points they are. Pressing Reset after power lands in tcboot's own Web recovery with `eth0`/`httpd` already up and no UART needed; holding Reset before power preempts tcboot and lands in the BootROM `Press x` prompt, which is the XMODEM path the wizard drives. The MF tcboot network layer is stated as unproven, so only the BootROM path can be assumed there.

### Release identity

- Repository releases carry no `fix` suffix; the version is `1.0.0-rc25` in every declaration site.
- A `selftest-safety` case compares `APP_VERSION`, `BUILD_TAG`, root `VERSION`, `data/VERSION`, `MANIFEST.release.version`, `MANIFEST.release.build_tag`, `FIRMWARE_CAPABILITIES.version`, and `RELEASE_VERSION` in `stock-launcher.sh.in`, and fails if any pair disagrees or if a `fix` suffix reappears. The version is duplicated across those files because different consumers read different ones; this test is what keeps the duplication honest.
- The six pinned runtime payloads are embedded and verified by `data/verify_release_assets.py` against the sizes and SHA256 values in `docs/RELEASE_ASSETS.md`. `verify_kit()` remains fail-closed: a missing, resized, or SHA-mismatched payload blocks the operation.
- The release archive is trimmed to the kit itself: `VERSION`, `LICENSE`, the four launcher scripts, `data/`, `docs/`, and an empty `work/`. Repository-side material — CI workflows, the ZIP import pipeline, the README — no longer ships inside it. `verify_release_assets.py` moved into `data/` and the pinned-asset table into `docs/`, so the archive root carries no loose tooling.
- Removed the stale `_incoming/` RC24 ZIP-parts manifest and dropped the parenthesis from the import workflow's filename.
- Fixed release notes losing their backtick-quoted values: the notes heredoc is unquoted, so every `` ` `` ran as command substitution and the published RC24 notes shipped with an empty archive name and SHA256.

### Credits

- Hardware run and original patch: Mikhail Skvortsov. The read-only-flow and write-authorization corrections came out of the RC24 review pass.

# 1.0.0-rc24 — persistent interactive menus

## 1.0.0-rc24 — 13 August 2026

### Repository sync — 14 August 2026

- Fixed stale current-version references in README/IMAGE_STATUS and `release.version` in MANIFEST; runtime/firmware payloads are unchanged.
- Architecture documentation now records the actual RC22 bad-block restore result: the stock main image/kernel booted, but the `data` UBIFS did not recover and triggered a watchdog reboot; this restore is not classified as HW PASS.
- GitHub repository import was updated for the complete RC24 layout, including ARCHITECTURE RU/EN, FIRMWARE_CAPABILITIES, root VERSION, and split `_incoming` ZIP parts.

- After success or an ordinary recoverable error, the interactive wizard stays open and offers `back to section / main menu / exit`.
- Invalid selections in the main/submenus and startup-mode selector now only re-prompt.
- `firmware`, `backup`, `credentials`, and `service` actions use one interactive wrapper; direct CLI subcommands retain standard process exit codes.
- `WRITE_STATE_UNKNOWN` sets a process-local `SAFETY-LATCH`: normal install, no-UART restore, and destructive Stage 2 are blocked; a successful full BootROM/UART recovery clears the latch.
- `KeyboardInterrupt`/`BaseException` are not swallowed by the wrapper, so an interruption during NAND activity cannot be reinterpreted as an ordinary cancellation that permits a retry.
- Firmware/transition/recovery payloads are byte-identical to RC23.

# 1.0.0-rc23 — timestamps and backup MAC metadata

## 1.0.0-rc23 — 13 August 2026

- Added an absolute local `[YYYY-MM-DD HH:MM:SS]` timestamp to operator-facing PC wizard lines and prompts.
- Input/getpass prompts now receive a log-only terminating newline so `LATEST.log` and the timestamped session log do not concatenate the next event with the prompt.
- Live-stock TFTP backup creates a SHA256-covered `DEVICE_MAC.txt` containing model/family, capture time, primary `eth0` MAC/fallback, and all discovered sysfs MACs; resume on a different known MAC is blocked.
- The USB backup agent creates the same `DEVICE_MAC.txt`; family is passed to the agent explicitly.
- Backup validation displays the source MAC when metadata is present; legacy backups without MAC metadata remain compatible.
- Recorded current HW evidence: the exact RC22 MF install completed `[1/8]..[8/8]` and production SSH+LuCI verification PASS. RC22 UART bad-block restore remains not fully validated because `/data` UBIFS recovery failed and caused a boot loop after restore.
- Firmware payloads are unchanged from RC22.

# 1.0.0-rc22 — bad-block-aware BootROM stock restore

## 1.0.0-rc22 — 13 August 2026

- Fixed a critical UART/BootROM restore defect on NAND with bad blocks: fixed 8-MiB `mtd write` commands could cross a bad eraseblock; U-Boot then skipped it and compacted the stream, while the next nominal chunk still started at the old physical offset and could re-program already written pages.
- `mtd bad bl2` and `mtd bad ubi` are now required before any erase/write; a bad BL2 eraseblock blocks restore before the destructive stage.
- Inside the canonical stock span, automatic handling is allowed only for bad blocks in the stock UBI-backed mutable physical region `0x052C0000..0x0EB60000` (config/data/oopsfs/log_truncated). A bad block in raw-critical bootloader/kernel/rootfs/flags fails closed because stock BMT mapping is not proven.
- After `mtd erase ubi`, the bad-block map is scanned again before the first IBU write. Each 8-MiB source chunk is split into contiguous physical good spans; RAM and NAND offsets advance identically, so a known bad PEB creates a physical hole rather than stream compaction.
- Every good span is read back and CRC32-verified. The bad-block map is checked again before BL2 and must remain exactly stable; any change blocks BL2.
- BL2 remains strictly LAST. Transition/recovery/production firmware payloads are byte-identical to RC21; RC22 changes PC-side U-Boot restore orchestration, metadata, and documentation.

# 1.0.0-rc21 — resilient Stage 5 and TFTP-first UI

## 1.0.0-rc21 — 13 August 2026

- Stage 6 switches to 350 ms polling after `[6/8]` so the short `[7/8]` and `[8/8]` window is not normally missed; if network handoff still hides them, strict production board/UBI verification reconciles them as post-boot verified events.
- A stalled reboot after `sysupgrade successful` now has a content-gated manual reboot path: timeout alone never authorizes power cycling; the operator must explicitly confirm the exact UART `sysupgrade successful` marker.
- Replaced the awkward `NET-DEBUG ... (not state identity)` line with concise `[NET] TCP ports:` telemetry.
- USB transport labels now state unambiguously that the USB drive is attached to the Nokia and the PC reaches it through Samba/FTP. TFTP remains choice 1, default, and recommended.
- Existing-backup install now prints explicit mtd0..mtd16 completeness, family/variant, canonical mtd16 span, and SHA256-manifest validation.
- Credentials from successful startup Web auto-detection are retained only in process memory and reused; installation no longer asks for the same Web credentials again.
- Added a Rich-colored startup banner: brown Unicode bear, cyan product name, green version/build tag. Rich 15.0.0 is vendored; no pip/network dependency is required.
- Transition/recovery/production payloads are unchanged from rc20.

- Fixed the stock Telnet disconnect seen after a long wait at `CONFIRM FORMAT AND FLASH`: after confirmation the wizard re-proves the root shell, reconnects if needed, and repeats the complete read-only `INSTALL.sh --preflight` before dispatching `--flash`.
- After an attempt to dispatch `--flash`, any disconnect/WinError/timeout becomes `STAGE1_HANDOFF_UNKNOWN`. Automatic destructive relaunch is forbidden; the wizard proceeds only with read-only transition/production observation.
- Removed the second “install a custom OpenWrt image” entry from the connection-method menu. Bundled/custom sysupgrade is now selected exactly once in the installation menu. Choosing a custom image no longer silently bypasses the model gate.
- TFTP is now first, the Enter default, and explicitly marked **recommended** in every operator transport menu. Backup uses TFTP first and USB second; installation-package transport uses TFTP first, then Samba and FTP.
- RC19 firmware payloads (MD/MF transition/recovery/production) are not rebuilt; RC20 changes PC-side orchestration, metadata, and documentation only.

# 1.0.0-rc19 — recovery transport hardening

- Restored pinned AArch64 `nokia-tftp` and `nokia-scp` in every MD/MF transition/recovery initramfs. `nokia-tftp` is a router-side TFTP GET client; the server remains on the PC.
- Fixed the RC16–RC18 packaging regression where recovery-client sources stayed in the release but the binaries disappeared from the Dark-based recovery images.
- Restore order is now `nokia-tftp -> TCP/nc -> SCP`; large-IBU SCP staging is no longer preferred.
- Critical safety fix: after `mtd write` is issued, a network failure is no longer treated as an ordinary transport failure. State becomes `WRITE_STATE_UNKNOWN` and automatic retry over another transport is forbidden.
- Recovery SSH now follows the transition policy: Dropbear `-B`, deterministic none-auth probing, and no dependency on the operator `known_hosts`.
- RC18 RECOVERY_SAFE FIPs, production MD Dark/MF Uname payloads, and BL2-LAST ordering remain unchanged.

# 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- Fixed a critical BootROM recovery defect: the ordinary AN7581 RAM U-Boot used `bootdelay=0` and could reach first-boot `ubi_format -> mtd erase ubi` before an interactive prompt was proven. A U-Boot banner is no longer considered control of the bootloader.
- RC18 ships recovery-only SAFE FIP derivatives for AN7581 and AN7583. BL31 is preserved byte-for-byte; BL33 gets `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, and neutralized persistent UBI environment volume names so NAND `ubootenv/ubootenv2` cannot re-enable autoboot.
- After a stable prompt, `master.py` requires the exact SAFE marker, `bootdelay=-1`, inert bootcmd, and a fresh nonce. No NAND write/erase/saveenv capability exists before this gate; only UART/XMODEM and then read-only geometry are allowed.
- Ctrl-C after the banner remains only a secondary safety net: it is sent as a paced series until the prompt, not once. The primary safety boundary is inside the recovery BL33.
- Linux fallback after a missed BootROM-recovery U-Boot prompt is disabled fail-closed for both families.
- Full stock restore retains the existing invariant: body/IBU erase+write+readback first, exact stock BL2 LAST. U-Boot prints the `mtd erase ubi` range relative to the partition; physical BL2 is outside that erase.
- LAN1/2.5G remains prohibited for every transition/recovery process; use LAN2/LAN3/LAN4.
- Exact RC18 SAFE FIP bytes require the first hardware regression before promotion to HW CONFIRMED.

- RC18 packaging correction: the first published RC18 failed closed before COM was opened with `BL33 LZMA decode failed`. The builder used Python `FORMAT_ALONE` (which emits EOPM) and then rewrote the header from unknown-size to known-size. One liblzma accepted that mixed form while strict Windows liblzma correctly returned `Corrupt input data`; BootROM decoder compatibility could not be claimed either.
- SAFE BL33 is now encoded with `LZMA_FILTER_LZMA1EXT` in the same representation as the source Airoha payloads: known uncompressed size + **no EOPM**. Runtime preflight no longer decodes BL33 on the operator PC: exact whole-FIP and compressed BL31/BL33 SHA256 are the release gate, while full decode/marker audit remains part of build/release QA.

# 1.0.0-rc17fix5 — transition/recovery LAN1/2.5G safety policy

- LAN1 / 2.5G is treated as an unstable transport and is prohibited for every transition/recovery operation; operators are explicitly directed to LAN2/LAN3/LAN4.
- Added the actual build-time patcher `data/recovery/transition-network-source/patch_transition_network.py`. It size-preservingly patches initramfs `02_network`, rebuilds FIT hashes, and fail-closed disables the `2500base-x` MAC in DT.
- MD/MF auto/manual transition and stock-recovery no longer create/enable LAN1; exact initramfs network scripts contain no literal `lan1`.
- MD/MF production sysupgrade payloads remain byte-identical to the previous release; destructive installer ordering is unchanged.
- Corrected the old documentation invariant: active DSA user ports are LAN2/LAN3/LAN4; `lan1..4` is no longer a hardware PASS criterion.

# 1.0.0-rc17fix4 — recovery DT hardening / pre-SSH diagnostics

- Fixed the MF stock-recovery release blocker: the recovery FIT no longer carries the production DT. `all_flash` remains read-only, `bl2` is writable only in RAM recovery, `mtd2=ibu`, and there is no pre-restore `linux,ubi` auto-attach.
- MD and MF stock-recovery now use the same fail-closed pre-restore NVMEM topology: read-only raw `ri-stock` at `0x05200000/0x00040000`, `macaddr@3e` (`mac-base`, 6 bytes), with Ethernet MAC consumers bound to that raw RI provider. Recovery Ethernet no longer depends on the future UBI `ri` volume.
- `docs/dtb-evidence/` carries byte-exact DTBs for MD/MF recovery/transition/production. QA now proves for both families that recovery != production, recovery BL2 is writable, `ibu` has no `linux,ubi`, Ethernet uses raw-RI MAC NVMEM, and Ethernet/switch and active DSA LAN2/LAN3/LAN4 are present.
- Manual READY no longer uses the approximate `/proc/net/route` fallback. The exact address is parsed from `/proc/net/fib_trie`, with exact `ip -4 addr` output as fallback.
- Both manual initramfs images contain `uhttpd` and its init script. The PC master can now consume `/www/medveflasher-manual.status` as content-based pre-SSH diagnostics; READY and custom image transfer still require SSH content identity.

# 1.0.0-rc17fix3 — persistent manual READY / reviewable DT evidence

- Manual transition no longer freezes at `NETWORK_NOT_READY` after 60 seconds. The family/LAN/SSH readiness monitor runs in the background until READY, so the PC-side 600 s retry now observes state that can actually change.
- The READY gate no longer depends on `netstat`: SSH LISTEN is parsed from `/proc/net/tcp{,6}`, LAN 192.168.1.1 from `/proc/net/fib_trie` / `/proc/net/route`; `ip` is fallback only. Preflight confirms `sbin/ip`, `bin/netstat`, and `bin/cat` exist in both manual initramfs images.
- `/tmp/NOKIA_MANUAL_STATE` and `/www/medveflasher-manual.status` now expose ASCII key/value diagnostics: `STATE`, `REASON`, board, br-lan/IP/SSH flags, and `DEFERRED`.
- Auto transition still performs destructive work autonomously, while Ethernet is required for PC-side live progress/control-plane telemetry. MF/MD transition DTs retain the raw `ri-stock` pre-format NVMEM policy.
- `fullflash` rc=0 without reboot is no longer classified as FAILED; it becomes verification-pending and requires production verification.
- `docs/dtb-evidence/` contains byte-exact DTBs extracted from MD/MF auto/manual transition, stock-recovery, and production sysupgrade images, allowing REVIEW_ONLY to independently inspect NVMEM/MTD/network topology without runtime ITBs.

# 1.0.0-rc17fix2 — transition network / Dark MD audit

- Fixed the root cause of missing Ethernet in MF transition before formatting: MAC NVMEM now comes from read-only raw stock RI at `0x05200000+0x3e`, not from the future UBI `ri` volume. This applies to auto and manual transitions.
- Auto mode needs Ethernet for PC-side live progress/control-plane, not for the autonomous destructive installer itself. RC17fix2 restores that channel.
- MF target `mtd2` keeps label `ubi` for compatibility with the hardware-confirmed installer, while pre-format `linux,ubi` auto-attach is disabled.
- All MD ITBs were audited. Production sysupgrade and stock recovery were already Dark 6.18.41; auto/manual transition were still old 6.18.39 r35573. RC17fix2 rebases both transitions onto the selected Dark 6.18.41 / r0-486b4a4 kernel and a minimized initramfs while retaining the fail-closed installer gates.
- Manual readiness is family-specific; the MF path no longer contains an MD board-name hardcode.

## 1.0.0-rc17fix

- Fixed a critical UART stock-restore false positive: after BL2 readback, `reset` is sent through the paced U-Boot line helper and a fresh boot must be independently confirmed on UART.
- An open TCP/80 or TCP/443 is no longer proof of stock boot. The actual Nokia stock login page content (`pubkey` fingerprint) is required.
- If automatic reset is not confirmed, the wizard explicitly states that NAND restore is already PASS and one manual power-cycle is now safe; monitoring continues without Enter.
- If stock boot cannot be proven, the final state is `POST_RESTORE_BOOT_UNKNOWN`, never a false SUCCESS.
- Firmware payloads and transition bundles are byte-identical to RC17; only PC-side orchestration, metadata, and documentation changed.

## 1.0.0-rc17

- MF-A RC16 hardware evidence confirms the refreshed EVB XMODEM pair, RAM U-Boot, full stock restore, BL2-last [7/8], [8/8], production sysupgrade, and OpenWrt boot.
- Transition monitoring now has an exact HTTP marker/status/log endpoint; ports 22/23/80/443 are NET-DEBUG telemetry only and never identify state.
- WAITING_FOR_SYSTEM is correctly treated as pre-destructive normal-init wait, not production handoff.
- A single controlled power-cycle is suggested after 120 s only if the control plane explicitly reported SAFE_TO_POWER_CYCLE=1 and destructive step 1/8 was never observed.
- Restore Stock over SSH is bound to the validated backup family; MF no longer falls through an MD-only gate.
- START exposes brick BootROM/UART recovery before stock Web auto-detection.
- On-device shell payloads are ASCII/English only; localization remains PC-side in master.py.
- Final production verification requires board + canonical UBI volumes + OpenWrt release + LuCI content probe.
- RC17 auto-transition identity: MD bundle `21626880` / `47631c782b75aef2a13082a4da2ffcee687742d8d743ed357a5753236b640962`, FIT `7509716` / `4a898c31dc69065decc267d5ede173530932079d5fc75344a417cf4e5946d392`; MF bundle `17694720` / `988fb4aa960441aa7176672c23181a373f54690fcc9a63389124adc8c7a6a188`, FIT `7649300` / `be365db3dabf68eb4e5cad56087e5af241f8fdb2c24c8936bf427d57cf7e469c`. Production tails at `0x800000` are byte-identical to RC16.

## 1.0.0-rc16 — 12 August 2026

- MD/AN7581 production payload is refreshed to the selected Dark patched 2026-08-09 snapshot (`r0-486b4a4`, kernel 6.18.41). Embedded sysupgrade: `13226255` bytes, SHA256 `c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03`; LuCI is confirmed by direct filesystem inspection.
- MD stock recovery now uses the Dark kernel/rootfs. Selected source initramfs: `11141120` bytes, SHA256 `a8e24301925c4a7b120594b61aa679bac835b26ef70736fd28a69c9029ffda3b`. Shipped MedveFlasher recovery FIT: `11099648` bytes, SHA256 `c709d3824a968ef2f671176ce159b1c87cbe7a07cd54a9d8849a016ee8ade1ac`; only the recovery DT is rebuilt: `all_flash` RO, `bl2` writable only in recovery, `ibu=0x20000..0x10000000`.
- MD automatic transition is rebuilt around the exact new sysupgrade: `21626880` bytes, SHA256 `5e658b2c50719db5e552c0c047aea0d58044ebcbea016a3e61707b2c62d3affe`; manual transition remains exactly 8 MiB, SHA256 `0baac2ee30e752893942edf614aa0515117abb5fae10985d200879a2c226bb56`.
- MF/AN7583 keeps the Uname production UBI build-set unchanged: sysupgrade `9191705` / `db881b80…`, production preloader `118333` / `778d10a6…`, FIP `319568` / `99b6c20a…`, stock-recovery initramfs `7471104` / `65c3b1a6…`.
- MF EVB BootROM/XMODEM recovery pair remains bundled/offline: preloader `118322` / `c2ac1c18…`, FIP `339224` / `b2f5f93f…`. The refreshed exact-byte pair itself was HW-confirmed on Nokia XG-040G-MF by the RC16 full BootROM/XMODEM stock-restore run on 2026-08-12.
- Fixed stale MF `transition_fit_totalsize` values from rc15fix: auto `7649360`, manual `7648816`. `verify_kit()` now binds MANIFEST size/SHA/FIT totalsize/FIT SHA/production size+SHA to the actual four transition bundles and fails closed on drift.
- Removed the unused stale MF snapshot-initramfs pin from the active recovery metadata contract. Runtime recovery downloads/cache fallback remain forbidden.
- Preserved rc15/rc15fix safety invariants: transition-only writable BL2, production BL2 read-only, repeated pinned BL2 provenance gate before `[7/8]`, BL2-last + readback, stage2 SSH/Telnet read-only monitoring, and immediate stop on `FAILED`.
- RC16 MD payload refresh passed static/FIT/DT/SHA/LuCI QA; hardware regression of the refreshed MD payload-set remains required before raising it to HW-confirmed status.

## 1.0.0-rc15fix — 11 August 2026

- MF emergency BootROM/UART recovery is repinned to the AN7583 EVB stages from the OpenWrt snapshot observed on 2026-08-11: preloader `118322` / `c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f` and BL31+U-Boot FIP `339224` / `b2f5f93f52afbaf539fe362267b13a91fb0a3a22c4ea770f2fc984dece176c12`. They are mandatory inside the full rollup and verified locally before BootROM/XMODEM; runtime download is absent. The recovery flow was hardware-confirmed earlier; the refreshed exact-byte pair is marked for HW re-confirmation.
- Removed runtime download and the `work/recovery-cache/mf` fallback. Snapshot metadata is provenance only; recovery does not need network access before RAM U-Boot is captured.
- `verify_kit()` and the UART recovery path both fail closed on exact size/SHA256 verification of the bundled AN7583 stages.
- Fixed the `continue without profile` UI: the recovery menu reports `no profile selected (MD/MF)` instead of MD. Installation is blocked without a profile; BootROM/UART restore still derives the family from the validated stock backup.
- After opening COM, brick recovery enters `[READY]` and monitors `Press x / C` immediately; the extra Enter prompt is removed and the first RX buffer is preserved so an already-present BootROM prompt cannot be discarded.
- The failed rc15 mutable-snapshot run stopped during payload preparation, before opening the BootROM/XMODEM session and before any NAND write.

## 1.0.0-rc15 — August 11, 2026

- The rc14fix6 MF-A hardware run confirmed transition boot, UBI format/attach, canonical volume creation, and bosa/ri/FIP/fallback-FIT readback. BL2-last was correctly stopped by Linux because the transition DT inherited the production `read-only` flag on `bl2`.
- MF auto/manual transition DTs now expose writable `bl2` plus a dedicated `medveflasher,transition-writable-bl2` marker; production sysupgrade/FDT bytes are unchanged and keep `bl2` read-only.
- Before format the installer requires the transition marker and MTD_WRITEABLE on BL2. Immediately before `[7/8]` it rechecks exact pinned preloader/FIP size+SHA256, complete BL2 SHA256, FF prefix, and payload at 0x800.
- Auto-transition Dropbear now offers the deterministic BatchMode path required by the wizard; the shared MD/MF stage2 monitor uses SSH with a read-only Telnet fallback for state/log retrieval. `FAILED` is surfaced immediately.
- BACKUP_HW_VALIDATED, live MF-A gates, explicit confirmation, UBI readback and BL2-last ordering are unchanged.

## 1.0.0-rc14fix6 — August 11, 2026

- Fixed the root cause of false `RAM BusyBox applet missing: ...` failures: the self-test no longer parses no-argument `busybox` text as an applet inventory. Vendor BusyBox on MF may omit `Currently defined functions`, making the old check fail on the first requested applet regardless of actual availability.
- Every actually required RAM applet is now tested with a direct `staged-busybox <applet> --help` probe; probe stdin is `/dev/null` so the pre-write self-test cannot stall waiting for input.
- Clarified the rc14fix5 diagnosis: removing `awk` from RAM SHA parsing remains valid, but `missing awk/dd` did not prove the applet itself was absent.
- UART FIFO isolation, shared MD/MF engine, payloads, safety gates, readbacks and BL2-last are unchanged. All probes still run before erase/write.

## 1.0.0-rc14fix5 — August 11, 2026

- Fixes the MF stock BusyBox blocker `RAM BusyBox applet missing: awk`: the RAM worker no longer requires `awk` as a BusyBox applet. `sha256sum` output is parsed with POSIX shell parameter expansion and no external tool.
- Stock-side preflight may still use the vendor standalone `awk` while the stock rootfs is present; the destructive RAM path does not depend on it.
- Keeps the rc14fix4 UART FIFO hotfix unchanged. Safety gates, transition/readback, `BACKUP_HW_VALIDATED`, MF-A geometry, and BL2-last ordering are unchanged; the observed failure was before erase/write.

## 1.0.0-rc14fix4 — August 11, 2026

- Fixed the live MF-A blocker `tee: /dev/console: I/O error`: vendor stock exposes `/dev/console` with suitable mode bits while an actual write may still return `EIO`.
- UART is no longer a direct output of the primary `tee`. Caller/session/USB logging is independent; UART receives a copy through a separate draining FIFO relay. If UART returns `EIO`, the relay keeps draining and disables only serial duplication.
- Serial auto-detection prefers `/dev/ttyS0` before `/dev/console`. The output-mirror implementation banner is removed from the operator console.
- Destructive gates, MF-A geometry, `BACKUP_HW_VALIDATED`, explicit confirmation, readback, and BL2-last ordering are unchanged. The rc14fix3 failure happened before erase/write.

## 1.0.0-rc14fix3 — August 11, 2026

- Refactors MD and MF onto one profile-driven installer engine: shared `install_openwrt_wizard(profile, ...)`, shared personalization, and one `data/stock-launcher.sh.in`; board-specific differences live in `InstallProfile` and strict hardware gates.
- Synchronizes the MD/MF menus: install with mandatory backup, install from an existing backup, stock restore, BootROM/UART recovery, and capabilities. The auto/custom sysupgrade submenu is identical.
- Removes runtime repacking from the architecture: ready auto/manual bundles are used directly. Standalone MF auto/manual transition FITs, the standalone MF sysupgrade, and standalone production preloader/FIP are removed as duplicates of the ready bundles/initramfs payloads.
- Retains the rc14fix2 BusyBox `sh` fix. MF-A `BACKUP_HW_VALIDATED`, live MF/UID0/MTD gates, readback, and BL2-last ordering are unchanged.

## 1.0.0-rc14fix2 — August 11, 2026

- Fixes the live MF-A permanent stage-1 blocker: the stock BusyBox RAM-staged binary does not expose a separate `ash` applet. The worker now runs through BusyBox `sh`; destructive sequencing is unchanged.
- Makes the MF flashing menu device-specific: VERIFIED MF no longer shows MD-only actions or internal capability banners.
- Compresses console preflight to gate summaries. Full technical transcript is retained only in the timestamped `session-*.log`; `LATEST.log` remains operator-clean. Raw Telnet command/RC markers are no longer printed on the failure path.
- Fail-closed gates, `BACKUP_HW_VALIDATED`, live MF-A `/proc==sysfs`, explicit confirmation, readback, and BL2-last ordering are unchanged.

## 1.0.0-rc14fix — August 11, 2026

- Enables the permanent all-in-UBI installer for hardware-confirmed stock **MF-A**. `BACKUP_HW_VALIDATED`, live Web/Telnet/UID0, a fresh MF-A `/proc/mtd == sysfs` gate, and the exact `CONFIRM FORMAT AND FLASH` phrase are mandatory.
- The architecture mirrors MD: the stock stage writes the transition bundle to `mtd14/nsb_master` with full readback SHA256, then writes the personalized environment in the final `mtd0` erase block; after reboot the MF transition performs the UBI migration.
- Auto mode embeds the MF UBI sysupgrade, size `9191705`, SHA256 `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b`. Manual mode is exactly 8 MiB with no production payload and accepts a user-selected sysupgrade after remote `sysupgrade -T`/installer validation.
- Pinned MF UBI build-set: preloader SHA256 `778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e`, FIP SHA256 `99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7`, target `airoha/an7583`, board `nokia,xg-040g-mf-ubi`.
- The transition preserves stock `bosa/ri`, formats only the future UBI region after BL2, creates fixed UBI volume IDs 0..5 (`ubootenv`, `ubootenv2`, `bosa`, `ri`, `fip`, `fit`), writes and reads back bosa/ri/FIP/fallback FIT; the complete BL2 with the mandatory `0x800` FF prefix is written **last** and read back.
- For live MF-A, `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, and `CAP_PERMANENT_INSTALL` are now `ENABLED - EXPERIMENTAL`; they are not labeled hardware-confirmed until the first successful permanent run. MF-B/MIRROR write paths remain blocked.
- The hardware-confirmed UART/BootROM full-stock restore path is unchanged and remains the emergency rollback. The MD install path is not refactored.

## 1.0.0-rc14 — August 11, 2026

- Adds `CAP_MF_TRANSITION_BOOT` and a dedicated hardware test for **MF-A only**: verified stock Web → Telnet/UID0 → `BACKUP_HW_VALIDATED` → live MF-A `/proc/mtd == sysfs` → TFTP deployment of a device-specific transition package.
- New `data/mf-transition-bundle.bin` is the pinned MF recovery initramfs zero-padded to `0x800000`; SHA256 and FIT totalsize are pinned in code/MANIFEST/SHA256SUMS. It contains no sysupgrade payload.
- New `data/stock-mf-transition-launcher.sh.in` is isolated from the hardware-confirmed MD launcher. It accepts only MF-A, writes `mtd14/nsb_master` first, verifies full readback SHA256, rechecks the untouched source env, then erases/writes only `mtd0+0x60000..0x7ffff` (`0x20000`) last and verifies readback.
- After reboot, the PC proves RAM OpenWrt through LuCI or SSH board identity and records `MF_TRANSITION_HW_VALIDATED.json`; the workflow **stops there**. `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, and `CAP_PERMANENT_INSTALL` remain BLOCKED.
- MF-A transition requires a backup carrying `BACKUP_HW_VALIDATED`; MF-A-MIRROR/MF-B/MF-B-MIRROR are recognized but blocked from the rc14 write gate.
- UI labels MD install entries `[MD ONLY]` and exposes a separate `[MF-A HW TEST]` item.
- Established MD install/restore and BootROM backup/restore paths are not refactored.

## 1.0.0-rc13 — August 11, 2026

- The repeat live MF-A rc12fix run completed end-to-end: all `mtd0..mtd16` were captured through `*ro`, `mtd16` passed `router gzip stream SHA256 == PC file SHA256`, followed by `verify_stock_restore_backup()` and `BACKUP_HW_VALIDATED`. For a live MF-A, `CAP_FULL_BACKUP` is now `YES - HW CONFIRMED`.
- The flashing menu now has a read-only **firmware capabilities** probe. It re-proves Web/Telnet/UID0/MTD family+variant and renders release-level hardware gates.
- Added machine-readable `data/FIRMWARE_CAPABILITIES.json` and expanded the stock-audit parser with `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, `CAP_PERMANENT_INSTALL`, and `CAP_UART_RECOVERY`.
- In rc13, MF `CAP_UBI_FORMAT`, `CAP_UBI_VOLUME_WRITE`, `CAP_BOOTLOADER_REPLACE`, and `CAP_PERMANENT_INSTALL` remain `BLOCKED`; no new destructive MF write commands were added. `CAP_RAM_OPENWRT=PARTIAL`: RAM recovery is confirmed, while the normal-install transition remains a separate HW gate.
- When startup has `[DEVICE] ... MF [VERIFIED]`, MD-only install entries and stage 2 from verified stock MF fail closed earlier with an explicit capability message. The proven MD bootcmd+transition+UBI path is unchanged.
- Fixed the stale MF-backup success wording: `second-read SHA256` now correctly says `transport-stream SHA256`.

## 1.0.0-rc12fix — August 11, 2026

- Fixes the hardware-observed false fatal gate in normal MF backup: a second full `mtd16` read no longer has to match the first snapshot because running stock mutates `config/data/log` while the multi-minute capture is in progress.
- `mtd16` transport integrity is now checked against the **exact transmitted gzip stream**: `gzip -1 | tee FIFO | tftp` with a parallel Nokia-side `sha256sum`; the router stream SHA256 must match the received PC `.gz` SHA256.
- MF `mtd16` resume no longer compares a retained snapshot against current live NAND. A retained file is accepted only after gzip/exact-size PASS and a valid `mtd16_transport_sha256.txt`; an old rc12 snapshot without transport evidence is recaptured.
- TFTP progress now uses adaptive `B/KiB/MiB/GiB` units, removes misleading initial `0.0 MiB`, uses `[1/17]..[17/17]`, and reports both raw and compressed sizes on completion.
- The live rc12 MF run confirmed Web/Telnet/root, MF-A, `/proc/mtd == sysfs`, `*ro` reads, and successful TFTP PUT for all 17 MTD devices including full `mtd16`; completion was blocked only by the old second-read gate.
- Final `verify_stock_restore_backup()` and the ordering of `BACKUP_COMPLETE`/`BACKUP_HW_VALIDATED` are unchanged. Permanent MF installation remains disabled.

## 1.0.0-rc12 — August 11, 2026

- Adds read-only XG-040G-MD/XG-040G-MF auto-detection through the stock Web UI immediately after language selection. Manual MD/MF selection is UI fallback only and never replaces live Web/MTD gates before backup/write.
- Enables normal MF stock backup through the running stock firmware: Web credentials -> Telnet -> proven UID 0 -> `/proc/mtd` + sysfs cross-check -> MF-A/MF-B -> `/dev/mtd*ro` reads -> gzip/TFTP PUT to the PC.
- MF `mtd16` is verified after transfer by an independent second `/dev/mtd16ro | sha256sum` read; resume rechecks a retained `mtd16` against the current NAND before accepting it.
- A completed TFTP backup is passed through `verify_stock_restore_backup()`: family/variant, exact sizes, manifest, stable-slice consistency with canonical `mtd16`, and rejection of known OpenWrt preloader layouts in stock BL2. `BACKUP_COMPLETE` and `BACKUP_HW_VALIDATED` are written only after that validator passes.
- MF USB backup prefers read-only MTD nodes and is gated by UID 0 plus `/proc/mtd`/sysfs consistency.
- Fixes the stock-audit parser to use `CAPABILITY-EVIDENCE` as a Model/SoC fallback when the stock DT/sysinfo omits them. The real MF audit now renders `XG-040G-MF / AN7583DT`.
- Extends the read-only audit with `/proc/cmdline`, broader dmesg, sysfs NAND/UBI inventory, and metadata/strings/text capture for discovered upgrade utilities. BusyBox 1.16 compatibility replaces `grep -x` with a portable exact-line pattern.
- Accepts the live rc11 MF audit as hardware evidence: Web/Telnet are verified, `user_ftp` has UID/GID 0, `su` is BusyBox, MF-A and `mtd16=0x0EBA0000` are confirmed, and `/proc/mtd` matches sysfs.
- Permanent MF installation remains disabled. The hardware-confirmed MD bootcmd+initramfs installation path and UART restore paths are unchanged.

## 1.0.0-rc11 — August 10, 2026

- Diagnostic MF/MD build: adds an integrated stock audit path Web -> Telnet -> interactive `su` -> mandatory `id -u = 0` -> MTD/UBI/users/upgrade inventory.
- Adds the second field-observed MF layout `MF-B`: `mtd2=0x003B6D40`, `mtd3=0x01D10000`, `mtd4=0x00480000`, `mtd5=0x02400000`, plus its mirrored form. MF-A remains accepted.
- Renames `STOCK_ALL_FLASH_SIZE` to `STOCK_RESTORE_SPAN`; `0x0EBA0000` is now explicitly the stock restore span, not physical NAND capacity.
- Stock audit derives physical NAND only from NAND-driver/dmesg evidence and cross-checks `/proc/mtd` against sysfs; stock `mtd0` is no longer misinterpreted as the entire NAND.
- The PC parser does not infer Web/Telnet/root capabilities from the model: root requires `uid=0 + rc=0`; upgrade write verbs are accepted only from explicit `AUDIT_HIT` markers.
- BootROM backup gains a runtime destructive-command firewall and selftest; normal/permanent MF installation remains blocked pending a separate hardware gate.
- Adds `docs/OPENWRT_TODO_RU.md` / `OPENWRT_TODO_EN.md` and standalone `data/diagnostics/mf-stock-audit.sh` + `mf_audit_parse.py`.
- MF UART stock restore status is updated to hardware-confirmed full restore.

## 1.0.0-rc10fix2 — August 10, 2026

- MD/MF BootROM backup no longer uses SSH/Dropbear: the recovery FIT boots with `rdinit=/bin/sh`, UART controls a minimal BusyBox shell, and Ethernet is used only for TFTP PUT.
- Before the first NAND read, the wizard verifies the model, `all_flash=256 MiB`, required BusyBox applets, and a tiny RAM-only TFTP PUT probe.
- Every NAND chunk is read only from `/dev/mtd0`, transferred as `gzip` over TFTP, then checked against a second independent `dd | sha256sum` read. `erase`, `write`, `saveenv`, UBI attach/mount, and SSH are not used in the backup path.
- Fixes the hardware-observed MF case where TCP/22 was open but Dropbear rejected SSH because of blank-root policy; SSH retry was removed instead of hiding the cause.
- Resume re-hashes every retained chunk from the current NAND before skipping it, preventing a directory from another device from being silently mixed into a new backup.


## 1.0.0-rc10fix — 10 August 2026

- Fixed the credential audit when the stock Web UI terminates a request with `Remote end closed connection without response`. The HTTP transport now retries transient disconnect/reset/URL failures and avoids keep-alive reuse (`Connection: close`).
- If encrypted login closes the socket and plain compatibility is explicitly allowed by the credential audit, the wizard now attempts the plain login form instead of aborting.
- A persistent Web failure in the credentials menu is now non-fatal: hardcoded/default values remain visible and, when Telnet is already open, an optional read-only `/etc/passwd`/`/etc/group` inventory can be run with manually entered device credentials.
- `data/__pycache__` is excluded from release rollups and `SHA256SUMS`.

# Nokia Router MedveFlasher changelog

## 1.0.0-rc10 — 10 August 2026

- Grouped the main menu into flashing/recovery, backup, and preparation/continuation; added a dedicated top-level credentials/users/privileges item.
- Stage 2 now explicitly means transition OpenWrt is already in RAM → verify → format UBI → flash sysupgrade → monitor first boot.
- Added credential audit for the Web default, device-specific Telnet/FTP/Samba secrets, `/etc/passwd` + `/etc/group`, UID/GID/groups/home/shell, and UID-0 credential verification without dictionary guessing.
- Secret output bypasses the logging tee and is console-only; logs receive only `[SECRET OMITTED FROM LOG]`.
- No unverified `telecomadmin` password is hardcoded; the account is reported when actually detected on the device.
- BootROM backup retries SSH handshake/probe after TCP/22 to handle the early Dropbear race observed as exit code 255.


## 1.0.0-rc9fix — 10 August 2026

- Removed the unnecessary manual `Enter` from menu item 8 BootROM/UART backup: after UART/IP/TFTP/destination selection the wizard opens the serial port and immediately starts live UART monitoring, leaving both hands free for Reset and power.
- `Press x` is detected automatically and the wizard sends `x`; repeated `C` characters advance directly to XMODEM without another keyboard confirmation.
- The RX buffer is no longer flushed on the **first** BootROM wait, so an already-arrived `Press x`/`C` sequence is preserved. Stale ACK/`C` cleanup remains enabled between the preloader and FIP stages.
- The rc9 MF hardware run confirmed automatic `Press x` → `C` → XMODEM AN7583 preloader transfer. rc9fix changes entry UX/synchronization only and adds no NAND write command to the read-only backup path.
- VERSION/MANIFEST/README/CHANGELOG/IMAGE_STATUS/ARCHITECTURE synchronized for rc9fix in Russian and English.

## 1.0.0-rc9 — 10 August 2026

- Added menu item `8 — create a read-only backup through BootROM/UART (MD/MF)`: BootROM/XMODEM starts the SoC-specific preloader and U-Boot in RAM, then a model-specific recovery FIT is loaded over TFTP and runs only from RAM. This mode never erases or writes NAND.
- Backup captures the first `0x0EBA0000` bytes of `all_flash` in 30 chunks of up to 8 MiB, sends gzip streams to the PC by TFTP PUT, and validates each saved chunk SHA256 against a second independent NAND read in recovery Linux. Verified chunks can be resumed via `.raw.sha256` sidecars.
- The PC synthesizes a conventional MedveFlasher `mtd0..mtd16` backup plus `bosa.bin`, `ri.bin`, `proc_mtd.txt`, `SHA256SUMS.txt`, and `BOOTROM_BACKUP.json`; the splitter/validator was tested against the real MF backup.
- Bundled MF stock-recovery FIT `data/recovery/mf/nokia-xg040gmf-stock-recovery-initramfs.itb`, SHA256 `65c3b1a610dd56fee917e1b7c30d23592821b1321cb0ed1134cccbad7fdd819c`, for the RAM-only read-only backup path.
- The rc8fix2 MF hardware run confirmed scripted `mtd list`, network `setenv`, and the first 8-MiB TFTP load. It also showed that AN7583 U-Boot has no `hash sha256`; the script stopped before any NAND write.
- U-Boot brick-restore verification now uses `crc32`: the PC source remains SHA256-pinned, while post-TFTP RAM and every readback are checked by CRC32. BL2 remains last.
- VERSION/MANIFEST/README/CHANGELOG/IMAGE_STATUS/ARCHITECTURE synchronized for rc9 in Russian and English.

## 1.0.0-rc8fix2 — 10 August 2026

- Fixed the second hardware-found MF brick-recovery blocker: after `[UBOOT_PROMPT]`, rc8fix still had delayed Ctrl-C input, so the first scripted `mtd list` did not execute; the operator confirmed the geometry manually in the UART shell.
- `wait_uboot_prompt()` no longer transmits Ctrl-C every 120 ms. A break is sent only after the U-Boot banner/menu appears; after a prompt the wizard requires UART quiet and clears stale input before commands.
- `uboot_command()` no longer sends `command; echo marker_RC_$?` on one line. The command and a separate return-code query now use two CR-terminated lines with light pacing and independent prompt waits.
- Manual `mtd list` on real XG-040G-MF/AN7583 hardware confirmed 256 MiB SPI-NAND, erase block `0x20000`, `bl2=0x20000`, and `ubi=0x0FFE0000`. The script did not write NAND in that run.
- VERSION/MANIFEST/README/IMAGE_STATUS/ARCHITECTURE are synchronized for rc8fix2 in Russian and English.

## 1.0.0-rc8fix — 10 August 2026

- Fixed the hardware-found MF brick-recovery blocker: OpenWrt AN7583 U-Boot on a real XG-040G-MF uses the `U-Boot>` prompt while rc8 accepted only `AN7581>`, `AN7583>`, and `=>`.
- Prompt detection now accepts line-boundary `U-Boot>` and the case where an already-sent Ctrl-C has appended `<INTERRUPT>`; break transmission stops immediately once the prompt is recognized.
- Hardware-confirmed the MF chain BootROM `C` → XMODEM AN7583 preloader → XMODEM BL31/U-Boot → U-Boot 2026.07 in RAM; AN7583, 512 MiB RAM, 256 MiB SPI-NAND, and Ethernet were detected. NAND writes had not started in this test.
- The read-only `mtd list` gate still runs before the first write and requires exact `bl2=0x20000`, `ubi=0x0FFE0000`, erase block `0x20000` geometry; MF Linux fallback remains disabled fail-closed.
- VERSION/MANIFEST/README/IMAGE_STATUS/ARCHITECTURE are synchronized for rc8fix in Russian and English.

## 1.0.0-rc8 — 10 August 2026

- Added the first **brick-recovery path for Nokia XG-040G-MF / AN7583**. Normal OpenWrt installation remains XG-040G-MD / AN7581 only.
- The restore validator no longer treats the MD-only `mtd2..mtd5` sizes as a physical `all_flash` invariant. Brick recovery classifies known MD/MF stock slot profiles separately while retaining strict `mtd0/mtd1/mtd6/mtd7/mtd14/mtd15` versus `mtd16` checks.
- Validated the supplied MF backup: `mtd16=0x0EBA0000`, all stable slices match, and the `mtd13/log` difference is correctly accepted as a live partition.
- The MF XMODEM profile uses official OpenWrt `airoha/an7583` snapshot artifacts: the AN7583 EVB preloader, AN7583 EVB BL31+U-Boot FIP, and Nokia XG-040G-MF initramfs. Exact sizes and SHA256 values are pinned in `data/recovery/mf/OPENWRT_SNAPSHOT.json`.
- If MF artifacts are not present locally, the wizard can fetch only the pinned rc8 files over HTTPS and accepts them only on exact size/SHA256 matches. A rotated snapshot stops the procedure before XMODEM/NAND.
- Added `AN7583>` prompt recognition while retaining generic `=>`. The Linux/recovery fallback is intentionally disabled for MF in rc8: failure to capture RAM U-Boot leaves NAND untouched.
- Added `python3 data/master.py fetch-mf-recovery` to prefetch and verify the MF recovery artifacts while the PC still has Internet access.
- `verify_kit()` now also fail-closes on mismatched root `VERSION`, `data/VERSION`, MANIFEST `version/build_tag`, or MF snapshot metadata.
- Added `docs/ARCHITECTURE_RU.md` and `docs/ARCHITECTURE_EN.md`; README, CHANGELOG, IMAGE_STATUS, and MANIFEST are synchronized for rc8.

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

