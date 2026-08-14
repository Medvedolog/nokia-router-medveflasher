<div align="center">

# 🐻 Nokia Router MedveFlasher

**Current repository release / Текущий релиз:** `1.0.0-rc24`

**Full-cycle OpenWrt support: Nokia XG-040G-MD / AN7581 + Nokia XG-040G-MF / AN7583**

</div>

> [!IMPORTANT]
> **Nokia XG-040G-MF is now a first-class full-cycle target, not an experimental side path.** RC24 supports MF through the same primary stock → device-bound backup → root/preflight → transition → all-in-UBI migration → production OpenWrt verification cycle as MD. The MF installation cycle is hardware-confirmed through `[1/8]..[8/8]`, production SSH identity and LuCI HTTP-content verification.
>
> **MF теперь полноценная целевая модель полного цикла.** RC24 поддерживает Nokia XG-040G-MF от stock-определения и полного backup до transition, all-in-UBI migration и проверенной загрузки production OpenWrt с SSH + LuCI.

> [!CAUTION]
> NAND flashing is destructive. Keep a validated, device-bound stock backup and stable power. BL2 remains LAST in destructive migration/recovery paths. A timeout or port state alone never authorizes a retry or power-cycle.

## Supported hardware / Поддерживаемые модели

| Model | SoC | Primary OpenWrt install cycle | Recovery note |
|---|---|---|---|
| Nokia XG-040G-MD | Airoha AN7581 | **Supported / HW evidence** | RECOVERY_SAFE BootROM/UART path |
| Nokia XG-040G-MF | Airoha AN7583 | **Supported / full-cycle HW confirmed** | RECOVERY_SAFE BootROM/UART path; RC22 special bad-block stock restore remains separately non-final |

## Documentation

- [README — Русский](docs/README_RU.md)
- [README — English](docs/README_EN.md)
- [CHANGELOG — Русский](docs/CHANGELOG_RU.md)
- [CHANGELOG — English](docs/CHANGELOG.md)
- [ARCHITECTURE — Русский](docs/ARCHITECTURE_RU.md)
- [ARCHITECTURE — English](docs/ARCHITECTURE_EN.md)
- [Image status — Русский](docs/IMAGE_STATUS_RU.md)
- [Image status — English](docs/IMAGE_STATUS_EN.md)
- [OpenWrt TODO — Русский](docs/OPENWRT_TODO_RU.md)
- [OpenWrt TODO — English](docs/OPENWRT_TODO_EN.md)

## Current safety/status notes

- MD and MF-A permanent all-in-UBI install paths have hardware evidence; MF stock→OpenWrt full install is confirmed through production SSH + LuCI. Exact byte/status scope is tracked in `data/FIRMWARE_CAPABILITIES.json` and `docs/IMAGE_STATUS_*`.
- RC18 `RECOVERY_SAFE` RAM U-Boot remains the mandatory BootROM/UART safety boundary: stable prompt + exact marker + nonce before NAND capability.
- RC22 bad-block UART restore is **not** classified as a complete HW PASS. Real MF hardware completed write/readback and booted the stock main image/kernel, but `data` UBIFS recovery failed and stock entered watchdog reboot before a later successful OpenWrt install.
- Transition/recovery control-plane excludes LAN1/2.5G; use LAN2/LAN3/LAN4.
- RC24 interactive menus stay open after ordinary success/recoverable errors; `WRITE_STATE_UNKNOWN` activates a process-local SAFETY-LATCH and never authorizes a destructive retry.

## Repository import through `_incoming`

Use `.github/workflows/import_medveflasher_from_zip.yml`. It accepts either a full release ZIP or contiguous `.zip.part-NNN` files plus the required logical `.zip.sha256` sidecar. For GitHub web upload, the prepared import parts are kept **below 25 MB each**. The workflow verifies the reassembled outer archive, exact internal `data/SHA256SUMS` coverage, version/manifest/capability consistency and selftests before importing and committing.

## Offline runtime

Critical runtime/recovery payloads are shipped in the repository/release and SHA256-pinned. Normal install/recovery must not depend on mutable runtime firmware downloads.
