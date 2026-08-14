## 1.0.0-rc24 — regression gates

- HW/Windows: complete several different wizard actions in one process and confirm `section -> main -> next action` navigation without closing `START.cmd`.
- Induce a safe pre-write error and confirm return to menus without process exit.
- Separately test `WRITE_STATE_UNKNOWN`: SAFETY-LATCH must block normal install/no-UART restore/Stage 2 and clear only after successful full BootROM/UART recovery.

## 1.0.0-rc23 — regression gates

- HW-check timestamp presentation in the Windows console/LATEST/session log.
- HW-check `DEVICE_MAC.txt` for direct TFTP and USB backup, including equality with the source Nokia MAC.
- Do not promote the RC22/RC23 UART bad-block stock restore to production PASS until stock `/data` UBIFS restores without a watchdog boot loop.

## 1.0.0-rc22 — MedveFlasher regression gates

- HW: repeat MF/MD BootROM stock restore on NAND with known bad blocks and confirm physical good-span mapping, readback CRC32, and BL2-LAST.
- Stock Bootloader BMT Support remains a separate TODO: RC22 intentionally fails closed for bad blocks in raw-critical stock regions.

## 1.0.0-rc21 — MedveFlasher regression gates

- Hardware-test a long pause at `CONFIRM FORMAT AND FLASH`: an expired stock Telnet session must reconnect safely and repeat the read-only preflight.
- Induce a channel loss after `--flash` dispatch: expect `STAGE1_HANDOFF_UNKNOWN` and no destructive relaunch.
- Verify TFTP is default item 1 for installation and normal stock backup.

## 1.0.0-rc19 — restore transport

- Hardware regression: validate `nokia-tftp` streaming IBU restore on MD and MF.
- An induced network failure **before** `mtd write` may use safe fallback; after the `RESTORE_WRITE_STARTED` marker, automatic fallback must be blocked as `WRITE_STATE_UNKNOWN`.
- The known MD initramfs panic remains a separate upstream issue; do not conflate it with production/sysupgrade stability.

> rc18: BootROM recovery uses RECOVERY_SAFE RAM U-Boot with autoboot disabled by construction and prompt+nonce capability gating; exact safe FIP bytes are HW-regression pending. LAN1/2.5G remains prohibited for transition/recovery.
## 1.0.0-rc18 — RECOVERY_SAFE RAM U-Boot / prompt capability gate

- Fixed a critical BootROM recovery defect: the ordinary AN7581 RAM U-Boot used `bootdelay=0` and could reach first-boot `ubi_format -> mtd erase ubi` before an interactive prompt was proven. A U-Boot banner is no longer considered control of the bootloader.
- RC18 ships recovery-only SAFE FIP derivatives for AN7581 and AN7583. BL31 is preserved byte-for-byte; BL33 gets `bootdelay=-1`, inert `bootcmd/preboot`, marker `medveflasher_recovery_safe=rc18`, and neutralized persistent UBI environment volume names so NAND `ubootenv/ubootenv2` cannot re-enable autoboot.
- After a stable prompt, `master.py` requires the exact SAFE marker, `bootdelay=-1`, inert bootcmd, and a fresh nonce. No NAND write/erase/saveenv capability exists before this gate; only UART/XMODEM and then read-only geometry are allowed.
- Ctrl-C after the banner remains only a secondary safety net: it is sent as a paced series until the prompt, not once. The primary safety boundary is inside the recovery BL33.
- Linux fallback after a missed BootROM-recovery U-Boot prompt is disabled fail-closed for both families.
- Full stock restore retains the existing invariant: body/IBU erase+write+readback first, exact stock BL2 LAST. U-Boot prints the `mtd erase ubi` range relative to the partition; physical BL2 is outside that erase.
- LAN1/2.5G remains prohibited for every transition/recovery process; use LAN2/LAN3/LAN4.
- Exact RC18 SAFE FIP bytes require the first hardware regression before promotion to HW CONFIRMED.

> rc17fix5: LAN1/2.5G is prohibited for all MedveFlasher transition/recovery paths; use LAN2/LAN3/LAN4 only. Production 2.5G remains a separate experimental upstream/interoperability item.
> Historical rc17fix4: recovery DT hardening is statically closed before the first destructive MF/MD test: recovery-specific IBU/BL2/raw-RI topology for both families. Current HW gate is manual READY/network regression, then live auto progress; exact rc17fix4 recovery/transition bytes remain hardware-regression pending.
> Historical rc15 note: rc15: transition-only writable BL2 and stage2 live-monitor are integrated; next MF HW closure is BL2 write/readback + production sysupgrade + final boot.

# Nokia XG-040G-MD / XG-040G-MF — OpenWrt ToDo

Snapshot of the task list as of August 10, 2026. This is an upstream/interoperability roadmap for reference, not a MedveFlasher commitment. External PR status is not automatically refreshed by this document.

## High Priority

1. **[MF] USB Support** — testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24609

2. **[MF] LAN1 2.5 Gbit Port Operation** — **unstable for transition/recovery; MedveFlasher prohibits this port for every transitional/emergency procedure.** Testing here applies only to production OpenWrt/interoperability; use LAN2/LAN3/LAN4 for the flasher.  
   https://github.com/openwrt/openwrt/pull/24624

3. **[MD/MF] NPU Firmware Boot Fix & RAM Optimization** — testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24593

4. **[MF] OpenWrt U-Boot Support** — testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24654

5. **[MD/MF] OpenWrt U-Boot Reset Button Fix** — the reset button does not work in U-Boot; without UART, triggering TFTP recovery is impossible. Find the root cause and implement a fix.

6. **[MF] OpenWrt U-Boot Easy Installation Method** — provide a straightforward installation path; MedveFlasher is the current installer-utility workstream.  
   https://github.com/Medvedolog/nokia-router-medveflasher

## Medium Priority

1. **[MD] FUDAN SPI-NAND Support in OpenWrt U-Boot** — testing and feedback required.  
   https://github.com/openwrt/openwrt/pull/24624

2. **[MD/MF] LAN1 LED Behavior** — investigate build-dependent missing LED behavior and fix it.

3. **[MD/MF] Stock Bootloader Sysupgrade Bootloop** — reproduce and fix temporary post-sysupgrade bootloops with `Kernel panic - not syncing: Oops: Fatal exception`.

4. **[MD/MF] RCU Network Anomalies** — produce a proper bug report and documented reproduction steps.

5. **[MD] SkyHigh SPI-NAND Robust Read Workaround** — port and test the robust-read workaround.  
   https://github.com/openwrt/openwrt/pull/21896#issuecomment-3866937030

6. **[MD] LAN2-4 network activity LED blinking** — build firmware, hardware-test, and provide feedback.

## Low Priority

1. **[MD/MF] Stock Bootloader BMT Support** — implement and test Bad Block Management Table support.

## Relation to MedveFlasher rc14

- MF full UART stock restore is hardware-confirmed.
- MF-A and MF-B stock slot layouts are recognized by the validator.
- Stock audit collects BMT/NAND/UBI evidence from `dmesg` rather than inferring it from one constant.
- Normal MF stock backup is hardware-confirmed for MF-A; rc14 adds a separate MF-A stock→RAM transition hardware gate and stops before UBI/sysupgrade. Permanent MF installation remains disabled until this transition and the later UBI/write gates are hardware-confirmed.
- SSH-free BootROM read-only backup remains a separate hardware-validation item.


> rc14fix6: RAM BusyBox applet availability is probed directly; OpenWrt image/patch roadmap unchanged.
