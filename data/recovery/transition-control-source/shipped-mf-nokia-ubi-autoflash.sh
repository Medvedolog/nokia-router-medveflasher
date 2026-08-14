#!/bin/ash
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
STATE=/tmp/NOKIA_AUTOFLASH_STATE
FAILED=/tmp/NOKIA_AUTOFLASH_FAILED
LOG=/tmp/nokia-autoflash.log
LOCK=/tmp/nokia-autoflash.lock
STATUS=/www/medveflasher-transition.status
WEBLOG=/www/medveflasher-transition.log
publish() {
    mkdir -p /www
    safe=0
    case "$1" in BOOTING|WAITING_FOR_SYSTEM|CHECKING) safe=1 ;; esac
    { echo MEDVEFLASHER_TRANSITION_PROTOCOL=1; echo MODE=TRANSITION; echo FAMILY=MF; echo BOARD=nokia,xg-040g-mf-ubi; echo STATE="$1"; echo SAFE_TO_POWER_CYCLE="$safe"; } > "$STATUS.tmp"
    mv "$STATUS.tmp" "$STATUS"
}
kmsg_line() { printf '%s
' "$1" | dd of=/dev/kmsg bs=4096 count=1 2>/dev/null || true; }
state() { printf '%s
' "$1" > "$STATE"; publish "$1"; kmsg_line "NOKIA-AUTOFLASH: state=$1"; }
note() { mkdir -p /www; printf '%s
' "$*" | tee -a "$LOG" "$WEBLOG"; kmsg_line "NOKIA-AUTOFLASH: $*"; }
fail() {
    reason="$*"; state FAILED; printf '%s
' "$reason" > "$FAILED"
    note "AUTOMATIC FLASH DID NOT COMPLETE: $reason"
    note 'Transition remains online for diagnostics. Read /tmp/nokia-autoflash.log before reboot.'
    exit 1
}
mkdir "$LOCK" 2>/dev/null || exit 0
mkdir -p /www
: > "$LOG"; : > "$WEBLOG"; rm -f "$FAILED"
state WAITING_FOR_SYSTEM
note 'Autonomous stage 2 is enabled; no SSH command is required.'
ready=0; second=0
while [ "$second" -lt 60 ]; do
    if [ -r /tmp/sysinfo/board_name ] && [ -x /usr/sbin/nokia-ubi-installer ]; then ready=1; break; fi
    second=$((second + 1)); sleep 1
done
[ "$ready" = 1 ] || fail 'normal init did not expose board information within 60 seconds'
sleep 5
state CHECKING
export NOKIA_AUTOMATIC_FULLFLASH=1
note 'Running read-only hardware, NAND, payload and embedded OpenWrt checks.'
if ! nokia-ubi-installer check embedded-openwrt-sysupgrade >> "$LOG" 2>&1; then fail 'read-only check failed; NAND was not formatted by this attempt'; fi
state FORMATTING_AND_FLASHING
note 'Checks passed. Starting autonomous all-in-UBI format, BL2/FIP write and embedded OpenWrt sysupgrade.'
nokia-ubi-installer fullflash embedded-openwrt-sysupgrade >> "$LOG" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
    state FULLFLASH_RETURNED_0
    note 'fullflash returned status 0 without a reboot/disconnect. This is not classified as FAILED; PC-side production verification is still required.'
    note 'Do not power-cycle based on this state. Keep the transition online for verification or diagnostics.'
    exit 0
fi
fail "fullflash returned unexpectedly with nonzero status $rc"
#
