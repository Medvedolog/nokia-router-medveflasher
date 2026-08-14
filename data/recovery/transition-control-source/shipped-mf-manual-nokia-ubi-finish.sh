#!/bin/ash
# Finish Nokia all-in-UBI installation by validating and flashing production FIT.
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
EXPECTED_SHA='db881b8053cdfbdf49dd6c2336dee3ddfa489966456a3e75556c5a0f6cc7663b'
DEFAULT_NAME='openwrt-airoha-an7583-nokia_xg-040g-mf-ubi-squashfs-sysupgrade.itb'

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
expected_sha() {
    local expected
    expected="${NOKIA_EXPECTED_SYSUPGRADE_SHA:-}"
    [ -n "$expected" ] || expected="$(cat /tmp/NOKIA_CUSTOM_SYSUPGRADE_SHA256 2>/dev/null || true)"
    [ -n "$expected" ] || expected="$EXPECTED_SHA"
    case "$expected" in *[!0-9a-fA-F]*|'') die 'invalid expected sysupgrade SHA256' ;; esac
    [ "${#expected}" -eq 64 ] || die 'invalid expected sysupgrade SHA256 length'
    printf '%s\n' "$(printf '%s' "$expected" | tr 'A-F' 'a-f')"
}

find_image() {
    local candidate
    if [ "${1:-}" = embedded-openwrt-sysupgrade ]; then
        nokia-ubi-installer check embedded-openwrt-sysupgrade >/dev/null 2>&1 || return 1
        [ -f /tmp/nokia-embedded-openwrt-sysupgrade.itb ] || return 1
        printf '%s\n' /tmp/nokia-embedded-openwrt-sysupgrade.itb
        return 0
    fi
    if [ -n "${1:-}" ]; then
        [ -f "$1" ] || return 1
        printf '%s\n' "$1"
        return 0
    fi
    if [ -f /tmp/nokia-embedded-openwrt-sysupgrade.itb ]; then
        printf '%s\n' /tmp/nokia-embedded-openwrt-sysupgrade.itb
        return 0
    fi
    for candidate in \
        "$PWD/$DEFAULT_NAME" \
        "/tmp/$DEFAULT_NAME" \
        /mnt/*/"$DEFAULT_NAME" \
        /mnt/*/*/"$DEFAULT_NAME" \
        /media/*/"$DEFAULT_NAME" \
        /media/*/*/"$DEFAULT_NAME"; do
        [ -f "$candidate" ] || continue
        printf '%s\n' "$candidate"
        return 0
    done
    return 1
}

[ "$(id -u)" = 0 ] || die 'root privileges are required'
[ -r /tmp/sysinfo/board_name ] || die 'board_name is unavailable'
[ "$(cat /tmp/sysinfo/board_name)" = 'nokia,xg-040g-mf-ubi' ] || die 'not running Nokia UBI initramfs'
command -v nokia-ubi-installer >/dev/null 2>&1 || die 'nokia-ubi-installer tool is missing'
command -v sysupgrade >/dev/null 2>&1 || die 'sysupgrade is missing'

if [ ! -f /tmp/NOKIA_UBI_INSTALL_COMPLETE ]; then
    log 'Completion marker is absent; trying non-destructive UBI attach.'
    nokia-ubi-installer attach || die 'complete UBI layout was not found'
fi

IMAGE="$(find_image "${1:-}" 2>/dev/null || true)"
[ -n "$IMAGE" ] || die "cannot resolve embedded OpenWrt sysupgrade or requested image path"
SELECTED_SHA="$(expected_sha)"
[ "$(sha_file "$IMAGE")" = "$SELECTED_SHA" ] || die 'selected UBI sysupgrade SHA256 mismatch'

log "Image: $IMAGE"
log "SHA256: $SELECTED_SHA"
log 'Running mandatory image/layout check...'
nokia-ubi-installer status || die 'UBI layout check failed'
sysupgrade -T "$IMAGE" || die 'sysupgrade -T rejected the image'
log '[OK] UBI sysupgrade image accepted.'
log ''
log 'FINAL STEP: replacing fallback fit with production OpenWrt; no -F and no settings preservation.'
if [ ! -f /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED ]; then
    if [ "${NOKIA_PC_CONFIRMED_CUSTOM_FLASH:-0}" = 1 ]; then
        log 'Custom image authorization received from the PC wizard after validation.'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    elif [ "${NOKIA_AUTOMATIC_FULLFLASH:-0}" = 1 ]; then
        log 'Automatic stage 2 authorization inherited from the confirmed stock stage.'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    else
        log 'A complete verified stock backup must be saved on the PC and NAND must be SkyHigh ML02G300WHI00.'
        printf 'Type exactly CONFIRM FORMAT AND FLASH: '
        IFS= read -r answer
        [ "$answer" = 'CONFIRM FORMAT AND FLASH' ] || die 'cancelled'
        touch /tmp/NOKIA_FORMAT_AND_FLASH_CONFIRMED
    fi
fi
sync
exec sysupgrade -v -n "$IMAGE"
