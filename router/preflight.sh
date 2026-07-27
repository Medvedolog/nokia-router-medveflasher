#!/bin/ash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/lib.sh"

BUNDLE="${1:-$SCRIPT_DIR}"
BACKUP="${2:-}"

log '== Nokia XG-040G-MD stock-layout preflight =='
log 'No flash writes are performed by this script.'
log ''

log '[1/7] Current identity'
id

log '[2/7] Exact stock MTD layout'
verify_stock_layout
cat /proc/mtd

log '[3/7] Read/write device access'
for dev in /dev/mtd0 /dev/mtd11 /dev/mtd14 /dev/mtd0ro /dev/mtd11ro /dev/mtd14ro; do
    [ -e "$dev" ] || die "missing $dev"
done
[ -r /dev/mtd0ro ] || die 'cannot read /dev/mtd0ro'
[ -w /dev/mtd0 ] || die 'cannot write /dev/mtd0; elevate with the stock firmware method first'
[ -w /dev/mtd11 ] || die 'cannot write /dev/mtd11'
[ -w /dev/mtd14 ] || die 'cannot write /dev/mtd14'

log '[4/7] NAND guard'
reject_fudan_if_detected
log 'No FudanMicro signature detected. Physical SkyHigh confirmation is still required by the bundle marker.'

log '[5/7] Installation bundle'
verify_bundle "$BUNDLE"

log '[6/7] Backup presence'
if [ -n "$BACKUP" ]; then
    [ -f "$BACKUP/mtd0_bootloader.bin.gz" ] || die 'missing bootloader backup'
    [ -f "$BACKUP/mtd16_all_flash.bin.gz" ] || die 'missing all_flash backup'
    [ -f "$BACKUP/bosa.bin" ] || die 'missing bosa.bin'
    [ -f "$BACKUP/ri.bin" ] || die 'missing ri.bin'
    [ "$(file_size "$BACKUP/bosa.bin")" -eq 262144 ] || die 'bosa.bin has an unexpected size'
    [ "$(file_size "$BACKUP/ri.bin")" -eq 262144 ] || die 'ri.bin has an unexpected size'
    log "Backup directory accepted: $BACKUP"
else
    log 'WARNING: backup directory was not supplied to preflight.'
fi

log '[7/7] Required writer'
command_exists mtd_debug || die 'mtd_debug is not installed on the stock firmware'

log ''
log 'PREFLIGHT PASSED.'
log 'Before installation: disconnect fiber, use stable power, keep UART recovery available.'
log 'The destructive script writes env to mtd0+0x60000, kernel to mtd14, rootfs to mtd11.'
