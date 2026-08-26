#!/bin/ash
# Nokia XG-040G family full stock backup agent.
set -eu
umask 077
MODEL_NAME="${NOKIA_MODEL_NAME:-Nokia XG-040G-MD}"
BACKUP_PREFIX="${NOKIA_BACKUP_PREFIX:-nokia-xg040gmd-backup}"
select_language() {
    case "${NOKIA_LANG:-}" in ru|en) return 0 ;; esac
    if [ -t 0 ]; then
        printf '%s\n' 'Select language / Vyberite yazyk:' '  1. RUS' '  2. ENG'
        printf 'RUS or ENG [1/2]: '
        IFS= read -r answer
        case "$answer" in 2|en|EN|eng|ENG) NOKIA_LANG=en ;; *) NOKIA_LANG=ru ;; esac
    else
        NOKIA_LANG=ru
    fi
    export NOKIA_LANG
}
select_language
say2() { if [ "$NOKIA_LANG" = en ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
die2() { if [ "$NOKIA_LANG" = en ]; then printf 'ERROR: %s\n' "$2" >&2; else printf 'OShIBKA: %s\n' "$1" >&2; fi; exit 1; }
find_usb() {
    for p in /mnt/USB_disc1 /mnt/USB_Disc* /mnt/USB_disc* /mnt/usb* /mnt/sd* /media/*; do
        [ -d "$p" ] && [ -w "$p" ] || continue
        printf '%s\n' "$p"; return 0
    done
    return 1
}
[ "$(id -u)" = 0 ] || die2 'trebuetsya UID 0' 'UID 0 is required'
[ -r /proc/mtd ] || die2 '/proc/mtd nedostupen' '/proc/mtd is unavailable'
DEST_ROOT="${1:-}"
[ -n "$DEST_ROOT" ] || DEST_ROOT="$(find_usb || true)"
[ -n "$DEST_ROOT" ] || die2 'ne naydena dostupnaya dlya zapisi USB-fleshka' 'no writable USB mount was found'
[ -d "$DEST_ROOT" ] && [ -w "$DEST_ROOT" ] || die2 "net dostupa na zapis: $DEST_ROOT" "not writable: $DEST_ROOT"

usb_marker() { [ "${NOKIA_USB_MARKERS:-0}" = 1 ] && { printf '%s' "$1"; printf '%s' "$2"; printf '__\n'; } || true; }
usb_say2() { [ "${NOKIA_USB_QUIET:-0}" = 1 ] || say2 "$1" "$2"; }
usb_preflight() {
    MOUNT_SOURCE="$(awk -v p="$DEST_ROOT" '$2==p {print $1; exit}' /proc/mounts)"
    MOUNT_FS="$(awk -v p="$DEST_ROOT" '$2==p {print $3; exit}' /proc/mounts)"
    [ -n "$MOUNT_SOURCE" ] && [ -n "$MOUNT_FS" ] || die2 "USB-put ne yavlyaetsya otdelnoy smontirovannoy faylovoy sistemoy: $DEST_ROOT" "USB path is not a separately mounted filesystem: $DEST_ROOT"
    case "$MOUNT_FS" in
        vfat|fat|msdos) ;;
        *) die2 "trebuetsya FAT/FAT32; obnaruzhena faylovaya sistema $MOUNT_FS" "FAT/FAT32 is required; detected filesystem: $MOUNT_FS" ;;
    esac
    [ -d "$DEST_ROOT" ] && [ -w "$DEST_ROOT" ] || die2 "net dostupa na zapis: $DEST_ROOT" "not writable: $DEST_ROOT"
    PROBE="$DEST_ROOT/.nokia-usb-write-test-$$"
    printf 'nokia-usb-preflight\n' > "$PROBE" || die2 "ne udalos sozdat testovyy fayl na $DEST_ROOT" "cannot create a test file on $DEST_ROOT"
    sync
    [ -s "$PROBE" ] || die2 'testovyy fayl USB zapisan nekorrektno' 'USB write-test file is invalid'
    rm -f "$PROBE" || die2 'ne udalos udalit testovyy fayl USB' 'cannot remove the USB write-test file'
    FREE_KB="$(df -k "$DEST_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
    [ -n "$FREE_KB" ] || die2 "ne udalos opredelit svobodnoe mesto na $DEST_ROOT" "cannot determine free space on $DEST_ROOT"
    [ "$FREE_KB" -ge 2097152 ] || die2 "nedostatochno mesta na USB: ${FREE_KB} KiB; trebuetsya minimum 2 GiB" "not enough free space on USB: ${FREE_KB} KiB; at least 2 GiB is required"
    usb_say2 "[OK] USB mount: $DEST_ROOT" "[OK] USB mount: $DEST_ROOT"
    usb_say2 "[OK] FAT/FAT32: $MOUNT_FS; istochnik: $MOUNT_SOURCE" "[OK] FAT/FAT32: $MOUNT_FS; source: $MOUNT_SOURCE"
    usb_say2 "[OK] Proverka zapisi proydena; svobodno ${FREE_KB} KiB" "[OK] Write test passed; ${FREE_KB} KiB free"
    usb_marker '__USB_MOUNT__' "$DEST_ROOT"
    usb_marker '__USB_SOURCE__' "$MOUNT_SOURCE"
    usb_marker '__USB_FILESYSTEM__' "$MOUNT_FS"
    usb_marker '__USB_FREE_KB__' "$FREE_KB"
    usb_marker '__USB_PREFLIGHT_OK__' '1'
}
usb_preflight
[ "${2:-}" = --preflight ] && exit 0
STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo undated)"
DEST_FINAL="$DEST_ROOT/${BACKUP_PREFIX}-$STAMP"
DEST="$DEST_FINAL.incomplete"
i=0
while [ -e "$DEST" ] || [ -e "$DEST_FINAL" ]; do
    i=$((i+1))
    DEST_FINAL="$DEST_ROOT/${BACKUP_PREFIX}-$STAMP-$i"
    DEST="$DEST_FINAL.incomplete"
done
mkdir "$DEST" || die2 "ne udalos sozdat $DEST" "cannot create $DEST"
printf 'Backup is incomplete until this directory is renamed and BACKUP_COMPLETE appears.\n' > "$DEST/BACKUP_INCOMPLETE"
cp /proc/mtd "$DEST/proc_mtd.txt"
cat /proc/cmdline > "$DEST/cmdline.txt" 2>/dev/null || true
uname -a > "$DEST/uname.txt" 2>/dev/null || true
dmesg > "$DEST/dmesg_full.txt" 2>/dev/null || true
id > "$DEST/id.txt" 2>/dev/null || true
# Device identity metadata. MD uses the base MAC in RI/mtd7@0x3e because stock
# eth0 may be the compiled placeholder 00:aa:bb:01:23:40. MF keeps its existing
# sysfs identity behavior; this MD field fix does not redefine MF provenance.
RI_MAC_OFFSET=62
RI_MAC_LENGTH=6
PRIMARY_IF=unknown
PRIMARY_SOURCE=unknown
PRIMARY_MAC=UNKNOWN
IDENTITY_SOURCE=unknown
if [ "${NOKIA_BACKUP_FAMILY:-unknown}" = md ]; then
    RI_DEV=/dev/mtd7ro
    [ -r "$RI_DEV" ] || RI_DEV=/dev/mtd7
    if [ -r "$RI_DEV" ]; then
        RI_HEX="$(dd if="$RI_DEV" bs=1 skip="$RI_MAC_OFFSET" count="$RI_MAC_LENGTH" 2>/dev/null | hexdump -v -e '6/1 "%02x"' | tr 'A-F' 'a-f')"
        if [ "${#RI_HEX}" -eq 12 ] && [ "$RI_HEX" != 000000000000 ] && [ "$RI_HEX" != ffffffffffff ]; then
            PRIMARY_MAC="$(printf '%s\n' "$RI_HEX" | sed 's/../&:/g;s/:$//')"
            PRIMARY_IF=ri
            PRIMARY_SOURCE=stock-ri-mtd7@0x3e
        else
            PRIMARY_SOURCE=stock-ri-mtd7-unavailable
        fi
    else
        PRIMARY_SOURCE=stock-ri-mtd7-unavailable
    fi
    IDENTITY_SOURCE=stock-ri-mtd7
else
    if [ -r /sys/class/net/eth0/address ]; then
        PRIMARY_IF=eth0
        PRIMARY_MAC="$(cat /sys/class/net/eth0/address 2>/dev/null | tr 'A-F' 'a-f')"
    else
        for p in /sys/class/net/*/address; do
            [ -r "$p" ] || continue
            i="${p%/address}"; i="${i##*/}"
            [ "$i" = lo ] && continue
            PRIMARY_IF="$i"
            PRIMARY_MAC="$(cat "$p" 2>/dev/null | tr 'A-F' 'a-f')"
            break
        done
    fi
    PRIMARY_SOURCE="stock-linux-sysfs:$PRIMARY_IF"
    IDENTITY_SOURCE=stock-linux-sysfs
fi
{
    printf 'model=%s\n' "$MODEL_NAME"
    printf 'family=%s\n' "${NOKIA_BACKUP_FAMILY:-unknown}"
    printf 'captured_at_local=%s\n' "$(date +%Y-%m-%dT%H:%M:%S%z 2>/dev/null || echo unknown)"
    printf 'captured_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    printf 'source=%s\n' "$IDENTITY_SOURCE"
    printf 'primary_source=%s\n' "$PRIMARY_SOURCE"
    printf 'primary_interface=%s\n' "$PRIMARY_IF"
    printf 'primary_mac=%s\n' "$PRIMARY_MAC"
    if [ "${NOKIA_BACKUP_FAMILY:-unknown}" = md ]; then
        printf 'ri_offset=0x3e\n'
        printf 'ri_length=6\n'
    fi
    for p in /sys/class/net/*/address; do
        [ -r "$p" ] || continue
        i="${p%/address}"; i="${i##*/}"
        [ "$i" = lo ] && continue
        a="$(cat "$p" 2>/dev/null | tr 'A-F' 'a-f')"
        printf 'interface_%s=%s\n' "$i" "$a"
    done
} > "$DEST/DEVICE_MAC.txt"
if [ "${NOKIA_BACKUP_FAMILY:-unknown}" = md ]; then
    if [ "$PRIMARY_MAC" = UNKNOWN ]; then
        usb_say2 '[WARNING] RI MAC ne prochitan; sysfs MAC ostalis tolko diagnostikoy.' '[WARNING] RI MAC was not readable; sysfs MACs are diagnostic only.'
    else
        usb_say2 "[OK] Device MAC iz RI mtd7@0x3e: $PRIMARY_MAC" "[OK] Device MAC from RI mtd7@0x3e: $PRIMARY_MAC"
    fi
else
    usb_say2 "[OK] Backup source MAC: $PRIMARY_MAC ($PRIMARY_IF)" "[OK] Backup source MAC: $PRIMARY_MAC ($PRIMARY_IF)"
fi
RAW="$DEST/.mtd-read-in-progress.bin"
trap 'rm -f "$RAW"' EXIT INT TERM
n=0
while [ "$n" -le 16 ]; do
    dev="/dev/mtd$n"
    if [ "${NOKIA_PREFER_RO_MTD:-0}" = 1 ] && [ -r "/dev/mtd${n}ro" ]; then
        dev="/dev/mtd${n}ro"
    fi
    [ -r "$dev" ] || die2 "otsutstvuet $dev" "missing $dev"
    name="$(awk -v m="mtd$n:" '$1==m {gsub(/\"/,"",$4); print $4}' /proc/mtd)"
    size_hex="$(awk -v m="mtd$n:" '$1==m {print $2}' /proc/mtd)"
    [ -n "$name" ] || name=unknown
    [ -n "$size_hex" ] || die2 "ne udalos opredelit razmer mtd$n" "cannot determine the size of mtd$n"
    expected=$((0x$size_hex))
    out="$DEST/mtd${n}_${name}.bin.gz"
    rm -f "$RAW"
    say2 "[$n/16] Chtenie $dev ($name), ozhidaetsya=$expected" "[$n/16] Reading $dev ($name), expected=$expected"
    dd if="$dev" of="$RAW" bs=131072 2>"$DEST/dd-mtd$n.log" || die2 "oshibka chteniya: $dev" "read failed: $dev"
    actual="$(wc -c < "$RAW" | tr -d ' ')"
    [ "$actual" -eq "$expected" ] || die2 "nepolnoe chtenie: mtd$n $actual != $expected" "short read: mtd$n $actual != $expected"
    gzip -1 < "$RAW" > "$out" || die2 "oshibka gzip: $out" "gzip failed: $out"
    gzip -t "$out" || die2 "proverka gzip ne proydena: $out" "gzip verification failed: $out"
    rm -f "$RAW"
    sync
    n=$((n+1))
done
trap - EXIT INT TERM
gzip -dc "$DEST"/mtd6_*.bin.gz > "$DEST/bosa.bin"
gzip -dc "$DEST"/mtd7_*.bin.gz > "$DEST/ri.bin"
( cd "$DEST"; sha256sum *.bin *.bin.gz *.txt > SHA256SUMS.txt )
printf '%s full backup completed\n' "$MODEL_NAME" > "$DEST/BACKUP_COMPLETE"
rm -f "$DEST/BACKUP_INCOMPLETE"
sync
mv "$DEST" "$DEST_FINAL" || die2 "ne udalos zavershit katalog $DEST_FINAL" "cannot finalize directory $DEST_FINAL"
DEST="$DEST_FINAL"
sync
say2 'BACKUP ZAVERShEN' 'BACKUP COMPLETE'
say2 "Katalog backup: $DEST" "Backup directory: $DEST"
printf '__BACKUP_DIR__'; printf '%s' "$DEST"; printf '__\n'
