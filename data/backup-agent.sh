#!/bin/ash
# Nokia XG-040G family full stock backup agent.
set -eu
umask 077
MODEL_NAME="${NOKIA_MODEL_NAME:-Nokia XG-040G-MD}"
BACKUP_PREFIX="${NOKIA_BACKUP_PREFIX:-nokia-xg040gmd-backup}"
select_language() {
    case "${NOKIA_LANG:-}" in ru|en) return 0 ;; esac
    if [ -t 0 ]; then
        printf '%s\n' 'Select language / Выберите язык:' '  1. RUS' '  2. ENG'
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
die2() { if [ "$NOKIA_LANG" = en ]; then printf 'ERROR: %s\n' "$2" >&2; else printf 'ОШИБКА: %s\n' "$1" >&2; fi; exit 1; }
find_usb() {
    for p in /mnt/USB_disc1 /mnt/USB_Disc* /mnt/USB_disc* /mnt/usb* /mnt/sd* /media/*; do
        [ -d "$p" ] && [ -w "$p" ] || continue
        printf '%s\n' "$p"; return 0
    done
    return 1
}
[ "$(id -u)" = 0 ] || die2 'требуется UID 0' 'UID 0 is required'
[ -r /proc/mtd ] || die2 '/proc/mtd недоступен' '/proc/mtd is unavailable'
DEST_ROOT="${1:-}"
[ -n "$DEST_ROOT" ] || DEST_ROOT="$(find_usb || true)"
[ -n "$DEST_ROOT" ] || die2 'не найдена доступная для записи USB-флешка' 'no writable USB mount was found'
[ -d "$DEST_ROOT" ] && [ -w "$DEST_ROOT" ] || die2 "нет доступа на запись: $DEST_ROOT" "not writable: $DEST_ROOT"

usb_marker() { [ "${NOKIA_USB_MARKERS:-0}" = 1 ] && { printf '%s' "$1"; printf '%s' "$2"; printf '__\n'; } || true; }
usb_say2() { [ "${NOKIA_USB_QUIET:-0}" = 1 ] || say2 "$1" "$2"; }
usb_preflight() {
    MOUNT_SOURCE="$(awk -v p="$DEST_ROOT" '$2==p {print $1; exit}' /proc/mounts)"
    MOUNT_FS="$(awk -v p="$DEST_ROOT" '$2==p {print $3; exit}' /proc/mounts)"
    [ -n "$MOUNT_SOURCE" ] && [ -n "$MOUNT_FS" ] || die2 "USB-путь не является отдельной смонтированной файловой системой: $DEST_ROOT" "USB path is not a separately mounted filesystem: $DEST_ROOT"
    case "$MOUNT_FS" in
        vfat|fat|msdos) ;;
        *) die2 "требуется FAT/FAT32; обнаружена файловая система $MOUNT_FS" "FAT/FAT32 is required; detected filesystem: $MOUNT_FS" ;;
    esac
    [ -d "$DEST_ROOT" ] && [ -w "$DEST_ROOT" ] || die2 "нет доступа на запись: $DEST_ROOT" "not writable: $DEST_ROOT"
    PROBE="$DEST_ROOT/.nokia-usb-write-test-$$"
    printf 'nokia-usb-preflight\n' > "$PROBE" || die2 "не удалось создать тестовый файл на $DEST_ROOT" "cannot create a test file on $DEST_ROOT"
    sync
    [ -s "$PROBE" ] || die2 'тестовый файл USB записан некорректно' 'USB write-test file is invalid'
    rm -f "$PROBE" || die2 'не удалось удалить тестовый файл USB' 'cannot remove the USB write-test file'
    FREE_KB="$(df -k "$DEST_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
    [ -n "$FREE_KB" ] || die2 "не удалось определить свободное место на $DEST_ROOT" "cannot determine free space on $DEST_ROOT"
    [ "$FREE_KB" -ge 2097152 ] || die2 "недостаточно места на USB: ${FREE_KB} КиБ; требуется минимум 2 ГиБ" "not enough free space on USB: ${FREE_KB} KiB; at least 2 GiB is required"
    usb_say2 "[OK] USB mount: $DEST_ROOT" "[OK] USB mount: $DEST_ROOT"
    usb_say2 "[OK] FAT/FAT32: $MOUNT_FS; источник: $MOUNT_SOURCE" "[OK] FAT/FAT32: $MOUNT_FS; source: $MOUNT_SOURCE"
    usb_say2 "[OK] Проверка записи пройдена; свободно ${FREE_KB} КиБ" "[OK] Write test passed; ${FREE_KB} KiB free"
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
mkdir "$DEST" || die2 "не удалось создать $DEST" "cannot create $DEST"
printf 'Backup is incomplete until this directory is renamed and BACKUP_COMPLETE appears.\n' > "$DEST/BACKUP_INCOMPLETE"
cp /proc/mtd "$DEST/proc_mtd.txt"
cat /proc/cmdline > "$DEST/cmdline.txt" 2>/dev/null || true
uname -a > "$DEST/uname.txt" 2>/dev/null || true
dmesg > "$DEST/dmesg_full.txt" 2>/dev/null || true
id > "$DEST/id.txt" 2>/dev/null || true
RAW="$DEST/.mtd-read-in-progress.bin"
trap 'rm -f "$RAW"' EXIT INT TERM
n=0
while [ "$n" -le 16 ]; do
    dev="/dev/mtd$n"
    [ -r "$dev" ] || die2 "отсутствует $dev" "missing $dev"
    name="$(awk -v m="mtd$n:" '$1==m {gsub(/\"/,"",$4); print $4}' /proc/mtd)"
    size_hex="$(awk -v m="mtd$n:" '$1==m {print $2}' /proc/mtd)"
    [ -n "$name" ] || name=unknown
    [ -n "$size_hex" ] || die2 "не удалось определить размер mtd$n" "cannot determine the size of mtd$n"
    expected=$((0x$size_hex))
    out="$DEST/mtd${n}_${name}.bin.gz"
    rm -f "$RAW"
    say2 "[$n/16] Чтение $dev ($name), ожидается=$expected" "[$n/16] Reading $dev ($name), expected=$expected"
    dd if="$dev" of="$RAW" bs=131072 2>"$DEST/dd-mtd$n.log" || die2 "ошибка чтения: $dev" "read failed: $dev"
    actual="$(wc -c < "$RAW" | tr -d ' ')"
    [ "$actual" -eq "$expected" ] || die2 "неполное чтение: mtd$n $actual != $expected" "short read: mtd$n $actual != $expected"
    gzip -1 < "$RAW" > "$out" || die2 "ошибка gzip: $out" "gzip failed: $out"
    gzip -t "$out" || die2 "проверка gzip не пройдена: $out" "gzip verification failed: $out"
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
mv "$DEST" "$DEST_FINAL" || die2 "не удалось завершить каталог $DEST_FINAL" "cannot finalize directory $DEST_FINAL"
DEST="$DEST_FINAL"
sync
say2 'BACKUP ЗАВЕРШЁН' 'BACKUP COMPLETE'
say2 "Каталог backup: $DEST" "Backup directory: $DEST"
printf '__BACKUP_DIR__'; printf '%s' "$DEST"; printf '__\n'
