#!/bin/ash
set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=router/lib.sh
. "$SCRIPT_DIR/lib.sh"

MODE="${1:-}"
BUNDLE="${2:-}"
BACKUP="${3:-}"
case "$MODE" in
    --dry-run|--install)
        ;;
    *)
        die "usage: ash $0 --dry-run|--install BUNDLE_DIR BACKUP_DIR"
        ;;
esac
[ -n "$BUNDLE" ] || die 'bundle directory is required'
[ -n "$BACKUP" ] || die 'verified backup directory is required'

ash "$SCRIPT_DIR/preflight.sh" "$BUNDLE" "$BACKUP"

if [ "$MODE" = '--dry-run' ]; then
    log 'DRY RUN PASSED. No flash writes were performed.'
    exit 0
fi

cat <<'EOF_DANGER'

DANGER: this operation overwrites parts of the SPI-NAND flash.
It is experimental and can brick the device. XG-PON is unsupported by OpenWrt.
Disconnect fiber. Use stable power. Do not continue without UART recovery access.

Type exactly: FLASH NOKIA XG-040G-MD
EOF_DANGER
printf '> '
IFS= read -r confirmation
[ "$confirmation" = 'FLASH NOKIA XG-040G-MD' ] || die 'confirmation did not match'

ENV_FILE="$BUNDLE/OpenWrt.mtd2.u-boot-env.bin"
KERNEL_FILE="$BUNDLE/factory-kernel.bin"
ROOTFS_FILE="$BUNDLE/factory-rootfs.bin"
ENV_SHA="$(sha_file "$ENV_FILE")"
KERNEL_SHA="$(sha_file "$KERNEL_FILE")"
ROOTFS_SHA="$(sha_file "$ROOTFS_FILE")"
KERNEL_SIZE="$(file_size "$KERNEL_FILE")"
ROOTFS_SIZE="$(file_size "$ROOTFS_FILE")"
FLASH_STARTED=0

flash_failed() {
    status="$?"
    if [ "$FLASH_STARTED" -eq 1 ] && [ "$status" -ne 0 ]; then
        log ''
        log 'CRITICAL: flashing stopped after NAND modification began.'
        log 'DO NOT power-cycle blindly. Capture the complete log and prepare UART recovery.'
    fi
    exit "$status"
}
trap flash_failed 0
trap 'exit 130' INT TERM HUP

log 'Starting official stock-layout write sequence.'
log 'Do not remove power.'
sync
FLASH_STARTED=1

# Write the boot-switching environment last. This minimizes the time during
# which bootcmd points at an image set that has not yet passed read-back checks.
log '[1/3] Writing factory rootfs to mtd11 (data)'
mtd_debug erase /dev/mtd11 0x0 0x80e0000
mtd_debug write /dev/mtd11 0x0 "$ROOTFS_SIZE" "$ROOTFS_FILE"
ROOTFS_READBACK="$(readback_sha /dev/mtd11ro "$ROOTFS_SIZE")"
[ "$ROOTFS_READBACK" = "$ROOTFS_SHA" ] || die 'rootfs read-back hash mismatch'

log '[2/3] Writing factory kernel to mtd14 (nsb_master)'
mtd_debug erase /dev/mtd14 0x0 0x2880000
mtd_debug write /dev/mtd14 0x0 "$KERNEL_SIZE" "$KERNEL_FILE"
KERNEL_READBACK="$(readback_sha /dev/mtd14ro "$KERNEL_SIZE")"
[ "$KERNEL_READBACK" = "$KERNEL_SHA" ] || die 'kernel read-back hash mismatch'

log '[3/3] Writing OpenWrt U-Boot environment to mtd0 offset 0x60000'
mtd_debug erase /dev/mtd0 0x60000 0x20000
mtd_debug write /dev/mtd0 0x60000 0x20000 "$ENV_FILE"
ENV_READBACK="$(dd if=/dev/mtd0ro bs=131072 skip=3 count=1 2>/dev/null | sha256sum | awk '{print $1}')"
[ "$ENV_READBACK" = "$ENV_SHA" ] || die 'environment read-back hash mismatch'

sync
FLASH_STARTED=0
trap - 0 INT TERM HUP
log 'All read-back hashes match. Rebooting in 5 seconds.'
sleep 5
reboot
