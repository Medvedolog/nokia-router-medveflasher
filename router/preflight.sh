#!/bin/ash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/lib.sh"

BUNDLE="${1:-}"
BACKUP="${2:-}"
[ -n "$BUNDLE" ] || die "usage: ash $0 BUNDLE_DIR BACKUP_DIR"
[ -n "$BACKUP" ] || die "usage: ash $0 BUNDLE_DIR BACKUP_DIR"

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
report_nand_detection

log '[5/7] Installation bundle'
verify_bundle "$BUNDLE"

log '[6/7] Full backup integrity'
verify_backup_dir "$BACKUP"
log "Backup verified: $BACKUP"

log '[7/7] Required writer'
command_exists mtd_debug || die 'mtd_debug is not installed on the stock firmware'

log ''
log 'PREFLIGHT PASSED.'
log 'Before installation: disconnect fiber, use stable power, keep UART recovery available.'
log 'The destructive script writes rootfs to mtd11, kernel to mtd14, and env to mtd0+0x60000 last.'
