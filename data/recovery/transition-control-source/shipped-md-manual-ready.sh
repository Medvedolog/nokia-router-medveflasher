#!/bin/sh /etc/rc.common
START=99
EXPECTED_BOARD="nokia,xg-040g-md-ubi"
FAMILY="MD"
STATE_FILE=/tmp/NOKIA_MANUAL_STATE
READY_FILE=/tmp/NOKIA_MANUAL_TRANSITION_READY
STATUS_FILE=/www/medveflasher-manual.status
LOCK_DIR=/tmp/nokia-manual-ready.lock

kmsg() { printf '%s\n' "$*" | dd of=/dev/kmsg bs=4096 count=1 2>/dev/null || true; }

read_board() {
    BOARD=""
    if [ -r /tmp/sysinfo/board_name ]; then
        IFS= read -r BOARD < /tmp/sysinfo/board_name || true
    fi
}

has_lan_address() {
    seen=0
    if [ -r /proc/net/fib_trie ]; then
        while IFS= read -r line; do
            case "$line" in
                *"192.168.1.1") seen=1 ;;
                *"/32 host LOCAL"*) [ "$seen" = 1 ] && return 0; seen=0 ;;
                *) seen=0 ;;
            esac
        done < /proc/net/fib_trie
    fi
    if command -v ip >/dev/null 2>&1; then
        ipout="$(ip -4 addr show dev br-lan 2>/dev/null || true)"
        case "$ipout" in *"inet 192.168.1.1/24"*) return 0 ;; esac
    fi
    return 1
}

ssh22_listening() {
    for table in /proc/net/tcp /proc/net/tcp6; do
        [ -r "$table" ] || continue
        while IFS=' ' read -r sl local remote state rest; do
            case "$local" in
                *:0016) [ "$state" = 0A ] && return 0 ;;
            esac
        done < "$table"
    done
    return 1
}

collect_deferred() {
    DEFERRED=""
    if [ ! -r /sys/kernel/debug/devices_deferred ] && [ -d /sys/kernel/debug ] && command -v mount >/dev/null 2>&1; then
        mount -t debugfs debugfs /sys/kernel/debug 2>/dev/null || true
    fi
    if [ -r /sys/kernel/debug/devices_deferred ]; then
        while IFS= read -r dev; do
            [ -n "$dev" ] || continue
            if [ -n "$DEFERRED" ]; then DEFERRED="$DEFERRED,$dev"; else DEFERRED="$dev"; fi
        done < /sys/kernel/debug/devices_deferred
    else
        DEFERRED=unavailable
    fi
    [ -n "$DEFERRED" ] || DEFERRED=none
}

probe_network() {
    read_board
    BR_LAN_PRESENT=0
    LAN_192_168_1_1=0
    SSH22_LISTEN=0
    REASON=NONE
    [ "$BOARD" = "$EXPECTED_BOARD" ] || { REASON=BOARD_MISMATCH; return 1; }
    [ -d /sys/class/net/br-lan ] || { REASON=BR_LAN_MISSING; return 1; }
    BR_LAN_PRESENT=1
    has_lan_address || { REASON=LAN_ADDRESS_MISSING; return 1; }
    LAN_192_168_1_1=1
    ssh22_listening || { REASON=SSH22_NOT_LISTENING; return 1; }
    SSH22_LISTEN=1
    return 0
}

emit_state() {
    printf '%s\n' 'MEDVEFLASHER_MANUAL_PROTOCOL=1'
    printf '%s\n' 'MODE=TRANSITION'
    printf 'FAMILY=%s\n' "$FAMILY"
    printf 'EXPECTED_BOARD=%s\n' "$EXPECTED_BOARD"
    printf 'BOARD=%s\n' "$BOARD"
    printf 'STATE=%s\n' "$1"
    printf 'REASON=%s\n' "$2"
    printf 'BR_LAN_PRESENT=%s\n' "$BR_LAN_PRESENT"
    printf 'LAN_192_168_1_1=%s\n' "$LAN_192_168_1_1"
    printf 'SSH22_LISTEN=%s\n' "$SSH22_LISTEN"
    printf 'DEFERRED=%s\n' "$DEFERRED"
}

write_state() {
    collect_deferred
    mkdir -p /www
    emit_state "$1" "$2" > "$STATE_FILE.tmp"
    mv "$STATE_FILE.tmp" "$STATE_FILE"
    emit_state "$1" "$2" > "$STATUS_FILE.tmp"
    mv "$STATUS_FILE.tmp" "$STATUS_FILE"
}

monitor_network() {
    mkdir "$LOCK_DIR" 2>/dev/null || return 0
    trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT HUP INT TERM
    last_key=""
    while :; do
        if probe_network; then
            write_state WAITING_FOR_CUSTOM_IMAGE NONE
            : > "$READY_FILE"
            kmsg "NOKIA-MANUAL: READY board=$BOARD lan=192.168.1.1/24 ssh22=LISTEN deferred=$DEFERRED"
            return 0
        fi
        key="$REASON:$BOARD:$BR_LAN_PRESENT:$LAN_192_168_1_1:$SSH22_LISTEN"
        if [ "$key" != "$last_key" ]; then
            write_state NETWORK_NOT_READY "$REASON"
            kmsg "NOKIA-MANUAL: NOT_READY reason=$REASON board=$BOARD deferred=$DEFERRED"
            last_key="$key"
        fi
        sleep 1
    done
}

start() {
    rm -f "$READY_FILE"
    BOARD=""; BR_LAN_PRESENT=0; LAN_192_168_1_1=0; SSH22_LISTEN=0; DEFERRED=unknown
    write_state STARTING_NETWORK STARTING
    monitor_network &
    return 0
}
