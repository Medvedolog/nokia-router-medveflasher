#!/bin/ash
# Manual fallback for Nokia XG-040G-MD stock firmware.
set -eu
case "${NOKIA_LANG:-}" in
  ru|en) ;;
  *)
    printf '%s\n' 'Select language / Выберите язык:' '  1. RUS' '  2. ENG'
    printf 'RUS or ENG [1/2]: '
    IFS= read -r answer
    case "$answer" in 2|en|EN|eng|ENG) NOKIA_LANG=en ;; *) NOKIA_LANG=ru ;; esac
    export NOKIA_LANG
    ;;
esac
say2() { if [ "$NOKIA_LANG" = en ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
die2() { if [ "$NOKIA_LANG" = en ]; then printf 'ERROR: %s\n' "$2" >&2; else printf 'ОШИБКА: %s\n' "$1" >&2; fi; exit 1; }
SERVER="${1:-192.168.1.254}"
BLOCK_SIZE="${2:-4096}"
cd /tmp
tftp -p -l /proc/mtd -r proc_mtd.txt -b "$BLOCK_SIZE" "$SERVER" || die2 'не удалось отправить proc_mtd.txt' 'failed to send proc_mtd.txt'
for i in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do
    fifo="/tmp/nokia-mtd${i}.fifo"
    remote="mtd${i}.bin.gz"
    rm -f "$fifo"; mkfifo "$fifo"
    say2 "Передача mtd${i}..." "Streaming mtd${i}..."
    tftp -p -l "$fifo" -r "$remote" -b "$BLOCK_SIZE" "$SERVER" &
    tftp_pid=$!
    if ! dd if="/dev/mtd${i}" bs=131072 2>"/tmp/mtd${i}-dd.log" | gzip -1 > "$fifo"; then
        kill "$tftp_pid" 2>/dev/null || true; rm -f "$fifo"
        die2 "ошибка чтения/gzip для mtd${i}" "read/gzip failed for mtd${i}"
    fi
    rm -f "$fifo"
    wait "$tftp_pid" || die2 "ошибка TFTP для mtd${i}" "TFTP failed for mtd${i}"
done
say2 'Все файлы отправлены. Перед прошивкой проверьте gzip и распакованные размеры на ПК.' 'All files were sent. Verify gzip integrity and decompressed sizes on the PC before flashing.'
