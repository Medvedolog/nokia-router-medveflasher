# Nokia XG-040G-MD Stock Installer for OpenWrt

> **Experimental. High brick risk. UART recovery must be available.**

This project automates the official OpenWrt **stock-layout** installation path
for the Nokia / Nokia Shanghai Bell XG-040G-MD based on Airoha AN7581. It does
not install `tcboot`, does not replace BL2/FIP, and does not convert the device
to OpenWrt's all-in-UBI bootloader layout.

The installer targets the exact stock partition table observed on the supported
China Mobile unit and writes:

- personalized U-Boot environment to `mtd0` at offset `0x60000`, length `0x20000`;
- OpenWrt factory kernel to `mtd14` (`nsb_master`);
- OpenWrt factory rootfs to `mtd11` (`data`).

## Critical limitations

- **XG-PON is unavailable after installing OpenWrt.**
- Initial support is restricted to **SkyHigh ML02G300WHI00** SPI-NAND.
- FudanMicro FM25G02B is rejected when detected.
- Only the exact stock MTD layout documented below is accepted.
- Snapshot firmware changes frequently. Kernel and rootfs must come from the
  same OpenWrt build and must pass the provided validation.
- This is not an atomic update. A power failure can brick the device.

## Supported stock layout

```text
mtd0  00080000 bootloader
mtd1  00040000 romfile
mtd2  003af6da kernel
mtd3  01cc0000 rootfs
mtd4  00480000 kernel_slave
mtd5  02400000 rootfs_slave
mtd6  00040000 bosa
mtd7  00040000 ri
mtd8  00040000 flag
mtd9  00040000 flagback
mtd10 00a00000 config
mtd11 080e0000 data
mtd12 00400000 oopsfs
mtd13 00a00000 log
mtd14 02880000 nsb_master
mtd15 02880000 nsb_slave
mtd16 0eba0000 all_flash
```

## Required OpenWrt files

Download from one matching `airoha/an7581` snapshot build:

```text
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-kernel.bin
openwrt-airoha-an7581-nokia_xg-040g-md-squashfs-factory-rootfs.bin
sha256sums
```

Do not use `sysupgrade.bin`, `initramfs-uImage.itb`, `tcboot` images, or
`nokia_xg-040g-md-ubi-*` files with this installer.

## 1. Create and verify a full stock backup

Copy `router/backup.sh` and `router/lib.sh` to a USB drive, enter the stock
Telnet shell, elevate using the method appropriate for the firmware, and run:

```sh
/mnt/BOOT/backup.sh /mnt/BOOT/nokia-xg040gmd-backup
```

Copy the resulting directory to at least two independent storage locations.
Verify it on a PC:

```sh
python3 tools/verify_backup.py /path/to/nokia-xg040gmd-backup
```

Never publish the generated dumps.

## 2. Generate a personalized U-Boot environment

The official OpenWrt upgrade hook changes only `bootcmd`. This tool reads the
valid environment from the device's own bootloader backup, preserves all other
variables, changes `bootcmd`, recalculates CRC32, and creates the required
`0x20000` partition image:

```sh
python3 tools/prepare_env.py \
  --input /path/to/nokia-xg040gmd-backup/mtd0_bootloader.bin.gz \
  --output /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --report-json /tmp/env-report.json
```

Expected boot command:

```text
flash read 0xc0000 0x800000 0x85000000; bootm 0x85000000
```

If the stock environment CRC is invalid, the tool stops. It does not silently
construct a generic donor environment. A separately obtained and verified
`0x20000` donor environment can be passed to `--input`, but this preserves the
donor variables and is therefore a fallback for controlled testing, not the
preferred community workflow. Never commit that binary to the repository.

## 3. Prepare a validated USB bundle

```sh
python3 tools/prepare_bundle.py \
  --kernel /path/to/openwrt-...-squashfs-factory-kernel.bin \
  --rootfs /path/to/openwrt-...-squashfs-factory-rootfs.bin \
  --env /tmp/OpenWrt.mtd2.u-boot-env.bin \
  --sha256sums /path/to/openwrt-snapshot/sha256sums \
  --output /path/to/usb/nokia-install-bundle \
  --confirm-skyhigh
```

The command validates the official OpenWrt `sha256sums`, exact Nokia stock-layout
filenames, FIT/UBI magic, sizes, environment CRC and boot command. Router scripts
are normalized to LF before the USB bundle and `SHA256SUMS` are created.

## 4. Run read-only preflight on the stock router

Disconnect fiber and use stable power:

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --dry-run \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

Do not proceed unless every check passes.

## 5. Experimental installation

```sh
ash /mnt/BOOT/nokia-install-bundle/flash-stock-layout.sh --install \
  /mnt/BOOT/nokia-install-bundle \
  /mnt/BOOT/nokia-xg040gmd-backup
```

The script requires the exact phrase `FLASH NOKIA XG-040G-MD`. It writes rootfs
first, kernel second and the boot-switching U-Boot environment last, verifies
read-back SHA-256 hashes, synchronizes, and reboots. Run scripts through `ash`
when the bundle is stored on a Windows/FAT USB drive.

## Windows 10/11

No compilation is required when Python 3.12 is installed. The unified command is:

```powershell
py -3.12 tools\nokia_tools.py prepare-usb --help
```

A standalone Windows x64 EXE can be built locally with
`windows\build-windows.ps1`, or from **Actions → Build Windows kit → Run
workflow**. Detailed instructions are in `windows/README_WINDOWS_RU.md`.

## Recovery

Keep the complete `mtd16_all_flash.bin.gz` backup and UART hardware available.
Recovery and return-to-stock operations overwrite the boot flash and are not
automated in this experimental release.

## Project status

`0.1.1-experimental`: backup, validation, personalized environment generation,
and guarded stock-layout write path. Real-device review and testing are still
required before treating the installer as generally safe.

See [the English notes](docs/README_EN.md) for a compact English summary.
