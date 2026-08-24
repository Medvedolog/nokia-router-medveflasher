#!/bin/ash
STATE_FILE=/tmp/NOKIA_AUTOFLASH_STATE
FAILED_FILE=/tmp/NOKIA_AUTOFLASH_FAILED
AUTO_LOG=/tmp/nokia-autoflash.log

printf '\n=== Nokia autonomous stage 2 ===\n'
if [ -r "$STATE_FILE" ]; then
    state="$(cat "$STATE_FILE")"
    printf 'State: %s\n' "$state"
    case "$state" in
        FAILED)
            printf 'AUTOMATIC FLASH DID NOT COMPLETE. The initramfs is waiting for SSH diagnostics.\n'
            [ -r "$FAILED_FILE" ] && { printf 'Reason: '; cat "$FAILED_FILE"; }
            printf 'Do not reboot blindly. Inspect:\n  cat /tmp/nokia-autoflash.log\n  cat /tmp/nokia-ubi-installer.log\n'
            ;;
        WAITING_FOR_SYSTEM|CHECKING|FORMATTING_AND_FLASHING)
            printf 'Automatic work is active. Do not run another installer and do not remove power.\n'
            ;;
        *)
            printf 'Unknown state; inspect /tmp/nokia-autoflash.log before reboot.\n'
            ;;
    esac
else
    printf 'AUTOMATIC FLASH DID NOT START. The initramfs is waiting for SSH diagnostics.\n'
    printf 'Check service and logs:\n  /etc/init.d/nokia-autoflash status\n  logread | grep NOKIA-AUTOFLASH\n'
fi
[ -r "$AUTO_LOG" ] && { printf '%s\n' 'Last autoflash messages:'; tail -n 12 "$AUTO_LOG"; }
printf '=================================\n\n'
unset STATE_FILE FAILED_FILE AUTO_LOG state
