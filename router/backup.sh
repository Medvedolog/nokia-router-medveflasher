#!/bin/ash
set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=router/lib.sh
. "$SCRIPT_DIR/lib.sh"

FORCE=0
if [ "${1:-}" = '--force' ]; then
    FORCE=1
    shift
fi
TARGET="${1:-/mnt/BOOT/nokia-xg040gmd-backup}"

verify_stock_layout
command_exists gzip || die 'gzip is required'
command_exists sha256sum || die 'sha256sum is required'

mkdir -p "$TARGET"
cd "$TARGET" || die "cannot enter $TARGET"

if [ "$FORCE" -ne 1 ] && ls mtd*.bin.gz >/dev/null 2>&1; then
    die 'backup files already exist; use --force only after copying them elsewhere'
fi

cat /proc/mtd > proc_mtd.txt
id > id.txt 2>/dev/null || true
uname -a > uname.txt 2>/dev/null || true
cat /proc/cpuinfo > cpuinfo.txt 2>/dev/null || true
dmesg > dmesg_full.txt 2>/dev/null || true
dmesg | grep -i -E 'nand|spi|sky|fudan|ml02|s34ml|mtd|ubi|bad|ecc' > dmesg_nand_mtd.txt 2>/dev/null || true
awk 'NR>1 {gsub(":", "", $1); gsub("\"", "", $4); print $1, $4}' /proc/mtd > mtd_map.txt

while read -r mtd name; do
    safe="$(printf '%s' "$name" | sed 's/[^A-Za-z0-9_.-]/_/g')"
    output="${mtd}_${safe}.bin.gz"
    temporary=".${output}.tmp"
    log "Backing up $mtd ($name)"
    rm -f "$temporary"
    gzip -9 -c "/dev/${mtd}ro" > "$temporary" || die "failed to read $mtd"
    gzip -t "$temporary" || die "gzip verification failed for $mtd"
    mv "$temporary" "$output"
    sync
done < mtd_map.txt

dd if=/dev/mtd6ro of=bosa.bin bs=131072 count=2 2>/dev/null
dd if=/dev/mtd7ro of=ri.bin bs=131072 count=2 2>/dev/null
[ "$(file_size bosa.bin)" -eq 262144 ] || die 'invalid bosa.bin size'
[ "$(file_size ri.bin)" -eq 262144 ] || die 'invalid ri.bin size'

rm -f SHA256SUMS.txt files_lh.txt
for file in *; do
    [ -f "$file" ] || continue
    [ "$file" = 'SHA256SUMS.txt' ] && continue
    sha256sum "$file"
done > .SHA256SUMS.tmp
mv .SHA256SUMS.tmp SHA256SUMS.txt
ls -lh > .files_lh.tmp
mv .files_lh.tmp files_lh.txt
sync

log "Backup completed: $TARGET"
log 'Copy it to at least two independent locations. Do not publish raw dumps.'
