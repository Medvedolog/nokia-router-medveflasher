# Nokia Router MedveFlasher 1.0.0-rc30 image status

This file answers one question: **what exactly ships in the release, and which parts of it are confirmed on real hardware.** Per-version chronology lives in [CHANGELOG.md](CHANGELOG.md).

## Hardware-evidence summary

| Path | Status |
|---|---|
| MD permanent all-in-UBI install | ✅ **HW PASS** — RC18/RC20 lineage, `[1/8]..[8/8]`, BL2-last, production sysupgrade |
| MF-A permanent all-in-UBI install | ✅ **HW PASS** — `[1/8]..[8/8]`, UBI migration, production SSH + LuCI |
| Normal stock backup MD/MF (Telnet + TFTP) | ✅ **HW CONFIRMED** — `BACKUP_HW_VALIDATED` |
| Read-only BootROM/UART backup | ✅ **HW CONFIRMED** |
| UART/BootROM full stock restore | ✅ **HW CONFIRMED** on the RC16 preloader/FIP pair |
| UART stock restore on NAND with bad blocks (RC22 mapper) | ⚠️ **NOT FULL PASS** — see below |
| RC18 `RECOVERY_SAFE` SAFE FIP, exact bytes | `RC18_SAFE_PENDING_HW` — the path itself is confirmed, the exact bytes await regression |
| PC-side changes RC21–RC30 | STATIC_QA_PASS, HW regression pending |

### ⚠️ RC22 bad-block restore — why this is not a PASS

On real MF hardware the write and readback completed, BMT/BBT and the partition table came up, and the stock main image and kernel booted — but the `data` UBIFS failed recovery (`ubifs_recover_master_node`) and the device entered a watchdog boot loop. Until a dedicated fix and validation, this path is classified as a **partial hardware failure / recovery not validated**, not a success.

The trigger that produced the mapper in the first place: a real restore exposed `mtd bad ubi = 0x05d00000, 0x05d20000, 0x05de0000`, after which RC21 failed at IBU readback 13/30 at `ubi+0x06000800` with `-74`.

### Payload stability

Firmware/transition/recovery payloads are **unchanged since RC19**. RC20–RC30 alter only PC-side orchestration, metadata, and documentation, so hardware evidence for the install paths carries across those releases without rebuilding images.

### RC25: slot variant versus hardware evidence

The `MF-A permanent all-in-UBI install` row keeps its variant on purpose: the run
happened on MF-A hardware, and the evidence describes that. From RC25 the slot
variant no longer authorizes or refuses an install — `MF-B`, mirrored variants,
and recognized MD revisions follow the same policy — but hardware confirmation
stays tied to what was actually run. In RC25 the authorization comes from the
backup, the exact stock handoff targets, and the physical NAND/UBI geometry
check, not from a variant label.

---

## RC17fix2 exact transition artifacts

- MD auto: size `21626880`, SHA256 `7b817391930572664ef4a5a27fa3e53bda103115e5fb5e34f9949626a24e9b95`, FIT totalsize `7810596`, FIT SHA256 `aeac0f15dc8fadfc1f5f604f0f6d55256a499eaa0ac63c0a4035dc2de836a06a`.
- MD manual: size `8388608`, SHA256 `e5606341dd8c64ea9638c61efeb61050a1dc64df11beb344d52fd3ca208e68eb`, FIT totalsize `7810012`, FIT SHA256 `08218a49e58daf7ebed83db6d46727a60b7621761cc1f687a76f74e6601c3dbb`.
- MF auto: size `17694720`, SHA256 `8e45db3676a760831745b45c976e2a11b8bf13fc64ca6224922a42ee0209c8cf`, FIT totalsize `7827180`, FIT SHA256 `cfb5902e6ee67995d34a1b8bd767b8a3082331585f3b51be6c943ec44e22446e`.
- MF manual: size `8388608`, SHA256 `a7a5e1cb19b95e831305882f04201a4c3162f775a72554155d84eab2fe52087a`, FIT totalsize `7826668`, FIT SHA256 `09e916bbe31cf3c7138aba8bbaaa3c3af00e7f63fbcba33218fe5461f1faf35d`.

These exact RC17fix2 transition bytes are static-QA PASS and **hardware-regression pending**. The MF destructive all-in-UBI sequence itself remains hardware-confirmed from RC16; production payload bytes are unchanged.

## Historical RC17: transition control-plane rebuild


Production payload bytes are unchanged from RC16. Only automatic transition FIT control-plane/logging and RC17 release identity changed.

