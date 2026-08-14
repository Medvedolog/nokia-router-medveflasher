#!/bin/sh
# Nokia XG-040G-MD / XG-040G-MF stock inventory audit.
# Run only AFTER the PC-side MedveFlasher session has proved UID 0.
# No flash/NAND writes. Discovered upgrade utilities are never executed.

if command -v timeout >/dev/null 2>&1; then
    T='timeout 15'
else
    T=''
fi

run() {
    echo "$ $*"
    # shellcheck disable=SC2086
    $T sh -c "$*" </dev/null 2>&1
    rc=$?
    echo "--- rc=$rc ---"
    return 0
}

section() { echo; echo "===$1==="; }

printf '%s\n' '===MF-STOCK-AUDIT==='
printf 'audit_version=3\n'
printf 'generated_epoch=%s\n' "$(date +%s 2>/dev/null || echo NA)"

section ROOT-STATUS
uid="$(id -u 2>/dev/null)"
rc=$?
printf 'AUDIT_ROOT_UID=%s\n' "${uid:-UNKNOWN}"
printf 'AUDIT_ROOT_RC=%s\n' "$rc"
run 'id'
run 'whoami'

section IDENTITY
run 'uname -a'
run 'cat /proc/version'
run 'cat /proc/cpuinfo'
run 'cat /proc/device-tree/model 2>/dev/null; echo'
run 'cat /tmp/sysinfo/model 2>/dev/null'
run 'cat /tmp/sysinfo/board_name 2>/dev/null'
run 'cat /etc/board.json 2>/dev/null'
run 'for f in /etc/version /etc/openwrt_release /etc/os-release /etc/*version* /usr/etc/version; do [ -f "$f" ] && { echo "# $f"; cat "$f"; }; done'
run 'cat /proc/device-tree/serial-number 2>/dev/null; echo'
run 'cat /sys/class/net/eth0/address 2>/dev/null'

section USERS
run 'cat /etc/passwd'
run 'cat /etc/group'

section SU-IMPLEMENTATION
run 'command -v su || which su'
run 'readlink -f "$(command -v su 2>/dev/null)" 2>/dev/null'
run 'ls -l "$(command -v su 2>/dev/null)" 2>/dev/null'
run 'stat "$(command -v su 2>/dev/null)" 2>/dev/null'
run 'busybox --list 2>/dev/null | grep "^su$"'
run 'su --help </dev/null 2>&1 | head -8'

section MTD
run 'cat /proc/mtd'
run 'ls -l /dev/mtd* 2>/dev/null'
run 'for d in /sys/class/mtd/mtd*; do [ -d "$d" ] || continue; dev=$(basename "$d"); n=$(cat "$d/name" 2>/dev/null); s=$(cat "$d/size" 2>/dev/null); e=$(cat "$d/erasesize" 2>/dev/null); echo "SYSFS_MTD dev=$dev name=$n size=$s erasesize=$e"; done'

section NAND-UBI
run 'cat /proc/cmdline 2>/dev/null'
run 'dmesg 2>/dev/null | head -400'
run 'dmesg 2>/dev/null | grep -Ei "nand|spi-nand|mtd|ubi|bmt|bad *block" | head -240'
run 'find /sys \( -iname "*nand*" -o -iname "*spi*nand*" -o -iname "*ubi*" \) 2>/dev/null | head -160'
run 'for f in /sys/class/ubi/ubi*/mtd_num /sys/class/ubi/ubi*/total_eraseblocks /sys/class/ubi/ubi*/eraseblock_size /sys/class/ubi/ubi*/avail_eraseblocks; do [ -r "$f" ] && echo "SYSFS_UBI path=$f value=$(cat "$f" 2>/dev/null)"; done'
run 'ubinfo -a 2>/dev/null'
run 'cat /proc/mounts'
run 'df -h 2>/dev/null'

section READ-PRIMITIVES
run 'for x in cat dd gzip tftp sha256sum mtd ubinfo strings od; do if command -v "$x" >/dev/null 2>&1; then echo "AUDIT_TOOL name=$x present=1 path=$(command -v "$x")"; else echo "AUDIT_TOOL name=$x present=0"; fi; done'
run 'tftp --help 2>&1 | head -20'

section STOCK-UPGRADE-MECHANISM
# Enumerate and inspect only; nothing discovered here is executed.
run 'find /etc /usr /bin /sbin -type f \( -iname "*upgrade*" -o -iname "*update*" -o -iname "*flash*" -o -iname "*ubi*" \) 2>/dev/null | head -250 | while IFS= read -r f; do echo "AUDIT_FILE path=$f"; done'
run 'find /etc /usr /bin /sbin -type f \( -iname "*upgrade*" -o -iname "*update*" -o -iname "*flash*" -o -iname "*ubi*" \) 2>/dev/null | head -250 | while IFS= read -r f; do grep -nEi "mtd +write|nand +write|ubiupdatevol|ubiformat|ubimkvol|ubirmvol|flashcp|sysupgrade|mtd_write" "$f" 2>/dev/null | head -40 | while IFS= read -r hit; do echo "AUDIT_HIT path=$f hit=$hit"; done; done'
run 'find /etc /usr /bin /sbin -type f \( -iname "*upgrade*" -o -iname "*update*" -o -iname "*flash*" -o -iname "*ubi*" \) 2>/dev/null | head -250 | while IFS= read -r f; do sz=$(wc -c < "$f" 2>/dev/null | tr -d " "); sha=$(sha256sum "$f" 2>/dev/null | awk "{print \\$1}"); link=$(readlink -f "$f" 2>/dev/null); echo "AUDIT_META path=$f size=${sz:-unknown} sha256=${sha:-unknown} real=${link:-$f}"; if head -c 4 "$f" 2>/dev/null | od -An -tx1 2>/dev/null | grep -q "7f 45 4c 46"; then echo "AUDIT_BINARY path=$f"; if command -v strings >/dev/null 2>&1; then strings "$f" 2>/dev/null | grep -Ei "nand|mtd|ubi|ioctl|flash|kernel|rootfs|slave|active|boot" | head -80 | while IFS= read -r z; do echo "AUDIT_STRING path=$f text=$z"; done; fi; else head -120 "$f" 2>/dev/null | while IFS= read -r z; do echo "AUDIT_TEXT path=$f text=$z"; done; fi; done'

section END
printf '%s\n' '===MF-STOCK-AUDIT-END==='