- MD auto transition: `21626880`, SHA256 `47631c782b75aef2a13082a4da2ffcee687742d8d743ed357a5753236b640962`, FIT totalsize `7509716`, FIT SHA256 `4a898c31dc69065decc267d5ede173530932079d5fc75344a417cf4e5946d392`, 8-MiB window SHA256 `e25b1156b945c66516bedccf420efe1c835b80d7701ce9d7201fc1d178cbb4b1`;
- MF auto transition: `17694720`, SHA256 `988fb4aa960441aa7176672c23181a373f54690fcc9a63389124adc8c7a6a188`, FIT totalsize `7649300`, FIT SHA256 `be365db3dabf68eb4e5cad56087e5af241f8fdb2c24c8936bf427d57cf7e469c`, 8-MiB window SHA256 `325bef457b611e81cf4a45885fb82c91b96ad1c9de14ae40d4adcf82461b3428`;
- MD/MF manual transition bundles remain byte-identical to RC16.
- MD/MF production tails from offset `0x800000` remain byte-identical to RC16.
- RC17 auto-transition delta is statically validated; a hardware regression run is still pending.


## RC16: MD / AN7581 — Dark patched build-set

Production target: `airoha/an7581`, board `nokia,xg-040g-md-ubi`, revision `r0-486b4a4`, kernel `6.18.41`.

- selected source initramfs: `11141120` bytes, SHA256 `a8e24301925c4a7b120594b61aa679bac835b26ef70736fd28a69c9029ffda3b`;
- shipped MedveFlasher RAM stock-recovery FIT: `11294372` bytes, SHA256 `4a6f579bb0d623bd5b582ed38d88735ac94079083d485bcc16f2ee7d706665f0`;
- production sysupgrade: `13226255` bytes, SHA256 `c6f06fcf4d155201aad3347cb0558ed11319be24f82d44106a061406d23dda03`;
- auto transition bundle: `21626880` bytes, SHA256 `5e658b2c50719db5e552c0c047aea0d58044ebcbea016a3e61707b2c62d3affe`, FIT totalsize `7509816`, production offset `0x800000`;
- manual transition: `8388608` bytes, SHA256 `0baac2ee30e752893942edf614aa0515117abb5fae10985d200879a2c226bb56`, FIT totalsize `7508736`, no embedded production image.

Production LuCI is confirmed by direct SquashFS/filesystem inspection: `cgi-bin/luci`, `luci-base`, admin/network/status/system modules, `rpcd-mod-luci`, `uhttpd`, and web assets are present.

The recovery FIT is not a blind copy of the UBI initramfs: kernel/rootfs are preserved from the selected Dark image while the recovery DT is rebuilt for stock restore. `all_flash` remains read-only, `bl2` is writable only in recovery, and production `ubi` is replaced by the recovery `ibu` view so BL2-last stock restore stays possible. Dark PHY/NPU DT changes remain present. Static/FIT/DT/SHA QA: PASS; the refreshed MD payload-set still requires hardware regression.

## RC16: MF / AN7583 — Uname production set retained

The production UBI build-set remains unchanged from rc15fix:

- production preloader: `118333`, SHA256 `778d10a65276085b70bec005248fc87ec208b43b0239502f15ade20fe528301e`;
- production BL31/U-Boot FIP: `319568`, SHA256 `99b6c20a7cb46a56692eaeb9f086f70fc7e987a641396653e6a8fb5c03e07aa7`;
- production sysupgrade: `9191705`, SHA256 `db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b`;
- bundled stock-recovery initramfs: `7486892`, SHA256 `f0591c84132fa6d93e8f41fa9e4ff57729a8ba698850f0dfc2ce2032726ff76f`;
- auto transition: `17694720`, SHA256 `c83898a4e2b22aa9ff0d16cd4f018812439c2665b24bf0588776815cd94fdf59`, FIT totalsize `7649360`;
- manual transition: `8388608`, SHA256 `17f70f23bf2bc465628915509fc853c1d2bc160ff0d299479a258080e20ee8b7`, FIT totalsize `7648816`.

The MF production sysupgrade also passed direct filesystem LuCI validation.

## RC16: MF BootROM/XMODEM offline recovery pins

- EVB preloader: `118322`, SHA256 `c2ac1c183b18bc34632c958dfe0bd1dfdfb607f090e39c41126956641893362f`;
- EVB BL31+U-Boot FIP: `339224`, SHA256 `b2f5f93f52afbaf539fe362267b13a91fb0a3a22c4ea770f2fc984dece176c12`.

Both files are carried in the full rollup and checked by exact size/SHA256 before the destructive path. Runtime download/cache fallback is absent. The refreshed exact-byte pair itself is HW-confirmed on Nokia XG-040G-MF by the RC16 full BootROM/XMODEM stock-restore run on 2026-08-12.

## RC16 release-integrity gates

`verify_kit()` binds all four transition bundles to MANIFEST using actual full size/SHA256, FIT totalsize/FIT SHA256, and production size/SHA256. This closes the `MANIFEST.json` drift found in rc15fix. Transition-only writable BL2, production read-only BL2, provenance gate before BL2-last, readback, and immediate stage2 stop on `FAILED` are retained.
- RC17fix changes no firmware payload bytes; only post-UART-restore reboot/stock-Web verification was fixed.
